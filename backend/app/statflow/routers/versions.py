"""MVP-18 endpoints: clean / transform with immutable versions + operation history."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Dataset, User
from app.rbac import ORG_ROLE_VIEWER
from app.services.data_service import dataframe_records
from app.services.validation_service import validate_frame
from app.statflow import remediation, version_store
from app.statflow.operations import (
    CLEAN,
    TRANSFORM,
    OperationError,
    append_frames,
    apply_operation,
    catalog,
    merge_frames,
    operation_group,
)
from app.statflow.schemas import (
    DatasetJoinRequest,
    OperationRequest,
    RemediationRequest,
)
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/datasets", tags=["statflow-v1-operations"])


def _fail(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _load_frame(db: Session, dataset: Dataset, version: Optional[int]) -> Any:
    return version_store.load_version_frame(db, dataset, version)


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
            created_by=user.id,
        )
    except (VersionError, OperationError) as exc:
        raise _fail(exc)

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


@router.post("/{dataset_id}/remediate")
def remediate(
    dataset_id: int,
    payload: RemediationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fix what the Validate stage found -> new dataset version.

    One click over the mundane findings: an empty column, a number
    read as text, a few duplicated rows. The fixes are the ordinary
    cleaning operations, so the history records a real sequence of
    steps rather than a bypass of them, and the original version
    stays exactly as uploaded -- which is what keeps the finding it
    produced recomputable.

    A finding whose fix would be a guess (negative values, identifier
    columns) is never applied by the default click; it is opt-in per
    finding. The response re-validates the new version and returns
    what is left, so the reader sees the result rather than having
    to trust it.
    """
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        version_record, frame = _load_frame(db, dataset, payload.dataset_version)
        report = validate_frame(frame)
        result = remediation.remediate_frame(
            frame, report, [fix.model_dump() for fix in (payload.fixes or [])] if payload.fixes else None
        )
        validation_after = validate_frame(result["frame"])

        if not result["changed"]:
            return {
                "dataset_id": dataset.id,
                "remediated": False,
                "version": None,
                "current_version": int(version_record.version),
                "applied": [],
                "skipped": result["skipped"],
                "warnings": result["warnings"],
                "row_count": result["rows_after"],
                "column_count": result["columns_after"],
                "validation_after": validation_after,
            }

        new_version, operation = version_store.create_version(
            db,
            dataset,
            result["frame"],
            operation_group=CLEAN,
            operation_type="remediate",
            configuration={
                "fixes": [
                    {"code": fix["code"], "column": fix["column"]}
                    for fix in result["applied"]
                ]
            },
            source_version=int(version_record.version),
            summary={
                "applied": result["applied"],
                "rows_before": result["rows_before"],
                "rows_after": result["rows_after"],
                "columns_before": result["columns_before"],
                "columns_after": result["columns_after"],
                "findings_remaining": len(validation_after.get("issues") or []),
            },
            warnings=result["warnings"],
            label=payload.label or "Usafishaji otomatiki",
            created_by=user.id,
        )
    except (VersionError, OperationError) as exc:
        raise _fail(exc)

    return {
        "dataset_id": dataset.id,
        "remediated": True,
        "version": new_version.version,
        "current_version": new_version.version,
        "operation": operation.to_dict(),
        "applied": result["applied"],
        "skipped": result["skipped"],
        "warnings": result["warnings"],
        "row_count": new_version.row_count,
        "column_count": new_version.column_count,
        "validation_after": validation_after,
    }


@router.post("/{dataset_id}/join")
def join_dataset(
    dataset_id: int,
    payload: DatasetJoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Merge or append a second dataset -> new version of this one.

    The result becomes a new immutable version of *this* dataset; neither input
    is altered. That is what lets the cleaned or joined table be handed
    straight to the analysis engine afterwards: analysis reads a version, and
    this endpoint produces one.
    """
    dataset = get_owned_dataset(dataset_id, db, user)
    if dataset.id == payload.other_dataset_id:
        raise _fail(
            OperationError(
                "A dataset cannot be joined to itself. Pick a different second dataset."
            )
        )
    try:
        # get_owned_dataset applies the same permission check to the second
        # dataset, so a merge cannot be used to read data the caller is not
        # allowed to see.
        other = get_owned_dataset(payload.other_dataset_id, db, user, require_file=False)
        version_record, frame = _load_frame(db, dataset, payload.dataset_version)
        _, other_frame = _load_frame(db, other, payload.other_dataset_version)

        handler = (
            append_frames if payload.operation_type == "append" else merge_frames
        )
        result, summary, warnings = handler(frame, other_frame, payload.configuration)

        new_version, operation = version_store.create_version(
            db,
            dataset,
            result,
            operation_group=TRANSFORM,
            operation_type=payload.operation_type,
            configuration={
                **payload.configuration,
                "other_dataset_id": other.id,
                "other_dataset_version": int(
                    version_store.get_version(
                        db, other, payload.other_dataset_version
                    ).version
                ),
            },
            source_version=int(version_record.version),
            summary=summary,
            warnings=warnings,
            label=payload.label,
            created_by=user.id,
        )
    except (VersionError, OperationError) as exc:
        raise _fail(exc)

    return {
        "dataset_id": dataset.id,
        "other_dataset_id": other.id,
        "version": new_version.version,
        "current_version": new_version.version,
        "operation": operation.to_dict(),
        "summary": summary,
        "warnings": warnings,
        "row_count": new_version.row_count,
        "column_count": new_version.column_count,
    }


@router.get("/{dataset_id}/operations")
def operations_history(
    dataset_id: int,
    version: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Operation history (audit trail) — exactly the shape the spec documents."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
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
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
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
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
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
