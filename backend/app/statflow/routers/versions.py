"""MVP-18 endpoints: clean / transform with immutable versions + operation history."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Dataset, User
from app.services.data_service import dataframe_records
from app.statflow import version_store
from app.statflow.operations import (
    CLEAN,
    TRANSFORM,
    OperationError,
    apply_operation,
    catalog,
    operation_group,
)
from app.statflow.schemas import OperationRequest
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/datasets", tags=["statflow-v1-operations"])


def _fail(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _load_frame(db: Session, dataset: Dataset, version: Optional[int]) -> Any:
    version_store.ensure_base_version(db, dataset)
    record = version_store.get_version(db, dataset, version)
    return record, version_store.read_version_file(record)


@router.get("/operations/catalog")
def operations_catalog(user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """The cleaning/transformation operations the engine supports."""
    return catalog()


def _apply(
    dataset_id: int,
    payload: OperationRequest,
    db: Session,
    user: User,
    expected_group: str,
) -> Dict[str, Any]:
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        if operation_group(payload.operation_type) != expected_group:
            raise OperationError(
                f"'{payload.operation_type}' is not a {expected_group} operation. "
                "Use the other endpoint (clean vs transform)."
            )
        version_record, frame = _load_frame(db, dataset, payload.dataset_version)
        cleaned, summary, warnings = apply_operation(
            frame, payload.operation_type, payload.configuration
        )
        new_version, operation = version_store.create_version(
            db,
            dataset,
            cleaned,
            operation_group=expected_group,
            operation_type=payload.operation_type,
            configuration=payload.configuration,
            source_version=int(version_record.version),
            summary=summary,
            warnings=warnings,
            label=payload.label,
        )
    except (VersionError, OperationError) as exc:
        raise _fail(exc)

    # Keep the legacy dataset summary in sync with the current version.
    dataset.row_count = new_version.row_count
    dataset.column_count = new_version.column_count
    dataset.status = "cleaned"
    db.commit()

    return {
        "dataset_id": dataset.id,
        "version": new_version.version,
        "current_version": new_version.version,
        "operation": operation.to_dict(),
        "summary": summary,
        "warnings": warnings,
        "row_count": new_version.row_count,
        "column_count": new_version.column_count,
    }


@router.post("/{dataset_id}/clean")
def clean(
    dataset_id: int,
    payload: OperationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Apply a cleaning operation -> new dataset version."""
    return _apply(dataset_id, payload, db, user, CLEAN)


@router.post("/{dataset_id}/transform")
def transform(
    dataset_id: int,
    payload: OperationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Apply a transformation operation -> new dataset version."""
    return _apply(dataset_id, payload, db, user, TRANSFORM)


@router.get("/{dataset_id}/operations")
def operations_history(
    dataset_id: int,
    version: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Operation history (audit trail) — exactly the shape the spec documents."""
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    try:
        version_store.ensure_base_version(db, dataset)
        lineage = version_store.lineage(db, dataset)
        operations = version_store.list_operations(db, dataset, version)
    except VersionError as exc:
        raise _fail(exc)
    return {
        "dataset_id": dataset.id,
        "current_version": lineage[-1]["version"] if lineage else None,
        "operations": [operation.to_dict() for operation in operations],
        "versions": lineage,
    }


@router.get("/{dataset_id}/versions/{version}")
def version_detail(
    dataset_id: int,
    version: int,
    preview_rows: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Details + preview rows of one dataset version."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        record = version_store.get_version(db, dataset, version)
        frame = version_store.read_version_file(record)
    except VersionError as exc:
        raise _fail(exc)
    return {
        "version": record.to_dict(),
        "preview_rows": dataframe_records(frame, preview_rows),
    }


@router.get("/{dataset_id}/versions/{version}/download")
def download_version(
    dataset_id: int,
    version: int,
    format: str = Query(default="parquet", pattern="^(parquet|csv)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Download one dataset version as parquet (or CSV)."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        record = version_store.get_version(db, dataset, version)
        frame = version_store.read_version_file(record)
    except VersionError as exc:
        raise _fail(exc)

    payload, media_type, extension = version_store.version_bytes(frame, format)
    filename = f"{dataset.original_filename.rsplit('.', 1)[0]}_v{version}.{extension}"
    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
