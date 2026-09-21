"""Chart endpoints: create a chart (Plotly-ready data) + list/read saved charts."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Chart, Dataset, User
from app.schemas import ChartListItem, ChartRequest, ChartResponse
from app.services.chart_service import build_chart_data
from app.services.data_service import read_dataframe

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
        "chart_type": record.chart_type,
        "config": config,
        "chart_data": (record.config or {}).get("_chart_data", {}),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/datasets/{dataset_id}/charts", response_model=ChartResponse)
def create_chart(
    dataset_id: int,
    payload: ChartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Build chart data from the dataset and store the chart settings."""
    dataset = get_owned_dataset(dataset_id, db, user)
    frame = read_dataframe(dataset.storage_path)
    config = payload.config.model_dump()

    try:
        chart_data = build_chart_data(frame, payload.chart_type, config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # The generated series are cached with the config so a saved chart can be
    # re-rendered and exported later without recomputing from the raw file.
    stored_config = {**config, "_chart_data": chart_data}
    record = Chart(
        dataset_id=dataset.id, chart_type=payload.chart_type, config=stored_config
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
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
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
    dataset = db.get(Dataset, record.dataset_id)
    if dataset is None or dataset.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this chart")
    return _chart_payload(record)
