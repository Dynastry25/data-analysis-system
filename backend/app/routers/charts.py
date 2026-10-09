"""Chart endpoints: create a chart (Plotly-ready data) + list/read saved charts."""

from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Chart, Job, User
from app.rbac import ORG_ROLE_VIEWER
from app.schemas import ChartListItem, ChartRequest, ChartResponse, JobType
from app.services.chart_service import build_chart_data
from app.services.job_processor import process_job
from app.statflow import version_store
from app.statflow.version_store import VersionError

router = APIRouter(tags=["charts"])


def _chart_payload(record: Chart) -> Dict[str, Any]:
    config = {
        key: value
        for key, value in (record.config or {}).items()
        if key != "_chart_data"
    }
    return {
        "chart_id": record.id,
        "dataset_id": record.dataset_id,
        "dataset_version": (
            record.dataset_version_record.version
            if record.dataset_version_record is not None
            else None
        ),
        "chart_type": record.chart_type,
        "config": config,
        "chart_data": (record.config or {}).get("_chart_data", {}),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/datasets/{dataset_id}/charts", response_model=ChartResponse)
def create_chart(
    dataset_id: int,
    payload: ChartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Build chart data from the dataset and store the chart settings.

    If use_job_queue is true, the chart rendering is queued as a background job
    and the job ID is returned immediately.
    """
    dataset = get_owned_dataset(dataset_id, db, user)

    if payload.use_job_queue:
        # Create a job for the chart rendering
        job = Job(
            user_id=user.id,
            job_type=JobType.CHART_RENDER,
            dataset_id=dataset.id,
            status="pending",
            progress=0,
            payload={
                "chart_type": payload.chart_type.value if hasattr(payload.chart_type, 'value') else str(payload.chart_type),
                "config": payload.config.model_dump(),
                "dataset_version": payload.dataset_version,
                "save": True,
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Start the job processing in background
        background_tasks.add_task(process_job, job.id)

        return {
            "job_id": job.id,
            "status": "pending",
            "message": "Chart rendering queued. Use /api/v1/jobs/{job_id} to check progress.",
        }

    # Synchronous execution (original behavior)
    try:
        version_record, frame = version_store.load_version_frame(
            db, dataset, payload.dataset_version
        )
        config = payload.config.model_dump()
        chart_data = build_chart_data(frame, payload.chart_type, config)
        # Source attribution, per the visualization rules: "data source/version
        # visibility" is a requirement, not a nicety. A chart that does not say
        # which dataset version it came from cannot be checked, and in a tool
        # where every operation creates a new version that is the difference
        # between a result and a guess.
        chart_data.setdefault("meta", {})
        chart_data["meta"].update(
            {
                "dataset_id": dataset.id,
                "dataset_name": dataset.original_filename,
                "dataset_version": int(version_record.version),
                "rows_total": int(frame.shape[0]),
            }
        )
    except (VersionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # The generated series are cached with the config so a saved chart can be
    # re-rendered and exported later without recomputing from the raw file.
    stored_config = {**config, "_chart_data": chart_data}
    record = Chart(
        dataset_id=dataset.id,
        dataset_version_id=version_record.id,
        chart_type=payload.chart_type,
        config=stored_config,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _chart_payload(record)


@router.get("/datasets/{dataset_id}/charts", response_model=List[ChartListItem])
def list_charts(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Every chart saved for one dataset."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    records = (
        db.query(Chart)
        .filter(Chart.dataset_id == dataset.id)
        .order_by(Chart.id.desc())
        .all()
    )
    return [_chart_payload(record) for record in records]


@router.get("/charts/{chart_id}", response_model=ChartResponse)
def get_chart(
    chart_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One saved chart including its data (ownership checked through the dataset)."""
    record = db.get(Chart, chart_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Chart not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )
    return _chart_payload(record)
