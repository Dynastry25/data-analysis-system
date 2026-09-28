#!/usr/bin/env python
"""Bring an existing development database onto the Alembic chain.

Why this exists
---------------
This project calls ``Base.metadata.create_all()`` on startup. That creates
missing tables but never alters tables that already exist, and it never writes
an ``alembic_version`` row. A developer database created before the admin
migration therefore looks "migrated" to the app while missing every admin
column, and the first login fails with::

    no such column: users.system_role

The repair is a stamp at the last revision the data actually matches, then a
normal upgrade. The script refuses to touch anything it cannot verify, and
takes a backup first.

Usage
-----
    python -m tools.adopt_existing_db --stamp 7c3d9f2a41b8
    python -m tools.adopt_existing_db --verify
    python -m tools.adopt_existing_db --stamp 7c3d9f2a41b8 --apply

Without ``--apply`` it only reports what it would do.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# Columns that revision b6e1f0a9c743 introduced. A database missing any of them
# is older than that revision and must be stamped before it.
POST_BASELINE_MARKERS = {
    "dataset_versions": {"created_by"},
    "analysis_runs": {"notes"},
    "charts": {"analysis_run_id"},
    "exported_reports": {"format"},
}

# Columns that revision c3d8a1f70e25 introduced. A database that already has
# them has had the admin migration applied by other means.
ADMIN_MARKERS = {
    "users": {"system_role", "status", "suspended_at", "suspended_reason", "last_active_at"},
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA index_list({table})")}


def _revision(conn: sqlite3.Connection) -> str | None:
    if "alembic_version" not in _tables(conn):
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def _missing_admin(conn: sqlite3.Connection) -> set[str]:
    have = _columns(conn, "users")
    return ADMIN_MARKERS["users"] - have


def _looks_pre_provenance(conn: sqlite3.Connection) -> bool:
    for table, wanted in POST_BASELINE_MARKERS.items():
        if wanted - _columns(conn, table):
            return True
    return False


def _report(db: Path) -> dict:
    conn = sqlite3.connect(db)
    try:
        return {
            "tables": _tables(conn),
            "revision": _revision(conn),
            "missing_admin": _missing_admin(conn),
            "pre_provenance": _looks_pre_provenance(conn),
            "user_indexes": _indexes(conn, "users"),
            "audit_indexes": _indexes(conn, "audit_logs") if "audit_logs" in _tables(conn) else set(),
            "users": conn.execute("SELECT count(*) FROM users").fetchone()[0]
            if "users" in _tables(conn)
            else 0,
        }
    finally:
        conn.close()


def _backup(db: Path) -> Path:
    stamp = "pre-alembic-adopt"
    target = db.with_name(f"{db.name}.{stamp}.bak")
    index = 1
    while target.exists():
        target = db.with_name(f"{db.name}.{stamp}.{index}.bak")
        index += 1
    shutil.copy2(db, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="app.db", help="SQLite file (default: app.db)")
    parser.add_argument(
        "--stamp",
        help="revision whose schema the data already matches, e.g. 7c3d9f2a41b8",
    )
    parser.add_argument("--apply", action="store_true", help="actually write changes")
    parser.add_argument("--verify", action="store_true", help="only report the state")
    args = parser.parse_args(argv)

    db = Path(args.db)
    if not db.exists():
        print(f"no database at {db}", file=sys.stderr)
        return 1

    state = _report(db)
    print(f"database            : {db.resolve()}")
    print(f"alembic revision    : {state['revision'] or 'none (never stamped)'}")
    print(f"users               : {state['users']}")
    print(f"admin columns missing: {sorted(state['missing_admin']) or 'none'}")
    print(
        "pre-provenance      : "
        + ("yes, older than b6e1f0a9c743" if state["pre_provenance"] else "no")
    )

    if args.verify:
        return 0

    if state["revision"]:
        print(
            f"\nalready stamped at {state['revision']}; use `alembic upgrade head` instead.",
        )
        return 0

    if not args.stamp:
        print("\nno --stamp given, so nothing changed.", file=sys.stderr)
        return 1

    expected_stamp = "7c3d9f2a41b8" if state["pre_provenance"] else None
    if expected_stamp and args.stamp != expected_stamp:
        print(
            f"\nrefusing: this database predates b6e1f0a9c743, so the only correct\n"
            f"stamp is {expected_stamp}, not {args.stamp}.",
            file=sys.stderr,
        )
        return 1

    if not state["missing_admin"]:
        print(
            "\nrefusing: the admin columns are already present, so this database was\n"
            "not created by create_all() against the pre-admin model. Investigate\n"
            "before stamping.",
            file=sys.stderr,
        )
        return 1

    if not args.apply:
        print(
            f"\nwould back up {db.name}, stamp {args.stamp}, then `alembic upgrade head`.\n"
            "Re-run with --apply to do it."
        )
        return 0

    backup = _backup(db)
    print(f"\nbackup              : {backup}")

    from alembic import command
    from alembic.config import Config

    # ``migrations/env.py`` builds its engine from ``app.database``, which reads
    # ``DATABASE_URL``. Setting only ``sqlalchemy.url`` in the config would be
    # silently ignored, and the migration would run against the *app's*
    # database while this script reported on a different file. The URL is
    # verified against the engine before anything is written.
    import os

    from app.database import engine as app_engine

    wanted = f"sqlite:///{db.resolve().as_posix()}"
    if str(app_engine.url) != wanted:
        print(
            f"\nrefusing: the app engine points at {app_engine.url}, not {wanted}.\n"
            "Set DATABASE_URL to this file and re-run, so that the migration and\n"
            "this report cannot disagree.",
            file=sys.stderr,
        )
        return 1

    os.environ["DATABASE_URL"] = wanted

    config = Config("alembic.ini")
    command.stamp(config, args.stamp)
    print(f"stamped             : {args.stamp}")
    command.upgrade(config, "head")
    print("upgraded            : head")

    after = _report(db)

    from alembic.script import ScriptDirectory
    from alembic.config import Config as AlembicConfig

    head = ScriptDirectory.from_config(AlembicConfig("alembic.ini")).get_current_head()

    print(f"\nalembic revision    : {after['revision']}")
    print(f"admin columns missing: {sorted(after['missing_admin']) or 'none'}")
    print(f"users               : {after['users']}")
    if after["missing_admin"] or after["revision"] != head:
        print(f"\nFAILED: expected revision {head}, found {after['revision']}.", file=sys.stderr)
        return 1
    print(f"\nOK: the database is at head ({head}) and every admin column exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
