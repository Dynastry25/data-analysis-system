"""Analysis endpoints: run a statistical analysis + read past results."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisResult, Dataset, User
from app.schemas import AnalyzeRequest, AnalyzeResponse, AnalysisListItem
from app.services.analysis_service import run_analysis
from app.services.data_service import read_dataframe

router = APIRouter(tags=["analysis"])


@router.post("/datasets/{dataset_id}/analyze", response_model=AnalyzeResponse)
def run_analysis_endpoint(
    dataset_id: int,
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run descriptive stats / correlation / regression / hypothesis test."""
    dataset = get_owned_dataset(dataset_id, db, user)
    frame = read_dataframe(dataset.storage_path)

    try:
        result_data = run_analysis(frame, payload.analysis_type, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    record = AnalysisResult(
        dataset_id=dataset.id,
        analysis_type=payload.analysis_type,
        result_data={**result_data, "parameters": payload.parameters or {}},
    )
    db.add(record)
    dataset.status = "analyzed"
    db.commit()
    db.refresh(record)

    return {
        "analysis_id": record.id,
        "dataset_id": dataset.id,
        "analysis_type": record.analysis_type,
        "parameters": payload.parameters or {},
        "result_data": record.result_data,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/datasets/{dataset_id}/analysis", response_model=List[AnalysisListItem])
def list_analysis(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """All saved analysis results for one dataset."""
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    records = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.dataset_id == dataset.id)
        .order_by(AnalysisResult.id.desc())
        .all()
    )
    return [
        {
            "analysis_id": record.id,
            "dataset_id": record.dataset_id,
            "analysis_type": record.analysis_type,
            "parameters": (record.result_data or {}).get("parameters", {}),
            "result_data": record.result_data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record in records
    ]


@router.get("/analysis/{analysis_id}", response_model=AnalyzeResponse)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One saved analysis result (ownership checked through its dataset)."""
    record = db.get(AnalysisResult, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis result not found")
    dataset = db.get(Dataset, record.dataset_id)
    if dataset is None or dataset.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="You do not have access to this analysis result"
        )
    return {
        "analysis_id": record.id,
        "dataset_id": record.dataset_id,
        "analysis_type": record.analysis_type,
        "parameters": (record.result_data or {}).get("parameters", {}),
        "result_data": record.result_data,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
