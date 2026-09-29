import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load `backend/.env` if present. It does NOT override variables already set in
# the environment (dotenv default), so Render/Docker-injected values win. Use it
# to point a production/local run at the Render Postgres database without
# touching the sqlite default used for plain local development.
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_DEV_SECRET_KEY_DATA_ANALYSIS_PLATFORM")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

API_PREFIX = "/api"

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
REPORTS_DIR = STORAGE_DIR / "reports"

# Upload formats, in two groups. The delimited/spreadsheet group is read by
# pandas alone; the statistical package group (Stata .dta, SPSS .sav/.zsav/.por,
# R .RData/.rda/.rds) goes through app.services.stat_file_readers.
TABLE_EXTENSIONS = {".csv", ".xlsx", ".json", ".tsv", ".txt", ".parquet"}
STAT_EXTENSIONS = {".dta", ".sav", ".zsav", ".por", ".rdata", ".rds", ".rda"}
ALLOWED_EXTENSIONS = TABLE_EXTENSIONS | STAT_EXTENSIONS
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Comma-separated allow-list so local dev and the deployed frontend can both
# call the same API, e.g. FRONTEND_ORIGIN="http://localhost:3000,https://statflow.vercel.app"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if origin.strip()
]
