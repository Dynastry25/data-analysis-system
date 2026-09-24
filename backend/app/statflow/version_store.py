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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Dataset, DatasetOperation, DatasetVersion
from app.services.data_service import read_dataframe, to_jsonable

try:  # parquet is preferred; CSV is a transparent fallback
    from importlib.util import find_spec

    PARQUET_AVAILABLE = find_spec("pyarrow") is not None
except Exception:  # pragma: no cover - defensive
    PARQUET_AVAILABLE = False

DEFAULT_FORMAT = "parquet" if PARQUET_AVAILABLE else "csv"


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


def write_version_file(
    df: pd.DataFrame, dataset: Dataset, version: int
) -> Tuple[Path, str]:
    """Persist a DataFrame as the file backing ``version``; returns (path, format)."""
    folder = versions_dir(dataset)
    if PARQUET_AVAILABLE:
        parquet_path = folder / f"v{version}.parquet"
        try:
            _normalise_for_parquet(df).to_parquet(parquet_path, index=False)
            return parquet_path, "parquet"
        except Exception:  # noqa: BLE001 - fall back to CSV
            parquet_path.unlink(missing_ok=True)

    csv_path = folder / f"v{version}.csv"
    df.to_csv(csv_path, index=False)
    return csv_path, "csv"


def read_version_file(version: DatasetVersion) -> pd.DataFrame:
    """Read the DataFrame behind one version."""
    path = Path(version.storage_path)
    if not path.exists():
        raise VersionError(f"File for version {version.version} is missing")
    if version.file_format == "parquet":
        frame = pd.read_parquet(path)
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
    existing = get_version_or_none(db, dataset, 1)
    if existing is not None:
        return existing

    frame = read_dataframe(dataset.storage_path)
    path, file_format = write_version_file(frame, dataset, 1)
    version = DatasetVersion(
        dataset_id=dataset.id,
        version=1,
        parent_version=None,
        storage_path=str(path),
        file_format=file_format,
        row_count=int(frame.shape[0]),
        column_count=int(frame.shape[1]),
        is_current=1,
        label="original upload",
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


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
) -> Tuple[DatasetVersion, DatasetOperation]:
    """Write a new immutable version plus its operation-history entry."""
    if frame.shape[0] == 0:
        raise VersionError(
            "This operation would produce an empty dataset, nothing was changed"
        )
    if frame.shape[1] == 0:
        raise VersionError("This operation would remove every column")

    latest = get_version_or_none(db, dataset, source_version)
    if latest is None:
        latest = ensure_base_version(db, dataset)

    # The source version may be old (branching off v3 while v7 is current), so the
    # new number always comes from the highest existing version instead.
    highest = (
        db.query(DatasetVersion.version)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.version.desc())
        .first()
    )
    new_number = (int(highest[0]) if highest else 0) + 1
    path, file_format = write_version_file(frame, dataset, new_number)

    # Only the newest version stays marked as current.
    db.query(DatasetVersion).filter(
        DatasetVersion.dataset_id == dataset.id
    ).update({DatasetVersion.is_current: 0})

    version = DatasetVersion(
        dataset_id=dataset.id,
        version=new_number,
        parent_version=int(latest.version),
        storage_path=str(path),
        file_format=file_format,
        row_count=int(frame.shape[0]),
        column_count=int(frame.shape[1]),
        is_current=1,
        label=label,
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
    db.commit()
    db.refresh(version)
    db.refresh(operation)
    return version, operation


def list_operations(
    db: Session, dataset: Dataset, version: Optional[int] = None
) -> List[DatasetOperation]:
    """Operation history (optionally only the steps that led to ``version``)."""
    query = db.query(DatasetOperation).filter(
        DatasetOperation.dataset_id == dataset.id
    )
    if version is not None:
        query = query.filter(DatasetOperation.result_version <= version)
    return query.order_by(DatasetOperation.sequence).all()


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

