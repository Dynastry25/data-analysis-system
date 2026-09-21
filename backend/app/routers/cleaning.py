"""Cleaning endpoints: apply a cleaning action + read the audit trail."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import CleaningAction, User
from app.schemas import CleanRequest, CleanResponse, CleaningHistoryItem
from app.services.data_service import apply_cleaning_action, profile_columns

router = APIRouter(prefix="/datasets", tags=["cleaning"])


@router.post("/{dataset_id}/clean", response_model=CleanResponse)
def clean_dataset(
    dataset_id: int,
    payload: CleanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run one cleaning action on the stored file and record it in the audit trail."""
    from app.routers.datasets import sync_dataset_columns

    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        cleaned, applied = apply_cleaning_action(
            dataset.storage_path, payload.action_type, payload.parameters
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    profiles = profile_columns(cleaned)
    dataset.row_count = int(cleaned.shape[0])
    dataset.column_count = int(cleaned.shape[1])
    dataset.status = "cleaned"
    sync_dataset_columns(db, dataset, profiles)

    db.add(
        CleaningAction(
            dataset_id=dataset.id,
            action_type=payload.action_type,
            parameters={**(payload.parameters or {}), "applied": applied},
        )
    )
    db.commit()
    db.refresh(dataset)

    return {
        "dataset_id": dataset.id,
        "status": dataset.status,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "applied_action": applied,
    }


@router.get("/{dataset_id}/cleaning-history", response_model=List[CleaningHistoryItem])
def cleaning_history(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Audit trail: every cleaning action applied to this dataset."""
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    actions = (
        db.query(CleaningAction)
        .filter(CleaningAction.dataset_id == dataset.id)
        .order_by(CleaningAction.id.desc())
        .all()
    )
    return [action.to_dict() for action in actions]
