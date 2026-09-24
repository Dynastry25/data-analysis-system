import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_DEV_SECRET_KEY_DATA_ANALYSIS_PLATFORM")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

API_PREFIX = "/api"

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
REPORTS_DIR = STORAGE_DIR / "reports"

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json", ".tsv", ".txt", ".parquet"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CORS_ORIGINS = [os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")]
