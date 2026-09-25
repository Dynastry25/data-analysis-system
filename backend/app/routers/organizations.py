"""Organizations, members and projects (Phase 1 / master prompt).

Mounted at ``/api/v1/organizations``. Every route resolves the acting user from the
JWT and then applies the org RBAC ladder via :mod:`app.rbac`.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    ORG_ROLE_ADMIN,
    ORG_ROLE_ANALYST,
    ORG_ROLE_OWNER,
    ORG_ROLE_VIEWER,
    Dataset,
    Organization,
    OrganizationMember,
    Project,
    Team,
    TeamMember,
    User,
)
from app.rbac import (
    get_organization,
    get_organization_membership,
    is_admin,
    is_owner,
    require_membership,
    require_org_role,
)
from app.schemas import (
    MemberAddRequest,
    MemberResponse,
    MemberUpdateRequest,
    OrganizationCreateRequest,
    OrganizationListItem,
    OrganizationResponse,
    OrganizationUpdateRequest,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    TeamCreateRequest,
    TeamMemberAddRequest,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ------------------------------------------------------------------- helpers


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "organization"


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, n = base, 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def _member_counts(db: Session, organization_id: int) -> dict:
    member_count = (
        db.query(func.count(OrganizationMember.id))
        .filter(OrganizationMember.organization_id == organization_id)
        .scalar()
        or 0
    )
    project_count = (
        db.query(func.count(Project.id))
        .filter(Project.organization_id == organization_id)
        .scalar()
        or 0
    )
    return {"member_count": member_count, "project_count": project_count}


def _org_response(
    org: Organization, db: Session, member: Optional[OrganizationMember] = None
) -> dict:
    base = org.to_dict()
    base.update(_member_counts(db, org.id))
    base["my_role"] = member.role if member else None
    return base


def _get_project(db: Session, organization_id: int, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_response(db: Session, project: Project) -> dict:
    data = project.to_dict()
    data["dataset_count"] = (
        db.query(func.count(Dataset.id))
        .filter(Dataset.project_id == project.id)
        .scalar()
        or 0
    )
    return data


def _get_team(db: Session, organization_id: int, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None or team.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _team_response(db: Session, team: Team) -> dict:
    data = team.to_dict()
    data["member_count"] = (
        db.query(func.count(TeamMember.id)).filter(TeamMember.team_id == team.id).scalar() or 0
    )
    return data


# ------------------------------------------------------------------- org CRUD


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    slug = payload.slug or _unique_slug(db, payload.name)
    if db.query(Organization).filter(Organization.slug == slug).first():
        raise HTTPException(
            status_code=409, detail="An organization with this slug already exists"
        )

    org = Organization(
        name=payload.name.strip(),
        slug=slug,
        description=payload.description,
        created_by=user.id,
    )
    db.add(org)
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=ORG_ROLE_OWNER))
    db.commit()
    db.refresh(org)
    return _org_response(org, db, get_organization_membership(db, org.id, user.id))


@router.get("", response_model=list[OrganizationListItem])
def list_organizations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    membership = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.id.desc())
        .all()
    )
    result = []
    for m in membership:
        org = db.get(Organization, m.organization_id)
        if org is not None:
            result.append(_org_response(org, db, m))
    return result


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization_detail(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    member = require_membership(db, organization_id, user)
    org = get_organization(db, organization_id)
    return _org_response(org, db, member)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: int,
    payload: OrganizationUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    actor = require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    org = get_organization(db, organization_id)
    if payload.name is not None:
        org.name = payload.name.strip()
    if payload.description is not None:
        org.description = payload.description
    db.commit()
    db.refresh(org)
    return _org_response(org, db, actor)


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    actor = require_org_role(db, organization_id, user, ORG_ROLE_OWNER)
    org = get_organization(db, organization_id)
    db.delete(org)
    db.commit()
    return None


# ------------------------------------------------------------------ members


@router.post(
    "/{organization_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED
)
def add_member(
    organization_id: int,
    payload: MemberAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    actor = require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    if payload.role == ORG_ROLE_OWNER and not is_owner(actor):
        raise HTTPException(
            status_code=403, detail="Only the owner can grant the owner role"
        )

    target = (
        db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail="No account exists with this email address"
        )
    existing = get_organization_membership(db, organization_id, target.id)
    if existing:
        raise HTTPException(
            status_code=409, detail="This user is already a member of the organization"
        )

    member = OrganizationMember(
        organization_id=organization_id, user_id=target.id, role=payload.role
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member.to_dict()


@router.get("/{organization_id}/members", response_model=list[MemberResponse])
def list_members(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_membership(db, organization_id, user)
    members = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.id)
        .all()
    )
    return [m.to_dict() for m in members]


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(
    organization_id: int,
    user_id: int,
    payload: MemberUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    actor = require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    member = get_organization_membership(db, organization_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if is_owner(member):
        raise HTTPException(
            status_code=403, detail="The owner role cannot be changed or removed"
        )
    if not is_owner(actor):
        # admins may only shuffle analyst <-> viewer
        if is_admin(member) or payload.role not in (ORG_ROLE_ANALYST, ORG_ROLE_VIEWER):
            raise HTTPException(
                status_code=403,
                detail="Admins can only manage analyst and viewer roles",
            )
    member.role = payload.role
    db.commit()
    db.refresh(member)
    return member.to_dict()


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    organization_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    actor = require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    if user_id == user.id:
        raise HTTPException(
            status_code=400, detail="Use 'delete organization' to leave as owner"
        )
    member = get_organization_membership(db, organization_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if is_owner(member):
        raise HTTPException(status_code=403, detail="The owner cannot be removed")
    if not is_owner(actor) and is_admin(member):
        raise HTTPException(
            status_code=403, detail="Only the owner can remove an admin"
        )
    db.delete(member)
    db.commit()
    return None


# ----------------------------------------------------------------- projects


@router.post(
    "/{organization_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
def create_project(
    organization_id: int,
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_org_role(db, organization_id, user, ORG_ROLE_ANALYST)
    duplicate = (
        db.query(Project)
        .filter(
            Project.organization_id == organization_id,
            func.lower(Project.name) == payload.name.strip().lower(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409, detail="A project with this name already exists"
        )
    project = Project(
        organization_id=organization_id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(db, project)


@router.get("/{organization_id}/projects", response_model=list[ProjectResponse])
def list_projects(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_membership(db, organization_id, user)
    projects = (
        db.query(Project)
        .filter(Project.organization_id == organization_id)
        .order_by(Project.id.desc())
        .all()
    )
    return [_project_response(db, p) for p in projects]


@router.patch("/{organization_id}/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    organization_id: int,
    project_id: int,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    project = _get_project(db, organization_id, project_id)
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.description is not None:
        project.description = payload.description
    db.commit()
    db.refresh(project)
    return _project_response(db, project)


@router.delete(
    "/{organization_id}/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_project(
    organization_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    project = _get_project(db, organization_id, project_id)
    db.delete(project)
    db.commit()
    return None


# -------------------------------------------------------------------- teams


@router.post(
    "/{organization_id}/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED
)
def create_team(
    organization_id: int,
    payload: TeamCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_org_role(db, organization_id, user, ORG_ROLE_ANALYST)
    duplicate = (
        db.query(Team)
        .filter(
            Team.organization_id == organization_id,
            func.lower(Team.name) == payload.name.strip().lower(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    team = Team(
        organization_id=organization_id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=user.id,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return _team_response(db, team)


@router.get("/{organization_id}/teams", response_model=list[TeamResponse])
def list_teams(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_membership(db, organization_id, user)
    teams = (
        db.query(Team)
        .filter(Team.organization_id == organization_id)
        .order_by(Team.id.desc())
        .all()
    )
    return [_team_response(db, t) for t in teams]


@router.patch("/{organization_id}/teams/{team_id}", response_model=TeamResponse)
def update_team(
    organization_id: int,
    team_id: int,
    payload: TeamUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    team = _get_team(db, organization_id, team_id)
    if payload.name is not None:
        duplicate = (
            db.query(Team)
            .filter(
                Team.organization_id == organization_id,
                Team.id != team_id,
                func.lower(Team.name) == payload.name.strip().lower(),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A team with this name already exists")
        team.name = payload.name.strip()
    if payload.description is not None:
        team.description = payload.description
    db.commit()
    db.refresh(team)
    return _team_response(db, team)


@router.delete(
    "/{organization_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_team(
    organization_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    team = _get_team(db, organization_id, team_id)
    db.delete(team)
    db.commit()
    return None


@router.post(
    "/{organization_id}/teams/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_team_member(
    organization_id: int,
    team_id: int,
    payload: TeamMemberAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    team = _get_team(db, organization_id, team_id)
    if db.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if get_organization_membership(db, organization_id, payload.user_id) is None:
        raise HTTPException(
            status_code=403, detail="Only organization members can join a team"
        )
    existing = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team.id,
            TeamMember.user_id == payload.user_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This user is already in the team")
    member = TeamMember(team_id=team.id, user_id=payload.user_id)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member.to_dict()


@router.get(
    "/{organization_id}/teams/{team_id}/members", response_model=list[TeamMemberResponse]
)
def list_team_members(
    organization_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_membership(db, organization_id, user)
    _get_team(db, organization_id, team_id)
    members = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id)
        .order_by(TeamMember.id)
        .all()
    )
    return [m.to_dict() for m in members]


@router.delete(
    "/{organization_id}/teams/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_team_member(
    organization_id: int,
    team_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    require_org_role(db, organization_id, user, ORG_ROLE_ADMIN)
    team = _get_team(db, organization_id, team_id)
    member = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    db.delete(member)
    db.commit()
    return None