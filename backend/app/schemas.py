"""Pydantic request/response models (they also power the auto-generated /docs)."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Lets the UI decide whether to offer an admin link, without an extra
    # request that would 403 for every ordinary user on every page. The server
    # still enforces every admin action independently of this field.
    system_role: Optional[str] = None


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
    # The question this column answers, as the file's author wrote it. None when
    # the source format carries no labels (CSV, Excel, Parquet) or the column is
    # unlabelled.
    variable_label: Optional[str] = None
    # code -> word, for a labelled categorical. None means "not a labelled
    # categorical", which is not the same as an empty mapping.
    value_labels: Optional[Dict[str, str]] = None


class UploadResponse(BaseModel):
    dataset_id: int
    original_filename: str
    project_id: Optional[int] = None
    row_count: int
    column_count: int
    columns: List[ColumnProfile]
    status: str = "uploaded"


class BatchUploadResult(BaseModel):
    """One file's outcome inside a batch."""

    status: str
    filename: str
    # Present when the file was read; absent when it failed.
    dataset_id: Optional[int] = None
    project_id: Optional[int] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    columns: List[ColumnProfile] = []
    # Why this file failed, when it did.
    detail: Optional[str] = None


class BatchUploadResponse(BaseModel):
    uploaded_count: int
    failed_count: int
    results: List[BatchUploadResult]


# ------------------------------------------------------------ Web scraping


class ScrapePreviewRequest(BaseModel):
    """A public http(s) page whose HTML tables the user wants to see."""

    url: str = Field(..., min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def _url_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("url is required")
        return value


class ScrapeTablePreview(BaseModel):
    """One table as it would become a dataset — enough to choose by."""

    index: int
    row_count: int
    column_count: int
    columns: List[str]
    preview_rows: List[Dict[str, Any]] = []


class ScrapePreviewResponse(BaseModel):
    url: str
    # Where the page actually ended up after redirects, so the UI can show the
    # real host when a short link resolves somewhere else.
    final_url: str
    title: Optional[str] = None
    table_count: int
    tables: List[ScrapeTablePreview]


class ScrapeImportRequest(BaseModel):
    """Import one previously previewed table as a dataset.

    ``table_index`` refers to the order ``/scrape/preview`` returned for the
    same URL; both endpoints derive it from the same deterministic parse, so no
    server-side cache has to sit between the two calls.
    """

    url: str = Field(..., min_length=8, max_length=2048)
    table_index: int = Field(..., ge=0)
    # Same semantics as a file upload's project_id: absent/null keeps the
    # dataset personal; present requires analyst+ in that project's org.
    project_id: Optional[int] = None
    # Optional display name; the backend always stores it as .csv.
    filename: Optional[str] = Field(None, max_length=200)

    @field_validator("url")
    @classmethod
    def _url_stripped(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("url is required")
        return value

    @field_validator("filename")
    @classmethod
    def _filename_optional(cls, value: Optional[str]) -> Optional[str]:
        value = (value or "").strip()
        return value or None


class DatasetSummary(BaseModel):
    id: int
    user_id: int
    original_filename: str
    file_type: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    status: str
    uploaded_at: Optional[str] = None
    row_count: int = 0
    column_count: int = 0
    current_version: Optional[int] = None


class DatasetProjectRequest(BaseModel):
    """Move a dataset into a project, or back to personal with ``null``."""

    project_id: Optional[int]


class DatasetDetailResponse(BaseModel):
    dataset: Dict[str, Any]
    dataset_version: int
    columns: List[ColumnProfile]
    preview_rows: List[Dict[str, Any]]


class ProfileResponse(BaseModel):
    dataset_id: int
    dataset_version: int
    row_count: int
    column_count: int
    columns: List[ColumnProfile]


class MessageResponse(BaseModel):
    detail: str


# --------------------------------------------------------------- Journey


# --------------------------------------------------------------- Validation


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    column: Optional[str] = None
    detail: Dict[str, Any] = {}


class ValidationResponse(BaseModel):
    """Deterministic data-quality findings for the Validate stage."""

    dataset_id: int
    dataset_version: int
    row_count: int
    column_count: int
    verdict: Literal["clean", "warnings", "blocked"]
    error_count: int
    warning_count: int
    info_count: int
    summary: str
    issues: List[ValidationIssue]


# --------------------------------------------------------------- Explore


class ExploreColumn(BaseModel):
    name: str
    data_type: Optional[str] = None
    kind: Literal["numeric", "categorical", "datetime", "text", "boolean"]
    missing_count: int
    missing_ratio: float
    unique_count: Optional[int] = None
    # Numeric only.
    min: Any = None
    max: Any = None
    mean: Any = None
    median: Any = None
    std: Any = None
    quantiles: Dict[str, Any] = {}
    # Categorical only.
    top_values: List[Dict[str, Any]] = []
    histogram: List[Dict[str, Any]] = []
    # From the source file, when it carried any. See ColumnProfile.
    variable_label: Optional[str] = None
    value_labels: Optional[Dict[str, str]] = None


class ExplorePair(BaseModel):
    x: str
    y: str
    method: Literal["pearson", "spearman"]
    coefficient: float
    strength: Literal["weak", "moderate", "strong"]
    interpretation: str


class ExploreResponse(BaseModel):
    """Shape of the data before choosing a statistical method."""

    dataset_id: int
    dataset_version: int
    row_count: int
    column_count: int
    columns: List[ExploreColumn]
    correlations: List[ExplorePair]
    warnings: List[str] = []


class JourneyStageResponse(BaseModel):
    """One stage's honest completion state, computed from stored records."""

    key: str
    step: int
    done: bool
    # None for a stage that leaves no record at all, so it can never be done.
    record_count: Optional[int] = None
    reason: str


class JourneyResponse(BaseModel):
    """Progress for the 11-stage journey, used by the shell on every page."""

    dataset_id: int
    dataset_status: str
    stages: List[JourneyStageResponse]

    @property
    def done_count(self) -> int:  # pragma: no cover - convenience only
        return sum(1 for stage in self.stages if stage.done)


# --------------------------------------------------------------- Charts

ChartType = Literal["bar", "line", "scatter", "histogram", "box", "pie", "heatmap"]
AggregationType = Literal["sum", "mean", "count", "min", "max", "median"]


PaletteName = Literal["default", "ocean", "sunset", "forest"]
AxisScale = Literal["linear", "log"]


class ChartFilterCondition(BaseModel):
    """One row-filter condition on a chart, mirroring ``op_filter``.

    Keeping this shape next to (not inside) the cleaning operation is
    deliberate: a chart filter draws from fewer rows without writing a new
    dataset version, so it shares the operators but lives on the chart.
    """

    column: str = Field(..., min_length=1)
    operator: str = Field(..., min_length=1)
    value: Any = None
    values: Optional[List[Any]] = None


class ChartFilter(BaseModel):
    conditions: List[ChartFilterCondition] = Field(default_factory=list)
    logic: Literal["and", "or"] = "and"


class ChartAnnotation(BaseModel):
    """A text note pinned to a data position on a chart.

    Coordinates are data values (not pixels): annotations travel with the data
    when the chart is re-rendered or exported.
    """

    text: str = Field(..., min_length=1, max_length=280)
    x: Any
    y: Any = None
    series: Optional[str] = None


class ChartFormat(BaseModel):
    """Presentation choices saved with a chart (Visualization Studio)."""

    palette: Optional[PaletteName] = None
    show_data_labels: Optional[bool] = None
    show_grid: Optional[bool] = None
    x_scale: Optional[AxisScale] = None
    y_scale: Optional[AxisScale] = None


class ChartConfig(BaseModel):
    x: str
    y: Optional[str] = None
    group_by: Optional[str] = None
    aggregate: AggregationType = "sum"
    bins: Optional[int] = Field(default=None, ge=1, le=200)
    limit: Optional[int] = Field(default=5000, ge=1, le=50000)
    format: Optional[ChartFormat] = None
    # --- Visualization Studio: channel encodings --------------------------
    # All optional: an old config without them draws exactly like before.
    # color_by colours points (scatter), splits distributions (box) or shares
    # of a part-to-whole (pie) by a categorical column; size_by scales scatter
    # markers by a numeric column; facet_by draws one panel per column value.
    color_by: Optional[str] = None
    size_by: Optional[str] = None
    facet_by: Optional[str] = None
    # A chart-level filter (same operators as the Filter operation): the chart
    # draws from fewer rows without writing a new dataset version.
    filters: Optional[ChartFilter] = None
    # Text notes pinned to data positions (kept separate from the pixel grid).
    annotations: List[ChartAnnotation] = Field(default_factory=list)


class ChartRequest(BaseModel):
    chart_type: ChartType
    config: ChartConfig
    dataset_version: Optional[int] = None


class ChartResponse(BaseModel):
    chart_id: int
    dataset_id: int
    dataset_version: Optional[int] = None
    chart_type: str
    config: Dict[str, Any]
    chart_data: Dict[str, Any]
    created_at: Optional[str] = None


class ChartListItem(ChartResponse):
    pass


# --------------------------------------------------------------- Dashboards

DashboardWidgetType = Literal["kpi", "chart", "filter", "insight", "text"]

WIDGET_TYPES_FOR_ERROR = "kpi, chart, filter, insight, text"


def _validate_dashboard_widgets(widgets: List[Dict[str, Any]]) -> None:
    """Keep a dashboard honest: every widget has a known type and a stable id.

    The ``config`` JSON lives in the database, so a malformed dashboard could be
    saved once and then break every render. Validating here means a dashboard is
    either well-formed or rejected at save time — never silently dropped later.
    """
    for index, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            raise ValueError(f"Widget {index} must be an object")
        widget_id = widget.get("id")
        if not isinstance(widget_id, str) or not widget_id.strip():
            raise ValueError(f"Widget {index} needs a stable string id")
        widget_type = widget.get("type")
        if widget_type not in WIDGET_TYPES_FOR_ERROR.split(", "):
            raise ValueError(
                f"Widget {widget_id} has unknown type '{widget_type}'. "
                f"Allowed: {WIDGET_TYPES_FOR_ERROR}."
            )
        if widget_type == "chart" and not isinstance(widget.get("chart_id"), int):
            raise ValueError(f"Chart widget {widget_id} needs a chart_id")
        if widget_type == "kpi" and widget.get("source") is None:
            raise ValueError(f"KPI widget {widget_id} needs a source")


class DashboardRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: Optional[str] = Field(default=None, max_length=200)
    widgets: List[Dict[str, Any]] = Field(default_factory=list)
    dataset_version: Optional[int] = None

    @field_validator("widgets")
    @classmethod
    def _widgets_must_be_valid(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        _validate_dashboard_widgets(value)
        return value


class DashboardUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    title: Optional[str] = Field(default=None, max_length=200)
    widgets: Optional[List[Dict[str, Any]]] = Field(default=None)

    @field_validator("widgets")
    @classmethod
    def _widgets_must_be_valid_optional(
        cls, value: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        if value is not None:
            _validate_dashboard_widgets(value)
        return value


class DashboardResponse(BaseModel):
    dashboard_id: int
    dataset_id: int
    dataset_version: Optional[int] = None
    dataset_version_id: Optional[int] = None
    name: str
    title: Optional[str] = None
    config: Dict[str, Any]
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DashboardListItem(DashboardResponse):
    pass


# --------------------------------------------------------------- Dashboard Collaboration

DashboardShareRole = Literal["viewer", "editor", "admin"]


class DashboardShareCreate(BaseModel):
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    role: DashboardShareRole = "viewer"
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _check_target(self) -> "DashboardShareCreate":
        if self.user_id is None and self.organization_id is None:
            raise ValueError("Either user_id or organization_id must be provided")
        if self.user_id is not None and self.organization_id is not None:
            raise ValueError("Provide either user_id or organization_id, not both")
        return self


class DashboardShareUpdate(BaseModel):
    role: Optional[DashboardShareRole] = None
    expires_at: Optional[datetime] = None


class DashboardShareResponse(BaseModel):
    id: int
    dashboard_id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    role: DashboardShareRole
    created_by: Optional[int] = None
    created_by_email: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


class DashboardCommentCreate(BaseModel):
    widget_id: Optional[str] = None
    parent_id: Optional[int] = None
    content: str = Field(min_length=1, max_length=5000)


class DashboardCommentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class DashboardCommentResponse(BaseModel):
    id: int
    dashboard_id: int
    widget_id: Optional[str] = None
    user_id: int
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    parent_id: Optional[int] = None
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    replies: List["DashboardCommentResponse"] = Field(default_factory=list)


DashboardCommentResponse.model_rebuild()


# --------------------------------------------------------------- Job Queue (Feature 25)

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
JobType = Literal["analysis", "report_export", "dataset_clean", "dataset_transform", "chart_render", "ml_training"]


class JobCreate(BaseModel):
    job_type: JobType
    dataset_id: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class JobResponse(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    dataset_id: Optional[int] = None
    job_type: JobType
    status: JobStatus
    progress: int
    payload: Dict[str, Any]
    result: Dict[str, Any]
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None


class JobListResponse(BaseModel):
    items: List[JobResponse]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------- Export

ExportFormat = Literal["pdf", "xlsx", "docx", "pptx", "html"]


class ExportRequest(BaseModel):
    format: ExportFormat
    dataset_version: Optional[int] = None
    include_analysis_ids: List[int] = Field(default_factory=list)
    include_chart_ids: List[int] = Field(default_factory=list)


class ExportResponse(BaseModel):
    report_id: int
    status: str


class ReportStatusResponse(BaseModel):
    report_id: int
    dataset_id: int
    dataset_version: Optional[int] = None
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



# ---------------------------------------------------------------- Admin portal


class AdminUserListItem(BaseModel):
    id: int
    full_name: str
    email: str
    system_role: Optional[str] = None
    status: str
    is_suspended: bool
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None
    suspended_reason: Optional[str] = None
    organization_count: int = 0
    dataset_count: int = 0
    analysis_count: int = 0


class AdminUserListResponse(BaseModel):
    items: List[AdminUserListItem]
    total: int
    page: int
    page_size: int


class AdminUserUpdateRequest(BaseModel):
    """Admin edit of an account. Every field is optional; send only what changes."""

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    system_role: Optional[Literal["super_admin", "platform_admin", "admin_viewer"]] = None
    status: Optional[Literal["active", "suspended"]] = None
    suspended_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("full_name")
    @classmethod
    def _name_stripped(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be empty")
        return value

    @model_validator(mode="after")
    def _null_only_where_allowed(self) -> "AdminUserUpdateRequest":
        """Distinguish "not supplied" from "supplied as null".

        Revoking a platform role is a real operation and arrives as an explicit
        null, so null cannot simply be dropped. Only ``system_role`` accepts it;
        every other field would violate its column constraint, so an explicit
        null is rejected here instead of failing later as a database error.
        """
        provided = self.model_fields_set
        for name in ("full_name", "status", "suspended_reason"):
            if name in provided and getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be set to null")
        return self

    def changes(self) -> Dict[str, Any]:
        """Only the fields actually present in the request body.

        ``exclude_unset`` is what makes an explicit null survive, which is how a
        role is revoked rather than merely left alone.
        """
        return dict(self.model_dump(exclude_unset=True))


class AdminOverviewResponse(BaseModel):
    """Headline numbers for the admin dashboard (F.2 / spec 26)."""

    total_users: int
    active_users: int
    suspended_users: int
    active_last_7_days: int
    platform_staff: int
    organizations: int
    datasets: int
    analyses: int
    total_rows_profiled: int
    storage_bytes: int
    pending_reports: int
    failed_reports: int
    audit_events_last_24h: int
    denied_last_24h: int


class AdminAlert(BaseModel):
    """Right-side operational alerts on the admin dashboard (spec 26)."""

    level: Literal["danger", "warning", "info"]
    title: str
    detail: str
    action: Optional[str] = None


class AdminOverviewAlerts(BaseModel):
    alerts: List[AdminAlert]


class AdminOrganizationListItem(BaseModel):
    id: int
    name: str
    slug: str
    created_at: Optional[str] = None
    member_count: int = 0
    project_count: int = 0
    dataset_count: int = 0
    analysis_count: int = 0


class AdminOrganizationListResponse(BaseModel):
    items: List[AdminOrganizationListItem]
    total: int


class AdminDatasetListItem(BaseModel):
    id: int
    original_filename: str
    file_type: str
    status: str
    row_count: int
    column_count: int
    created_at: Optional[str] = None
    owner_email: Optional[str] = None
    owner_id: Optional[int] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    latest_version: Optional[int] = None


class AdminDatasetListResponse(BaseModel):
    items: List[AdminDatasetListItem]
    total: int


class AdminAuditListItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    actor_email: Optional[str] = None
    organization_id: Optional[int] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    result: str
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: Optional[str] = None


class AdminAuditListResponse(BaseModel):
    items: List[AdminAuditListItem]
    total: int
    page: int
    page_size: int


class AdminActionResponse(BaseModel):
    ok: bool = True
    message: str


class AdminMeResponse(BaseModel):
    """The caller's own platform identity.

    Deliberately a field rather than prose: a client that has to read the role
    out of a message string will eventually get it wrong.
    """

    id: int
    email: str
    system_role: str
    status: str