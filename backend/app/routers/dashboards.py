"""Dashboard endpoints: create, list, read, update and delete a saved dashboard.

A dashboard is a named arrangement of widgets over sources that already exist —
saved analyses, saved charts and column summaries. It is pinned to a dataset
version, exactly like a chart, so a dashboard opened today renders the numbers
that were in the dataset when the dashboard was built.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import Dashboard, User
from app.rbac import ORG_ROLE_ANALYST, ORG_ROLE_VIEWER
from app.schemas import (
    DashboardListItem,
    DashboardRequest,
    DashboardResponse,
    DashboardUpdateRequest,
)
from app.statflow import version_store
from app.statflow.version_store import VersionError

router = APIRouter(tags=["dashboards"])


def _dashboard_payload(record: Dashboard) -> Dict[str, Any]:
    return record.to_dict()


@router.post("/datasets/{dataset_id}/dashboards", response_model=DashboardResponse)
def create_dashboard(
    dataset_id: int,
    payload: DashboardRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save a dashboard against the dataset's current version."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        version_record, _ = version_store.load_version_frame(
            db, dataset, payload.dataset_version
        )
    except (VersionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    record = Dashboard(
        dataset_id=dataset.id,
        dataset_version_id=version_record.id,
        name=payload.name,
        title=payload.title,
        config={"widgets": payload.widgets},
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _dashboard_payload(record)


@router.get("/datasets/{dataset_id}/dashboards", response_model=List[DashboardListItem])
def list_dashboards(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Every dashboard saved for one dataset."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    records = (
        db.query(Dashboard)
        .filter(Dashboard.dataset_id == dataset.id)
        .order_by(Dashboard.id.desc())
        .all()
    )
    return [_dashboard_payload(record) for record in records]


@router.get("/dashboards/{dashboard_id}", response_model=DashboardResponse)
def get_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One saved dashboard (ownership checked through the dataset)."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )
    return _dashboard_payload(record)


@router.put("/dashboards/{dashboard_id}", response_model=DashboardResponse)
def update_dashboard(
    dashboard_id: int,
    payload: DashboardUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Rename, retitle or replace the widget layout of a saved dashboard."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )
    if payload.name is not None:
        record.name = payload.name
    if payload.title is not None:
        record.title = payload.title or None
    if payload.widgets is not None:
        current = dict(record.config or {})
        current["widgets"] = payload.widgets
        record.config = current
    db.commit()
    db.refresh(record)
    return _dashboard_payload(record)


@router.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Remove a dashboard. The analyses and charts it referenced stay intact."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )
    db.delete(record)
    db.commit()