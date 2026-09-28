"""Exercise the admin migration on databases with different histories.

Two histories have to work, and neither may be guessed at:

* a fresh database built purely by migrations;
* a database that ``create_all()`` built from the *new* model while the tables
  were still at the pre-admin shape, so ``audit_logs`` already exists.

The second case is the one that breaks a naive ``create_table``, because the
table is already there.

Every case runs in its own subprocess. ``app.database.engine`` is bound to
``DATABASE_URL`` at import time, so a database cannot be swapped after the
import has happened, and on Windows an inherited connection also blocks the
temporary directory from being removed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import sqlite3
import tempfile
from pathlib import Path

FAILURES: list[str] = []
PASSES = 0

ADMIN_COLUMNS = {
    "system_role",
    "status",
    "suspended_at",
    "suspended_reason",
    "last_active_at",
}
AUDIT_INDEXES = {
    "ix_audit_logs_user_id",
    "ix_audit_logs_organization_id",
    "ix_audit_logs_action",
    "ix_audit_logs_resource",
    "ix_audit_logs_result",
    "ix_audit_logs_created_at",
}


def check(condition: bool, label: str) -> None:
    global PASSES
    if condition:
        PASSES += 1
        print(f"  [ok] {label}")
    else:
        FAILURES.append(label)
        print(f"  [FAIL] {label}")


def tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def columns(db: Path, table: str) -> set[str]:
    if table not in tables(db):
        return set()
    conn = sqlite3.connect(db)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def indexes(db: Path, table: str) -> set[str]:
    if table not in tables(db):
        return set()
    conn = sqlite3.connect(db)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA index_list({table})")}
    finally:
        conn.close()


def revision(db: Path) -> str | None:
    if "alembic_version" not in tables(db):
        return None
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def run(case: str, db: Path, env_extra: dict[str, str] | None = None) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db.resolve().as_posix()}"
    env["PYTHONPATH"] = "."
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, __file__, "--worker", case, str(db)],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-15:])
        check(False, f"worker {case} exited {result.returncode}\n{tail}")


# --------------------------------------------------------------------------
# workers
# --------------------------------------------------------------------------
def worker_alembic(command: str, revision_arg: str) -> None:
    from alembic import command as alembic_command
    from alembic.config import Config

    config = Config("alembic.ini")
    getattr(alembic_command, command)(config, revision_arg)


def worker_create_all() -> None:
    """Build the whole schema from the current model, the way startup does."""
    import app.models  # noqa: F401 - registers every table on Base
    from app.database import Base, engine

    Base.metadata.create_all(engine)


def worker_rollback_user_columns(db: Path) -> None:
    """Return `users` to its pre-admin shape, leaving audit_logs in place."""
    conn = sqlite3.connect(db)
    try:
        for index in ("ix_users_status", "ix_users_system_role"):
            conn.execute(f"DROP INDEX IF EXISTS {index}")
        for column in ADMIN_COLUMNS:
            conn.execute(f"ALTER TABLE users DROP COLUMN {column}")
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------
def case_fresh_database(db: Path) -> None:
    print("\n1) A database built only by migrations")
    run("alembic-upgrade-head", db)
    check(revision(db) is not None, "the fresh database is stamped at head")
    check(ADMIN_COLUMNS <= columns(db, "users"), "every admin column exists on users")
    check("audit_logs" in tables(db), "audit_logs is created")
    check(AUDIT_INDEXES <= indexes(db, "audit_logs"), "every audit index exists")

    run("alembic-downgrade-baseline", db)
    check(
        not (ADMIN_COLUMNS & columns(db, "users")),
        "downgrade removes the admin columns from users",
    )
    check("audit_logs" not in tables(db), "downgrade drops audit_logs")

    run("alembic-upgrade-head", db)
    check(ADMIN_COLUMNS <= columns(db, "users"), "re-upgrade restores the admin columns")


def case_create_all_database(db: Path) -> None:
    """The history that breaks a naive create_table: audit_logs already exists.

    This mirrors the real development database. A developer started on an early
    revision, so ``users`` and ``dataset_versions`` were built from that older
    model. Later they pulled the admin model and the app ran ``create_all()``
    on startup, which created the brand new ``audit_logs`` table and left every
    table that already existed exactly as it was. So the database is at the
    pre-admin user shape, with an ``audit_logs`` already in place.
    """
    print("\n2) A database create_all() touched while the tables were older")
    run("alembic-upgrade-baseline", db)
    check(
        not (ADMIN_COLUMNS & columns(db, "users")),
        "the baseline leaves users without the admin columns",
    )
    check("audit_logs" not in tables(db), "the baseline has no audit_logs")

    # Startup behaviour: create missing tables, never alter existing ones.
    run("create-all", db)
    check("audit_logs" in tables(db), "create_all added the new audit_logs table")
    check(
        not (ADMIN_COLUMNS & columns(db, "users")),
        "create_all left the older users table untouched, as it always does",
    )
    check(
        "created_by" not in columns(db, "dataset_versions"),
        "create_all left the older dataset_versions untouched too",
    )

    run("alembic-stamp-baseline", db)
    check(revision(db) == "7c3d9f2a41b8", "stamped at the pre-admin revision")

    # The assertion that matters: the migration must not crash on a table that
    # create_all already made.
    run("alembic-upgrade-head", db)
    check(revision(db) is not None, "the migration survives a pre-existing audit_logs")
    check(ADMIN_COLUMNS <= columns(db, "users"), "the admin columns are added")
    check("audit_logs" in tables(db), "the existing audit_logs is left in place")
    check(AUDIT_INDEXES <= indexes(db, "audit_logs"), "its indexes are complete")

    run("alembic-downgrade-baseline", db)
    check("audit_logs" not in tables(db), "downgrade drops the table it did not create")
    check(
        not (ADMIN_COLUMNS & columns(db, "users")),
        "downgrade removes the columns it did add",
    )


def case_rerun_is_safe(db: Path) -> None:
    """Upgrade, downgrade, upgrade again. A migration that cannot round-trip is
    not finished, and this is the only way to find that out."""
    print("\n3) Upgrade, downgrade and upgrade again")
    run("alembic-upgrade-head", db)
    check(ADMIN_COLUMNS <= columns(db, "users"), "the first upgrade applies")
    run("alembic-downgrade-baseline", db)
    check(
        not (ADMIN_COLUMNS & columns(db, "users")), "the downgrade reverts the columns"
    )
    run("alembic-upgrade-head", db)
    check(ADMIN_COLUMNS <= columns(db, "users"), "the second upgrade applies again")
    check(revision(db) is not None, "the database ends at head")


CASES = {
    "alembic-upgrade-head": lambda db: worker_alembic("upgrade", "head"),
    "alembic-downgrade-baseline": lambda db: worker_alembic("downgrade", "7c3d9f2a41b8"),
    "alembic-stamp-baseline": lambda db: worker_alembic("stamp", "7c3d9f2a41b8"),
    "alembic-upgrade-baseline": lambda db: worker_alembic("upgrade", "7c3d9f2a41b8"),
    "create-all": lambda db: worker_create_all(),
    "rollback-user-columns": worker_rollback_user_columns,
}


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "--worker":
        CASES[argv[2]](Path(argv[3]))
        return 0

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        case_fresh_database(tmp / "fresh.db")
        case_create_all_database(tmp / "createall.db")
        case_rerun_is_safe(tmp / "roundtrip.db")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print(f"ALL MIGRATION CHECKS PASSED ({PASSES} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
