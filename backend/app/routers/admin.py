"""Admin portal API (master prompt 31 / F.1-F.14).

Mounted at ``/api/v1/admin``. Three properties are load-bearing and are enforced
here rather than in the UI:

* every route passes through :mod:`app.platform_rbac`, which uses the platform
  ladder (``super_admin`` > ``platform_admin`` > ``admin_viewer``). Holding an
  organization ``admin`` role grants nothing here;
* reads of operational data are separated from writes, so ``admin_viewer`` can
  never mutate an account;
* every state-changing action appends an :class:`~app.models.AuditLog` row.

The portal may *observe* other organizations' operational metadata (size, row
count, status, owner). It deliberately does not expose dataset contents, so
becoming an administrator is not a route to reading other people's data: that
isolation guarantee is the master prompt's section 34.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    PLATFORM_ROLE_ADMIN,
    PLATFORM_ROLE_LEVEL,
    PLATFORM_ROLE_SUPER_ADMIN,
    PLATFORM_ROLE_VIEWER,
    USER_STATUS_ACTIVE,
    USER_STATUS_SUSPENDED,
    AnalysisRun,
    AuditLog,
    Dataset,
    DatasetVersion,
    ExportedReport,
    Organization,
    OrganizationMember,
    Project,
    User,
)
from app.platform_rbac import (
    assert_not_last_super_admin,
    assert_not_self,
    require_platform_role,
    require_super_admin,
)
from app.schemas import (
    AdminActionResponse,
    AdminAlert,
    AdminAuditListItem,
    AdminAuditListResponse,
    AdminDatasetListItem,
    AdminDatasetListResponse,
    AdminOrganizationListItem,
    AdminOrganizationListResponse,
    AdminOverviewAlerts,
    AdminOverviewResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)

router = APIRouter()

REPORT_STATUS_PENDING = "processing"
REPORT_STATUS_FAILED = "failed"


def _count(db: Session, column) -> int:
    return int(db.execute(select(func.count(column))).scalar() or 0)


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    """Clamp pagination so a caller cannot ask the database for every row."""
    return max(1, page), min(100, max(1, page_size))


def _storage_bytes(db: Session) -> int:
    """Total bytes of stored dataset files.

    Measured from the real files rather than a cached counter, because a
    cached total that silently disagrees with the disk is worse than no total
    at all. Missing files are skipped instead of raising, so one deleted upload
    does not blank out the whole metric.
    """
    total = 0
    for (path,) in db.execute(
        select(DatasetVersion.storage_path).where(
            DatasetVersion.storage_path.isnot(None)
        )
    ).all():
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    for (path,) in db.execute(
        select(Dataset.storage_path).where(Dataset.storage_path.isnot(None))
    ).all():
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total


# ---------------------------------------------------------------- Overview


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminOverviewResponse:
    """Headline platform numbers (F.2). Readable by any platform role."""
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(days=1)

    total_users = _count(db, User.id)
    active_users = int(
        db.execute(
            select(func.count(User.id)).where(User.status == USER_STATUS_ACTIVE)
        ).scalar()
        or 0
    )
    suspended_users = int(
        db.execute(
            select(func.count(User.id)).where(User.status == USER_STATUS_SUSPENDED)
        ).scalar()
        or 0
    )
    recent_users = int(
        db.execute(
            select(func.count(User.id)).where(User.last_active_at >= week_ago)
        ).scalar()
        or 0
    )
    staff = int(
        db.execute(
            select(func.count(User.id)).where(
                User.system_role.in_(list(PLATFORM_ROLE_LEVEL.keys()))
            )
        ).scalar()
        or 0
    )
    organizations = _count(db, Organization.id)
    datasets = _count(db, Dataset.id)
    analyses = _count(db, AnalysisRun.id)
    total_rows = int(
        db.execute(select(func.coalesce(func.sum(Dataset.row_count), 0))).scalar() or 0
    )
    pending_reports = int(
        db.execute(
            select(func.count(ExportedReport.id)).where(
                ExportedReport.status == REPORT_STATUS_PENDING
            )
        ).scalar()
        or 0
    )
    failed_reports = int(
        db.execute(
            select(func.count(ExportedReport.id)).where(
                ExportedReport.status == REPORT_STATUS_FAILED
            )
        ).scalar()
        or 0
    )
    audit_24h = int(
        db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.created_at >= day_ago)
        ).scalar()
        or 0
    )
    denied_24h = int(
        db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.created_at >= day_ago,
                AuditLog.result == audit.RESULT_DENIED,
            )
        ).scalar()
        or 0
    )

    return AdminOverviewResponse(
        total_users=total_users,
        active_users=active_users,
        suspended_users=suspended_users,
        active_last_7_days=recent_users,
        platform_staff=staff,
        organizations=organizations,
        datasets=datasets,
        analyses=analyses,
        total_rows_profiled=total_rows,
        storage_bytes=_storage_bytes(db),
        pending_reports=pending_reports,
        failed_reports=failed_reports,
        audit_events_last_24h=audit_24h,
        denied_last_24h=denied_24h,
    )


@router.get("/overview/alerts", response_model=AdminOverviewAlerts)
def admin_overview_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminOverviewAlerts:
    """Operational alerts for the admin dashboard's right rail (spec 26).

    Only conditions the platform can actually evidence are raised. A row that
    merely could be alarming is not an alert, and inventing one would train
    administrators to ignore the panel.
    """
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    alerts: list[AdminAlert] = []

    failed_reports = int(
        db.execute(
            select(func.count(ExportedReport.id)).where(
                ExportedReport.status == REPORT_STATUS_FAILED
            )
        ).scalar()
        or 0
    )
    if failed_reports:
        alerts.append(
            AdminAlert(
                level="danger",
                title="Report exports are failing",
                detail=f"{failed_reports} export(s) ended in a failed state.",
                action="/admin/reports",
            )
        )

    denied = int(
        db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.created_at >= day_ago,
                AuditLog.result == audit.RESULT_DENIED,
            )
        ).scalar()
        or 0
    )
    if denied:
        alerts.append(
            AdminAlert(
                level="warning",
                title="Unusual access activity",
                detail=(
                    f"{denied} refused access attempt(s) in the last 24 hours. "
                    "Review the audit log for the actors involved."
                ),
                action="/admin/audit",
            )
        )

    queued = int(
        db.execute(
            select(func.count(ExportedReport.id)).where(
                ExportedReport.status == REPORT_STATUS_PENDING
            )
        ).scalar()
        or 0
    )
    if queued:
        alerts.append(
            AdminAlert(
                level="info",
                title="Exports still running",
                detail=f"{queued} export(s) are still processing.",
                action="/admin/reports",
            )
        )

    if not alerts:
        alerts.append(
            AdminAlert(
                level="info",
                title="No outstanding alerts",
                detail=(
                    "No failed exports, no refused access and nothing queued "
                    "in the last 24 hours."
                ),
            )
        )
    return AdminOverviewAlerts(alerts=alerts)


@router.get("/me", response_model=AdminActionResponse)
def admin_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminActionResponse:
    """Which platform role the caller holds, so the UI can shape itself.

    Returns 403 for non-staff, which the frontend uses to hide the admin nav
    entirely rather than showing a link that would fail.
    """
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    return AdminActionResponse(
        message=f"Platform role: {user.system_role}",
    )


# ---------------------------------------------------------------- Users


@router.get("/users", response_model=AdminUserListResponse)
def admin_list_users(
    search: Optional[str] = Query(default=None, max_length=150),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    role_filter: Optional[str] = Query(default=None, alias="system_role"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminUserListResponse:
    """Searchable user list (F.3 / spec 27). Readable by any platform role."""
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    page, page_size = _paginate(page, page_size)

    conditions = []
    if search:
        needle = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(User.email).like(needle),
                func.lower(User.full_name).like(needle),
            )
        )
    if status_filter:
        conditions.append(User.status == status_filter)
    if role_filter:
        conditions.append(User.system_role == role_filter)

    total = int(
        db.execute(select(func.count(User.id)).where(*conditions)).scalar() or 0
    )
    rows = (
        db.execute(
            select(User)
            .where(*conditions)
            .order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    items = []
    for row in rows:
        member_count = int(
            db.execute(
                select(func.count(OrganizationMember.id)).where(
                    OrganizationMember.user_id == row.id
                )
            ).scalar()
            or 0
        )
        dataset_count = int(
            db.execute(
                select(func.count(Dataset.id)).where(Dataset.user_id == row.id)
            ).scalar()
            or 0
        )
        analysis_count = int(
            db.execute(
                select(func.count(AnalysisRun.id))
                .join(Dataset, AnalysisRun.dataset_id == Dataset.id)
                .where(Dataset.user_id == row.id)
            ).scalar()
            or 0
        )
        items.append(
            AdminUserListItem(
                **row.to_admin_dict(),
                organization_count=member_count,
                dataset_count=dataset_count,
                analysis_count=analysis_count,
            )
        )

    return AdminUserListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/users/{user_id}", response_model=AdminUserListItem)
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminUserListItem:
    """Single user record for the detail pane (F.3)."""
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserListItem(**target.to_admin_dict())


@router.patch("/users/{user_id}", response_model=AdminUserListItem)
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminUserListItem:
    """Edit an account: name, platform role, or suspension.

    The narrowest gate is ``platform_admin``. Granting or revoking a *super*
    admin is restricted further to ``super_admin`` and is audited separately,
    because that is the one edit that decides who can undo any other edit.
    """
    changes = payload.changes()
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No supported changes were supplied",
        )

    # Role management is reserved for a super admin (spec 37 lists managing
    # admins under Super Admin only, and not under Platform Admin). Everything
    # else on this route needs platform_admin.
    if "system_role" in changes:
        require_super_admin(db, user)
    else:
        require_platform_role(db, user, PLATFORM_ROLE_ADMIN)

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    before_role = target.system_role
    before_status = target.status

    if "system_role" in changes:
        assert_not_self(user, target, "change the platform role of")
        # Losing the top role counts as demoting the last super admin, so the
        # same guard covers a revoke as well as a demotion.
        assert_not_last_super_admin(db, user, target)
        target.system_role = changes["system_role"]

    if "status" in changes:
        assert_not_self(user, target, "change the status of")
        if changes["status"] == USER_STATUS_SUSPENDED:
            assert_not_last_super_admin(db, user, target)
            target.status = USER_STATUS_SUSPENDED
            target.suspended_at = datetime.now(timezone.utc)
            target.suspended_reason = payload.suspended_reason
        else:
            target.status = USER_STATUS_ACTIVE
            target.suspended_at = None
            target.suspended_reason = None

    if "full_name" in changes:
        target.full_name = changes["full_name"]

    db.commit()
    db.refresh(target)

    audit.record(
        db,
        "admin.user.update",
        user=user,
        resource="user",
        resource_id=target.id,
        request=request,
        metadata={
            "target_email": target.email,
            "changes": sorted(changes.keys()),
            "previous_role": before_role,
            "new_role": target.system_role,
            "previous_status": before_status,
            "new_status": target.status,
        },
    )

    return AdminUserListItem(**target.to_admin_dict())


@router.post("/users/{user_id}/suspend", response_model=AdminUserListItem)
def admin_suspend_user(
    user_id: int,
    request: Request,
    reason: Optional[str] = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminUserListItem:
    """Suspend an account (F.3). Blocks sign-in immediately."""
    require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    assert_not_self(user, target, "suspend")
    assert_not_last_super_admin(db, user, target)

    target.status = USER_STATUS_SUSPENDED
    target.suspended_at = datetime.now(timezone.utc)
    target.suspended_reason = reason
    db.commit()
    db.refresh(target)

    audit.record(
        db,
        "admin.user.suspend",
        user=user,
        resource="user",
        resource_id=target.id,
        request=request,
        metadata={"target_email": target.email, "reason": reason},
    )
    return AdminUserListItem(**target.to_admin_dict())


@router.post("/users/{user_id}/reactivate", response_model=AdminUserListItem)
def admin_reactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminUserListItem:
    """Restore a suspended account (F.3)."""
    require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    assert_not_self(user, target, "reactivate")

    target.status = USER_STATUS_ACTIVE
    target.suspended_at = None
    target.suspended_reason = None
    db.commit()
    db.refresh(target)

    audit.record(
        db,
        "admin.user.reactivate",
        user=user,
        resource="user",
        resource_id=target.id,
        request=request,
        metadata={"target_email": target.email},
    )
    return AdminUserListItem(**target.to_admin_dict())


# ------------------------------------------------------- Organizations


@router.get("/organizations", response_model=AdminOrganizationListResponse)
def admin_list_organizations(
    search: Optional[str] = Query(default=None, max_length=150),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminOrganizationListResponse:
    """Organization list with operational counts (F.4 / spec 28)."""
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    page, page_size = _paginate(page, page_size)

    conditions = []
    if search:
        needle = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Organization.name).like(needle),
                func.lower(Organization.slug).like(needle),
            )
        )

    total = int(
        db.execute(select(func.count(Organization.id)).where(*conditions)).scalar() or 0
    )
    rows = (
        db.execute(
            select(Organization)
            .where(*conditions)
            .order_by(Organization.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    items = []
    for row in rows:
        items.append(
            AdminOrganizationListItem(
                id=row.id,
                name=row.name,
                slug=row.slug,
                created_at=row.created_at.isoformat() if row.created_at else None,
                member_count=int(
                    db.execute(
                        select(func.count(OrganizationMember.id)).where(
                            OrganizationMember.organization_id == row.id
                        )
                    ).scalar()
                    or 0
                ),
                project_count=int(
                    db.execute(
                        select(func.count(Project.id)).where(
                            Project.organization_id == row.id
                        )
                    ).scalar()
                    or 0
                ),
                dataset_count=int(
                    db.execute(
                        select(func.count(Dataset.id))
                        .join(Project, Dataset.project_id == Project.id)
                        .where(Project.organization_id == row.id)
                    ).scalar()
                    or 0
                ),
                analysis_count=int(
                    db.execute(
                        select(func.count(AnalysisRun.id))
                        .join(Dataset, AnalysisRun.dataset_id == Dataset.id)
                        .join(Project, Dataset.project_id == Project.id)
                        .where(Project.organization_id == row.id)
                    ).scalar()
                    or 0
                ),
            )
        )

    return AdminOrganizationListResponse(items=items, total=total)


# ---------------------------------------------------------------- Datasets


@router.get("/datasets", response_model=AdminDatasetListResponse)
def admin_list_datasets(
    search: Optional[str] = Query(default=None, max_length=255),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminDatasetListResponse:
    """Dataset administration view (F.5 / spec 29).

    Metadata only. The dataset's rows are never exposed here, so this screen
    cannot be used to read another organization's data.
    """
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    page, page_size = _paginate(page, page_size)

    conditions = []
    if search:
        needle = f"%{search.strip().lower()}%"
        conditions.append(func.lower(Dataset.original_filename).like(needle))
    if status_filter:
        conditions.append(Dataset.status == status_filter)

    total = int(
        db.execute(select(func.count(Dataset.id)).where(*conditions)).scalar() or 0
    )
    rows = (
        db.execute(
            select(Dataset, User, Organization, Project)
            .join(User, Dataset.user_id == User.id, isouter=True)
            .outerjoin(Project, Dataset.project_id == Project.id)
            .outerjoin(Organization, Project.organization_id == Organization.id)
            .where(*conditions)
            .order_by(Dataset.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )

    items = []
    for dataset, owner, organization, _project in rows:
        latest = db.execute(
            select(func.max(DatasetVersion.version)).where(
                DatasetVersion.dataset_id == dataset.id
            )
        ).scalar()
        items.append(
            AdminDatasetListItem(
                id=dataset.id,
                original_filename=dataset.original_filename,
                file_type=dataset.file_type,
                status=dataset.status,
                row_count=dataset.row_count or 0,
                column_count=dataset.column_count or 0,
                created_at=(
                    dataset.created_at.isoformat() if dataset.created_at else None
                ),
                owner_email=owner.email if owner is not None else None,
                owner_id=dataset.user_id,
                organization_id=organization.id if organization is not None else None,
                organization_name=(
                    organization.name if organization is not None else None
                ),
                latest_version=int(latest) if latest is not None else None,
            )
        )

    return AdminDatasetListResponse(items=items, total=total)


# ---------------------------------------------------------------- Audit log


@router.get("/audit", response_model=AdminAuditListResponse)
def admin_list_audit(
    action: Optional[str] = Query(default=None, max_length=60),
    result_filter: Optional[str] = Query(default=None, alias="result"),
    user_id: Optional[int] = Query(default=None),
    resource: Optional[str] = Query(default=None, max_length=60),
    search: Optional[str] = Query(default=None, max_length=150),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminAuditListResponse:
    """Searchable audit log (F.10 / spec 32).

    Read-only by design: there is no write or delete route for audit entries
    anywhere in this module.
    """
    require_platform_role(db, user, PLATFORM_ROLE_VIEWER)
    page, page_size = _paginate(page, page_size)

    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if result_filter:
        conditions.append(AuditLog.result == result_filter)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if resource:
        conditions.append(AuditLog.resource == resource)
    if search:
        needle = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(AuditLog.actor_email).like(needle),
                func.lower(AuditLog.action).like(needle),
                func.lower(AuditLog.resource_id).like(needle),
            )
        )

    total = int(
        db.execute(select(func.count(AuditLog.id)).where(*conditions)).scalar() or 0
    )
    rows = (
        db.execute(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return AdminAuditListResponse(
        items=[AdminAuditListItem(**row.to_dict()) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
