import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, get_db_connection
from services.government_api import sync_government_data


def main():
    connection = get_db_connection()
    if connection is None:
        app.logger.error("Scheduled government data sync could not connect to the database.")
        return 1

    try:
        result = sync_government_data(connection)
    finally:
        connection.close()

    print(result["message"])
    return 0 if result["status"] in {"success", "success_no_records"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
