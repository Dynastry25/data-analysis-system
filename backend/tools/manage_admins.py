"""Grant, list and revoke platform roles from the command line.

Why this exists
---------------
The admin portal is unreachable until somebody holds a platform role, and the
first role cannot come from the portal itself, because the portal requires a
role to open. There has to be a way in from outside the application, or the
feature is only usable by editing rows by hand.

This tool is that way in. It is deliberately **not** an HTTP endpoint: a route
that can promote its own caller is a privilege escalation, and a route that
cannot promote anyone is not an answer. Only an operator with shell access and
database credentials runs this.

What it will not do
-------------------
* Promote a suspended account. Reactivate it first, deliberately.
* Remove the last super admin. A platform with no one able to manage roles
  cannot be recovered through the UI.
* Invent a role that is not in the ladder.

Usage
-----
    python -m tools.manage_admins list
    python -m tools.manage_admins grant demo@example.com --role super_admin
    python -m tools.manage_admins grant a@x.com --role platform_admin
    python -m tools.manage_admins revoke a@x.com
"""

from __future__ import annotations

import argparse
import sys

from app.database import SessionLocal
from app.models import (
    PLATFORM_ROLE_ADMIN,
    PLATFORM_ROLE_SUPER_ADMIN,
    PLATFORM_ROLE_VIEWER,
    User,
)

ROLES = {
    PLATFORM_ROLE_VIEWER,
    PLATFORM_ROLE_ADMIN,
    PLATFORM_ROLE_SUPER_ADMIN,
}

ROLE_ORDER = {
    PLATFORM_ROLE_VIEWER: 1,
    PLATFORM_ROLE_ADMIN: 2,
    PLATFORM_ROLE_SUPER_ADMIN: 3,
}


def fail(message: str) -> None:
    print(f"refusing: {message}")
    raise SystemExit(1)


def count_active_super_admins(session) -> int:
    from sqlalchemy import func, select

    return session.execute(
        select(func.count())
        .select_from(User)
        .where(User.system_role == PLATFORM_ROLE_SUPER_ADMIN)
        .where(User.status == "active")
    ).scalar_one()


def cmd_list(_args) -> int:
    session = SessionLocal()
    try:
        rows = session.query(User).order_by(User.id).all()
        if not rows:
            print("no users at all")
            return 0
        print(f"{'id':>4}  {'role':<16} {'status':<10} email")
        for user in rows:
            role = user.system_role or "-"
            print(f"{user.id:>4}  {role:<16} {user.status:<10} {user.email}")
        active = count_active_super_admins(session)
        print(f"\n{active} active super admin(s).")
        if active == 0:
            print(
                "Nobody can open the admin portal. To fix that:\n"
                f"    python -m tools.manage_admins grant <email> --role super_admin"
            )
        return 0
    finally:
        session.close()


def cmd_grant(args) -> int:
    if args.role not in ROLES:
        fail(f"{args.role!r} is not a platform role. Choose from {sorted(ROLES)}.")

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == args.email).first()
        if user is None:
            fail(
                f"no account for {args.email}. Register the account in the app first, "
                "then grant the role."
            )
        if user.status != "active":
            fail(
                f"{user.email} is {user.status}. Reactivate the account before giving "
                "it a platform role, so suspension is never silently undone."
            )
        if user.system_role == args.role:
            print(f"{user.email} already holds {args.role}.")
            return 0

        previous = user.system_role
        if previous == PLATFORM_ROLE_SUPER_ADMIN and args.role != PLATFORM_ROLE_SUPER_ADMIN:
            if count_active_super_admins(session) <= 1:
                fail(
                    "that is the only active super admin, and demoting it would leave "
                    "nobody able to manage platform roles"
                )

        user.system_role = args.role
        session.commit()
        print(f"{user.email}: {previous or 'no role'} -> {args.role}")
        print(
            f"\nSign in again so the app picks up the new role, then open /admin."
        )
        return 0
    finally:
        session.close()


def cmd_revoke(args) -> int:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == args.email).first()
        if user is None:
            fail(f"no account for {args.email}")
        if user.system_role is None:
            print(f"{user.email} already has no platform role.")
            return 0
        if user.system_role == PLATFORM_ROLE_SUPER_ADMIN:
            if count_active_super_admins(session) <= 1:
                fail(
                    "that is the only active super admin; promoting someone else "
                    "first is the only way to hand over"
                )
        previous = user.system_role
        user.system_role = None
        session.commit()
        print(f"{user.email}: {previous} -> no role")
        return 0
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show every user and their platform role").set_defaults(
        func=cmd_list
    )

    grant = sub.add_parser("grant", help="give an account a platform role")
    grant.add_argument("email")
    grant.add_argument(
        "--role",
        default=PLATFORM_ROLE_SUPER_ADMIN,
        choices=sorted(ROLES, key=lambda r: ROLE_ORDER[r]),
        help="defaults to super_admin, which is the first door into the portal",
    )
    grant.set_defaults(func=cmd_grant)

    revoke = sub.add_parser("revoke", help="remove a platform role")
    revoke.add_argument("email")
    revoke.set_defaults(func=cmd_revoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
