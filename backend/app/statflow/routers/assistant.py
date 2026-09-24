"""MVP-21 endpoint: the statistical assistant.

    POST /assistant/ask
    Question -> intent parser -> planner -> variable mapping -> method check
             -> analysis engine -> verified result -> explanation

The assistant plans and explains; it never computes statistics itself.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, User
from app.statflow import assistant, planning, version_store
from app.statflow.schemas import AskRequest
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/assistant", tags=["statflow-v1-assistant"])


def _fail(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/ask")
def ask_endpoint(
    payload: AskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Answer a plain-language question with a verified statistical result."""
    dataset = get_owned_dataset(payload.dataset_id, db, user)
    try:
        version_store.ensure_base_version(db, dataset)
        record = version_store.get_version(db, dataset, payload.dataset_version)
        frame = version_store.read_version_file(record)
        answer = assistant.ask(frame, payload.question)
    except (planning.PlanningError, VersionError) as exc:
        raise _fail(exc)

    # Store the verified run so it shows up in the analysis history.
    result = answer.get("result")
    if result is not None and answer.get("plan", {}).get("method"):
        run = AnalysisRun(
            dataset_id=dataset.id,
            dataset_version=int(record.version),
            analysis_type=str(answer["plan"]["method"]),
            status=str(result.get("status")),
            parameters=answer["plan"].get("parameters") or {},
            result=result,
        )
        db.add(run)
        dataset.status = "analyzed"
        db.commit()
        db.refresh(run)
        answer["analysis_id"] = run.id

    answer["dataset_id"] = dataset.id
    answer["dataset_version"] = int(record.version)
    return answer


@router.get("/examples")
def examples(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Example questions the rule-based assistant understands."""
    return {
        "examples": [
            "Does income differ between male and female?",
            "Je, mauzo yanatofautiana kati ya mikoa?",
            "What is the relationship between price and sales?",
            "Can we predict sales from price?",
            "Describe the age distribution.",
            "Je, kuna uhusiano kati ya jinsia na malipo?",
        ],
        "note": "The assistant detects the intent (difference/association/prediction/"
        "distribution) and maps the mentioned variables onto the dataset columns.",
    }
