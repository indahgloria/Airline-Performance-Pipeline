"""Central config. Everything comes from environment variables (or a .env file) so the
same code runs on your laptop (Postgres.app), in Docker, and in GitHub Actions."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

PG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "flights"),
    "user": os.getenv("PGUSER", os.getenv("USER", "postgres")),
    "password": os.getenv("PGPASSWORD", ""),
    # Set PGSSLMODE=require when the database is Amazon RDS (encrypts the connection).
    "sslmode": os.getenv("PGSSLMODE", ""),
}

# Optional S3 landing zone. Leave S3_BUCKET empty and the pipeline is purely local.
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "raw/bts/").strip("/") + "/"

RAW_DIR = Path(os.getenv("RAW_DIR", ROOT / "data" / "raw"))
REPORT_DIR = ROOT / "reports"
DBT_DIR = ROOT / "transform"

# Same file naming as the BTS "PREZIP" downloads, so real and fake files are interchangeable.
BTS_ZIP_NAME = "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
BTS_CSV_NAME = "On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_{year}_{month}.csv"
BTS_URL = "https://transtats.bts.gov/PREZIP/" + BTS_ZIP_NAME
