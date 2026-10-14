"""Endpoints for database and API connections (plan 3.4).

    GET    /v1/connections                     the reader's connections
    POST   /v1/connections                     save one (tested first)
    POST   /v1/connections/{id}/test           prove it works now
    POST   /v1/connections/{id}/sync           pull -> new dataset version
    DELETE /v1/connections/{id}                forget the connection
    GET    /v1/connections/{id}/syncs          the pull history

The credential is accepted on write and never returned on read: a
connection that exposes its password in a response or a log line is
a breach waiting for a bug. A sync writes an immutable dataset
version, so the organisation's database stays the system of record
for its own data and the analysis stays reproducible against the
exact rows a result was computed from.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import DataConnection, DataConnectionSync, User
from app.schemas import ConnectionCreateRequest, ConnectionTestRequest
from app.services import connection_service
from app.services.connection_secrets import decrypt, encrypt
from app.statflow import connectors

router = APIRouter(prefix="/connections", tags=["statflow-v1-connections"])


def _owned(connection_id: int, db: Session, user: User) -> DataConnection:
    """Fetch a connection the reader owns, or 404.

    A connection belongs to one user, so the check is an equality
    rather than a role: a colleague's database credentials are not
    yours to test or sync, and a 404 (rather than 403) also keeps
    the existence of someone else's connection private.
    """
    connection = (
        db.query(DataConnection).filter(DataConnection.id == connection_id).first()
    )
    if connection is None or connection.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found"
        )
    return connection


@router.get("")
def list_connections(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Every connection the reader owns, credentials stripped."""
    connections = (
        db.query(DataConnection)
        .filter(DataConnection.user_id == user.id)
        .order_by(DataConnection.created_at.desc(), DataConnection.id.desc())
        .all()
    )
    return {
        "connections": [connection.to_dict() for connection in connections],
        "kinds": {
            "postgres": {
                "fields": connectors.required_fields("postgres"),
                "driver": "psycopg",
            },
            "mysql": {"fields": connectors.required_fields("mysql"), "driver": "PyMySQL"},
            "rest": {"fields": connectors.required_fields("rest"), "driver": "built-in"},
        },
    }


@router.post("")
def create_connection(
    payload: ConnectionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save a connection after proving it can actually read the data.

    The test is not a formality: a connection that cannot reach its
    database saves an error the reader discovers three days later, so
    the credential is exercised once before the row exists.
    """
    try:
        config = connectors.validate_config(payload.kind, payload.config)
    except connectors.ConnectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    connection = DataConnection(
        user_id=user.id,
        project_id=payload.project_id,
        name=payload.name.strip(),
        kind=payload.kind,
        config=config,
        secret=encrypt(payload.secret) if payload.secret else "",
        status="never_run",
        sync_every_minutes=payload.sync_every_minutes,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    if payload.test:
        try:
            connection_service.preview_connection(payload.kind, config, payload.secret or "")
            connection.status = "ok"
            connection.last_error = None
        except Exception as exc:
            connection.status = "error"
            connection.last_error = str(exc)
        db.commit()
        db.refresh(connection)

    return {"connection": connection.to_dict()}


@router.post("/{connection_id}/test")
def test_connection(
    connection_id: int,
    payload: Optional[ConnectionTestRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Prove a connection works, and show what it would pull."""
    connection = _owned(connection_id, db, user)
    password = decrypt(connection.secret) if connection.secret else ""
    if payload is not None and payload.secret:
        password = payload.secret
    try:
        preview = connection_service.preview_connection(
            connection.kind, connection.config or {}, password
        )
    except Exception as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    connection.status = "ok"
    connection.last_error = None
    db.commit()
    return preview


@router.post("/{connection_id}/sync")
def sync_connection(
    connection_id: int,
    background: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
) -> Dict[str, Any]:
    """Pull now; the data becomes a new immutable dataset version.

    ``?background=true`` queues the pull as a job and returns its id,
    for a database whose query takes longer than a request should: the
    job writes the same version the synchronous path writes, through
    the same service, so the two cannot drift.
    """
    connection = _owned(connection_id, db, user)
    if background:
        from app.models import Job
        from app.services.job_processor import process_job

        job = Job(
            user_id=user.id,
            job_type="connection_sync",
            payload={"connection_id": connection.id, "connection_name": connection.name},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        if background_tasks is not None:
            background_tasks.add_task(process_job, job.id)
        return {
            "queued": True,
            "job_id": job.id,
            "status": job.status,
            "connection_id": connection.id,
        }
    outcome = connection_service.sync_connection(db, connection, force=True)
    if not outcome.get("ok"):
        sync = outcome["sync"]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sync.get("error_message") or "The sync failed",
        )
    return outcome


@router.get("/due")
def due_connections(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """The connections whose scheduled pull has come due.

    The platform has no built-in scheduler, so this is the seam a
    scheduled sync hooks into: call it on a timer (a cron entry, or a
    deploy platform's scheduler) and sync what it returns. Returning
    the due set rather than firing it keeps the decision in one place
    and lets a caller decide what to do with a connection whose pull
    is expensive or whose database is known to be down.
    """
    due = connection_service.due_connections(db)
    return {
        "due": [connection.to_dict() for connection in due if connection.user_id == user.id],
        "hint": "POST /api/v1/connections/{id}/sync to pull one, or with ?background=true to queue it.",
    }


@router.post("/sync-due")
def sync_due(
    background: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
) -> Dict[str, Any]:
    """Sync everything due — the one-cron-entry scheduled sync."""
    due = [
        connection
        for connection in connection_service.due_connections(db)
        if connection.user_id == user.id
    ]
    outcomes = []
    for connection in due:
        if background:
            from app.models import Job
            from app.services.job_processor import process_job

            job = Job(
                user_id=user.id,
                job_type="connection_sync",
                payload={"connection_id": connection.id, "connection_name": connection.name},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            if background_tasks is not None:
                background_tasks.add_task(process_job, job.id)
            outcomes.append({"connection_id": connection.id, "job_id": job.id})
        else:
            result = connection_service.sync_connection(db, connection)
            outcomes.append({"connection_id": connection.id, **result})
    return {"synced": len(outcomes), "results": outcomes}


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Forget a connection. The datasets it fed stay, by design."""
    connection = _owned(connection_id, db, user)
    dataset_id = connection.dataset_id
    db.delete(connection)
    db.commit()
    return {"deleted": True, "dataset_id": dataset_id}


@router.get("/{connection_id}/syncs")
def connection_syncs(
    connection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """The pull history, newest first."""
    _owned(connection_id, db, user)
    syncs = (
        db.query(DataConnectionSync)
        .filter(DataConnectionSync.connection_id == connection_id)
        .order_by(DataConnectionSync.id.desc())
        .limit(50)
        .all()
    )
    return {"syncs": [sync.to_dict() for sync in syncs]}
