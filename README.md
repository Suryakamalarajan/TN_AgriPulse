# TN AgriPulse

TN AgriPulse is a beginner-friendly Tamil Nadu agricultural market analytics project built with Flask, Python, and data visualization. It helps users explore mandi market prices, compare crops, and study historical trends using real data when available.

## Project Structure

- `app.py` – Flask app and routes
- `config.py` – environment-based configuration
- `database/schema.sql` – MySQL schema for production setup
- `services/government_api.py` – official data.gov.in fetcher and sync logic
- `services/data_analysis.py` – Pandas/NumPy analytics helpers
- `templates/` – HTML pages
- `static/css/` – styling
- `static/js/` – chart and table interactions
- `.env.example` – environment variable example
- `.gitignore` – local secrets and file exclusions
- `requirements.txt` – Python dependencies

## Database Setup

This project is designed for MySQL in production, but it also includes a SQLite fallback so the app can run in a beginner environment without a full local MySQL service.

### MySQL (recommended)

1. Run the schema from the project folder in PowerShell:

   ```powershell
   Get-Content .\database\schema.sql | & "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p
   ```

   The script creates and selects `tn_agripulse`; no separate `USE` command is needed. Alternatively, open `database/schema.sql` in MySQL Workbench and execute the whole script there.
2. Set `DB_TYPE=mysql` in `.env` and fill in your host, username, password, and database name.

The market table uses ordinary indexes for filtering rather than a unique index over all its long text columns, which can exceed MySQL's maximum index-key size. The application checks for duplicate records before insert.

### Insert illustrative DEMO market prices

When the app starts with `DB_TYPE=mysql`, it inserts the 20 bundled DEMO records into the existing table if their source IDs are not already present. The operation is safe to repeat and preserves all other records. To run the same idempotent seed manually:

```powershell
python .\database\seed_demo_market_prices.py
```

The script inserts 20 illustrative Tamil Nadu records into the existing `market_prices` table. It does not create tables, and repeated runs skip its existing `DEMO-TN-20261104-*` source IDs. All rows use source `DEMO` and verification status `unverified`; they are not live government prices. The Market Prices page shows a DEMO badge and explanatory warning for these rows. To validate the bundled data without connecting to MySQL, run `python .\database\seed_demo_market_prices.py --check`.

### SQLite fallback

If MySQL is not available, leave `DB_TYPE=sqlite` in `.env` and the application will automatically create a local database file named `tn_agripulse.db`.

The application creates `market_prices` if it is missing and adds the `verification_status` column to an existing table when needed. MySQL users should configure a database account with permission to create/alter this table; the app applies that small schema migration when it first connects.

## Local Setup (Windows / PowerShell)

Note: for the best Pandas compatibility, use Python 3.11 through 3.14. The project includes a fallback path for environments where Pandas is not available, but the official analytics flow prefers a supported Python version.

### 1) Check Python installation

```powershell
py --version
```

### 2) Install and open VS Code

Open VS Code and select the `TN_AgriPulse` folder.

### 3) Install or start MySQL / XAMPP MySQL

- Install MySQL Community Server or use XAMPP.
- Make sure MySQL is running before trying database access.

### 4) Create and open project folder

Open the folder named `TN_AgriPulse` in VS Code.

### 5) Create a Python virtual environment

```powershell
cd C:\Users\sussh\OneDrive\Apps\agri_market\TN_AgriPulse
py -m venv .venv
```

### 6) Activate the environment in PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 7) Install requirements

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 8) Create the database and tables

If using MySQL, run the schema from PowerShell while in the project folder (do not enter SQL statements directly at the PowerShell prompt):

```powershell
Get-Content .\database\schema.sql | & "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p
```

If using SQLite, the app makes the file automatically on first run.

### 9) Configure the database and authentication

```powershell
Copy-Item .env.example .env
```

Edit `.env` with your local database connection and a unique session key. Generate a session key in PowerShell:

```env
DB_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_local_mysql_password
MYSQL_DATABASE=tn_agripulse
DATA_GOV_API_KEY=your_api_key_here
SECRET_KEY=
ADMIN1_USERNAME=
ADMIN1_PASSWORD=
ADMIN2_USERNAME=
ADMIN2_PASSWORD=
```

Generate `SECRET_KEY` with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into `SECRET_KEY`. Set two distinct admin usernames and strong, different passwords of at least 12 characters. Administrator usernames and password hashes are provisioned from these environment variables; plaintext passwords are never stored. The app will not grant admin access until both complete pairs are configured. Keep `.env` private and never commit it.

On startup, the app creates the separate `auth_users` table and migrates existing `users` accounts into it as read-only users. Existing email addresses become usernames (case-insensitive). Existing market records are not rewritten or deleted. Visitors can register their own USER accounts from the login page; administrator accounts can only be configured through the server environment.

### 10) Run the app

```powershell
python app.py
```

Then open this in the browser:

```text
http://127.0.0.1:5000
```

## Deploy to Vercel

The repository includes a Vercel Python function entry point. Before deploying:

1. Push the project to a GitHub repository. Confirm `.env` and `.venv/` are not tracked; never publish credentials.
2. Create a managed MySQL database that accepts connections from Vercel. The local SQLite file and a MySQL host of `localhost` are not suitable for deployment because Vercel functions are temporary and run remotely.
3. In Vercel, choose **Add New → Project**, import the repository, and deploy from the project root. Vercel detects the Python function from `api/index.py` and installs dependencies from `requirements.txt`.
4. In the Vercel project settings, add these environment variables for **Production** (and Preview if needed):

   - `DB_TYPE=mysql`
   - `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` — values from the managed database provider
   - `SECRET_KEY` — a fresh random value of at least 32 characters
   - `ADMIN1_USERNAME`, `ADMIN1_PASSWORD`, `ADMIN2_USERNAME`, `ADMIN2_PASSWORD` — two distinct admin accounts with passwords of at least 12 characters
   - `SESSION_COOKIE_SECURE=true`
   - `DATA_GOV_API_KEY` — optional; required only for live government data sync

   Add variables under **Settings → Environment Variables**, then redeploy. Do not copy the local `.env` file into the repository or paste its contents into source code.
5. After deployment, open the Vercel URL and test login, dashboards, and database-backed pages. Check **Deployments → Functions → Logs** if startup or database connection fails.

The app initializes its MySQL tables when its Python function starts, so the configured database user must have permission to create/alter tables. Existing local SQLite data is not automatically transferred; migrate it separately if you need those records online. Database providers may require SSL or IP allowlisting; use the provider's Vercel connection instructions.

### 11) Log in and test roles

- Open the application URL. The two login cards are **User Login** and **Administrator Login**.
- Existing accounts can sign in with their existing email address as the username and their existing password.
- Administrators use the two account pairs configured in `.env`. On first startup, both passwords are hashed into `auth_users`.
- Visitors can register read-only USER accounts, and admins can also provision USER accounts from the Admin Dashboard. Neither registration path can create an admin; administrator accounts can only be configured through the server environment.
- Users can view dashboards, analytics, charts, market records, filters, and CSV exports. They cannot refresh or change market data.
- Admins can add, edit, delete, upload, and refresh market records. Use the Logout button to end the session.

### 12) Manage and import market data

- Visit Market Prices as an administrator and use **Add Market Price** to create a record. State, district, market, crop, arrival date, prices, unit, source, and verification status are required; variety is optional.
- Use the Edit and Delete actions to update or remove records. Deletion requires confirmation.
- Upload UTF-8 CSV or `.xlsx` files from the Admin Dashboard. Required headers are `state`, `district`, `market`, `commodity`, `arrival_date`, `min_price`, `max_price`, and `modal_price`. `variety`, `price_unit`, `source`, and `verification_status` are optional. Uploads are limited to 5,000 rows and are validated before the entire dataset is committed.
- Search commodity and market names, filter by district/crop/market and arrival date, and sort by modal price.
- Dashboard KPI cards and charts use records from the configured database and show total records, districts, commodities, and modal-price statistics.
- When using MySQL, startup inserts the DEMO sample rows once; restarting skips those IDs and keeps all other records.
- New manual records default to **Unverified**; records imported from the official government API are marked **Verified**.
- Download CSV after selecting records.
- Click Refresh Government Data on the dashboard once a valid API key is added.

### Automatic Government Data Sync (Windows)

The scheduled sync uses the same database and import logic as the dashboard's manual refresh. Add a valid data.gov.in API key to `DATA_GOV_API_KEY` in `.env`, then register a daily 6:00 AM task from PowerShell in the project folder:

```powershell
.\database\register_sync_task.ps1
```

The task runs while your Windows account is signed in. To run a sync immediately or troubleshoot it, use:

```powershell
.\.venv\Scripts\python.exe .\database\sync_government_data.py
```

Each run is recorded in `data_sync_logs`. Placeholder API key values are treated as missing, and no credentials are printed by the sync command. Change the task's trigger time in Task Scheduler if 6:00 AM is not suitable.

Market record APIs require a logged-in session for reads and an administrator session plus CSRF token for writes:

- `GET /api/market-records` — filtered, paginated database records
- `GET /api/market-records/<id>` — one database record
- `POST /api/market-records` — add a validated record (ADMIN only)
- `PUT /api/market-records/<id>` — update a validated record (ADMIN only)
- `DELETE /api/market-records/<id>` — delete a record (ADMIN only)

## Testing Checklist

- Anonymous dashboard and API access is rejected.
- A USER can read analytics and market records but receives HTTP 403 for admin pages and mutation APIs.
- Only the two configured admin accounts receive ADMIN role; their stored passwords are Werkzeug hashes.
- Self-registration and admin provisioning create only USER accounts; registration cannot create another ADMIN.
- Admin CRUD, refresh, and uploads require CSRF validation.
- Market filters, analytics, CSV export, and upload validation remain available to their permitted roles.

## Official Government API Note

The project uses the official data.gov.in dataset:

- Resource ID: `9ef84268-d588-465a-a308-a864a43d0070`
- Link: `https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070`

The API key must be kept in `.env` and never exposed in the frontend or public code.

## Common Errors and Fixes

- `ModuleNotFoundError`: run `pip install -r requirements.txt` inside the virtual environment.
- PowerShell blocks scripts: use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- Database connection errors: confirm MySQL is running and .env values match your setup.
- API key missing: add `DATA_GOV_API_KEY` to `.env`.
- CSV not downloaded: ensure you are logged in and the route is accessible.
- No data on dashboard: refresh the government API after adding the key or check if the API returned no valid records.

## Notes

This is an educational project and is not an official Tamil Nadu government website.
