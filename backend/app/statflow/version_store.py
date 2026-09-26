"""Immutable dataset versions.

Layout on disk (next to the uploaded file):

    storage/{user_id}/{dataset_id}/data.csv          <- original upload (never touched)
    storage/{user_id}/{dataset_id}/versions/v1.parquet
    storage/{user_id}/{dataset_id}/versions/v2.parquet
    ...

Version 1 always mirrors the uploaded dataset; every cleaning/transformation
operation writes a new file and a new ``DatasetVersion`` + ``DatasetOperation``
row, so earlier versions stay available for reproducibility.
"""

import io
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import Dataset, DatasetOperation, DatasetVersion
from app.services.data_service import read_dataframe, to_jsonable

try:  # parquet is preferred; CSV is a transparent fallback
    from importlib.util import find_spec

    PARQUET_AVAILABLE = find_spec("pyarrow") is not None
except Exception:  # pragma: no cover - defensive
    PARQUET_AVAILABLE = False

DEFAULT_FORMAT = "parquet" if PARQUET_AVAILABLE else "csv"
_VERSION_LOCKS = tuple(threading.RLock() for _ in range(64))
_VERSION_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4)
_TEMP_FILE_MAX_AGE_SECONDS = 24 * 60 * 60


class VersionError(ValueError):
    """Raised for invalid version requests (mapped to HTTP 400/404)."""


# ------------------------------------------------------------- file handling


def versions_dir(dataset: Dataset) -> Path:
    """Folder that holds every version file of a dataset."""
    base = Path(dataset.storage_path).parent if dataset.storage_path else None
    if base is None:
        raise VersionError("Dataset file is not available on the server")
    folder = base / "versions"
    folder.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - _TEMP_FILE_MAX_AGE_SECONDS
    for candidate in folder.glob(".v*.tmp"):
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue
    return folder


def _normalise_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Make mixed/object columns parquet-friendly without losing missing values."""
    frame = df.copy()
    for column in frame.columns:
        if frame[column].dtype == "object":
            values = frame[column].dropna()
            kinds = {type(value).__name__ for value in values.head(200)}
            if len(kinds) > 1 or "list" in kinds or "dict" in kinds:
                frame[column] = frame[column].astype("string")
    return frame


def _version_lock(dataset_id: int) -> threading.RLock:
    return _VERSION_LOCKS[dataset_id % len(_VERSION_LOCKS)]


def write_version_file(
    df: pd.DataFrame, dataset: Dataset, version: int
) -> Tuple[Path, str]:
    """Write a complete temporary version file and return (path, format)."""
    folder = versions_dir(dataset)
    if PARQUET_AVAILABLE:
        temporary_path = folder / f".v{version}.{uuid4().hex}.parquet.tmp"
        try:
            with temporary_path.open("xb") as handle:
                _normalise_for_parquet(df).to_parquet(handle, index=False)
            return temporary_path, "parquet"
        except FileExistsError:
            raise
        except Exception:  # noqa: BLE001 - fall back to CSV
            temporary_path.unlink(missing_ok=True)

    temporary_path = folder / f".v{version}.{uuid4().hex}.csv.tmp"
    with temporary_path.open("xb") as handle:
        df.to_csv(handle, index=False)
    return temporary_path, "csv"


def publish_version_file(
    temporary_path: Path, dataset: Dataset, version: int, file_format: str
) -> Path:
    final_path = versions_dir(dataset) / f"v{version}.{file_format}"
    os.replace(temporary_path, final_path)
    return final_path


def read_version_file(version: DatasetVersion) -> pd.DataFrame:
    """Read the DataFrame behind one version."""
    path = Path(version.storage_path)
    if not path.exists():
        raise VersionError(f"File for version {version.version} is missing")
    if version.file_format == "parquet":
        frame = pd.read_parquet(path)
    elif version.file_format == "source":
        frame = read_dataframe(path)
    else:
        frame = pd.read_csv(path, low_memory=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def version_bytes(df: pd.DataFrame, file_format: str) -> Tuple[bytes, str, str]:
    """Serialise a version for download: (bytes, media_type, extension)."""
    buffer = io.BytesIO()
    if file_format == "parquet" and PARQUET_AVAILABLE:
        _normalise_for_parquet(df).to_parquet(buffer, index=False)
        return (
            buffer.getvalue(),
            "application/vnd.apache.parquet",
            "parquet",
        )
    df.to_csv(buffer, index=False)
    return buffer.getvalue(), "text/csv", "csv"


# ----------------------------------------------------------- version records


def list_versions(db: Session, dataset: Dataset) -> List[DatasetVersion]:
    return (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.version)
        .all()
    )


def get_version(
    db: Session, dataset: Dataset, version: Optional[int] = None
) -> DatasetVersion:
    """Fetch one version, or the newest one when ``version`` is None."""
    query = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id)
    if version is None:
        record = query.order_by(DatasetVersion.version.desc()).first()
    else:
        record = query.filter(DatasetVersion.version == version).first()
    if record is None:
        label = "no versions exist yet" if version is None else f"version {version}"
        raise VersionError(f"Dataset version not found ({label})")
    return record


def ensure_base_version(db: Session, dataset: Dataset) -> DatasetVersion:
    """Create v1 from the uploaded file the first time a dataset is used."""
    with _version_lock(dataset.id):
        for attempt, delay in enumerate((*_VERSION_RETRY_DELAYS, None)):
            if attempt:
                db.rollback()
            existing = get_version_or_none(db, dataset, 1)
            if existing is not None:
                return existing

            frame = read_dataframe(dataset.storage_path)
            temporary_path = None
            try:
                db.query(Dataset).filter(Dataset.id == dataset.id).with_for_update().one()
                existing = get_version_or_none(db, dataset, 1)
                if existing is not None:
                    db.rollback()
                    return existing
                temporary_path, file_format = write_version_file(frame, dataset, 1)
                final_path = versions_dir(dataset) / f"v1.{file_format}"
                version = DatasetVersion(
                    dataset_id=dataset.id,
                    version=1,
                    parent_version=None,
                    storage_path=str(final_path),
                    file_format=file_format,
                    row_count=int(frame.shape[0]),
                    column_count=int(frame.shape[1]),
                    is_current=1,
                    label="original upload",
                    created_by=dataset.user_id,
                )
                db.add(version)
                db.flush()
                publish_version_file(temporary_path, dataset, 1, file_format)
                temporary_path = None
                db.commit()
            except FileExistsError:
                db.rollback()
            except IntegrityError:
                db.rollback()
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                existing = get_version_or_none(db, dataset, 1)
                if existing is not None:
                    return existing
            except Exception:
                db.rollback()
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise
            else:
                db.refresh(version)
                return version
            if delay is not None:
                time.sleep(delay)

    raise VersionError("Could not initialize the base version for this dataset")


def get_version_or_none(
    db: Session, dataset: Dataset, version: int
) -> Optional[DatasetVersion]:
    return (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.version == version,
        )
        .first()
    )


def resolve_version(
    db: Session, dataset: Dataset, version: Optional[int] = None
) -> DatasetVersion:
    ensure_base_version(db, dataset)
    return get_version(db, dataset, version)


def load_version_frame(
    db: Session, dataset: Dataset, version: Optional[int] = None
) -> Tuple[DatasetVersion, pd.DataFrame]:
    record = resolve_version(db, dataset, version)
    return record, read_version_file(record)


def create_version(
    db: Session,
    dataset: Dataset,
    frame: pd.DataFrame,
    *,
    operation_group: str,
    operation_type: str,
    configuration: Dict[str, Any],
    source_version: int,
    summary: Dict[str, Any],
    warnings: Optional[List[str]] = None,
    label: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Tuple[DatasetVersion, DatasetOperation]:
    """Write a new immutable version plus its operation-history entry."""
    if frame.shape[0] == 0:
        raise VersionError(
            "This operation would produce an empty dataset, nothing was changed"
        )
    if frame.shape[1] == 0:
        raise VersionError("This operation would remove every column")

    if get_version_or_none(db, dataset, source_version) is None:
        ensure_base_version(db, dataset)

    with _version_lock(dataset.id):
        for attempt, delay in enumerate((*_VERSION_RETRY_DELAYS, None)):
            if attempt:
                db.rollback()
            temporary_path = None
            try:
                locked_dataset = (
                    db.query(Dataset)
                    .filter(Dataset.id == dataset.id)
                    .with_for_update()
                    .one()
                )
                latest = get_version(db, dataset, source_version)
                highest = (
                    db.query(DatasetVersion.version)
                    .filter(DatasetVersion.dataset_id == dataset.id)
                    .order_by(DatasetVersion.version.desc())
                    .first()
                )
                new_number = (int(highest[0]) if highest else 0) + 1
                temporary_path, file_format = write_version_file(
                    frame, dataset, new_number
                )
                final_path = versions_dir(dataset) / f"v{new_number}.{file_format}"

                db.query(DatasetVersion).filter(
                    DatasetVersion.dataset_id == dataset.id
                ).update({DatasetVersion.is_current: 0})

                version = DatasetVersion(
                    dataset_id=dataset.id,
                    version=new_number,
                    parent_version=int(latest.version),
                    storage_path=str(final_path),
                    file_format=file_format,
                    row_count=int(frame.shape[0]),
                    column_count=int(frame.shape[1]),
                    is_current=1,
                    label=label,
                    created_by=created_by,
                )
                db.add(version)
                db.flush()

                sequence = (
                    db.query(DatasetOperation)
                    .filter(DatasetOperation.dataset_id == dataset.id)
                    .count()
                    + 1
                )
                operation = DatasetOperation(
                    dataset_id=dataset.id,
                    dataset_version_id=version.id,
                    sequence=sequence,
                    operation_group=operation_group,
                    operation_type=operation_type,
                    configuration=to_jsonable(configuration) or {},
                    source_version=int(latest.version),
                    result_version=new_number,
                    summary=to_jsonable(summary) or {},
                    warnings=to_jsonable(warnings or []) or [],
                )
                db.add(operation)
                locked_dataset.row_count = int(frame.shape[0])
                locked_dataset.column_count = int(frame.shape[1])
                locked_dataset.status = "cleaned"
                publish_version_file(
                    temporary_path, dataset, new_number, file_format
                )
                temporary_path = None
                db.commit()
            except FileExistsError:
                db.rollback()
            except (IntegrityError, OperationalError, OSError):
                db.rollback()
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            except Exception:
                db.rollback()
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise
            else:
                db.refresh(version)
                db.refresh(operation)
                return version, operation
            if delay is not None:
                time.sleep(delay)

    raise VersionError("Could not create a new version because the dataset is busy")


def list_operations(
    db: Session, dataset: Dataset, version: Optional[int] = None
) -> List[DatasetOperation]:
    """Operation history (optionally only the steps that led to ``version``)."""
    query = db.query(DatasetOperation).filter(
        DatasetOperation.dataset_id == dataset.id
    )
    if version is None:
        return query.order_by(DatasetOperation.sequence).all()

    get_version(db, dataset, version)
    versions = {
        item.version: item
        for item in db.query(DatasetVersion).filter(
            DatasetVersion.dataset_id == dataset.id
        )
    }
    operations = {
        item.result_version: item
        for item in db.query(DatasetOperation).filter(
            DatasetOperation.dataset_id == dataset.id
        )
    }
    branch: List[DatasetOperation] = []
    current = version
    while current in versions:
        operation = operations.get(current)
        if operation is not None:
            branch.append(operation)
        parent = versions[current].parent_version
        if parent is None or parent >= current:
            break
        current = int(parent)
    return list(reversed(branch))


def lineage(db: Session, dataset: Dataset) -> List[Dict[str, Any]]:
    """Human-readable version lineage: original -> v2 -> v3 ... with operations."""
    versions = list_versions(db, dataset)
    operations = {operation.result_version: operation for operation in list_operations(db, dataset)}
    chain: List[Dict[str, Any]] = []
    for version in versions:
        operation = operations.get(version.version)
        chain.append(
            {
                **version.to_dict(),
                "operation": (
                    {
                        "type": operation.operation_type,
                        "group": operation.operation_group,
                        "configuration": operation.configuration,
                        "summary": operation.summary,
                        "warnings": operation.warnings or [],
                    }
                    if operation
                    else None
                ),
                "filename": Path(version.storage_path).name,
            }
        )
    return chain

