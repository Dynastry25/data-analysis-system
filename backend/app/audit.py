"""Audit trail writer for security-relevant actions (master prompt 29 / F.10).

Kept separate from the routers so that recording an action is a one-liner at
the call site and so that the failure policy is decided in exactly one place.

Failure policy: **an audit failure must never turn a successful admin action
into an error**, because that would encourage callers to skip the call, and it
would leave the platform in a state where the change applied but the log did
not. Instead the write is attempted, and if the database rejects it the problem
is surfaced on the server's own logging channel so it is visible to operators
even though the user action already succeeded.
"""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User

logger = logging.getLogger("statflow.audit")

# Results stored against an entry.
RESULT_SUCCESS = "success"
RESULT_FAILURE = "failure"
RESULT_DENIED = "denied"


def client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort caller IP.

    ``X-Forwarded-For`` is consulted first because the app is deployed behind a
    proxy in production. The value is only ever recorded, never parsed into a
    decision, so a spoofed header cannot grant access.
    """
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)[:45]
    return None


def record(
    db: Session,
    action: str,
    *,
    user: Optional[User] = None,
    organization_id: Optional[int] = None,
    resource: Optional[str] = None,
    resource_id: Optional[Any] = None,
    result: str = RESULT_SUCCESS,
    request: Optional[Request] = None,
    actor_email: Optional[str] = None,
    metadata: Optional[dict] = None,
    commit: bool = True,
) -> Optional[AuditLog]:
    """Append one audit entry. Returns the entry, or None if it could not be saved.

    ``metadata`` must only ever hold values that are safe to show an operator:
    it is rendered straight into the admin audit screen.
    """
    entry = AuditLog(
        user_id=user.id if user is not None else None,
        organization_id=organization_id,
        actor_email=(actor_email or (user.email if user is not None else None)),
        action=action,
        resource=resource,
        resource_id=None if resource_id is None else str(resource_id),
        result=result,
        ip_address=client_ip(request),
        metadata_json=metadata,
    )
    try:
        db.add(entry)
        if commit:
            db.commit()
        else:
            db.flush()
        return entry
    except Exception:  # pragma: no cover - exercised only on a broken database
        logger.exception("Failed to write audit entry action=%s", action)
        try:
            db.rollback()
        except Exception:
            logger.exception("Failed to roll back after an audit write error")
        return None


def record_failure(
    db: Session,
    action: str,
    *,
    request: Optional[Request] = None,
    actor_email: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[AuditLog]:
    """Record a rejected or failed attempt, e.g. a login that did not succeed.

    Kept separate so the call site cannot forget the ``result`` flag: the whole
    point of writing the failed attempts is that they are the interesting rows.
    """
    return record(
        db,
        action,
        result=RESULT_FAILURE,
        request=request,
        actor_email=actor_email,
        metadata=metadata,
    )


def record_denied(
    db: Session,
    action: str,
    *,
    user: Optional[User] = None,
    request: Optional[Request] = None,
    metadata: Optional[dict] = None,
) -> Optional[AuditLog]:
    """Record an authorization refusal made by the platform itself."""
    return record(
        db,
        action,
        user=user,
        result=RESULT_DENIED,
        request=request,
        metadata=metadata,
    )
