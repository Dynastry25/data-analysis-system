"""MVP-22 endpoints: analysis templates for common org questions (plan 3.3).

    GET  /templates                                  the catalog
    POST /datasets/{id}/templates/{key}/run          run one, in order

A template is a translation: a question a reader already has, into
the variables and the analyses that answer it. The engine is
unchanged -- each step is an ordinary analysis with ordinary
parameters -- so a template result carries the same assumption
checks, guardrails and interpretation as a hand-built one, and the
response shows the parameters each step resolved to.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, User
from app.services.data_service import profile_columns
from app.statflow import planning, templates as template_engine
from app.statflow.planning import PlanningError
from app.statflow.routers.analysis import _frame_for
from app.statflow.version_store import VersionError

router = APIRouter(prefix="/templates", tags=["statflow-v1-templates"])


@router.get("")
def list_templates(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """The question shapes the templates answer, and what each needs."""
    return {
        "templates": template_engine.catalog(),
        "note": (
            "Kila template inatumia engine ile ile ya takwimu: hakuna njia "
            "ya mkato. Variables zinapendekezwa kwa aina yao (semantic "
            "type), na wewe unachagua kabla ya kuendesha."
        ),
    }


@router.post("/datasets/{dataset_id}/{template_key}/run")
def run_template(
    dataset_id: int,
    template_key: str,
    payload: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run a template's analyses against the dataset's current version.

    The body is ``{"choices": {step_key: {variable_key: column}},
    "dataset_version": N}``; anything omitted is filled from the
    dataset's own types, and the response reports which columns that
    was, so a suggestion the reader did not make is never a decision
    they cannot see.
    """
    dataset = get_owned_dataset(dataset_id, db, user)
    payload = payload or {}
    choices = payload.get("choices") or {}
    version = payload.get("dataset_version")
    try:
        record, frame = _frame_for(db, dataset, version)
        profile = [
            {**entry, "semantic_type": planning.semantic_type(frame[entry["name"]])}
            for entry in profile_columns(frame)
        ]
        for entry in profile:
            entry.setdefault("non_null_count", entry.get("count", 0))
        result = template_engine.run_template(frame, template_key, choices, profile)
    except (PlanningError, VersionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # The runs go into the analysis history the same way the statistics
    # page and the assistant do, so a template result is reproducible
    # and shows up where the reader already looks for results.
    for step in result["steps"]:
        step_result = step.get("result") or {}
        db.add(
            AnalysisRun(
                dataset_id=dataset.id,
                dataset_version=int(record.version),
                dataset_version_id=record.id,
                analysis_type=str(step["analysis_type"]),
                status=str(step_result.get("status", "success")),
                parameters=step["parameters"],
                result=step_result,
            )
        )
    dataset.status = "analyzed"
    db.commit()

    result["dataset_id"] = dataset.id
    result["dataset_version"] = int(record.version)
    result["dataset_version_id"] = record.id
    return result
