"""Shared FastAPI dependencies: current user + ownership checks."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ORG_ROLE_ANALYST,
    ORG_ROLE_LEVEL,
    Dataset,
    Organization,
    Project,
    User,
)
from app.security import JWTError, decode_token

# auto_error=False so we can raise our own consistent 401 payload.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the Bearer token."""
    if not token:
        raise _credentials_exception()
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise _credentials_exception()

    user = db.get(User, user_id)
    if user is None:
        raise _credentials_exception()
    return user


def get_owned_dataset(
    dataset_id: int,
    db: Session,
    user: User,
    *,
    require_file: bool = True,
    min_role: str = ORG_ROLE_ANALYST,
) -> Dataset:
    """Fetch a dataset and make sure the user may access it.

    Two scopes are supported:

    * **Personal** (``project_id`` is NULL): only the uploading owner has access
      — the original MVP privacy rule.
    * **Project** (``project_id`` set): project members reach the dataset through
      their organization role; ``min_role`` is the lowest role that passes
      (default ``analyst`` covers reads *and* writes).

    Users without a role high enough (or not members at all) get a 403.
    """
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    owned = dataset.user_id == user.id
    if dataset.project_id is not None:
        project = db.get(Project, dataset.project_id)
        organization = db.get(Organization, project.organization_id) if project else None
        membership = None
        if organization is not None:
            from app.models import OrganizationMember

            membership = (
                db.query(OrganizationMember)
                .filter(
                    OrganizationMember.organization_id == organization.id,
                    OrganizationMember.user_id == user.id,
                )
                .first()
            )
        org_ok = (
            membership is not None
            and ORG_ROLE_LEVEL.get(membership.role, 0) >= ORG_ROLE_LEVEL.get(min_role, 0)
        )
        if not (owned or org_ok):
            raise HTTPException(
                status_code=403, detail="You do not have access to this dataset"
            )
    elif not owned:
        raise HTTPException(
            status_code=403, detail="You do not have access to this dataset"
        )

    if require_file and not dataset.storage_path:
        raise HTTPException(
            status_code=409, detail="Dataset file is not available on the server"
        )
    return dataset
