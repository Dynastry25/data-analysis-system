"""Dataset endpoints: upload, list, detail + preview, profile, delete."""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Dataset, DatasetColumn, OrganizationMember, Project, User
from app.rbac import ORG_ROLE_ANALYST, ORG_ROLE_VIEWER, require_org_role
from app.schemas import (
    DatasetDetailResponse,
    DatasetProjectRequest,
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
    project_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Upload a CSV/XLSX file, profile it and register it in the database."""
    original_name = Path(file.filename or "").name
    try:
        extension = validate_extension(original_name)
    except ValueError as exc:
        raise _upload_error(str(exc))

    organization_id = None
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        organization_id = project.organization_id
        require_org_role(db, organization_id, user, ORG_ROLE_ANALYST)

    dataset = Dataset(
        user_id=user.id,
        project_id=project_id,
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
        "project_id": dataset.project_id,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": profiles,
        "status": dataset.status,
    }


@router.get("", response_model=List[DatasetSummary])
def list_datasets(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List the datasets the signed-in user may reach.

    That is their own uploads (personal and shared) plus the datasets inside
    projects of every organization they belong to — a team member has to be
    able to *find* the data their colleagues shared.
    """
    member_projects = (
        select(Project.id)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Project.organization_id,
        )
        .where(OrganizationMember.user_id == user.id)
    )
    datasets = (
        db.query(Dataset)
        .filter(
            or_(
                Dataset.user_id == user.id,
                Dataset.project_id.in_(member_projects),
            )
        )
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
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
    frame = read_dataframe(dataset.storage_path)
    profiles = profile_columns(frame)
    return {
        "dataset": dataset.to_summary_dict(),
        "columns": profiles,
        "preview_rows": dataframe_records(frame, PREVIEW_ROWS),
    }


@router.patch("/{dataset_id}/project", response_model=DatasetSummary)
def set_dataset_project(
    dataset_id: int,
    payload: DatasetProjectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Move a dataset into a project so the organization can reach it.

    Only the person who uploaded the dataset may move it: handing it to a
    project shares it with every org member, and taking it back makes it
    private again. ``project_id=None`` returns the dataset to personal scope.
    """
    dataset = get_owned_dataset(dataset_id, db, user, min_role="viewer")
    if dataset.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the dataset owner can move it between projects",
        )
    if payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        require_org_role(db, project.organization_id, user, ORG_ROLE_ANALYST)
    dataset.project_id = payload.project_id
    db.commit()
    db.refresh(dataset)
    return dataset.to_summary_dict()


@router.get("/{dataset_id}/profile", response_model=ProfileResponse)
def profile_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fresh per-column profile: type, missing count, unique count, min/max."""
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
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
    """Delete a dataset, its stored file, reports and every related record.

    Deleting is destructive, so it stays with whoever uploaded the dataset —
    sharing a dataset with a project must not hand colleagues the power to
    remove it.
    """
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    if dataset.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the dataset owner can delete it",
        )
    for report in list(dataset.reports):
        Path(report.storage_path).unlink(missing_ok=True)
    delete_dataset_files(dataset.storage_path)
    db.delete(dataset)
    db.commit()
    return {"detail": f"Dataset {dataset_id} deleted"}
