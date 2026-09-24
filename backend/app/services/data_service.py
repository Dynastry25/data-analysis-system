"""Dataset file handling: storing uploads, reading, and profiling.

Everything that touches the dataset files lives here so the routers stay thin.
"""

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES, STORAGE_DIR

CHUNK_SIZE = 1024 * 1024  # 1MB
PREVIEW_ROWS = 20

TRUTHY_STRINGS = {"true", "t", "yes", "y", "1", "ndiyo", "sawa"}
FALSY_STRINGS = {"false", "f", "no", "n", "0", "hapana"}


# ------------------------------------------------------------------ uploads


def validate_extension(filename: str) -> str:
    """Return the lower-case extension or raise ``ValueError``."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{ext or 'unknown'}'. Allowed types: {allowed}"
        )
    return ext


def store_upload_file(
    upload: UploadFile, user_id: int, dataset_id: int
) -> Tuple[Path, str]:
    """Stream an upload to ``storage/{user_id}/{dataset_id}/data{ext}``.

    Enforces the max file size *while* streaming so we never buffer a huge file in
    memory (big-data requirement). Returns ``(path, original_filename)``.
    """
    original_name = Path(upload.filename or "dataset").name
    ext = validate_extension(original_name)

    target_dir = STORAGE_DIR / str(user_id) / str(dataset_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"data{ext}"

    size = 0
    try:
        with target_path.open("wb") as handle:
            while True:
                chunk = upload.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    raise ValueError(
                        "File too large. Maximum allowed size is "
                        f"{MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB"
                    )
                handle.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    if size == 0:
        target_path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is empty")

    return target_path, original_name


def delete_dataset_files(dataset_path: str) -> None:
    """Remove a dataset file and its now-empty dataset folder (best effort)."""
    path = Path(dataset_path)
    try:
        path.unlink(missing_ok=True)
        folder = path.parent
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass


# --------------------------------------------------------------- read / write


def read_dataframe(path: str | Path) -> pd.DataFrame:
    """Read a stored CSV/XLSX dataset into a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise ValueError("Dataset file is missing from storage")

    if path.suffix.lower() == ".csv":
        last_error: Optional[Exception] = None
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(path, encoding=encoding, low_memory=False)
                break
            except UnicodeDecodeError as exc:  # try the next encoding
                last_error = exc
            except pd.errors.EmptyDataError as exc:
                raise ValueError("The CSV file has no columns to analyse") from exc
        else:  # pragma: no cover - defensive
            raise ValueError(f"Could not decode the CSV file: {last_error}")
    else:
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception as exc:  # openpyxl raises a wide range of errors
            raise ValueError(f"Could not read the Excel file: {exc}") from exc

    df.columns = [str(col).strip() for col in df.columns]
    if df.shape[1] == 0:
        raise ValueError("The file has no columns to analyse")
    return df


def write_dataframe(df: pd.DataFrame, path: str | Path) -> None:
    """Persist a DataFrame back to its original CSV/XLSX format."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False, engine="openpyxl")


def to_jsonable(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-serialisable Python values."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    # Plain Python scalars pass through untouched (NaN/inf were handled above);
    # without this branch ``float`` values would fall through to ``str(value)``.
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return [to_jsonable(v) for v in value]
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def series_to_list(series: pd.Series) -> List[Any]:
    """JSON-safe list for a whole column (sample-limited by the caller)."""
    return [to_jsonable(value) for value in series.tolist()]


def dataframe_records(
    df: pd.DataFrame, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Rows of a DataFrame as JSON-safe dicts (NaN/inf become null)."""
    frame = df if limit is None else df.head(limit)
    records: List[Dict[str, Any]] = []
    for row in frame.itertuples(index=False, name=None):
        records.append(
            {
                column: to_jsonable(value)
                for column, value in zip(frame.columns, row)
            }
        )
    return records


def infer_column_type(series: pd.Series) -> str:
    """Classify a column as numeric | date | boolean | text."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    sample = series.dropna()
    if sample.empty:
        return "text"

    # Values stored as strings that are actually numbers/booleans/dates.
    converted = pd.to_numeric(sample, errors="coerce")
    if converted.notna().mean() == 1.0:
        return "numeric"

    lowered = sample.astype(str).str.strip().str.lower()
    if lowered.isin(TRUTHY_STRINGS | FALSY_STRINGS).mean() == 1.0:
        return "boolean"

    if sample.astype(str).str.len().max() <= 32:
        dates = pd.to_datetime(sample, errors="coerce", format="mixed")
        if dates.notna().mean() == 1.0:
            return "date"

    return "text"


def numeric_columns(df: pd.DataFrame) -> List[str]:
    """Columns that can be treated as numeric (real numerics first)."""
    return [col for col in df.columns if infer_column_type(df[col]) == "numeric"]


def profile_columns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Per-column profiling: type, missing count, unique count, min/max."""
    profiles: List[Dict[str, Any]] = []
    for column in df.columns:
        series = df[column]
        data_type = infer_column_type(series)
        profile: Dict[str, Any] = {
            "name": column,
            "data_type": data_type,
            "missing_count": int(series.isna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
            "min": None,
            "max": None,
        }
        clean = series.dropna()
        if not clean.empty and data_type in {"numeric", "date"}:
            try:
                if data_type == "numeric":
                    numeric = pd.to_numeric(clean, errors="coerce").dropna()
                    if not numeric.empty:
                        profile["min"] = to_jsonable(numeric.min())
                        profile["max"] = to_jsonable(numeric.max())
                else:
                    dates = pd.to_datetime(clean, errors="coerce", format="mixed")
                    dates = dates.dropna()
                    if not dates.empty:
                        profile["min"] = to_jsonable(dates.min())
                        profile["max"] = to_jsonable(dates.max())
            except (TypeError, ValueError):
                pass
        profiles.append(profile)
    return profiles


def coerce_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Numeric view of ``column`` (raises ``ValueError`` if it is not numeric)."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist in this dataset")
    numeric = pd.to_numeric(df[column], errors="coerce")
    if numeric.notna().sum() == 0:
        raise ValueError(f"Column '{column}' is not numeric, choose another column")
    return numeric
