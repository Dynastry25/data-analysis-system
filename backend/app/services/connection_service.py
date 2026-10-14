"""Turning a connection into dataset versions (plan 3.4).

A connection is an ingest path. This service is the bridge between
"pull a frame from an organisational database or API" and "an
immutable dataset version the whole platform already knows how to
analyse, remediate, cache and trace".

The design choice that keeps everything else working: a connected
dataset is created the way an uploaded one is -- the frame is
written as the dataset's source file and v1 is made from it -- and
every later pull writes a new version through the same
``create_version`` the cleaning studio uses. So a connected dataset
is not a second class of data with its own rules: its lineage shows
each pull as an operation, its results cache by version, its
analyses are reproducible against the exact version they ran on, and
deleting the connection never deletes the data already analysed.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import DataConnection, DataConnectionSync, Dataset
from app.services.connection_secrets import decrypt
from app.services.data_service import STORAGE_DIR, profile_columns
from app.statflow import connectors, version_store

logger = logging.getLogger(__name__)


def connection_directory(user_id: int, dataset_id: int):
    """The dataset's folder, the same layout an upload uses."""
    folder = STORAGE_DIR / str(user_id) / str(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_dataset_for_connection(
    db: Session, connection: DataConnection, frame
) -> Dataset:
    """The first sync creates the dataset the connection feeds.

    The frame is written as the dataset's source file, and v1 is made
    from it, so a connected dataset is produced by exactly the code
    that produces an uploaded one -- not by a second path that could
    drift from it.
    """
    dataset = Dataset(
        user_id=connection.user_id,
        project_id=connection.project_id,
        original_filename=f"{connection.name}.{connection.kind}",
        file_type=connection.kind,
        storage_path="",
        status="uploaded",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    folder = connection_directory(connection.user_id, dataset.id)
    source_path = folder / "data.csv"
    frame.to_csv(source_path, index=False)
    dataset.storage_path = str(source_path)
    dataset.row_count = int(frame.shape[0])
    dataset.column_count = int(frame.shape[1])
    db.commit()
    db.refresh(dataset)

    version_store.ensure_base_version(db, dataset)
    # Label v1 so the version history says where the data came from:
    # "connection" rather than "original upload".
    from app.statflow.version_store import get_version

    record = get_version(db, dataset, 1)
    record.label = f"connection import ({connection.kind})"
    db.commit()
    return dataset


def sync_connection(
    db: Session, connection: DataConnection, *, force: bool = False
) -> Dict[str, Any]:
    """Pull a connection's data and write it as a new dataset version.

    Returns the sync record. A failed pull records the error on the
    connection and leaves the last good version exactly where it was:
    an unreachable database must not consume the dataset the reader
    is already analysing.
    """
    started = time.perf_counter()
    record = DataConnectionSync(connection_id=connection.id, status="running")
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        password = decrypt(connection.secret) if connection.secret else ""
        config = dict(connection.config or {})
        frame, fetch_ms = connectors.fetch_frame(connection.kind, config, password)
    except Exception as exc:
        record.status = "error"
        record.error_message = str(exc)
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()
        logger.info("Connection %s sync failed: %s", connection.id, exc)
        return {"sync": record.to_dict(), "ok": False}

    try:
        if connection.dataset_id is None:
            dataset = create_dataset_for_connection(db, connection, frame)
            connection.dataset_id = dataset.id
            db.commit()
            db.refresh(connection)
            version = 1
        else:
            dataset = db.query(Dataset).filter(Dataset.id == connection.dataset_id).one()
            current = version_store.get_version(db, dataset)
            version, _ = version_store.create_version(
                db,
                dataset,
                frame,
                operation_group="clean",
                operation_type="connection_sync",
                configuration={
                    "connection_id": connection.id,
                    "connection_name": connection.name,
                    "kind": connection.kind,
                    "source": _source_description(connection),
                },
                source_version=int(current.version),
                summary={
                    "rows_pulled": int(frame.shape[0]),
                    "columns_pulled": int(frame.shape[1]),
                    "connection": connection.name,
                    "fetch_ms": fetch_ms,
                },
                label=f"connection sync ({connection.name})",
                created_by=connection.user_id,
            )
            version = int(version.version)

        record.status = "ok"
        record.row_count = int(frame.shape[0])
        record.column_count = int(frame.shape[1])
        record.dataset_version = version
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        connection.status = "ok"
        connection.last_error = None
        connection.last_sync_at = _now()
        db.commit()
    except Exception as exc:
        record.status = "error"
        record.error_message = str(exc)
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()
        logger.exception("Connection %s sync could not be written", connection.id)
        return {"sync": record.to_dict(), "ok": False}

    return {
        "ok": True,
        "sync": record.to_dict(),
        "dataset_id": connection.dataset_id,
        "dataset_version": version,
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
    }


def preview_connection(
    kind: str, config: Dict[str, Any], password: str = ""
) -> Dict[str, Any]:
    """Pull a few rows to prove a connection works before it is saved."""
    started = time.perf_counter()
    frame, _ = connectors.fetch_frame(kind, config, password)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    profiles = profile_columns(frame.head(200))
    return {
        "ok": True,
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "columns": profiles,
        "preview_rows": _rows(frame.head(5)),
        "elapsed_ms": elapsed_ms,
    }


def _rows(frame):
    return [
        {
            str(column): _plain(value)
            for column, value in row.items()
        }
        for row in frame.to_dict(orient="records")
    ]


def _plain(value):
    try:
        if value != value:  # NaN
            return None
    except Exception:  # pragma: no cover
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _source_description(connection: DataConnection) -> str:
    config = connection.config or {}
    if connection.kind == "rest":
        return str(config.get("url"))
    host = config.get("host")
    database = config.get("database")
    table = config.get("table")
    query = config.get("query")
    target = f"table {table}" if table else "query"
    return f"{connection.kind}://{host}/{database} {target}".strip()


def due_connections(db: Session) -> List[DataConnection]:
    """Connections whose scheduled pull has come due.

    A connection never synced is due the moment it has a schedule,
    because "scheduled" and "never ran" together mean the reader asked
    for data and has none. A connection whose last sync failed is due
    too: retrying is the only way it can recover, and a crash-looping
    database shows its error plainly on the connection rather than
    failing quietly.
    """
    from datetime import timedelta

    now = _now()
    connections = (
        db.query(DataConnection)
        .filter(DataConnection.sync_every_minutes.isnot(None))
        .order_by(DataConnection.id)
        .all()
    )
    due: List[DataConnection] = []
    for connection in connections:
        if connection.status == "error":
            due.append(connection)
            continue
        if connection.last_sync_at is None:
            due.append(connection)
            continue
        age = now - _aware(connection.last_sync_at)
        if age >= timedelta(minutes=int(connection.sync_every_minutes or 0)):
            due.append(connection)
    return due


def _aware(moment):
    """A stored timestamp as an aware UTC datetime.

    SQLite hands back naive datetimes; comparing one against an aware
    ``utcnow()`` raises rather than guessing an offset, and guessing
    would make a schedule silently wrong for anyone east of UTC.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _now():
    return datetime.now(timezone.utc)
