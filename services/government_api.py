import os
import sqlite3
from datetime import datetime

import requests

from config import Config


RESOURCE_URL = Config.DATA_GOV_API_URL


def _normalize_string(value):
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value):
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_record(raw_record):
    state = _normalize_string(raw_record.get("state") or raw_record.get("State") or raw_record.get("STATE"))
    district = _normalize_string(raw_record.get("district") or raw_record.get("District") or raw_record.get("DISTRICT"))
    market = _normalize_string(raw_record.get("market") or raw_record.get("Market") or raw_record.get("MARKET"))
    commodity = _normalize_string(raw_record.get("commodity") or raw_record.get("Commodity") or raw_record.get("COMMODITY"))
    variety = _normalize_string(raw_record.get("variety") or raw_record.get("Variety") or raw_record.get("VARIETY"))
    arrival_date = _normalize_string(raw_record.get("arrival_date") or raw_record.get("arrivalDate") or raw_record.get("Arrival Date"))
    min_price = _safe_float(raw_record.get("min_price") or raw_record.get("minPrice") or raw_record.get("Min Price"))
    max_price = _safe_float(raw_record.get("max_price") or raw_record.get("maxPrice") or raw_record.get("Max Price"))
    modal_price = _safe_float(raw_record.get("modal_price") or raw_record.get("modalPrice") or raw_record.get("Modal Price"))
    price_unit = _normalize_string(raw_record.get("price_unit") or raw_record.get("Price Unit") or raw_record.get("unit") or "INR/Qtl")
    source_record_id = _normalize_string(raw_record.get("id") or raw_record.get("record_id") or raw_record.get("Record ID"))

    if not all([state, district, market, commodity, arrival_date]):
        return None

    return {
        "state": state,
        "district": district,
        "market": market,
        "commodity": commodity,
        "variety": variety or None,
        "arrival_date": arrival_date[:10] if len(arrival_date) >= 10 else arrival_date,
        "min_price": min_price,
        "max_price": max_price,
        "modal_price": modal_price,
        "price_unit": price_unit or "INR/Qtl",
        "source": "data.gov.in",
        "source_record_id": source_record_id or None,
    }


def _log_sync_status(connection, status, source, records_imported=0, total_pages=0, error_summary=None, api_status=None):
    connection.execute(
        "INSERT INTO data_sync_logs (status, source, records_imported, total_pages, error_summary, api_status) VALUES (?, ?, ?, ?, ?, ?)",
        (status, source, records_imported, total_pages, error_summary, api_status),
    )
    connection.commit()


def sync_government_data(connection):
    api_key = (Config.DATA_GOV_API_KEY or os.getenv("DATA_GOV_API_KEY", "")).strip()
    if not api_key or api_key.lower() in {
        "your_data_gov_api_key_here",
        "your_api_key_here",
        "your_api_key",
        "replace_me",
    }:
        _log_sync_status(connection, "missing_api_key", "data.gov.in", 0, 0, "API key is not configured.", "missing_api_key")
        return {"status": "missing_api_key", "message": "Government data API key is missing. Add DATA_GOV_API_KEY to the .env file.", "records_imported": 0}

    url = RESOURCE_URL
    offset = 0
    valid_records = []
    total_pages = 0

    try:
        while offset < (Config.MAX_PAGES * 1000):
            total_pages += 1
            response = requests.get(
                url,
                params={"api-key": api_key, "format": "json", "limit": 100, "offset": offset},
                timeout=Config.DATA_GOV_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            records = payload.get("records") or []
            if not records:
                break

            for record in records:
                filtered = _extract_record(record)
                if filtered is not None:
                    valid_records.append(filtered)

            if not payload.get("total"):
                break
            if offset + len(records) >= int(payload["total"]):
                break
            offset += len(records)
            if total_pages >= Config.MAX_PAGES:
                break

        if not valid_records:
            _log_sync_status(connection, "success_no_records", "data.gov.in", 0, total_pages, "No matching records returned by the official API.", "success")
            return {
                "status": "success_no_records",
                "message": "The official API responded successfully, but no matching Tamil Nadu records were returned.",
                "records_imported": 0,
            }

        inserted = 0
        for record in valid_records:
            existing = connection.execute(
                "SELECT id FROM market_prices WHERE state = ? AND district = ? AND market = ? AND commodity = ? AND arrival_date = ? AND COALESCE(variety, '') = COALESCE(?, '') AND COALESCE(source_record_id, '') = COALESCE(?, '') AND source = ?",
                (
                    record["state"],
                    record["district"],
                    record["market"],
                    record["commodity"],
                    record["arrival_date"],
                    record["variety"],
                    record["source_record_id"],
                    record["source"],
                ),
            ).fetchone()
            if existing:
                continue

            connection.execute(
                "INSERT INTO market_prices (state, district, market, commodity, variety, arrival_date, min_price, max_price, modal_price, price_unit, source, source_record_id, verification_status, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'verified', CURRENT_TIMESTAMP)",
                (
                    record["state"],
                    record["district"],
                    record["market"],
                    record["commodity"],
                    record["variety"],
                    record["arrival_date"],
                    record["min_price"],
                    record["max_price"],
                    record["modal_price"],
                    record["price_unit"],
                    record["source"],
                    record["source_record_id"],
                ),
            )
            inserted += 1

        connection.commit()
        _log_sync_status(connection, "success", "data.gov.in", inserted, total_pages, None, "success")
        return {"status": "success", "message": f"Imported {inserted} valid records from the government market API.", "records_imported": inserted}

    except requests.Timeout:
        _log_sync_status(connection, "timeout", "data.gov.in", 0, total_pages, "The government data API request timed out.", "timeout")
        return {"status": "timeout", "message": "The government data source timed out. Please try again later.", "records_imported": 0}
    except requests.RequestException as exc:
        _log_sync_status(connection, "http_failure", "data.gov.in", 0, total_pages, str(exc), "http_failure")
        return {"status": "http_failure", "message": f"Unable to reach the government data API: {exc}", "records_imported": 0}
    except ValueError as exc:
        _log_sync_status(connection, "invalid_response", "data.gov.in", 0, total_pages, str(exc), "invalid_response")
        return {"status": "invalid_response", "message": "The API returned an invalid response format.", "records_imported": 0}
