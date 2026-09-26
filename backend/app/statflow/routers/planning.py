"""MVP-20 endpoints: profile (variable detection) + recommend (validation)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, User
from app.rbac import ORG_ROLE_ANALYST, ORG_ROLE_VIEWER
from app.statflow import planning, stats_engine, version_store
from app.statflow.schemas import ProfileRequest, RecommendRequest
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/planning", tags=["statflow-v1-planning"])


def _fail(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _frame_for(
    db: Session,
    user: User,
    dataset_id: int,
    version: int | None,
    min_role: str,
) -> Any:
    dataset = get_owned_dataset(dataset_id, db, user, min_role=min_role)
    record, frame = version_store.load_version_frame(db, dataset, version)
    return dataset, record, frame


@router.post("/profile")
def profile_endpoint(
    payload: ProfileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Detect variables, semantic types and dataset-level diagnostics."""
    try:
        dataset, record, frame = _frame_for(
            db,
            user,
            payload.dataset_id,
            payload.dataset_version,
            ORG_ROLE_VIEWER,
        )
    except VersionError as exc:
        raise _fail(exc)
    result = planning.profile_dataset(frame)
    result["meta"]["dataset_id"] = dataset.id
    result["meta"]["dataset_version"] = int(record.version)
    return result


@router.post("/recommend")
def recommend_endpoint(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Candidate methods + diagnostics + a statistical recommendation.

    Pass ``run: true`` to execute the recommended analysis immediately
    (the result is the engine's verified standard result, stored as a run).
    """
    try:
        dataset, record, frame = _frame_for(
            db,
            user,
            payload.dataset_id,
            payload.dataset_version,
            ORG_ROLE_ANALYST if payload.run else ORG_ROLE_VIEWER,
        )
        recommendation = planning.recommend(
            frame,
            {
                "question": payload.question,
                "intent": payload.intent,
                "outcome": payload.outcome,
                "predictor": payload.predictor,
                "method": payload.method,
                "run": payload.run,
            },
        )
    except (planning.PlanningError, stats_engine.AnalysisError, VersionError) as exc:
        raise _fail(exc)

    recommendation["meta"]["dataset_id"] = dataset.id
    recommendation["meta"]["dataset_version"] = int(record.version)

    if payload.run and recommendation.get("result") is not None:
        run = AnalysisRun(
            dataset_id=dataset.id,
            dataset_version=int(record.version),
            dataset_version_id=record.id,
            analysis_type=recommendation["recommendation"]["analysis_type"],
            status=str(recommendation["result"].get("status")),
            parameters=recommendation["recommendation"]["parameters"],
            result=recommendation["result"],
        )
        db.add(run)
        dataset.status = "analyzed"
        db.commit()
        db.refresh(run)
        recommendation["analysis_id"] = run.id

    return recommendation
