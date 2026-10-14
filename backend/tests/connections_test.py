"""Database and API connectors (plan 3.4).

The strategic claim was "connect an organisational database" while
ingest was files and scraping only. These tests pin the properties
that make the new ingest path safe to add:

  * **A sync is an ingest path, not a data store.** The pull writes
    an immutable dataset version through the same ``create_version``
    the cleaning studio uses, so the lineage view shows each sync as
    an operation and the rest of the platform works unchanged.
  * **The credential never leaves the building.** It is encrypted at
    rest with a key derived from ``SECRET_KEY``, never returned by an
    endpoint, and a decryption that fails says so rather than
    pretending the password is empty.
  * **A connection that cannot reach its database is an honest
    error**, recorded on the connection, leaving the last good
    version exactly where it was -- an unreachable database must not
    consume the dataset a reader is already analysing.
  * **A query without a LIMIT gets one.** "SELECT * FROM 40 million
    rows" as a first sync is an outage waiting to happen.

Run it with:  python tests/connections_test.py
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="connections_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "connections-test-secret-key-0123456789"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402
from threading import Thread  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import connection_secrets  # noqa: E402
from app.statflow import connectors  # noqa: E402

PASSED = 0
ROWS = [{"id": index, "value": index * 2, "name": f"row {index}"} for index in range(25)]


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


class _Stub(BaseHTTPRequestHandler):
    """A local JSON endpoint: the shape an organisational API serves."""

    def do_GET(self):
        if self.path == "/rows":
            body = json.dumps(ROWS).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/wrapped":
            body = json.dumps({"meta": {"page": 1}, "data": ROWS[:5]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/csv":
            body = b"a,b\n1,x\n2,y\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/auth":
            if self.headers.get("Authorization") == "Bearer token-123":
                body = json.dumps(ROWS[:2]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(401)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def start_stub():
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


# ------------------------------------------------------------------- tests


def _case_credential_encryption() -> None:
    print("\n1) The credential is encrypted at rest and never returned")
    secret = "sup3r-s3cret-db-password"
    token = connection_secrets.encrypt(secret)
    check(token != secret, "the stored value is not the plaintext")
    check(secret not in token, "and the plaintext is not visible inside it")
    check(connection_secrets.decrypt(token) == secret, "it round-trips")

    # A rotated SECRET_KEY must fail loudly, not silently read as empty.
    # `app.config` reads the environment once at import, so the rotation
    # is done where the secret service actually reads it.
    from app import config as app_config

    original_key = app_config.SECRET_KEY
    app_config.SECRET_KEY = "a-different-key-entirely-987654321"
    connection_secrets.reset_cache()
    try:
        connection_secrets.decrypt(token)
        unclear = False
    except RuntimeError as exc:
        unclear = "SECRET_KEY" in str(exc) or "re-enter" in str(exc)
    check(unclear, "a key change is a readable error, not an empty password")
    app_config.SECRET_KEY = original_key
    connection_secrets.reset_cache()


def _case_query_limit_guard() -> None:
    print("\n2) A query without a LIMIT is guarded")
    check(
        connectors._ensure_limit("SELECT * FROM events")
        == f"SELECT * FROM events LIMIT {connectors.DEFAULT_ROW_LIMIT}",
        "a bare query gets the default limit",
    )
    check(
        connectors._ensure_limit("SELECT * FROM events LIMIT 10") == "SELECT * FROM events LIMIT 10",
        "the reader's own LIMIT is respected",
    )
    check(
        connectors._ensure_limit("select * from t;") == "SELECT * FROM events LIMIT 100000".replace(
            "SELECT * FROM events", "select * from t"
        ),
        "a trailing semicolon does not break the guard",
    )


def _case_rest_shapes() -> None:
    print("\n3) The REST connector reads the shapes APIs actually serve")
    server, port = start_stub()
    try:
        base = f"http://127.0.0.1:{port}"
        frame, _ = connectors.fetch_frame("rest", {"url": f"{base}/rows"})
        check(len(frame) == len(ROWS), f"a JSON array becomes {len(ROWS)} rows")
        check(list(frame.columns) == ["id", "value", "name"], "and the objects become columns")

        wrapped, _ = connectors.fetch_frame("rest", {"url": f"{base}/wrapped"})
        check(len(wrapped) == 5, "a single array inside an object is found wherever it is")

        csv_frame, _ = connectors.fetch_frame("rest", {"url": f"{base}/csv"})
        check(list(csv_frame.columns) == ["a", "b"], "a CSV body is read as a table too")

        authed, _ = connectors.fetch_frame(
            "rest", {"url": f"{base}/auth"}, "Bearer token-123"
        )
        check(len(authed) == 2, "the secret is sent as the Authorization header")

        refused = False
        try:
            connectors.fetch_frame("rest", {"url": f"{base}/auth"}, "Bearer wrong")
        except connectors.ConnectorError:
            refused = True
        check(refused, "a 401 is a readable error, not an empty dataset")
    finally:
        server.shutdown()


def _case_validation() -> None:
    print("\n4) An unusable connection is refused before it is stored")
    for kind, config in (
        ("postgres", {"host": "db"}),
        ("mysql", {}),
        ("rest", {"url": "ftp://not-http"}),
        ("rest", {}),
        ("queue", {"url": "http://x"}),
    ):
        refused = False
        try:
            connectors.validate_config(kind, config)
        except connectors.ConnectorError as exc:
            refused = bool(str(exc))
        check(refused, f"{kind} with {config} is refused")

    ok = connectors.validate_config(
        "rest", {"url": "https://api.example.org/rows", "headers": {"Accept": "application/json"}}
    )
    check(ok["url"] == "https://api.example.org/rows", "a valid REST connection passes")


def _case_sync_writes_a_version() -> None:
    print("\n5) A sync writes a version the whole platform already knows")
    server, port = start_stub()
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"full_name": "Asha Mwangi", "email": "conn@example.com", "password": "secret123"},
        )
        token = client.post(
            "/api/auth/login", json={"email": "conn@example.com", "password": "secret123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/api/v1/connections",
            json={
                "name": "Stub API",
                "kind": "rest",
                "config": {"url": f"http://127.0.0.1:{port}/rows"},
                "secret": "Bearer token-123",
            },
            headers=headers,
        )
        check(created.status_code == 200, "a tested connection is saved")
        connection = created.json()["connection"]
        check(connection["status"] == "ok", "and its test passed")
        check("secret" not in connection, "the response carries no secret field")
        check(connection["has_secret"] is True, "only a yes/no about whether one exists")
        check(
            "Bearer token-123" not in json.dumps(created.json()),
            "and the credential's value appears nowhere in the response",
        )

        connection_id = connection["id"]
        first = client.post(f"/api/v1/connections/{connection_id}/sync", headers=headers).json()
        check(first["ok"], "the first sync succeeds")
        check(first["dataset_version"] == 1, "and produces v1")
        dataset_id = first["dataset_id"]

        second = client.post(f"/api/v1/connections/{connection_id}/sync", headers=headers).json()
        check(second["dataset_version"] == 2, "the second sync produces v2, not an overwrite")

        # The dataset is a normal dataset, through the normal endpoints.
        detail = client.get(f"/api/datasets/{dataset_id}", headers=headers).json()
        check(detail["dataset"]["row_count"] == len(ROWS), "its rows are the pulled rows")
        check(detail["dataset_version"] == 2, "and its current version is v2")

        # And the lineage shows the pull as the operation it was.
        lineage = client.get(f"/api/v1/datasets/{dataset_id}/lineage", headers=headers).json()
        kinds = [
            (entry["version"], entry["produced_by"]["type"] if entry["produced_by"] else "import")
            for entry in lineage["versions"]
        ]
        check(kinds == [(1, "import"), (2, "connection_sync")],
              f"the lineage shows both the import and the sync (got {kinds})")

        history = client.get(f"/api/v1/connections/{connection_id}/syncs", headers=headers).json()
        check(len(history["syncs"]) == 2, "each pull is recorded in the history")

        listing = client.get("/api/v1/connections", headers=headers).json()
        check(
            all("secret" not in connection for connection in listing["connections"]),
            "listing never carries a secret field",
        )
        check(
            "Bearer token-123" not in json.dumps(listing),
            "and never carries the credential's value",
        )

        server.shutdown()


def _case_unreachable_source() -> None:
    print("\n6) An unreachable source is recorded, not invented")
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"full_name": "Asha Mwangi", "email": "conn2@example.com", "password": "secret123"},
        )
        token = client.post(
            "/api/auth/login", json={"email": "conn2@example.com", "password": "secret123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # A port with nothing listening: the connection must fail cleanly.
        dead = client.post(
            "/api/v1/connections",
            json={
                "name": "Dead API",
                "kind": "rest",
                "config": {"url": "http://127.0.0.1:1/rows"},
            },
            headers=headers,
        ).json()
        check(dead["connection"]["status"] == "error", "a dead endpoint is saved as an error")
        check(bool(dead["connection"]["last_error"]), "with the reason recorded")

        # A database that cannot be reached is a readable instruction,
        # not a stack trace: either the driver is missing (when this is
        # run where psycopg is absent) or the host refused us.
        ghost = client.post(
            "/api/v1/connections",
            json={
                "name": "Ghost DB",
                "kind": "postgres",
                "config": {
                    "host": "db.example.invalid",
                    "port": 5432,
                    "database": "app",
                    "user": "reader",
                    "table": "public.rows",
                },
                "secret": "not-a-real-password",
            },
            headers=headers,
        ).json()
        message = (ghost["connection"]["last_error"] or "").lower()
        check(
            "host" in message or "psycopg" in message or "driver" in message,
            f"an unreachable database says what to check ({message[:70]})",
        )
        check(ghost["connection"]["status"] == "error", "and is recorded as an error")


def _case_scheduled_sync_due() -> None:
    print("\n7) A scheduled connection becomes due on time")
    from app.models import DataConnection
    from app.services import connection_service
    from app.database import SessionLocal

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"full_name": "Asha Mwangi", "email": "conn3@example.com", "password": "secret123"},
        )
        token = client.post(
            "/api/auth/login", json={"email": "conn3@example.com", "password": "secret123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        db = SessionLocal()
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        scheduled = DataConnection(
            user_id=user_id,
            name="Hourly",
            kind="rest",
            config={"url": "http://127.0.0.1:1/rows"},
            sync_every_minutes=60,
        )
        never = DataConnection(
            user_id=user_id,
            name="Unscheduled",
            kind="rest",
            config={"url": "http://127.0.0.1:1/rows"},
            sync_every_minutes=None,
        )
        db.add_all([scheduled, never])
        db.commit()
        due = connection_service.due_connections(db)
        names = [connection.name for connection in due]
        check("Hourly" in names, "a scheduled connection that never ran is due now")
        check("Unscheduled" not in names, "an unscheduled one is never due")

        # Once it has synced within the window, it is no longer due.
        scheduled.last_sync_at = connection_service._now()
        db.commit()
        due = [connection.name for connection in connection_service.due_connections(db)]
        check("Hourly" not in due, "and not while the last sync is inside its window")

        scheduled.status = "error"
        db.commit()
        due = [connection.name for connection in connection_service.due_connections(db)]
        check("Hourly" in due, "a failed pull retries on the next window")

        # A reader only ever sees their own connections due.
        due_endpoint = client.get("/api/v1/connections/due", headers=headers).json()
        check(
            all(item["name"] != "Unscheduled" for item in due_endpoint["due"]),
            "the due endpoint returns only the reader's connections",
        )
        db.close()


def main() -> int:
    print("DATA CONNECTION TESTS")
    _case_credential_encryption()
    _case_query_limit_guard()
    _case_rest_shapes()
    _case_validation()
    _case_sync_writes_a_version()
    _case_unreachable_source()
    _case_scheduled_sync_due()
    print(f"\nALL CONNECTION TESTS PASSED ({PASSED} checks)")
    return 0


def test_connections() -> None:
    """pytest entry point: same run as ``python tests/connections_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
