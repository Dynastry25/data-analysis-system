"""Dashboard endpoints: create, list, read, update and delete a saved dashboard.

A dashboard is a named arrangement of widgets over sources that already exist —
saved analyses, saved charts and column summaries. It is pinned to a dataset
version, exactly like a chart, so a dashboard opened today renders the numbers
that were in the dataset when the dashboard was built.

Collaboration endpoints (Feature 21):
- Share dashboards with users or organizations (viewer/editor/admin roles)
- Comment threads on dashboards and individual widgets
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import (
    Dashboard,
    DashboardShare,
    DashboardComment,
    User,
    Organization,
)
from app.rbac import ORG_ROLE_ANALYST, ORG_ROLE_VIEWER
from app.schemas import (
    DashboardListItem,
    DashboardRequest,
    DashboardResponse,
    DashboardUpdateRequest,
    DashboardShareCreate,
    DashboardShareUpdate,
    DashboardShareResponse,
    DashboardCommentCreate,
    DashboardCommentUpdate,
    DashboardCommentResponse,
)
from app.statflow import version_store
from app.statflow.version_store import VersionError

router = APIRouter(tags=["dashboards"])


def _dashboard_payload(record: Dashboard) -> Dict[str, Any]:
    return record.to_dict()


# ---------------------------------------------------------------- Sharing


@router.post(
    "/dashboards/{dashboard_id}/shares",
    response_model=DashboardShareResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dashboard_share(
    dashboard_id: int,
    payload: DashboardShareCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Share a dashboard with a user or organization (viewer/editor/admin)."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    # Require admin role on the dashboard's dataset to share
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )

    # Check target exists
    target_user = None
    target_org = None
    if payload.user_id:
        target_user = db.get(User, payload.user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="User not found")
    if payload.organization_id:
        target_org = db.get(Organization, payload.organization_id)
        if target_org is None:
            raise HTTPException(status_code=404, detail="Organization not found")

    # Check if share already exists
    existing = (
        db.query(DashboardShare)
        .filter(
            DashboardShare.dashboard_id == dashboard_id,
            or_(
                DashboardShare.user_id == payload.user_id,
                DashboardShare.organization_id == payload.organization_id,
            ),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Share already exists for this target",
        )

    share = DashboardShare(
        dashboard_id=dashboard_id,
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        role=payload.role,
        created_by=user.id,
        expires_at=payload.expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share.to_dict()


@router.get("/dashboards/{dashboard_id}/shares", response_model=List[DashboardShareResponse])
def list_dashboard_shares(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List all shares for a dashboard."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )

    shares = (
        db.query(DashboardShare)
        .filter(DashboardShare.dashboard_id == dashboard_id)
        .order_by(DashboardShare.created_at.desc())
        .all()
    )
    return [share.to_dict() for share in shares]


@router.patch("/shares/{share_id}", response_model=DashboardShareResponse)
def update_dashboard_share(
    share_id: int,
    payload: DashboardShareUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update a share's role or expiration."""
    share = db.get(DashboardShare, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    # Require admin on the dashboard's dataset
    dashboard = db.get(Dashboard, share.dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        dashboard.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )

    if payload.role is not None:
        share.role = payload.role
    if payload.expires_at is not None:
        share.expires_at = payload.expires_at
    db.commit()
    db.refresh(share)
    return share.to_dict()


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_share(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Remove a share."""
    share = db.get(DashboardShare, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    dashboard = db.get(Dashboard, share.dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        dashboard.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )
    db.delete(share)
    db.commit()


# ---------------------------------------------------------------- Comments


@router.post(
    "/dashboards/{dashboard_id}/comments",
    response_model=DashboardCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dashboard_comment(
    dashboard_id: int,
    payload: DashboardCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Add a comment to a dashboard or widget."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )

    if payload.parent_id:
        parent = db.get(DashboardComment, payload.parent_id)
        if parent is None or parent.dashboard_id != dashboard_id:
            raise HTTPException(status_code=404, detail="Parent comment not found")

    comment = DashboardComment(
        dashboard_id=dashboard_id,
        widget_id=payload.widget_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        content=payload.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment.to_dict()


@router.get(
    "/dashboards/{dashboard_id}/comments",
    response_model=List[DashboardCommentResponse],
)
def list_dashboard_comments(
    dashboard_id: int,
    widget_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List comments for a dashboard (optionally filtered by widget)."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )

    query = db.query(DashboardComment).filter(
        DashboardComment.dashboard_id == dashboard_id,
        DashboardComment.parent_id.is_(None),  # top-level only; replies nested
    )
    if widget_id is not None:
        query = query.filter(DashboardComment.widget_id == widget_id)

    comments = query.order_by(DashboardComment.created_at.asc()).all()

    # Build tree with replies
    comment_map = {c.id: c.to_dict() for c in comments}
    for comment in comments:
        comment_map[comment.id]["replies"] = []

    replies = (
        db.query(DashboardComment)
        .filter(
            DashboardComment.dashboard_id == dashboard_id,
            DashboardComment.parent_id.isnot(None),
        )
        .order_by(DashboardComment.created_at.asc())
        .all()
    )
    for reply in replies:
        reply_dict = reply.to_dict()
        reply_dict["replies"] = []
        if reply.parent_id in comment_map:
            comment_map[reply.parent_id]["replies"].append(reply_dict)
        else:
            # orphan reply, add as top-level
            comment_map[reply.id] = reply_dict

    return list(comment_map.values())


@router.patch(
    "/comments/{comment_id}",
    response_model=DashboardCommentResponse,
)
def update_dashboard_comment(
    comment_id: int,
    payload: DashboardCommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Edit a comment (author only)."""
    comment = db.get(DashboardComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")
    comment.content = payload.content
    db.commit()
    db.refresh(comment)
    return comment.to_dict()


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a comment (author or dataset admin)."""
    comment = db.get(DashboardComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    dashboard = db.get(Dashboard, comment.dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    is_author = comment.user_id == user.id
    is_admin = False
    if not is_author:
        try:
            get_owned_dataset(
                dashboard.dataset_id,
                db,
                user,
                require_file=False,
                min_role=ORG_ROLE_ANALYST,
            )
            is_admin = True
        except HTTPException:
            pass
    if not is_author and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    db.delete(comment)
    db.commit()


@router.post("/datasets/{dataset_id}/dashboards", response_model=DashboardResponse)
def create_dashboard(
    dataset_id: int,
    payload: DashboardRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save a dashboard against the dataset's current version."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        version_record, _ = version_store.load_version_frame(
            db, dataset, payload.dataset_version
        )
    except (VersionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    record = Dashboard(
        dataset_id=dataset.id,
        dataset_version_id=version_record.id,
        name=payload.name,
        title=payload.title,
        config={"widgets": payload.widgets},
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _dashboard_payload(record)


@router.get("/datasets/{dataset_id}/dashboards", response_model=List[DashboardListItem])
def list_dashboards(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Every dashboard saved for one dataset."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    records = (
        db.query(Dashboard)
        .filter(Dashboard.dataset_id == dataset.id)
        .order_by(Dashboard.id.desc())
        .all()
    )
    return [_dashboard_payload(record) for record in records]


@router.get("/dashboards/{dashboard_id}", response_model=DashboardResponse)
def get_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """One saved dashboard (ownership checked through the dataset)."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_VIEWER,
    )
    return _dashboard_payload(record)


@router.put("/dashboards/{dashboard_id}", response_model=DashboardResponse)
def update_dashboard(
    dashboard_id: int,
    payload: DashboardUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Rename, retitle or replace the widget layout of a saved dashboard."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )
    if payload.name is not None:
        record.name = payload.name
    if payload.title is not None:
        record.title = payload.title or None
    if payload.widgets is not None:
        current = dict(record.config or {})
        current["widgets"] = payload.widgets
        record.config = current
    db.commit()
    db.refresh(record)
    return _dashboard_payload(record)


@router.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Remove a dashboard. The analyses and charts it referenced stay intact."""
    record = db.get(Dashboard, dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    get_owned_dataset(
        record.dataset_id,
        db,
        user,
        require_file=False,
        min_role=ORG_ROLE_ANALYST,
    )
    db.delete(record)
    db.commit()