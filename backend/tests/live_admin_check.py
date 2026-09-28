"""Check the admin portal against a running server and a real database.

The other suites use a throwaway database behind ``TestClient``, so they cannot
show whether the database on disk is reachable or whether the responses match
what a browser will parse. This one logs in over HTTP and walks every admin
endpoint. It exists because a wrong column name in a list serializer passed the
whole suite and only failed here.

It is deliberately awkward to run by accident. It needs ``--confirm``, it
refuses a non-localhost base URL, and it removes the super admin it promotes.

Usage
-----
    # terminal 1
    .\\venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8123
    # terminal 2
    .\\venv\\Scripts\\python.exe tests\\live_admin_check.py --confirm
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import urllib.parse

import httpx

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}

PATHS = (
    "/v1/admin/me",
    "/v1/admin/overview",
    "/v1/admin/overview/alerts",
    "/v1/admin/users",
    "/v1/admin/organizations",
    "/v1/admin/datasets",
    "/v1/admin/audit",
)


def fail(message: str) -> None:
    print(f"FAILED: {message}")
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8123/api"))
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="required, because this writes to the database",
    )
    args = parser.parse_args()

    if not args.confirm:
        print("refusing to write without --confirm")
        return 1

    base = args.base_url.rstrip("/")
    host = urllib.parse.urlparse(base).hostname or ""
    if host not in ALLOWED_HOSTS:
        fail(f"refusing to run against {base}: only {sorted(ALLOWED_HOSTS)} are allowed")

    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    email = f"adminsmoke-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(24)
    user_id: int | None = None

    session = SessionLocal()
    try:
        user = User(
            full_name="Admin Live Check",
            email=email,
            password_hash=hash_password(password),
            system_role="super_admin",
        )
        session.add(user)
        session.commit()
        user_id = user.id
        print(f"promoted a temporary super admin: {email}")
    finally:
        session.close()

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(f"{base}/auth/login", json={"email": email, "password": password})
            print(f"login                    -> {r.status_code}")
            if r.status_code != 200:
                fail(f"login failed: {r.text[:400]}")
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.get(f"{base}/auth/me", headers=headers)
            role = r.json().get("system_role")
            print(f"auth/me                  -> {r.status_code} system_role={role}")
            if r.status_code != 200 or role != "super_admin":
                fail("the profile does not report the platform role")

            for path in PATHS:
                r = client.get(f"{base}{path}", headers=headers)
                print(f"{path:<25} -> {r.status_code}")
                if r.status_code != 200:
                    fail(f"{path} returned {r.status_code}: {r.text[:400]}")

            me = client.get(f"{base}/v1/admin/me", headers=headers).json()
            print(f"admin/me payload keys    -> {sorted(me)}")
            if me.get("system_role") != "super_admin" or me.get("status") != "active":
                fail("admin/me is missing a structured role or status")
    finally:
        # A promoted account with a known password must not outlive the check.
        session = SessionLocal()
        try:
            if user_id is not None:
                removed = session.query(User).filter(User.id == user_id).delete()
                session.commit()
                print(f"removed the temporary admin ({removed} row)")
        finally:
            session.close()

    print("\nOK: the running server serves the whole admin portal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
