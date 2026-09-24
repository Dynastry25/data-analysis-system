"""Pydantic request models for the StatFlow v1 API."""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class OperationRequest(BaseModel):
    """POST /datasets/{id}/clean and /datasets/{id}/transform."""

    operation_type: str
    configuration: Dict[str, Any] = Field(default_factory=dict)
    dataset_version: Optional[int] = Field(
        default=None,
        description="Which version to start from (default: the latest version)",
    )
    label: Optional[str] = None


class AnalysisRequest(BaseModel):
    """POST /datasets/{id}/analysis (MVP-19 engine)."""

    analysis_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    dataset_version: Optional[int] = None
    save: bool = True


class ProfileRequest(BaseModel):
    dataset_id: int
    dataset_version: Optional[int] = None


class RecommendRequest(BaseModel):
    """POST /planning/recommend (MVP-20)."""

    dataset_id: int
    dataset_version: Optional[int] = None
    question: Optional[str] = None
    intent: Optional[Literal["difference", "association", "prediction", "distribution"]] = None
    outcome: Optional[str] = None
    predictor: Optional[str] = None
    method: Optional[str] = None
    run: bool = False


class AskRequest(BaseModel):
    """POST /assistant/ask (MVP-21)."""

    dataset_id: int
    question: str = Field(..., min_length=3)
    dataset_version: Optional[int] = None
