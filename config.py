import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "tn_agripulse")
    SQLITE_DATABASE = os.getenv("SQLITE_DATABASE", os.path.join(BASE_DIR, "tn_agripulse.db"))
    DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")
    DATA_GOV_API_URL = os.getenv(
        "DATA_GOV_API_URL",
        "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
    )
    DATA_GOV_TIMEOUT = int(os.getenv("DATA_GOV_TIMEOUT", "20"))
    MAX_PAGES = int(os.getenv("MAX_PAGES", "2"))
    ADMIN_ACCOUNTS = (
        (os.getenv("ADMIN1_USERNAME", ""), os.getenv("ADMIN1_PASSWORD", "")),
        (os.getenv("ADMIN2_USERNAME", ""), os.getenv("ADMIN2_PASSWORD", "")),
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)


def get_mysql_config():
    return {
        "host": Config.MYSQL_HOST,
        "port": Config.MYSQL_PORT,
        "user": Config.MYSQL_USER,
        "password": Config.MYSQL_PASSWORD,
        "database": Config.MYSQL_DATABASE,
        "autocommit": True,
    }
