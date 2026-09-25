"""Organization RBAC helpers (Phase 1 / master prompt).

Role ladder: owner (4) > admin (3) > analyst (2) > viewer (1). ``require_membership``
guards the org endpoints themselves; the dataset layer additionally consults the
role level via ``deps.get_owned_dataset``.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    ORG_ROLE_ADMIN,
    ORG_ROLE_ANALYST,
    ORG_ROLE_LEVEL,
    ORG_ROLE_OWNER,
    ORG_ROLE_VIEWER,
    Organization,
    OrganizationMember,
    User,
)


def role_level(role: Optional[str]) -> int:
    return ORG_ROLE_LEVEL.get(role or "", 0)


def has_org_role(member: Optional[OrganizationMember], minimum: str) -> bool:
    """True when ``member`` exists with a role at least ``minimum``."""
    return member is not None and role_level(member.role) >= role_level(minimum)


def get_organization_membership(
    db: Session, organization_id: int, user_id: int
) -> Optional[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .first()
    )


def get_organization(db: Session, organization_id: int) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def require_membership(
    db: Session, organization_id: int, user: User
) -> OrganizationMember:
    """Any membership (even viewer) is enough to read an organization."""
    org = get_organization(db, organization_id)
    member = get_organization_membership(db, org.id, user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return member


def require_org_role(
    db: Session, organization_id: int, user: User, minimum: str
) -> OrganizationMember:
    """Membership AND a role >= ``minimum``; raises 403 otherwise."""
    member = require_membership(db, organization_id, user)
    if not has_org_role(member, minimum):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action needs at least the '{minimum}' role",
        )
    return member


def is_owner(member: OrganizationMember) -> bool:
    return member.role == ORG_ROLE_OWNER


def is_admin(member: OrganizationMember) -> bool:
    return role_level(member.role) >= role_level(ORG_ROLE_ADMIN)


def is_writer(member: OrganizationMember) -> bool:
    """analyst+ can create projects, datasets and run analyses."""
    return role_level(member.role) >= role_level(ORG_ROLE_ANALYST)