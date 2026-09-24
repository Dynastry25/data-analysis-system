"""Dataset endpoints: upload, list, detail + preview, profile, delete."""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Dataset, DatasetColumn, User
from app.schemas import (
    DatasetDetailResponse,
    DatasetSummary,
    MessageResponse,
    ProfileResponse,
    UploadResponse,
)
from app.services.data_service import (
    PREVIEW_ROWS,
    dataframe_records,
    delete_dataset_files,
    profile_columns,
    read_dataframe,
    store_upload_file,
    validate_extension,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


def sync_dataset_columns(
    db: Session, dataset: Dataset, profiles: List[Dict[str, Any]]
) -> None:
    """Replace the stored column metadata for a dataset (from schema.sql table)."""
    db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset.id).delete()
    for profile in profiles:
        db.add(
            DatasetColumn(
                dataset_id=dataset.id,
                column_name=profile["name"],
                data_type=profile["data_type"],
                missing_count=profile["missing_count"],
                unique_count=profile["unique_count"],
            )
        )


def _upload_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


@router.post(
    "/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED
)
def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Upload a CSV/XLSX file, profile it and register it in the database."""
    original_name = Path(file.filename or "").name
    try:
        extension = validate_extension(original_name)
    except ValueError as exc:
        raise _upload_error(str(exc))

    dataset = Dataset(
        user_id=user.id,
        original_filename=original_name or "dataset",
        file_type=extension.lstrip("."),
        storage_path="",
        status="uploading",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    stored_path = None
    try:
        stored_path, original_name = store_upload_file(file, user.id, dataset.id)
        frame = read_dataframe(stored_path)
    except ValueError as exc:
        # ``store_upload_file`` cleans up its own partial file on error, but if
        # the file was written and then failed to *read*, we must remove it here
        # (``storage_path`` is still "" on the model at this point).
        if stored_path is not None:
            delete_dataset_files(stored_path)
        db.delete(dataset)
        db.commit()
        raise _upload_error(str(exc))

    profiles = profile_columns(frame)
    dataset.storage_path = str(stored_path)
    dataset.original_filename = original_name
    dataset.row_count = int(frame.shape[0])
    dataset.column_count = int(frame.shape[1])
    dataset.status = "uploaded"
    sync_dataset_columns(db, dataset, profiles)
    db.commit()
    db.refresh(dataset)

    return {
        "dataset_id": dataset.id,
        "original_filename": dataset.original_filename,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": profiles,
        "status": dataset.status,
    }


@router.get("", response_model=List[DatasetSummary])
def list_datasets(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List the datasets belonging to the signed-in user."""
    datasets = (
        db.query(Dataset)
        .filter(Dataset.user_id == user.id)
        .order_by(Dataset.uploaded_at.desc(), Dataset.id.desc())
        .all()
    )
    return [dataset.to_summary_dict() for dataset in datasets]


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Full dataset details plus the first rows as a preview."""
    dataset = get_owned_dataset(dataset_id, db, user)
    frame = read_dataframe(dataset.storage_path)
    profiles = profile_columns(frame)
    return {
        "dataset": dataset.to_summary_dict(),
        "columns": profiles,
        "preview_rows": dataframe_records(frame, PREVIEW_ROWS),
    }


@router.get("/{dataset_id}/profile", response_model=ProfileResponse)
def profile_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fresh per-column profile: type, missing count, unique count, min/max."""
    dataset = get_owned_dataset(dataset_id, db, user)
    frame = read_dataframe(dataset.storage_path)
    profiles = profile_columns(frame)
    dataset.row_count = int(frame.shape[0])
    dataset.column_count = int(frame.shape[1])
    sync_dataset_columns(db, dataset, profiles)
    db.commit()
    return {
        "dataset_id": dataset.id,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": profiles,
    }


@router.delete("/{dataset_id}", response_model=MessageResponse)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Delete a dataset, its stored file, reports and every related record."""
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    for report in list(dataset.reports):
        Path(report.storage_path).unlink(missing_ok=True)
    delete_dataset_files(dataset.storage_path)
    db.delete(dataset)
    db.commit()
    return {"detail": f"Dataset {dataset_id} deleted"}
