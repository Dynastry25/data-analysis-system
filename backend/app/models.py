"""SQLAlchemy models for the Data Analysis Platform MVP.

Mirrors schema.sql (7 related tables). JSONB columns from the PostgreSQL schema are
mapped with the portable ``JSON`` type so the same models work on SQLite (dev) and
PostgreSQL (production).

Phase 1 (organizations, projects, RBAC) adds the ``organizations``,
``organization_members`` and ``projects`` tables. A dataset is optionally placed
inside a project (``datasets.project_id``); datasets without a project stay
personally owned by the uploading user, keeping the MVP behaviour intact.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now (``datetime.utcnow`` is deprecated in Python 3.14)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Org RBAC


ORG_ROLE_OWNER = "owner"
ORG_ROLE_ADMIN = "admin"
ORG_ROLE_ANALYST = "analyst"
ORG_ROLE_VIEWER = "viewer"

# owner > admin > analyst > viewer. Higher wins; comparisons use ``>=``.
ORG_ROLES = (ORG_ROLE_OWNER, ORG_ROLE_ADMIN, ORG_ROLE_ANALYST, ORG_ROLE_VIEWER)
ORG_ROLE_LEVEL = {ORG_ROLE_OWNER: 4, ORG_ROLE_ADMIN: 3, ORG_ROLE_ANALYST: 2, ORG_ROLE_VIEWER: 1}


# --------------------------------------------------------- Platform RBAC

# A separate ladder from the org roles above: these answer "what may this
# person do across every organization?". An org ``admin`` is NOT a platform
# admin, so the two ladders never share a constant or a lookup table.

PLATFORM_ROLE_SUPER_ADMIN = "super_admin"
PLATFORM_ROLE_ADMIN = "platform_admin"
PLATFORM_ROLE_VIEWER = "admin_viewer"

# super_admin > platform_admin > admin_viewer. Higher wins; comparisons use ``>=``.
PLATFORM_ROLES = (
    PLATFORM_ROLE_SUPER_ADMIN,
    PLATFORM_ROLE_ADMIN,
    PLATFORM_ROLE_VIEWER,
)
PLATFORM_ROLE_LEVEL = {
    PLATFORM_ROLE_SUPER_ADMIN: 4,
    PLATFORM_ROLE_ADMIN: 3,
    PLATFORM_ROLE_VIEWER: 1,
}

# Account lifecycle, independent of the organization role a member holds.
USER_STATUS_ACTIVE = "active"
USER_STATUS_SUSPENDED = "suspended"
USER_STATUSES = (USER_STATUS_ACTIVE, USER_STATUS_SUSPENDED)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=utcnow)

    members = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="OrganizationMember.id",
    )
    projects = relationship(
        "Project",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="Project.id",
    )
    teams = relationship(
        "Team",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="Team.id",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OrganizationMember(Base):
    """Membership of a user in an organization + their RBAC role."""

    __tablename__ = "organization_members"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False, default=ORG_ROLE_ANALYST)
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "full_name": self.user.full_name if self.user else None,
            "email": self.user.email if self.user else None,
            "role": self.role,
            "joined_at": self.created_at.isoformat() if self.created_at else None,
        }


class Project(Base):
    """A work container inside an organization (Phase 1 / master prompt)."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="projects")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_project_org_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Team(Base):
    """A work unit inside an organization (Phase 1 / master prompt).

    Teams group org members for shared delivery; org roles continue to rule
    overall access, so a team has no separate permission level.
    """

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="teams")
    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="TeamMember.id",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_team_org_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TeamMember(Base):
    """Membership of an org member in a team."""

    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=utcnow)

    team = relationship("Team", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "full_name": self.user.full_name if self.user else None,
            "email": self.user.email if self.user else None,
            "joined_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    # Admin portal. ``system_role`` is platform-wide authority and is NULL for
    # ordinary users, so membership of an org admin role never grants it.
    system_role = Column(String(20), nullable=True, index=True)
    status = Column(String(20), nullable=False, default=USER_STATUS_ACTIVE, index=True)
    suspended_at = Column(DateTime, nullable=True)
    suspended_reason = Column(String(500), nullable=True)
    last_active_at = Column(DateTime, nullable=True)

    datasets = relationship(
        "Dataset", back_populates="user", cascade="all, delete-orphan"
    )
    reports = relationship(
        "ExportedReport", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_suspended(self) -> bool:
        return self.status == USER_STATUS_SUSPENDED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_admin_dict(self) -> dict:
        """Wider view for the admin portal only; never expose the password hash."""
        return {
            **self.to_dict(),
            "system_role": self.system_role,
            "status": self.status,
            "is_suspended": self.is_suspended,
            "suspended_at": self.suspended_at.isoformat() if self.suspended_at else None,
            "suspended_reason": self.suspended_reason,
            "last_active_at": (
                self.last_active_at.isoformat() if self.last_active_at else None
            ),
        }


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False, default="")
    file_type = Column(String(20), nullable=False)  # csv, xlsx, dta, sav, rdata, ...
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    status = Column(String(20), default="uploaded")  # uploaded, cleaned, analyzed
    uploaded_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="datasets")
    columns = relationship(
        "DatasetColumn",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetColumn.id",
    )
    charts = relationship(
        "Chart",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="Chart.id",
    )
    dashboards = relationship(
        "Dashboard",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="Dashboard.id",
    )
    reports = relationship(
        "ExportedReport", back_populates="dataset", cascade="all, delete-orphan"
    )
    versions = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version",
    )
    operations = relationship(
        "DatasetOperation",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetOperation.sequence",
    )
    analysis_runs = relationship(
        "AnalysisRun",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="AnalysisRun.id",
    )
    project = relationship("Project")

    def to_summary_dict(self) -> dict:
        current_version = max(
            (item.version for item in self.versions), default=None
        )
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "project_name": self.project.name if self.project else None,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "status": self.status,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "current_version": current_version,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name = Column(String(150), nullable=False)
    data_type = Column(String(30))  # numeric, text, date, boolean
    missing_count = Column(Integer, default=0)
    unique_count = Column(Integer)

    # The question this column answers, as the file's author wrote it
    # ("Sex of respondent"). Only Stata and SPSS carry this; it is NULL for
    # every other format and for an unlabelled column, which is the honest
    # answer rather than a synthesised one.
    variable_label = Column(String(500), nullable=True)

    # The code -> word lookup for a labelled categorical, as a JSON object of
    # strings on both sides so the same shape serves Stata (int codes) and
    # SPSS (float codes). NULL means "not a labelled categorical", which is
    # different from an empty object.
    value_labels = Column(JSON, nullable=True)

    dataset = relationship("Dataset", back_populates="columns")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.column_name,
            "column_name": self.column_name,
            "data_type": self.data_type,
            "missing_count": self.missing_count or 0,
            "unique_count": self.unique_count,
        }


class Chart(Base):
    __tablename__ = "charts"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chart_type = Column(String(30), nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="charts")
    dataset_version_record = relationship("DatasetVersion")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_version": (
                self.dataset_version_record.version
                if self.dataset_version_record is not None
                else None
            ),
            "dataset_version_id": self.dataset_version_id,
            "chart_type": self.chart_type,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Dashboard(Base):
    """A saved dashboard: a named grid of widgets pinned to a data version.

    A dashboard, like a chart, is an arrangement (``config``) over data that
    already exists — saved analyses and charts, column summaries, filters and
    free-text notes. It records *which* sources it points at, never a copy of
    the numbers, so the dashboard can be re-rendered and the reproducibility
    trail stays with the underlying analysis runs and charts.

    Widgets are stored as a JSON array inside ``config["widgets"]`` so adding a
    widget type never requires a migration. Each widget carries its ``id``
    (stable across saves), a ``type`` and widget-specific fields; unknown types
    are rejected at save time so an old dashboard can never be silently dropped.
    """

    __tablename__ = "dashboards"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(120), nullable=False, default="Dashboard")
    title = Column(String(200), nullable=True)
    config = Column(JSON, nullable=False)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    dataset = relationship("Dataset", back_populates="dashboards")
    dataset_version_record = relationship("DatasetVersion")

    def to_dict(self) -> dict:
        return {
            "dashboard_id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_version": (
                self.dataset_version_record.version
                if self.dataset_version_record is not None
                else None
            ),
            "dataset_version_id": self.dataset_version_id,
            "name": self.name,
            "title": self.title,
            "config": self.config or {},
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DatasetVersion(Base):
    """An immutable snapshot of a dataset (v1 = the uploaded file, then v2, v3 ...).

    Every cleaning/transformation operation writes a *new* version file, so the
    original data is never destroyed and any analysis can be reproduced against the
    exact version it used.
    """

    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)  # 1, 2, 3 ...
    parent_version = Column(Integer, nullable=True)
    storage_path = Column(String(500), nullable=False)
    file_format = Column(String(20), nullable=False, default="parquet")
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    is_current = Column(Integer, default=1)  # 1 for the newest version
    label = Column(String(255), nullable=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="versions")
    operations = relationship(
        "DatasetOperation",
        back_populates="resulting_version",
        cascade="all, delete-orphan",
        order_by="DatasetOperation.sequence",
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
    )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "dataset_id": self.dataset_id,
            "parent_version": self.parent_version,
            "file_format": self.file_format,
            "row_count": self.row_count or 0,
            "column_count": self.column_count or 0,
            "is_current": bool(self.is_current),
            "label": self.label,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatasetOperation(Base):
    """Audit trail entry: one cleaning/transformation step that produced a version."""

    __tablename__ = "dataset_operations"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)  # 1, 2, 3 ... within the dataset
    operation_group = Column(String(20), nullable=False)  # clean | transform
    operation_type = Column(String(50), nullable=False)
    configuration = Column(JSON, nullable=False)
    source_version = Column(Integer, nullable=False)
    result_version = Column(Integer, nullable=False)
    summary = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="operations")
    resulting_version = relationship("DatasetVersion", back_populates="operations")

    def to_dict(self) -> dict:
        """Matches the documented history shape: version / type / configuration."""
        return {
            "sequence": self.sequence,
            "version": self.result_version,
            "type": self.operation_type,
            "group": self.operation_group,
            "configuration": self.configuration or {},
            "source_version": self.source_version,
            "summary": self.summary or {},
            "warnings": self.warnings or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisRun(Base):
    """A statistical analysis executed against one dataset version (MVP-19 engine)."""

    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version = Column(Integer, nullable=False)
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="success")
    parameters = Column(JSON, nullable=True)
    result = Column(JSON, nullable=False)  # the standard result structure
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="analysis_runs")
    dataset_version_record = relationship("DatasetVersion")

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_version_id": self.dataset_version_id,
            "analysis_type": self.analysis_type,
            "status": self.status,
            "parameters": self.parameters or {},
            "result": self.result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExportedReport(Base):
    __tablename__ = "exported_reports"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_format = Column(String(10), nullable=False)  # pdf, xlsx
    storage_path = Column(String(500), nullable=False, default="")
    # Additions to schema.sql: an async export needs a status + error trail.
    status = Column(String(20), default="processing")  # processing|completed|failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="reports")
    dataset_version_record = relationship("DatasetVersion")
    user = relationship("User", back_populates="reports")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_version": (
                self.dataset_version_record.version
                if self.dataset_version_record is not None
                else None
            ),
            "dataset_version_id": self.dataset_version_id,
            "user_id": self.user_id,
            "file_format": self.file_format,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



# ---------------------------------------------------------------- Audit log


class AuditLog(Base):
    """Immutable record of a security-relevant action (master prompt 29 / F.10).

    Separate from ``data_operations``, which tracks dataset cleaning steps: this
    table answers "who touched whose account and what did it change", including
    the platform admin actions that have no dataset behind them.

    Rows are written append-only. There is no update helper and the admin API
    exposes reads only, so an entry cannot be edited from the normal UI.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)

    # NULL actor: a failed login belongs to someone who is not authenticated,
    # and the record of the attempt is exactly the thing worth keeping.
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email = Column(String(150), nullable=True)

    action = Column(String(60), nullable=False, index=True)
    resource = Column(String(60), nullable=True, index=True)
    resource_id = Column(String(80), nullable=True)
    result = Column(String(20), nullable=False, default="success", index=True)
    ip_address = Column(String(45), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    user = relationship("User")
    organization = relationship("Organization")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "actor_email": self.actor_email or (
                self.user.email if self.user is not None else None
            ),
            "organization_id": self.organization_id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "result": self.result,
            "ip_address": self.ip_address,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }