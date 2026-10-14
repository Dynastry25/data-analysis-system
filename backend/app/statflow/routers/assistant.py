"""MVP-21 endpoint: the statistical assistant.

    POST /assistant/ask
    Question -> intent parser -> planner -> variable mapping -> method check
             -> analysis engine -> verified result -> explanation

The assistant plans and explains; it never computes statistics itself.
It is rule-based (keyword tables + planner), deterministic, and
hallucination-free by construction -- it cannot invent a number it
never computed. An optional language provider may rephrase a question
the tables do not understand (`app.statflow.assistant_language`), and
can never touch a statistic; with no provider configured the
assistant is exactly what it was before.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, User
from app.statflow import assistant, assistant_language, planning, stats_engine, version_store
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
        record, frame = version_store.load_version_frame(
            db, dataset, payload.dataset_version
        )
        answer = assistant.ask(
            frame,
            payload.question,
            outcome=payload.outcome,
            predictor=payload.predictor,
        )
    except (planning.PlanningError, stats_engine.AnalysisError, VersionError) as exc:
        raise _fail(exc)

    # Store the verified run so it shows up in the analysis history.
    result = answer.get("result")
    if result is not None and answer.get("plan", {}).get("method"):
        run = AnalysisRun(
            dataset_id=dataset.id,
            dataset_version=int(record.version),
            dataset_version_id=record.id,
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
    answer["dataset_version_id"] = record.id
    return answer


@router.get("/examples")
def examples(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Example questions the rule-based assistant understands, verified."""
    return {
        "examples": [
            question
            for question, _ in assistant.EXAMPLE_QUESTIONS
        ],
        "note": (
            "The assistant is rule-based: it reads the question with keyword tables, "
            "maps the mentioned variables onto the dataset columns, and lets the "
            "statistics engine compute every number. It is not an AI model, and every "
            "example above is verified to parse to the intent it is listed under."
        ),
    }


@router.get("/coverage")
def coverage(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """What the assistant understands, as a specification (plan 3b.3).

    Publishing the coverage turns the limitation into a contract: the
    intents, the variable words, and the question shapes the keyword
    tables do NOT handle, all read from the same tables the parser
    runs, so the list cannot drift from the behaviour. A reader who
    knows what to ask gets an answer; a reader who asks outside the
    list is told so instead of being guessed at.
    """
    return assistant_language.coverage()
