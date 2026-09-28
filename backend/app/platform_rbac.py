"""Platform (admin portal) RBAC.

This ladder is deliberately **separate** from the organization ladder in
``app.rbac``. Org roles answer "what may this person do inside their own
organization?"; platform roles answer "what may this person do across every
organization?". An organization ``admin`` is not a platform admin and must
never be treated as one, so the two ladders share no constants and no
lookup tables.

Ladder (master prompt F.14 / design spec 37):

    super_admin (4) > platform_admin (3) > admin_viewer (1)
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    PLATFORM_ROLE_LEVEL,
    PLATFORM_ROLE_SUPER_ADMIN,
    PLATFORM_ROLE_VIEWER,
    USER_STATUS_ACTIVE,
    User,
)

#: An ordinary user has no platform access at all.
NO_PLATFORM_ROLE = ""


def platform_role_level(role: Optional[str]) -> int:
    """Ladder position of a platform role; unknown/empty roles score 0."""
    return PLATFORM_ROLE_LEVEL.get(role or "", 0)


def is_platform_staff(role: Optional[str]) -> bool:
    """True for any role that may open the admin portal at all."""
    return platform_role_level(role) >= platform_role_level(PLATFORM_ROLE_VIEWER)


def has_platform_role(user: User, minimum: str) -> bool:
    return platform_role_level(user.system_role) >= platform_role_level(minimum)


def require_platform_role(db: Session, user: User, minimum: str) -> User:
    """Gate for every admin endpoint.

    Raises 403 for non-staff and 403 for staff whose role is too low, and 401
    for anonymous callers. Permissions are always enforced here on the server:
    the admin UI is never the thing that decides who is allowed.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    if user.status != USER_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is suspended",
        )
    if not is_platform_staff(user.system_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires platform administrator access",
        )
    if not has_platform_role(user, minimum):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action needs at least the '{minimum}' platform role",
        )
    return user


def require_super_admin(db: Session, user: User) -> User:
    """Narrowest gate: reserved for the platform itself.

    Used for actions an admin must not be able to perform on other people,
    such as granting or revoking platform roles.
    """
    return require_platform_role(db, user, PLATFORM_ROLE_SUPER_ADMIN)


def assert_not_last_super_admin(db: Session, actor: User, target: User) -> None:
    """Refuse to strip the final super admin from the platform.

    Without this the last holder of the top role can lock every administrator
    out of the portal, and recovery would need direct database access.
    """
    if target.system_role != PLATFORM_ROLE_SUPER_ADMIN:
        return
    remaining = (
        db.query(User)
        .filter(
            User.system_role == PLATFORM_ROLE_SUPER_ADMIN,
            User.id != target.id,
            User.status == USER_STATUS_ACTIVE,
        )
        .count()
    )
    if remaining == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is the last active super admin: promote another "
                "super admin before changing this account"
            ),
        )


def assert_not_self(actor: User, target: User, action: str) -> None:
    """Stop an admin from suspending or deprivileging their own account."""
    if actor.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You cannot {action} your own account",
        )
