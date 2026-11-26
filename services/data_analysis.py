try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def _row_to_dict(row, columns=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    if columns is None:
        return row
    return dict(zip(columns, row))


def get_filter_options(conn):
    results = {}
    for column, query in {
        "district": "SELECT DISTINCT district FROM market_prices WHERE district IS NOT NULL AND district != '' ORDER BY district ASC",
        "commodity": "SELECT DISTINCT commodity FROM market_prices WHERE commodity IS NOT NULL AND commodity != '' ORDER BY commodity ASC",
        "market": "SELECT DISTINCT market FROM market_prices WHERE market IS NOT NULL AND market != '' ORDER BY market ASC",
    }.items():
        rows = conn.execute(query).fetchall()
        results[column] = [row[0] for row in rows]
    return results


def _market_price_where(filters=None):
    query = " WHERE 1=1"
    params = []
    if filters:
        for field, column, operator in (
            ("district", "district", "="),
            ("commodity", "commodity", "="),
            ("market", "market", "="),
            ("date_from", "arrival_date", ">="),
            ("date_to", "arrival_date", "<="),
        ):
            if filters.get(field):
                query += f" AND {column} {operator} ?"
                params.append(filters[field])
        if filters.get("search"):
            query += " AND (LOWER(commodity) LIKE LOWER(?) OR LOWER(market) LIKE LOWER(?))"
            term = f"%{filters['search']}%"
            params.extend((term, term))
    return query, params


def get_records_for_query(conn, filters=None, limit=None, offset=0, sort="arrival_date"):
    where_clause, params = _market_price_where(filters)
    order_by = {
        "arrival_date": "arrival_date DESC, fetched_at DESC, id DESC",
        "modal_price_asc": "modal_price ASC, arrival_date DESC, id DESC",
        "modal_price_desc": "modal_price DESC, arrival_date DESC, id DESC",
    }.get(sort, "arrival_date DESC, fetched_at DESC, id DESC")
    query = "SELECT * FROM market_prices" + where_clause + " ORDER BY " + order_by
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description] if cursor.description else []
    return [_row_to_dict(row, columns) for row in rows]


def count_records_for_query(conn, filters=None):
    where_clause, params = _market_price_where(filters)
    return conn.execute("SELECT COUNT(*) FROM market_prices" + where_clause, params).fetchone()[0]


def calculate_dashboard_metrics(conn):
    total = conn.execute("SELECT COUNT(*) AS value FROM market_prices").fetchone()[0]
    districts = conn.execute("SELECT COUNT(DISTINCT district) AS value FROM market_prices").fetchone()[0]
    crops = conn.execute("SELECT COUNT(DISTINCT commodity) AS value FROM market_prices").fetchone()[0]
    markets = conn.execute("SELECT COUNT(DISTINCT market) AS value FROM market_prices").fetchone()[0]
    price_metrics = conn.execute(
        "SELECT AVG(modal_price), MAX(modal_price), MIN(modal_price) FROM market_prices WHERE modal_price IS NOT NULL"
    ).fetchone()
    average_modal, highest_modal, lowest_modal = price_metrics
    latest = conn.execute(
        "SELECT MAX(fetched_at) AS value FROM market_prices WHERE fetched_at IS NOT NULL"
    ).fetchone()[0]
    demo_records = conn.execute(
        "SELECT COUNT(*) FROM market_prices WHERE UPPER(source) = 'DEMO'"
    ).fetchone()[0]
    sync_status = conn.execute(
        "SELECT status, sync_time FROM data_sync_logs ORDER BY sync_time DESC LIMIT 1"
    ).fetchone()

    base = {
        "total_records": total or 0,
        "distinct_districts": districts or 0,
        "distinct_crops": crops or 0,
        "distinct_markets": markets or 0,
        "average_modal_price": round(float(average_modal), 2) if average_modal is not None else 0,
        "highest_modal_price": round(float(highest_modal), 2) if highest_modal is not None else 0,
        "lowest_modal_price": round(float(lowest_modal), 2) if lowest_modal is not None else 0,
        "demo_records": demo_records or 0,
        "last_fetched": latest,
        "api_status": sync_status[0] if sync_status else "No sync run yet",
        "api_last_sync": sync_status[1] if sync_status else None,
        "message": "No verified market-price data is available yet." if total == 0 else "",
        "crop_data": [],
        "market_data": [],
        "trend_data": [],
        "crop_price_comparison": [],
        "district_price_data": [],
        "market_price_ranges": [],
    }

    if total == 0:
        return base

    records = get_records_for_query(conn)
    crop_totals = {}
    market_totals = {}
    trend_totals = {}
    crop_prices = {}
    district_totals = {}
    market_price_totals = {}

    for record in records:
        commodity = record.get("commodity")
        market = record.get("market")
        district = record.get("district")
        arrival = record.get("arrival_date")
        prices = {}
        for field in ("min_price", "modal_price", "max_price"):
            try:
                value = float(record[field]) if record.get(field) is not None else None
            except (TypeError, ValueError):
                value = None
            prices[field] = value

        modal = prices["modal_price"]
        if commodity and modal is not None:
            crop_totals.setdefault(commodity, {"total": 0.0, "count": 0})
            crop_totals[commodity]["total"] += modal
            crop_totals[commodity]["count"] += 1

        if market and modal is not None:
            market_totals.setdefault(market, {"total": 0.0, "count": 0})
            market_totals[market]["total"] += modal
            market_totals[market]["count"] += 1

        if arrival and modal is not None:
            trend_totals.setdefault(arrival, {"total": 0.0, "count": 0})
            trend_totals[arrival]["total"] += modal
            trend_totals[arrival]["count"] += 1

        if commodity:
            crop_prices.setdefault(commodity, {field: [] for field in prices})
            for field, value in prices.items():
                if value is not None:
                    crop_prices[commodity][field].append(value)

        if district and modal is not None:
            district_totals.setdefault(district, {"total": 0.0, "count": 0})
            district_totals[district]["total"] += modal
            district_totals[district]["count"] += 1

        if market:
            market_price_totals.setdefault(market, {field: [] for field in prices})
            for field, value in prices.items():
                if value is not None:
                    market_price_totals[market][field].append(value)

    base["crop_data"] = [
        {"commodity": commodity, "average_modal_price": round(info["total"] / info["count"], 2)}
        for commodity, info in sorted(crop_totals.items(), key=lambda item: item[1]["total"] / item[1]["count"], reverse=True)[:8]
    ]
    base["market_data"] = [
        {"market": market, "average_price": round(info["total"] / info["count"], 2)}
        for market, info in sorted(market_totals.items(), key=lambda item: item[1]["total"] / item[1]["count"], reverse=True)[:8]
    ]
    base["trend_data"] = [
        {"arrival_date": day, "average_modal_price": round(info["total"] / info["count"], 2)}
        for day, info in sorted(trend_totals.items())
    ]
    base["crop_price_comparison"] = [
        {
            "commodity": commodity,
            "average_min_price": round(sum(info["min_price"]) / len(info["min_price"]), 2) if info["min_price"] else None,
            "average_modal_price": round(sum(info["modal_price"]) / len(info["modal_price"]), 2) if info["modal_price"] else None,
            "average_max_price": round(sum(info["max_price"]) / len(info["max_price"]), 2) if info["max_price"] else None,
        }
        for commodity, info in sorted(
            crop_prices.items(),
            key=lambda item: sum(item[1]["modal_price"]) / len(item[1]["modal_price"]) if item[1]["modal_price"] else 0,
            reverse=True,
        )[:8]
    ]
    base["district_price_data"] = [
        {"district": district, "average_modal_price": round(info["total"] / info["count"], 2)}
        for district, info in sorted(
            district_totals.items(), key=lambda item: item[1]["total"] / item[1]["count"], reverse=True
        )[:10]
    ]
    base["market_price_ranges"] = [
        {
            "market": market,
            "average_min_price": round(sum(info["min_price"]) / len(info["min_price"]), 2) if info["min_price"] else None,
            "average_max_price": round(sum(info["max_price"]) / len(info["max_price"]), 2) if info["max_price"] else None,
        }
        for market, info in sorted(
            market_price_totals.items(),
            key=lambda item: sum(item[1]["modal_price"]) / len(item[1]["modal_price"]) if item[1]["modal_price"] else 0,
            reverse=True,
        )[:8]
    ]
    return base


def calculate_analytics_summary(conn):
    records = get_records_for_query(conn)
    if not records:
        return {
            "status": "empty",
            "message": "No verified market-price data is available yet.",
            "crop_averages": [],
            "market_differences": [],
            "district_counts": [],
            "historical_trends": [],
        }

    if pd is not None:
        df = pd.DataFrame(records)
        df["modal_price"] = pd.to_numeric(df["modal_price"], errors="coerce")
        df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")

        crop_averages = (
            df.groupby("commodity", dropna=False)["modal_price"].mean().reset_index(name="average_modal_price")
            .sort_values("average_modal_price", ascending=False)
            .head(10)
        )

        market_prices = (
            df.groupby(["commodity", "arrival_date", "market"], dropna=False)["modal_price"]
            .mean()
            .reset_index()
        )
        market_differences = []
        for commodity, commodity_group in market_prices.groupby("commodity", dropna=False):
            for day, day_group in commodity_group.groupby("arrival_date", dropna=False):
                if day_group.empty or len(day_group) < 2:
                    continue
                prices = day_group["modal_price"].dropna()
                diff = float(prices.max() - prices.min()) if not prices.empty else 0
                market_differences.append(
                    {
                        "commodity": commodity,
                        "arrival_date": day.strftime("%Y-%m-%d"),
                        "difference": round(diff, 2),
                    }
                )

        district_counts = (
            df.groupby(["district", "commodity"], dropna=False).size().reset_index(name="records").sort_values("records", ascending=False)
        )

        historical = df.groupby(["commodity", "arrival_date"], dropna=False)["modal_price"].mean().reset_index(name="average_modal_price")
        historical = historical.sort_values(["commodity", "arrival_date"]).reset_index(drop=True)

        return {
            "status": "ok",
            "crop_averages": [{"commodity": row["commodity"], "average_modal_price": round(float(row["average_modal_price"]), 2)} for _, row in crop_averages.iterrows()],
            "market_differences": market_differences,
            "district_counts": [{"district": row["district"], "commodity": row["commodity"], "records": int(row["records"])} for _, row in district_counts.iterrows()],
            "historical_trends": [{"commodity": row["commodity"], "arrival_date": row["arrival_date"].strftime("%Y-%m-%d"), "average_modal_price": round(float(row["average_modal_price"]), 2)} for _, row in historical.iterrows()],
        }

    crop_totals = {}
    for record in records:
        value = record.get("modal_price")
        commodity = record.get("commodity")
        if not commodity:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        crop_totals.setdefault(commodity, {"total": 0.0, "count": 0})
        crop_totals[commodity]["total"] += number
        crop_totals[commodity]["count"] += 1

    crop_averages = [
        {"commodity": commodity, "average_modal_price": round(info["total"] / info["count"], 2)}
        for commodity, info in sorted(crop_totals.items(), key=lambda item: item[1]["total"] / item[1]["count"], reverse=True)[:10]
    ]

    market_map = {}
    for record in records:
        commodity = record.get("commodity")
        day = record.get("arrival_date")
        market = record.get("market")
        try:
            price = float(record.get("modal_price"))
        except (TypeError, ValueError):
            continue
        key = (commodity, day)
        market_map.setdefault(key, []).append(price)

    market_differences = []
    for (commodity, day), prices in sorted(market_map.items()):
        if len(prices) >= 2:
            market_differences.append({"commodity": commodity, "arrival_date": day, "difference": round(max(prices) - min(prices), 2)})

    district_counts = {}
    for record in records:
        district = record.get("district")
        commodity = record.get("commodity")
        if district and commodity:
            district_counts[(district, commodity)] = district_counts.get((district, commodity), 0) + 1
    district_counts = [
        {"district": district, "commodity": commodity, "records": count}
        for (district, commodity), count in sorted(district_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    historical_map = {}
    for record in records:
        commodity = record.get("commodity")
        day = record.get("arrival_date")
        try:
            price = float(record.get("modal_price"))
        except (TypeError, ValueError):
            continue
        if commodity and day:
            historical_map.setdefault((commodity, day), []).append(price)
    historical_trends = [
        {"commodity": commodity, "arrival_date": day, "average_modal_price": round(sum(prices) / len(prices), 2)}
        for (commodity, day), prices in sorted(historical_map.items())
    ]

    return {
        "status": "ok",
        "crop_averages": crop_averages,
        "market_differences": market_differences,
        "district_counts": district_counts,
        "historical_trends": historical_trends,
    }
