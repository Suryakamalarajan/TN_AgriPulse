import csv
import io
import os
import re
import secrets
import sqlite3
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from itertools import islice

import mysql.connector
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config, get_mysql_config
from services.data_analysis import calculate_analytics_summary, calculate_dashboard_metrics, count_records_for_query, get_filter_options, get_records_for_query
from services.government_api import sync_government_data

app = Flask(__name__)
app.config.from_object(Config)
if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
    raise RuntimeError(
        "Set SECRET_KEY in .env to a random value of at least 32 characters before starting TN AgriPulse."
    )
app.secret_key = app.config["SECRET_KEY"]
_mysql_schema_ready = False
_mysql_auth_schema_ready = False


class DatabaseConnection:
    def __init__(self, connection, uses_mysql=False):
        self._connection = connection
        self._uses_mysql = uses_mysql

    def execute(self, query, parameters=()):
        if not self._uses_mysql:
            return self._connection.execute(query, parameters)

        cursor = self._connection.cursor()
        cursor.execute(query.replace("?", "%s"), parameters)
        return cursor

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _ensure_mysql_market_price_schema(connection):
    global _mysql_schema_ready
    if _mysql_schema_ready:
        return

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_prices (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            state VARCHAR(100) NOT NULL,
            district VARCHAR(100) NOT NULL,
            market VARCHAR(150) NOT NULL,
            commodity VARCHAR(120) NOT NULL,
            variety VARCHAR(150) DEFAULT NULL,
            arrival_date DATE NOT NULL,
            min_price DECIMAL(12,2) DEFAULT NULL,
            max_price DECIMAL(12,2) DEFAULT NULL,
            modal_price DECIMAL(12,2) DEFAULT NULL,
            price_unit VARCHAR(50) DEFAULT 'INR/Qtl',
            source VARCHAR(120) NOT NULL,
            source_record_id VARCHAR(200) DEFAULT NULL,
            verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            KEY idx_market_prices_filters (state, district, commodity, arrival_date),
            KEY idx_market_prices_market (market, commodity)
        )
        """
    )
    existing_column = connection.execute(
        "SHOW COLUMNS FROM market_prices LIKE ?", ("verification_status",)
    ).fetchone()
    if existing_column is None:
        connection.execute(
            "ALTER TABLE market_prices ADD COLUMN verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified'"
        )
    _mysql_schema_ready = True


def _ensure_mysql_auth_schema(connection):
    global _mysql_auth_schema_ready
    if _mysql_auth_schema_ready:
        return

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(191) NOT NULL UNIQUE,
            full_name VARCHAR(150) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'USER',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_auth_users_role (role)
        )
        """
    )
    _mysql_auth_schema_ready = True


def get_db_connection():
    if app.config["DB_TYPE"] == "mysql":
        try:
            connection = mysql.connector.connect(**get_mysql_config())
            connection.autocommit = False
        except mysql.connector.Error:
            app.logger.exception("Unable to connect to the configured MySQL database.")
            return None
        wrapped = DatabaseConnection(connection, uses_mysql=True)
        try:
            _ensure_mysql_market_price_schema(wrapped)
            _ensure_mysql_auth_schema(wrapped)
        except mysql.connector.Error:
            connection.close()
            app.logger.exception("Unable to initialize the market price database schema.")
            raise
        return wrapped

    connection = sqlite3.connect(app.config["SQLITE_DATABASE"])
    connection.row_factory = sqlite3.Row
    return DatabaseConnection(connection)


def fetchone_as_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return dict(row)
    if cursor.description is None:
        return row
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def _configured_admin_accounts():
    configured = app.config["ADMIN_ACCOUNTS"]
    if not any(username or password for username, password in configured):
        return ()
    if any(not username.strip() or not password for username, password in configured):
        raise RuntimeError(
            "Configure both administrator usernames and passwords in .env; "
            "both administrator accounts are required."
        )

    accounts = tuple(
        (username.strip().lower(), password)
        for username, password in configured
    )
    usernames = [username for username, _ in accounts]
    if len(set(usernames)) != 2:
        raise RuntimeError("The two administrator usernames must be distinct.")
    if any(
        len(username) > 191 or any(character.isspace() for character in username)
        for username in usernames
    ):
        raise RuntimeError("Administrator usernames must be at most 191 characters and contain no spaces.")
    if any(len(password) < 12 for _, password in accounts):
        raise RuntimeError("Administrator passwords must be at least 12 characters long.")
    if accounts[0][1] == accounts[1][1]:
        raise RuntimeError("The two administrator accounts must use different passwords.")
    return accounts


def _migrate_existing_users(connection):
    cursor = connection.execute(
        "SELECT email, full_name, password_hash FROM users"
    )
    while True:
        row = fetchone_as_dict(cursor)
        if row is None:
            break
        username = row["email"].strip().lower()
        if not username:
            continue
        existing = connection.execute(
            "SELECT id FROM auth_users WHERE username = ?", (username,)
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO auth_users (username, full_name, password_hash, role) "
                "VALUES (?, ?, ?, 'USER')",
                (username, row["full_name"], row["password_hash"]),
            )


def _provision_admin_accounts(connection):
    accounts = _configured_admin_accounts()
    if not accounts:
        app.logger.warning(
            "No administrator accounts are configured. Admin access is disabled until "
            "ADMIN1_USERNAME/PASSWORD and ADMIN2_USERNAME/PASSWORD are set in .env."
        )
        return

    for index, (username, password) in enumerate(accounts, start=1):
        current = fetchone_as_dict(
            connection.execute(
                "SELECT id, password_hash, role FROM auth_users WHERE username = ?",
                (username,),
            )
        )
        password_matches = False
        if current is not None:
            try:
                password_matches = check_password_hash(
                    current["password_hash"], password
                )
            except (TypeError, ValueError):
                password_matches = False
        if current is not None and current["role"] == "ADMIN" and password_matches:
            continue

        password_hash = generate_password_hash(password)
        if current is None:
            connection.execute(
                "INSERT INTO auth_users (username, full_name, password_hash, role) "
                "VALUES (?, ?, ?, 'ADMIN')",
                (username, f"Administrator {index}", password_hash),
            )
        else:
            connection.execute(
                "UPDATE auth_users SET full_name = ?, password_hash = ?, role = 'ADMIN' "
                "WHERE id = ?",
                (f"Administrator {index}", password_hash, current["id"]),
            )

    connection.execute(
        "DELETE FROM auth_users WHERE role = 'ADMIN' AND username NOT IN (?, ?)",
        tuple(username for username, _ in accounts),
    )


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _csrf_is_valid():
    submitted = request.headers.get("X-CSRFToken") or request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    return bool(expected and submitted and secrets.compare_digest(expected, submitted))


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


def init_database():
    if app.config["DB_TYPE"] == "mysql":
        connection = get_db_connection()
        if connection is None:
            raise RuntimeError(
                "MySQL is selected but unavailable. Check the local .env settings "
                "and ensure the MySQL server is running."
            )
        try:
            _migrate_existing_users(connection)
            _provision_admin_accounts(connection)
            connection.commit()
            from database.seed_demo_market_prices import seed_demo_records

            inserted, skipped = seed_demo_records(connection)
            app.logger.info(
                "DEMO market-price seed checked: inserted=%s, already_present=%s",
                inserted,
                skipped,
            )
        except (mysql.connector.Error, RuntimeError):
            connection.rollback()
            app.logger.exception("Unable to seed the illustrative MySQL market data.")
            raise
        finally:
            connection.close()
        return

    connection = sqlite3.connect(app.config["SQLITE_DATABASE"])
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('USER', 'ADMIN')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            district TEXT NOT NULL,
            market TEXT NOT NULL,
            commodity TEXT NOT NULL,
            variety TEXT DEFAULT NULL,
            arrival_date TEXT NOT NULL,
            min_price REAL DEFAULT NULL,
            max_price REAL DEFAULT NULL,
            modal_price REAL DEFAULT NULL,
            price_unit TEXT DEFAULT 'INR/Qtl',
            source TEXT NOT NULL,
            source_record_id TEXT DEFAULT NULL,
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS data_sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_time TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            source TEXT DEFAULT 'data.gov.in',
            records_imported INTEGER DEFAULT 0,
            total_pages INTEGER DEFAULT 0,
            error_summary TEXT DEFAULT NULL,
            api_status TEXT DEFAULT NULL
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_username ON auth_users(username)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_prices_filters ON market_prices(state, district, commodity, arrival_date)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_prices_market ON market_prices(market, commodity)"
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(market_prices)")}
    if "verification_status" not in columns:
        connection.execute(
            "ALTER TABLE market_prices ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified'"
        )
    _migrate_existing_users(DatabaseConnection(connection))
    _provision_admin_accounts(DatabaseConnection(connection))
    connection.commit()
    connection.close()


init_database()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id") or session.get("role") not in {"USER", "ADMIN"}:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id") or session.get("role") not in {"USER", "ADMIN"}:
            return jsonify({"error": "Login is required to view this resource."}), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id") or session.get("role") not in {"USER", "ADMIN"}:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Administrator login is required."}), 401
            flash("Please log in as an administrator to continue.", "warning")
            return redirect(url_for("login"))

        authorized_usernames = {
            username for username, _ in _configured_admin_accounts()
        }
        username = session.get("username")
        if session.get("role") != "ADMIN" or username not in authorized_usernames:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Administrator access is required."}), 403
            abort(403)

        connection = get_db_connection()
        if connection is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Database unavailable."}), 503
            return "Database unavailable.", 503
        try:
            account = fetchone_as_dict(
                connection.execute(
                    "SELECT role FROM auth_users WHERE username = ?", (username,)
                )
            )
        finally:
            connection.close()
        if account is None or account["role"] != "ADMIN":
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "Administrator access is required."}), 403
            abort(403)

        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _csrf_is_valid():
            if request.path.startswith("/api/"):
                return jsonify({"error": "A valid CSRF token is required."}), 400
            abort(400, description="A valid CSRF token is required.")
        return view(*args, **kwargs)

    return wrapped


MARKET_PRICE_FIELDS = {
    "state": 100,
    "district": 100,
    "market": 150,
    "commodity": 120,
    "variety": 150,
    "price_unit": 50,
    "source": 120,
    "verification_status": 30,
}
VERIFICATION_STATUSES = {"pending", "verified", "unverified"}


def validate_market_price_payload(payload):
    if not isinstance(payload, dict):
        return None, "A JSON object containing market record details is required."

    values = {}
    for field, max_length in MARKET_PRICE_FIELDS.items():
        value = payload.get(field, "")
        value = value.strip() if isinstance(value, str) else ""
        if field == "variety" and not value:
            values[field] = None
            continue
        if not value:
            return None, f"{field.replace('_', ' ').capitalize()} is required."
        if len(value) > max_length:
            return None, f"{field.replace('_', ' ').capitalize()} must be {max_length} characters or fewer."
        values[field] = value

    if values["verification_status"] not in VERIFICATION_STATUSES:
        return None, "Verification status must be pending, verified, or unverified."

    arrival_date = payload.get("arrival_date", "")
    if not isinstance(arrival_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", arrival_date):
        return None, "Arrival date must be a valid date in YYYY-MM-DD format."
    try:
        date.fromisoformat(arrival_date)
    except ValueError:
        return None, "Arrival date must be a valid date in YYYY-MM-DD format."
    values["arrival_date"] = arrival_date

    for field in ("min_price", "max_price", "modal_price"):
        try:
            price = Decimal(str(payload.get(field, "")))
        except (InvalidOperation, ValueError):
            return None, f"{field.replace('_', ' ').capitalize()} must be a valid number."
        if not price.is_finite() or price < 0 or price > Decimal("9999999999.99"):
            return None, f"{field.replace('_', ' ').capitalize()} must be between 0 and 9999999999.99."
        if price != price.quantize(Decimal("0.01")):
            return None, f"{field.replace('_', ' ').capitalize()} may have at most 2 decimal places."
        values[field] = float(price)

    if values["min_price"] > values["max_price"]:
        return None, "Minimum price cannot exceed maximum price."
    if not values["min_price"] <= values["modal_price"] <= values["max_price"]:
        return None, "Modal price must be between minimum and maximum prices."

    return values, None


def _serialize_market_record(record):
    for field, value in record.items():
        if isinstance(value, (date, datetime)):
            record[field] = value.isoformat()
        elif isinstance(value, Decimal):
            record[field] = float(value)
    return record


def _find_duplicate_market_record(connection, values, exclude_id=None):
    query = (
        "SELECT id FROM market_prices WHERE LOWER(state) = LOWER(?) "
        "AND LOWER(district) = LOWER(?) AND LOWER(market) = LOWER(?) "
        "AND LOWER(commodity) = LOWER(?) AND COALESCE(LOWER(variety), '') = LOWER(?) "
        "AND arrival_date = ? AND LOWER(source) = LOWER(?)"
    )
    parameters = (
        values["state"],
        values["district"],
        values["market"],
        values["commodity"],
        values["variety"] or "",
        values["arrival_date"],
        values["source"],
    )
    if exclude_id is not None:
        query += " AND id != ?"
        parameters += (exclude_id,)
    return connection.execute(query, parameters).fetchone()


def _market_record_error(message, status=400):
    return jsonify({"error": message}), status


@app.route("/")
def index():
    if session.get("role") == "ADMIN":
        return redirect(url_for("admin_dashboard"))
    if session.get("role") == "USER":
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        if not _csrf_is_valid():
            flash("Your registration form expired. Please try again.", "danger")
            return render_template("register.html"), 400

        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or len(full_name) > 150:
            flash("Enter a name of 1 to 150 characters.", "danger")
            return render_template("register.html")
        if (
            not username
            or len(username) > 191
            or any(character.isspace() for character in username)
        ):
            flash("Username is required, must be 191 characters or fewer, and cannot contain spaces.", "danger")
            return render_template("register.html")
        if len(password) < 12:
            flash("Password must be at least 12 characters long.", "danger")
            return render_template("register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        if username in {
            admin_username for admin_username, _ in _configured_admin_accounts()
        }:
            flash("That username is unavailable.", "danger")
            return render_template("register.html")

        connection = get_db_connection()
        if connection is None:
            flash("Database connection is unavailable right now.", "danger")
            return render_template("register.html"), 503

        try:
            connection.execute(
                "INSERT INTO auth_users (username, full_name, password_hash, role) "
                "VALUES (?, ?, ?, 'USER')",
                (username, full_name, generate_password_hash(password)),
            )
            connection.commit()
        except (sqlite3.IntegrityError, mysql.connector.IntegrityError):
            connection.rollback()
            flash("That username is already registered. Please choose another.", "danger")
            return render_template("register.html"), 409
        except (sqlite3.Error, mysql.connector.Error):
            connection.rollback()
            app.logger.exception("Unable to register a read-only user account.")
            flash("Registration could not be completed. Please try again later.", "danger")
            return render_template("register.html"), 500
        finally:
            connection.close()

        flash("Your read-only account was created. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and session.get("user_id"):
        if session.get("role") == "ADMIN":
            return redirect(url_for("admin_dashboard"))
        if session.get("role") == "USER":
            return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        login_type = request.form.get("login_type", "").strip().lower()
        requested_role = {"user": "USER", "admin": "ADMIN"}.get(login_type)

        if not _csrf_is_valid():
            flash("Your login form expired. Please try again.", "danger")
            return render_template("login.html"), 400
        if not username or not password or requested_role is None:
            flash("Choose a login type and enter your username and password.", "danger")
            return render_template("login.html")

        connection = get_db_connection()
        if connection is None:
            flash("Database connection is unavailable right now.", "danger")
            return render_template("login.html")

        cursor = connection.execute(
            "SELECT id, username, full_name, password_hash, role "
            "FROM auth_users WHERE username = ?",
            (username,),
        )
        row = fetchone_as_dict(cursor)
        connection.close()

        password_matches = False
        if row is not None:
            try:
                password_matches = check_password_hash(row["password_hash"], password)
            except (TypeError, ValueError):
                password_matches = False
        configured_admins = {
            admin_username for admin_username, _ in _configured_admin_accounts()
        }
        if (
            row is None
            or not password_matches
            or row["role"] != requested_role
            or (requested_role == "ADMIN" and username not in configured_admins)
        ):
            flash("Incorrect username or password for that login option.", "danger")
            return render_template("login.html")

        session.clear()
        session["user_id"] = row["id"]
        session["user_name"] = row["full_name"]
        session["username"] = row["username"]
        session["role"] = row["role"]
        session.permanent = True
        flash("Welcome back! You are now logged in.", "success")
        return redirect(
            url_for("admin_dashboard") if requested_role == "ADMIN"
            else url_for("dashboard")
        )

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    if not _csrf_is_valid():
        abort(400, description="A valid CSRF token is required.")
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    connection = get_db_connection()
    if connection is None:
        flash("The database is not available at the moment.", "danger")
        return render_template("admin_dashboard.html", stats={}), 503
    try:
        stats = calculate_dashboard_metrics(connection)
    finally:
        connection.close()
    return render_template("admin_dashboard.html", stats=stats)


def _normalize_upload_header(value):
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def _upload_row_payload(headers, values):
    row = {
        _normalize_upload_header(header): value
        for header, value in zip(headers, values)
        if header is not None
    }
    arrival_date = row.get("arrival_date")
    if isinstance(arrival_date, (date, datetime)):
        arrival_date = arrival_date.isoformat()[:10]
    return {
        "state": row.get("state"),
        "district": row.get("district"),
        "market": row.get("market"),
        "commodity": row.get("commodity"),
        "variety": row.get("variety") or "",
        "arrival_date": arrival_date,
        "min_price": row.get("min_price"),
        "max_price": row.get("max_price"),
        "modal_price": row.get("modal_price"),
        "price_unit": row.get("price_unit") or "INR/Qtl",
        "source": row.get("source") or "ADMIN_UPLOAD",
        "verification_status": row.get("verification_status") or "pending",
    }


@app.route("/admin/upload", methods=["POST"])
@admin_required
def upload_market_records():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        flash("Choose a CSV or .xlsx file to upload.", "danger")
        return redirect(url_for("admin_dashboard"))

    extension = uploaded_file.filename.rsplit(".", 1)[-1].lower()
    workbook = None
    try:
        if extension == "csv":
            content = uploaded_file.stream.read().decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            headers = next(reader, None)
            rows = list(islice(enumerate(reader, start=2), 5001))
        elif extension == "xlsx":
            workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
            worksheet = workbook.active
            row_iterator = worksheet.iter_rows(values_only=True)
            headers = next(row_iterator, None)
            rows = list(islice(enumerate(row_iterator, start=2), 5001))
        else:
            flash("Only CSV and .xlsx files are supported.", "danger")
            return redirect(url_for("admin_dashboard"))
    except UnicodeDecodeError:
        flash("The CSV must be encoded as UTF-8.", "danger")
        return redirect(url_for("admin_dashboard"))
    except csv.Error:
        app.logger.exception("Unable to parse the uploaded CSV file.")
        flash("The CSV file could not be parsed.", "danger")
        return redirect(url_for("admin_dashboard"))
    except (zipfile.BadZipFile, InvalidFileException, ValueError, KeyError):
        app.logger.exception("Unable to read the uploaded market-data workbook.")
        flash("The Excel file is invalid or could not be read.", "danger")
        return redirect(url_for("admin_dashboard"))
    finally:
        if workbook is not None:
            workbook.close()

    if not headers or not rows:
        flash("The uploaded file must contain a header row and at least one data row.", "danger")
        return redirect(url_for("admin_dashboard"))
    if len(rows) > 5000:
        flash("A single upload may contain at most 5,000 data rows.", "danger")
        return redirect(url_for("admin_dashboard"))

    required_headers = {
        "state", "district", "market", "commodity", "arrival_date",
        "min_price", "max_price", "modal_price",
    }
    normalized_headers = {_normalize_upload_header(header) for header in headers}
    missing_headers = sorted(required_headers - normalized_headers)
    if missing_headers:
        flash(
            "Missing required columns: " + ", ".join(missing_headers) + ".",
            "danger",
        )
        return redirect(url_for("admin_dashboard"))

    valid_rows = []
    seen_batch_keys = set()
    for row_number, row in rows:
        if not any(value not in (None, "") for value in row):
            continue
        values, error = validate_market_price_payload(
            _upload_row_payload(headers, row)
        )
        if error:
            flash(f"Row {row_number}: {error}", "danger")
            return redirect(url_for("admin_dashboard"))
        batch_key = tuple(
            str(values[field] or "").strip().lower()
            for field in (
                "state", "district", "market", "commodity", "variety",
                "arrival_date", "source",
            )
        )
        if batch_key in seen_batch_keys:
            flash(f"Row {row_number}: duplicate record in the uploaded file.", "danger")
            return redirect(url_for("admin_dashboard"))
        seen_batch_keys.add(batch_key)
        valid_rows.append((row_number, values))

    if not valid_rows:
        flash("The uploaded file contains no market records.", "danger")
        return redirect(url_for("admin_dashboard"))

    connection = get_db_connection()
    if connection is None:
        flash("Database connection is unavailable; no records were imported.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        for row_number, values in valid_rows:
            if _find_duplicate_market_record(connection, values):
                connection.rollback()
                flash(
                    f"Row {row_number}: a matching market record already exists; "
                    "no records were imported.",
                    "danger",
                )
                return redirect(url_for("admin_dashboard"))

        for _, values in valid_rows:
            connection.execute(
                """
                INSERT INTO market_prices
                    (state, district, market, commodity, variety, arrival_date, min_price,
                     max_price, modal_price, price_unit, source, verification_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(values[field] for field in (
                    "state", "district", "market", "commodity", "variety",
                    "arrival_date", "min_price", "max_price", "modal_price",
                    "price_unit", "source", "verification_status",
                )),
            )
        connection.commit()
    except (sqlite3.Error, mysql.connector.Error):
        connection.rollback()
        app.logger.exception("Unable to import the uploaded market-data file.")
        flash("The upload failed; no market records were imported.", "danger")
        return redirect(url_for("admin_dashboard"))
    finally:
        connection.close()

    flash(f"Successfully imported {len(valid_rows)} market records.", "success")
    return redirect(url_for("market_prices"))


@app.route("/admin/users", methods=["POST"])
@admin_required
def create_user_account():
    username = request.form.get("username", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    if (
        not username
        or len(username) > 191
        or any(character.isspace() for character in username)
    ):
        flash("Username is required, must be 191 characters or fewer, and cannot contain spaces.", "danger")
        return redirect(url_for("admin_dashboard"))
    if not full_name or len(full_name) > 150:
        flash("Enter a display name of 1 to 150 characters.", "danger")
        return redirect(url_for("admin_dashboard"))
    if len(password) < 12:
        flash("User passwords must be at least 12 characters long.", "danger")
        return redirect(url_for("admin_dashboard"))

    connection = get_db_connection()
    if connection is None:
        flash("Database connection is unavailable; the user account was not created.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        existing = connection.execute(
            "SELECT id FROM auth_users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            flash("That username is already in use.", "danger")
            return redirect(url_for("admin_dashboard"))
        connection.execute(
            "INSERT INTO auth_users (username, full_name, password_hash, role) "
            "VALUES (?, ?, ?, 'USER')",
            (username, full_name, generate_password_hash(password)),
        )
        connection.commit()
    except (sqlite3.IntegrityError, mysql.connector.IntegrityError):
        connection.rollback()
        flash("That username is already in use.", "danger")
        return redirect(url_for("admin_dashboard"))
    except (sqlite3.Error, mysql.connector.Error):
        connection.rollback()
        app.logger.exception("Unable to create the requested user account.")
        flash("The user account could not be created.", "danger")
        return redirect(url_for("admin_dashboard"))
    finally:
        connection.close()

    flash(f"Read-only user account '{username}' was created successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db_connection()
    if connection is None:
        flash("The database is not available at the moment.", "danger")
        return render_template("dashboard.html", stats={}, recent_records=[])

    stats = calculate_dashboard_metrics(connection)
    recent_records = get_records_for_query(connection, limit=5)
    connection.close()
    return render_template("dashboard.html", stats=stats, recent_records=recent_records)


@app.route("/market-prices")
@login_required
def market_prices():
    connection = get_db_connection()
    filters = get_filter_options(connection) if connection is not None else {"district": [], "commodity": [], "market": []}
    if connection is not None:
        connection.close()
    return render_template(
        "market_prices.html",
        filters=filters,
        can_manage=session.get("role") == "ADMIN",
    )


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/refresh-data", methods=["POST"])
@admin_required
def refresh_data():
    connection = get_db_connection()
    if connection is None:
        flash("Database connection is unavailable. Please check MySQL or SQLite configuration.", "danger")
        return redirect(url_for("dashboard"))

    result = sync_government_data(connection)
    connection.close()
    flash(result.get("message", "Government data refresh completed."), "success" if result.get("status") in {"success", "success_no_records"} else "warning")
    return redirect(url_for("dashboard"))


@app.route("/export/csv")
@login_required
def export_csv():
    filters = {
        "district": request.args.get("district"),
        "commodity": request.args.get("commodity"),
        "market": request.args.get("market"),
        "search": request.args.get("search", "").strip(),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    sort = request.args.get("sort", "arrival_date")
    connection = get_db_connection()
    if connection is None:
        flash("CSV export failed because the database is unavailable.", "danger")
        return redirect(url_for("market_prices"))

    records = get_records_for_query(connection, filters=filters, sort=sort)
    output = io.StringIO()
    fieldnames = [
        "state",
        "district",
        "market",
        "commodity",
        "variety",
        "arrival_date",
        "min_price",
        "max_price",
        "modal_price",
        "price_unit",
        "source",
        "verification_status",
        "fetched_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow({key: record.get(key, "") for key in fieldnames})

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=tn_agripulse_market_prices.csv"
    connection.close()
    return response


@app.route("/api/dashboard")
@api_login_required
def api_dashboard():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500

    stats = calculate_dashboard_metrics(connection)
    recent_records = get_records_for_query(connection, limit=5)
    connection.close()
    return jsonify({"kpis": stats, "recent_records": recent_records})


@app.route("/api/filters")
@api_login_required
def api_filters():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    result = get_filter_options(connection)
    connection.close()
    return jsonify(result)


@app.route("/api/market-records")
@api_login_required
def api_market_records():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        page = int(request.args.get("page", "1"))
        limit = int(request.args.get("limit", "10"))
    except ValueError:
        connection.close()
        return _market_record_error("Page and limit must be whole numbers.")
    if page < 1 or limit < 1 or limit > 100:
        connection.close()
        return _market_record_error("Page must be positive and limit must be between 1 and 100.")

    filters = {
        key: request.args.get(key, "").strip()
        for key in ("district", "commodity", "market", "date_from", "date_to", "search")
    }
    filtered = {key: value for key, value in filters.items() if value}
    if len(filtered.get("search", "")) > 100:
        connection.close()
        return _market_record_error("Search text must be 100 characters or fewer.")
    sort = request.args.get("sort", "arrival_date")
    if sort not in {"arrival_date", "modal_price_asc", "modal_price_desc"}:
        connection.close()
        return _market_record_error("Sort must be arrival_date, modal_price_asc, or modal_price_desc.")
    for field in ("date_from", "date_to"):
        if filtered.get(field):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filtered[field]):
                connection.close()
                return _market_record_error(f"{field.replace('_', ' ').capitalize()} must be a valid YYYY-MM-DD date.")
            try:
                date.fromisoformat(filtered[field])
            except ValueError:
                connection.close()
                return _market_record_error(f"{field.replace('_', ' ').capitalize()} must be a valid YYYY-MM-DD date.")
    if filtered.get("date_from") and filtered.get("date_to") and filtered["date_from"] > filtered["date_to"]:
        connection.close()
        return _market_record_error("Arrival from date cannot be later than arrival to date.")

    try:
        offset = (page - 1) * limit
        records = get_records_for_query(
            connection, filters=filtered, limit=limit, offset=offset, sort=sort
        )
        total = count_records_for_query(connection, filters=filtered)
        demo_total = connection.execute(
            "SELECT COUNT(*) FROM market_prices WHERE UPPER(source) = 'DEMO'"
        ).fetchone()[0]
        pages = max(1, (total + limit - 1) // limit)
        return jsonify({
            "records": [_serialize_market_record(record) for record in records],
            "total": total,
            "demo_records": demo_total,
            "page": page,
            "pages": pages,
        })
    except (sqlite3.Error, mysql.connector.Error):
        app.logger.exception("Unable to fetch market price records.")
        return jsonify({"error": "Unable to fetch market price records."}), 500
    finally:
        connection.close()


@app.route("/api/market-records/<int:record_id>", methods=["GET"])
@api_login_required
def api_market_record(record_id):
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        record = fetchone_as_dict(
            connection.execute("SELECT * FROM market_prices WHERE id = ?", (record_id,))
        )
        if record is None:
            return _market_record_error("Market price record not found.", 404)
        return jsonify({"record": _serialize_market_record(record)})
    except (sqlite3.Error, mysql.connector.Error):
        app.logger.exception("Unable to fetch market price record %s.", record_id)
        return jsonify({"error": "Unable to fetch market price record."}), 500
    finally:
        connection.close()


@app.route("/api/market-records", methods=["POST"])
@admin_required
def create_market_record():
    values, error = validate_market_price_payload(request.get_json(silent=True))
    if error:
        return _market_record_error(error)

    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        if _find_duplicate_market_record(connection, values):
            return _market_record_error("A record for this market, crop, date, and source already exists.", 409)

        cursor = connection.execute(
            """
            INSERT INTO market_prices
                (state, district, market, commodity, variety, arrival_date, min_price,
                 max_price, modal_price, price_unit, source, verification_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values[field] for field in (
                "state", "district", "market", "commodity", "variety", "arrival_date",
                "min_price", "max_price", "modal_price", "price_unit", "source",
                "verification_status",
            )),
        )
        connection.commit()
        record = fetchone_as_dict(
            connection.execute("SELECT * FROM market_prices WHERE id = ?", (cursor.lastrowid,))
        )
        return jsonify({"message": "Market price record added successfully.", "record": _serialize_market_record(record)}), 201
    except (sqlite3.IntegrityError, mysql.connector.IntegrityError):
        connection.rollback()
        return _market_record_error("A duplicate market price record already exists.", 409)
    except (sqlite3.Error, mysql.connector.Error):
        connection.rollback()
        app.logger.exception("Unable to add a market price record.")
        return jsonify({"error": "Unable to add the market price record."}), 500
    finally:
        connection.close()


@app.route("/api/market-records/<int:record_id>", methods=["PUT"])
@admin_required
def update_market_record(record_id):
    values, error = validate_market_price_payload(request.get_json(silent=True))
    if error:
        return _market_record_error(error)

    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        existing = connection.execute(
            "SELECT id FROM market_prices WHERE id = ?", (record_id,)
        ).fetchone()
        if existing is None:
            return _market_record_error("Market price record not found.", 404)
        if _find_duplicate_market_record(connection, values, exclude_id=record_id):
            return _market_record_error("A record for this market, crop, date, and source already exists.", 409)

        connection.execute(
            """
            UPDATE market_prices
            SET state = ?, district = ?, market = ?, commodity = ?, variety = ?,
                arrival_date = ?, min_price = ?, max_price = ?, modal_price = ?,
                price_unit = ?, source = ?, verification_status = ?
            WHERE id = ?
            """,
            tuple(values[field] for field in (
                "state", "district", "market", "commodity", "variety", "arrival_date",
                "min_price", "max_price", "modal_price", "price_unit", "source",
                "verification_status",
            )) + (record_id,),
        )
        connection.commit()
        record = fetchone_as_dict(
            connection.execute("SELECT * FROM market_prices WHERE id = ?", (record_id,))
        )
        return jsonify({"message": "Market price record updated successfully.", "record": _serialize_market_record(record)})
    except (sqlite3.IntegrityError, mysql.connector.IntegrityError):
        connection.rollback()
        return _market_record_error("A duplicate market price record already exists.", 409)
    except (sqlite3.Error, mysql.connector.Error):
        connection.rollback()
        app.logger.exception("Unable to update market price record %s.", record_id)
        return jsonify({"error": "Unable to update the market price record."}), 500
    finally:
        connection.close()


@app.route("/api/market-records/<int:record_id>", methods=["DELETE"])
@admin_required
def delete_market_record(record_id):
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        existing = connection.execute(
            "SELECT id FROM market_prices WHERE id = ?", (record_id,)
        ).fetchone()
        if existing is None:
            return _market_record_error("Market price record not found.", 404)
        connection.execute("DELETE FROM market_prices WHERE id = ?", (record_id,))
        connection.commit()
        return jsonify({"message": "Market price record deleted successfully."})
    except (sqlite3.Error, mysql.connector.Error):
        connection.rollback()
        app.logger.exception("Unable to delete market price record %s.", record_id)
        return jsonify({"error": "Unable to delete the market price record."}), 500
    finally:
        connection.close()


@app.route("/api/analytics")
@api_login_required
def api_analytics():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database unavailable"}), 500
    result = calculate_analytics_summary(connection)
    connection.close()
    return jsonify(result)


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
    )
