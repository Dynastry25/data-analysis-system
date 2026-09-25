"""Pydantic request/response models (they also power the auto-generated /docs)."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.security import is_valid_email


# ---------------------------------------------------------------- Auth


class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: str = Field(..., max_length=150)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_must_be_valid(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if not is_valid_email(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def _name_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("full_name is required")
        return value


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    created_at: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return (value or "").strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ------------------------------------------------------------- Datasets


class ColumnProfile(BaseModel):
    name: str
    data_type: Optional[str] = None
    missing_count: int = 0
    unique_count: Optional[int] = None
    min: Any = None
    max: Any = None


class UploadResponse(BaseModel):
    dataset_id: int
    original_filename: str
    project_id: Optional[int] = None
    row_count: int
    column_count: int
    columns: List[ColumnProfile]
    status: str = "uploaded"


class DatasetSummary(BaseModel):
    id: int
    original_filename: str
    file_type: Optional[str] = None
    project_id: Optional[int] = None
    status: str
    uploaded_at: Optional[str] = None
    row_count: int = 0
    column_count: int = 0


class DatasetProjectRequest(BaseModel):
    """Move a dataset into a project, or back to personal with ``null``."""

    project_id: Optional[int]


class DatasetDetailResponse(BaseModel):
    dataset: Dict[str, Any]
    columns: List[ColumnProfile]
    preview_rows: List[Dict[str, Any]]


class ProfileResponse(BaseModel):
    dataset_id: int
    row_count: int
    column_count: int
    columns: List[ColumnProfile]


class MessageResponse(BaseModel):
    detail: str


# --------------------------------------------------------------- Charts

ChartType = Literal["bar", "line", "scatter", "histogram"]
AggregationType = Literal["sum", "mean", "count", "min", "max", "median"]


class ChartConfig(BaseModel):
    x: str
    y: Optional[str] = None
    group_by: Optional[str] = None
    aggregate: AggregationType = "sum"
    bins: Optional[int] = Field(default=None, ge=1, le=200)
    limit: Optional[int] = Field(default=5000, ge=1, le=50000)


class ChartRequest(BaseModel):
    chart_type: ChartType
    config: ChartConfig


class ChartResponse(BaseModel):
    chart_id: int
    dataset_id: int
    chart_type: str
    config: Dict[str, Any]
    chart_data: Dict[str, Any]
    created_at: Optional[str] = None


class ChartListItem(ChartResponse):
    pass


# --------------------------------------------------------------- Export

ExportFormat = Literal["pdf", "xlsx"]


class ExportRequest(BaseModel):
    format: ExportFormat
    include_analysis_ids: List[int] = Field(default_factory=list)
    include_chart_ids: List[int] = Field(default_factory=list)


class ExportResponse(BaseModel):
    report_id: int
    status: str


class ReportStatusResponse(BaseModel):
    report_id: int
    dataset_id: int
    file_format: str
    status: str
    error_message: Optional[str] = None
    download_url: str
    created_at: Optional[str] = None


# -------------------------------------------------------- Organizations


OrgRole = Literal["owner", "admin", "analyst", "viewer"]


class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)
    slug: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe identifier; auto-generated from the name if omitted",
    )

    @field_validator("name")
    @classmethod
    def _name_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name is required")
        return value


class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)


class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    my_role: Optional[OrgRole] = None
    member_count: int = 0
    project_count: int = 0


class OrganizationListItem(OrganizationResponse):
    pass


class MemberAddRequest(BaseModel):
    email: str = Field(..., max_length=150)
    role: OrgRole = "analyst"

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if not is_valid_email(value):
            raise ValueError("Enter a valid email address")
        return value


class MemberUpdateRequest(BaseModel):
    role: OrgRole


class MemberResponse(BaseModel):
    id: int
    organization_id: int
    user_id: int
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    joined_at: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name is required")
        return value


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    dataset_count: int = 0


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name is required")
        return value


class TeamUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)


class TeamResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    member_count: int = 0


class TeamMemberAddRequest(BaseModel):
    user_id: int


class TeamMemberResponse(BaseModel):
    id: int
    team_id: int
    user_id: int
    full_name: Optional[str] = None
    email: Optional[str] = None
    joined_at: Optional[str] = None

