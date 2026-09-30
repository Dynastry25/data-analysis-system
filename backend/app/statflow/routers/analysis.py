"""MVP-19 endpoints: unified statistical analysis with the standard result."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, Dataset, User
from app.rbac import ORG_ROLE_VIEWER
from app.statflow import methods, stats_engine, version_store
from app.statflow.schemas import AnalysisRequest
from app.statflow.version_store import VersionError

router = APIRouter(tags=["statflow-v1-analysis"])


def _fail(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _frame_for(
    db: Session, dataset: Dataset, version: int | None
) -> Any:
    return version_store.load_version_frame(db, dataset, version)


@router.get("/analysis/types")
def analysis_types(user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Analyses the unified engine supports (+ the parameters each expects)."""
    return stats_engine.catalog()


@router.get("/analysis/methods")
def analysis_method_catalog(
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """The whole Methods of Analysis guide: categories, methods and stage plans.

    This is the reference the analysis studio reads. Every method carries its
    purpose, the dependent-variable type it suits, its assumptions, the outputs
    it must show, the alternatives to it, and the stage plan the guide says to
    follow when running it.
    """
    return methods.method_catalog()


@router.get("/analysis/methods/{method_key}")
def analysis_method_detail(
    method_key: str,
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One method with its full stage plan, or 404 when the key is unknown."""
    found = methods.method(method_key)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown method '{method_key}'",
        )
    found["stages"] = methods.stage_plan(found)
    return found


@router.post("/datasets/{dataset_id}/analysis")
def run_analysis_endpoint(
    dataset_id: int,
    payload: AnalysisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run one analysis on a dataset version and store the standard result."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        record, frame = _frame_for(db, dataset, payload.dataset_version)
        result = stats_engine.run_analysis(
            frame, payload.analysis_type, payload.parameters
        )
    except (stats_engine.AnalysisError, VersionError) as exc:
        raise _fail(exc)

    response: Dict[str, Any] = {
        "dataset_id": dataset.id,
        "dataset_version": int(record.version),
        "dataset_version_id": record.id,
        "analysis_type": payload.analysis_type,
        "status": result.get("status"),
        "result": result,
        "analysis_id": None,
    }
    if payload.save:
        run = AnalysisRun(
            dataset_id=dataset.id,
            dataset_version=int(record.version),
            dataset_version_id=record.id,
            analysis_type=payload.analysis_type,
            status=str(result.get("status")),
            parameters=payload.parameters or {},
            result=result,
        )
        db.add(run)
        dataset.status = "analyzed"
        db.commit()
        db.refresh(run)
        response["analysis_id"] = run.id
        response["created_at"] = run.created_at.isoformat() if run.created_at else None
    return response


@router.get("/datasets/{dataset_id}/analysis")
def list_analysis(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Every analysis run stored for a dataset."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.dataset_id == dataset.id)
        .order_by(AnalysisRun.id.desc())
        .all()
    )
    return [run.to_dict() for run in runs]


@router.get("/analysis/{analysis_id}")
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One stored analysis result (ownership checked via its dataset)."""
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    get_owned_dataset(
        run.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )
    return run.to_dict()
