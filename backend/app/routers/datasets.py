"""Dataset endpoints: upload, list, detail + preview, profile, delete."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import (
    AnalysisRun,
    Chart,
    Dataset,
    DatasetColumn,
    DatasetOperation,
    ExportedReport,
    OrganizationMember,
    Project,
    User,
)
from app.rbac import ORG_ROLE_ANALYST, ORG_ROLE_VIEWER, require_org_role
from app.schemas import (
    DatasetDetailResponse,
    DatasetProjectRequest,
    DatasetSummary,
    ExploreResponse,
    JourneyResponse,
    JourneyStageResponse,
    MessageResponse,
    ProfileResponse,
    UploadResponse,
    ValidationResponse,
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
from app.services.explore_service import explore_frame
from app.services.stat_file_readers import VariableLabels
from app.services.validation_service import validate_frame
from app.statflow import version_store
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/datasets", tags=["datasets"])


def sync_dataset_columns(
    db: Session,
    dataset: Dataset,
    profiles: List[Dict[str, Any]],
    labels: Optional[VariableLabels] = None,
) -> None:
    """Replace the stored column metadata for a dataset (from schema.sql table).

    ``labels`` carries the variable and value labels the source file declared.
    It is optional because versions written by a cleaning operation are Parquet
    and carry none: passing it on a later sync must not wipe the labels recorded
    at upload, so a caller that has no labels simply omits the argument and the
    existing rows are rebuilt without them.
    """
    db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset.id).delete()
    for profile in profiles:
        variable_label = None
        value_labels = None
        if labels is not None:
            variable_label, value_labels = labels.for_column(profile["name"])
        db.add(
            DatasetColumn(
                dataset_id=dataset.id,
                column_name=profile["name"],
                data_type=profile["data_type"],
                missing_count=profile["missing_count"],
                unique_count=profile["unique_count"],
                variable_label=variable_label,
                value_labels=value_labels,
            )
        )



def _stored_labels(db: Session, dataset_id: int) -> Dict[str, Dict[str, Any]]:
    """The labels recorded at upload, keyed by column name.

    Labels belong to the *file*, so they are read back from ``dataset_columns``
    rather than recomputed. A cleaning operation writes a Parquet version that
    has no labels of its own, but the columns it inherited still carry the
    labels from the original upload — which is the point: the researcher
    described ``gender`` once, and that description survives every operation.
    """
    rows = db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).all()
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.variable_label is None and row.value_labels is None:
            continue
        result[row.column_name] = {
            "variable_label": row.variable_label,
            "value_labels": row.value_labels,
        }
    return result


def _attach_labels(
    profiles: List[Dict[str, Any]], labels: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Put each column's label on its profile, leaving the rest untouched."""
    if not labels:
        return profiles
    for profile in profiles:
        entry = labels.get(profile.get("name"))
        if entry is None:
            continue
        profile["variable_label"] = entry.get("variable_label")
        profile["value_labels"] = entry.get("value_labels")
    return profiles


def _upload_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _load_current_frame(db: Session, dataset: Dataset) -> Any:
    try:
        return version_store.load_version_frame(db, dataset)
    except VersionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


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
        frame, labels = read_dataframe(stored_path, with_labels=True)
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
    sync_dataset_columns(db, dataset, profiles, labels)
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

    That is their own personal uploads plus the datasets inside projects of
    every organization they currently belong to.
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
                and_(Dataset.user_id == user.id, Dataset.project_id.is_(None)),
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
    version_record, frame = _load_current_frame(db, dataset)
    profiles = _attach_labels(
        profile_columns(frame), _stored_labels(db, dataset.id)
    )
    return {
        "dataset": dataset.to_summary_dict(),
        "dataset_version": int(version_record.version),
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
    version_record, frame = _load_current_frame(db, dataset)
    profiles = profile_columns(frame)
    return {
        "dataset_id": dataset.id,
        "dataset_version": int(version_record.version),
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "columns": profiles,
    }


@router.get("/{dataset_id}/validate", response_model=ValidationResponse)
def validate_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Deterministic data-quality findings for the Validate stage.

    The checks run in the backend so a reviewer can recompute every number from
    the same file. A blocked verdict means the file cannot be analysed yet, and
    the UI says that rather than letting the user discover it later.
    """
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
    version_record, frame = _load_current_frame(db, dataset)
    report = validate_frame(frame)
    return {
        "dataset_id": dataset.id,
        "dataset_version": int(version_record.version),
        **report,
    }


@router.get("/{dataset_id}/explore", response_model=ExploreResponse)
def explore_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Distributions, summary statistics and correlations, computed here.

    Nothing in the assistant is involved: a p-value, a correlation or a
    distribution must come from the engine, or it is not trustworthy.
    """
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)
    version_record, frame = _load_current_frame(db, dataset)
    described = explore_frame(frame)
    described["columns"] = _attach_labels(
        described["columns"], _stored_labels(db, dataset.id)
    )
    return {
        "dataset_id": dataset.id,
        "dataset_version": int(version_record.version),
        **described,
    }


@router.get("/{dataset_id}/journey", response_model=JourneyResponse)
def get_journey(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Progress for the 11-stage journey, counted from stored records only.

    The frontend owns the stage list; this endpoint only supplies the counts, so
    the two cannot drift into disagreeing about which stages exist.

    A stage is reported done only when a record proves it. Reading a validation
    report, exploring a distribution or asking the assistant writes nothing, so
    those stages can never report done, and neither can composing a report. The
    UI says so rather than showing a green tick the user cannot trust.
    """
    dataset = get_owned_dataset(dataset_id, db, user, min_role=ORG_ROLE_VIEWER)

    def count(model: Any, *extra: Any) -> int:
        query = db.query(model).filter(model.dataset_id == dataset.id)
        for clause in extra:
            query = query.filter(clause)
        return int(query.count())

    profiled_columns = count(DatasetColumn)
    clean_operations = count(DatasetOperation, DatasetOperation.operation_group == "clean")
    transform_operations = count(
        DatasetOperation, DatasetOperation.operation_group == "transform"
    )
    analysis_runs = count(AnalysisRun)
    charts = count(Chart)
    exports = count(ExportedReport, ExportedReport.status == "completed")

    # Record count per stage key. `None` means the stage leaves no record at all.
    records: Dict[str, Optional[int]] = {
        "upload": 1,
        "validate": None,
        "profile": profiled_columns,
        "clean": clean_operations,
        "transform": transform_operations,
        "explore": None,
        "analyze": analysis_runs,
        "visualize": charts,
        "explain": None,
        "report": None,
        "export": exports,
    }

    status = dataset.status
    done: Dict[str, bool] = {
        "upload": True,
        "validate": False,
        "profile": profiled_columns > 0,
        "clean": clean_operations > 0 or status == "cleaned",
        "transform": transform_operations > 0,
        "explore": False,
        "analyze": analysis_runs > 0 or status == "analyzed",
        "visualize": charts > 0,
        "explain": False,
        "report": False,
        "export": exports > 0,
    }

    reasons: Dict[str, str] = {
        "upload": "Faili imepakiwa",
        "validate": "Kagua matokeo ya schema na data quality",
        "profile": f"{profiled_columns} columns zimeprofile",
        "clean": f"{clean_operations} safisho zimewekwa",
        "transform": f"{transform_operations} mabadiliko yamewekwa",
        "explore": "Chunguza distributions na correlations",
        "analyze": f"{analysis_runs} uchambuzi umefanywa",
        "visualize": f"{charts} grafu zimeundwa",
        "explain": "Uliza swali kuhusu matokeo",
        "report": "Panga ripoti kutoka matokeo",
        "export": f"{exports} ripoti zimehamishwa",
    }

    # No stage is reported blocked. The product does not enforce an order, so
    # calling a later stage "blocked" would be a gate that does not exist. The
    # frontend decides what is "current" from the URL it is rendering; this
    # endpoint only reports what a stored record can prove.
    stages = [
        JourneyStageResponse(
            key=key,
            step=index + 1,
            done=done[key],
            record_count=records[key],
            reason=reasons[key],
        )
        for index, key in enumerate(records)
    ]

    return {
        "dataset_id": dataset.id,
        "dataset_status": status,
        "stages": stages,
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
