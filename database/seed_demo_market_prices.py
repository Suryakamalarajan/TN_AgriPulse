import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector

from config import Config, get_mysql_config


INITIAL_DEMO_RECORDS = (
    ("Tamil Nadu", "Tiruchirappalli", "Gandhi Market", "Tomato", "Hybrid", "2026-11-04", 1800, 2600, 2200, "DEMO-TN-20261104-001"),
    ("Tamil Nadu", "Chennai", "Koyambedu Market", "Onion", "Small Onion", "2026-11-04", 2800, 3800, 3300, "DEMO-TN-20261104-002"),
    ("Tamil Nadu", "Madurai", "Mattuthavani Market", "Banana", "Nendran", "2026-11-04", 2400, 3600, 3000, "DEMO-TN-20261104-003"),
    ("Tamil Nadu", "Coimbatore", "Uzhavar Sandhai", "Coconut", "Mature", "2026-11-04", 5200, 6800, 6000, "DEMO-TN-20261104-004"),
    ("Tamil Nadu", "Dindigul", "Oddanchatram Market", "Tomato", "Local", "2026-11-04", 1600, 2500, 2050, "DEMO-TN-20261104-005"),
    ("Tamil Nadu", "Salem", "Salem Market", "Turmeric", "Finger", "2026-11-04", 8500, 11200, 9800, "DEMO-TN-20261104-006"),
    ("Tamil Nadu", "Erode", "Erode Market", "Groundnut", "Bold", "2026-11-04", 6200, 7800, 7000, "DEMO-TN-20261104-007"),
    ("Tamil Nadu", "Thanjavur", "Thanjavur Market", "Paddy", "ADT 43", "2026-11-04", 2100, 2600, 2350, "DEMO-TN-20261104-008"),
    ("Tamil Nadu", "Tirunelveli", "Tirunelveli Market", "Maize", "Yellow", "2026-11-04", 2200, 2800, 2500, "DEMO-TN-20261104-009"),
    ("Tamil Nadu", "Vellore", "Vellore Market", "Brinjal", "Green", "2026-11-04", 2200, 3400, 2800, "DEMO-TN-20261104-010"),
    ("Tamil Nadu", "Thanjavur", "Kumbakonam Market", "Paddy", "BPT 5204", "2026-11-04", 2300, 2850, 2575, "DEMO-TN-20261104-011"),
    ("Tamil Nadu", "Coimbatore", "Pollachi Market", "Coconut", "Copra", "2026-11-04", 7800, 9800, 8800, "DEMO-TN-20261104-012"),
    ("Tamil Nadu", "Namakkal", "Rasipuram Market", "Green Chilli", "Long Green", "2026-11-04", 4200, 6200, 5200, "DEMO-TN-20261104-013"),
    ("Tamil Nadu", "Tiruppur", "Kangeyam Market", "Cotton", "Kapas", "2026-11-04", 6500, 7400, 6950, "DEMO-TN-20261104-014"),
    ("Tamil Nadu", "Tiruppur", "Dharapuram Market", "Maize", "Yellow", "2026-11-04", 2150, 2750, 2450, "DEMO-TN-20261104-015"),
    ("Tamil Nadu", "Theni", "Cumbum Market", "Mango", "Banganapalli", "2026-11-04", 3800, 5600, 4700, "DEMO-TN-20261104-016"),
    ("Tamil Nadu", "Kanyakumari", "Kanyakumari Market", "Black Gram", "Whole", "2026-11-04", 7200, 8900, 8050, "DEMO-TN-20261104-017"),
    ("Tamil Nadu", "Chennai", "Koyambedu Market", "Ladies Finger", "Green", "2026-11-04", 2600, 3900, 3250, "DEMO-TN-20261104-018"),
    ("Tamil Nadu", "Madurai", "Mattuthavani Market", "Onion", "Big Onion", "2026-11-04", 2500, 3600, 3050, "DEMO-TN-20261104-019"),
    ("Tamil Nadu", "Dindigul", "Oddanchatram Market", "Tomato", "Hybrid", "2026-11-04", 1700, 2700, 2200, "DEMO-TN-20261104-020"),
)

ADDITIONAL_MARKETS = (
    ("Tiruchirappalli", "Gandhi Market"),
    ("Chennai", "Koyambedu Market"),
    ("Madurai", "Mattuthavani Market"),
    ("Coimbatore", "Uzhavar Sandhai"),
    ("Dindigul", "Oddanchatram Market"),
    ("Salem", "Salem Market"),
    ("Erode", "Erode Market"),
    ("Thanjavur", "Thanjavur Market"),
    ("Tirunelveli", "Tirunelveli Market"),
    ("Vellore", "Vellore Market"),
    ("Thanjavur", "Kumbakonam Market"),
    ("Coimbatore", "Pollachi Market"),
    ("Namakkal", "Rasipuram Market"),
    ("Tiruppur", "Kangeyam Market"),
    ("Tiruppur", "Dharapuram Market"),
    ("Theni", "Cumbum Market"),
    ("Kanyakumari", "Kanyakumari Market"),
    ("Karur", "Karur Market"),
    ("Krishnagiri", "Krishnagiri Market"),
    ("Krishnagiri", "Hosur Market"),
    ("Virudhunagar", "Virudhunagar Market"),
    ("Sivaganga", "Sivaganga Market"),
    ("Ariyalur", "Ariyalur Market"),
    ("Perambalur", "Perambalur Market"),
    ("Tiruvannamalai", "Tiruvannamalai Market"),
)

ADDITIONAL_COMMODITIES = (
    ("Tomato", "Hybrid", 2200),
    ("Onion", "Big Onion", 3200),
    ("Paddy", "ADT 43", 2450),
    ("Banana", "Nendran", 3000),
    ("Coconut", "Mature", 6200),
    ("Turmeric", "Finger", 9800),
    ("Groundnut", "Bold", 7000),
    ("Maize", "Yellow", 2500),
    ("Cotton", "Kapas", 6950),
    ("Mango", "Banganapalli", 4700),
    ("Brinjal", "Green", 2800),
    ("Green Chilli", "Long Green", 5200),
    ("Ladies Finger", "Green", 3250),
    ("Black Gram", "Whole", 8050),
    ("Red Gram", "Whole", 7600),
    ("Sugarcane", "Co 86032", 3400),
    ("Tapioca", "White", 2600),
    ("Sesame", "Black", 11200),
    ("Ragi", "Finger Millet", 3900),
    ("Garlic", "Local", 14500),
)

ADDITIONAL_DEMO_COUNT = len(ADDITIONAL_MARKETS) * len(ADDITIONAL_COMMODITIES)
FIRST_ADDITIONAL_SOURCE_ID = 521


def build_additional_demo_records():
    records = []
    for market_index, (district, market) in enumerate(ADDITIONAL_MARKETS):
        for commodity_index, (commodity, variety, base_modal) in enumerate(ADDITIONAL_COMMODITIES):
            record_number = FIRST_ADDITIONAL_SOURCE_ID + market_index * len(ADDITIONAL_COMMODITIES) + commodity_index
            variation_percent = (market_index * 7 + commodity_index * 3) % 21 - 10
            modal = round(base_modal * (100 + variation_percent) / 100 / 10) * 10
            minimum = round(modal * 0.85 / 10) * 10
            maximum = round(modal * 1.15 / 10) * 10
            days_before_latest = 16 + (market_index * 3 + commodity_index) % 15
            arrival_date = (date(2026, 11, 4) - timedelta(days=days_before_latest)).isoformat()
            source_record_id = f"DEMO-TN-20261104-{record_number:03d}"
            records.append(
                (
                    "Tamil Nadu", district, market, commodity, variety, arrival_date,
                    minimum, maximum, modal, source_record_id,
                )
            )
    return tuple(records)


DEMO_RECORDS = INITIAL_DEMO_RECORDS + build_additional_demo_records()


def validate_demo_records():
    expected_count = len(INITIAL_DEMO_RECORDS) + ADDITIONAL_DEMO_COUNT
    if len(DEMO_RECORDS) != expected_count:
        raise ValueError(f"Expected {expected_count} demo records, found {len(DEMO_RECORDS)}.")

    record_ids = [record[-1] for record in DEMO_RECORDS]
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("Demo source record IDs must be unique.")

    for record in DEMO_RECORDS:
        minimum, maximum, modal = record[6:9]
        if not minimum <= modal <= maximum:
            raise ValueError(f"Invalid price range in demo record {record[-1]}.")


def seed_demo_records(connection):
    cursor = connection.cursor()
    lock_name = "tn_agripulse_demo_market_prices_seed"
    lock_acquired = False
    try:
        cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 10))
        lock_result = cursor.fetchone()
        lock_acquired = lock_result is not None and lock_result[0] == 1
        if not lock_acquired:
            raise RuntimeError("Could not acquire the database lock for DEMO market-price seeding.")

        cursor.execute("SHOW TABLES LIKE %s", ("market_prices",))
        if cursor.fetchone() is None:
            raise RuntimeError("The market_prices table is missing. Run database/schema.sql first.")

        cursor.execute("SHOW COLUMNS FROM market_prices")
        columns = {row[0] for row in cursor.fetchall()}
        required = {
            "state", "district", "market", "commodity", "variety", "arrival_date",
            "min_price", "max_price", "modal_price", "price_unit", "source",
            "source_record_id", "verification_status",
        }
        missing = required - columns
        if missing:
            raise RuntimeError(
                "The existing market_prices table is missing required columns: "
                + ", ".join(sorted(missing))
                + ". Run the current database/schema.sql and restart the app to apply its migration."
            )

        insert_query = """
            INSERT INTO market_prices
                (state, district, market, commodity, variety, arrival_date, min_price,
                 max_price, modal_price, price_unit, source, source_record_id,
                 verification_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'INR/Qtl', 'DEMO', %s, 'unverified')
        """
        inserted = 0
        skipped = 0
        for record in DEMO_RECORDS:
            source_record_id = record[-1]
            cursor.execute(
                "SELECT id FROM market_prices WHERE source = 'DEMO' AND source_record_id = %s LIMIT 1",
                (source_record_id,),
            )
            if cursor.fetchone() is not None:
                skipped += 1
                continue
            cursor.execute(insert_query, record[:9] + (source_record_id,))
            inserted += 1

        connection.commit()
        return inserted, skipped
    finally:
        if lock_acquired:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
            cursor.fetchone()
        cursor.close()


def main():
    parser = argparse.ArgumentParser(
        description="Insert illustrative, unverified DEMO market prices into MySQL."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate bundled records without connecting to a database.",
    )
    args = parser.parse_args()

    validate_demo_records()
    if args.check:
        print(f"Validated {len(DEMO_RECORDS)} demo records; no database was changed.")
        return 0

    if Config.DB_TYPE != "mysql":
        print(
            "DB_TYPE is not set to mysql. Configure DB_TYPE=mysql and your local MySQL "
            "connection settings in .env, then run this script again.",
            file=sys.stderr,
        )
        return 1

    connection = None
    try:
        connection = mysql.connector.connect(**get_mysql_config())
        connection.autocommit = False
        inserted, skipped = seed_demo_records(connection)
        print(
            f"Demo seed complete: inserted {inserted}, skipped {skipped} existing "
            "records. All seeded rows have source=DEMO and verification_status=unverified."
        )
        return 0
    except (mysql.connector.Error, RuntimeError) as exc:
        if connection is not None:
            connection.rollback()
        print(f"Demo seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
