"""Admin portal tests (master prompt 31 / F.1-F.15).

The point of these tests is the security boundary. They assert, against the
running API rather than against helper functions, that:

* an ordinary user and an organization ``admin`` both get 403 from every admin
  route - the platform ladder is genuinely separate from the org ladder;
* ``admin_viewer`` can read but cannot mutate, and only a ``super_admin`` can
  change a platform role;
* the platform cannot be locked out of its own admin portal;
* a suspension takes effect on the very next request, not at token expiry;
* every state change is written to an append-only audit log, and the audit log
  has no write or delete route.

Runs against a temporary database + storage. Also discoverable by pytest.

Run it with:  python tests/admin_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="admin_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "admin-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    PLATFORM_ROLE_ADMIN,
    PLATFORM_ROLE_SUPER_ADMIN,
    PLATFORM_ROLE_VIEWER,
    AuditLog,
    Dataset,
    User,
)

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def register(client, name, email, password="secret123"):
    r = client.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    token = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, r.json()["id"]


def promote(user_id: int, role: str) -> None:
    """Set a platform role directly, standing in for a real super-admin edit."""
    db = SessionLocal()
    try:
        target = db.get(User, user_id)
        target.system_role = role
        db.commit()
    finally:
        db.close()


def main() -> int:
    print(f"Test workspace: {TEST_ROOT}\n")

    with TestClient(app) as client:
        print("1) The platform ladder is separate from the organization ladder")
        h_plain, id_plain = register(client, "Plain User", "plain@example.com")
        h_viewer, id_viewer = register(client, "Support Viewer", "viewer@example.com")
        h_admin, id_admin = register(client, "Platform Admin", "padmin@example.com")
        h_super, id_super = register(client, "Super Admin", "super@example.com")
        promote(id_viewer, PLATFORM_ROLE_VIEWER)
        promote(id_admin, PLATFORM_ROLE_ADMIN)
        promote(id_super, PLATFORM_ROLE_SUPER_ADMIN)

        # An organization admin must not inherit platform authority. This is the
        # specific confusion the separate ladder exists to prevent, so it is
        # checked with a real org-admin membership rather than assumed.
        h_org = h_plain
        h_orgadmin, _id_orgadmin = register(
            client, "Org Admin", "orgadmin@example.com"
        )
        r = client.post(
            "/api/v1/organizations",
            json={"name": "Acme", "slug": "acme"},
            headers=h_org,
        )
        check(r.status_code == 201, "org owner creates an organization")
        org_id = r.json()["id"]
        r = client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "orgadmin@example.com", "role": "admin"},
            headers=h_org,
        )
        check(r.status_code in (200, 201), "a member is added to the organization")

        r = client.get("/api/v1/admin/overview", headers=h_orgadmin)
        check(r.status_code == 403,
              "an organization admin is refused platform access")
        r = client.get("/api/v1/admin/users", headers=h_orgadmin)
        check(r.status_code == 403, "user list is closed to an organization admin")
        r = client.get("/api/v1/admin/overview", headers=h_admin)
        check(r.status_code == 200, "a platform admin reads the overview")
        r = client.get("/api/v1/admin/me", headers=h_viewer)
        check(r.status_code == 200, "an admin viewer can confirm its own access")
        check(r.json().get("system_role") == "admin_viewer",
              "the role is a structured field, not prose to be parsed")
        check(r.json().get("status") == "active",
              "the shell also reports the account status")
        r = client.get("/api/v1/admin/me", headers=h_org)
        check(r.status_code == 403,
              "a non-staff member cannot even open the admin shell")

        print("\n1b) The profile tells the UI whether to offer the admin link")
        r = client.get("/api/auth/me", headers=h_org)
        check(r.status_code == 200, "a signed-in user reads its own profile")
        check(r.json().get("system_role") is None,
              "an ordinary member reports no platform role, so no admin link")
        r = client.get("/api/auth/me", headers=h_viewer)
        check(r.json().get("system_role") == "admin_viewer",
              "staff see their role on the profile without a 403 probe")

        print("\n2) Every admin route requires a platform role")
        for path in (
            "/api/v1/admin/overview",
            "/api/v1/admin/overview/alerts",
            "/api/v1/admin/users",
            "/api/v1/admin/organizations",
            "/api/v1/admin/datasets",
            "/api/v1/admin/audit",
        ):
            check(client.get(path, headers=h_org).status_code == 403,
                  f"{path} refuses a non-staff member")
            check(client.get(path).status_code == 401,
                  f"{path} refuses an anonymous caller")

        print("\n3) A viewer can read but never mutate")
        r = client.get("/api/v1/admin/users", headers=h_viewer)
        check(r.status_code == 200, "viewer reads the user list")
        check(r.json()["total"] >= 4, "the user list shows the registered accounts")
        first = r.json()["items"][0]
        check("password_hash" not in first, "the user list never leaks a password hash")
        check("system_role" in first, "the user list reports the platform role")

        r = client.post(f"/api/v1/admin/users/{id_plain}/suspend", headers=h_viewer)
        check(r.status_code == 403, "viewer cannot suspend an account")
        r = client.patch(
            f"/api/v1/admin/users/{id_plain}",
            json={"full_name": "Renamed By Viewer"},
            headers=h_viewer,
        )
        check(r.status_code == 403, "viewer cannot edit an account")
        r = client.post(f"/api/v1/admin/users/{id_plain}/reactivate", headers=h_viewer)
        check(r.status_code == 403, "viewer cannot reactivate an account")

        print("\n4) Only a super admin may change platform roles")
        r = client.patch(
            f"/api/v1/admin/users/{id_plain}",
            json={"system_role": PLATFORM_ROLE_VIEWER},
            headers=h_admin,
        )
        check(r.status_code == 403, "a platform admin cannot grant platform roles")
        r = client.patch(
            f"/api/v1/admin/users/{id_plain}",
            json={"system_role": PLATFORM_ROLE_VIEWER},
            headers=h_super,
        )
        check(r.status_code == 200, "a super admin can grant a platform role")
        check(r.json()["system_role"] == PLATFORM_ROLE_VIEWER,
              "the granted role is persisted")
        client.patch(
            f"/api/v1/admin/users/{id_plain}",
            json={"system_role": None},
            headers=h_super,
        )
        r = client.get(f"/api/v1/admin/users/{id_plain}", headers=h_super)
        check(r.json()["system_role"] is None,
              "a platform role can be revoked by sending an explicit null")
        r = client.get("/api/v1/admin/overview", headers=h_org)
        check(r.status_code == 403,
              "a revoked account loses platform access immediately")

        print("\n5) Suspension takes effect immediately")
        r = client.post(
            f"/api/v1/admin/users/{id_plain}/suspend",
            params={"reason": "testing enforcement"},
            headers=h_admin,
        )
        check(r.status_code == 200, "platform admin suspends an account")
        check(r.json()["status"] == "suspended", "the account is reported suspended")
        check(r.json()["suspended_reason"] == "testing enforcement",
              "the suspension reason is recorded")
        r = client.get("/api/datasets", headers=h_org)
        check(r.status_code == 403,
              "a suspended account cannot use an already-issued token")
        check(r.status_code != 404,
              "the suspension is enforced, not merely an unknown route")
        r = client.post(
            "/api/auth/login",
            json={"email": "plain@example.com", "password": "secret123"},
        )
        check(r.status_code == 403, "a suspended account cannot sign in again")

        r = client.post(f"/api/v1/admin/users/{id_plain}/reactivate", headers=h_admin)
        check(r.status_code == 200, "platform admin reactivates the account")
        r = client.get("/api/auth/me", headers=h_org)
        check(r.status_code == 200, "the account works again once reactivated")

        print("\n6) The platform cannot lock itself out")
        r = client.post(f"/api/v1/admin/users/{id_super}/suspend", headers=h_super)
        check(r.status_code == 400, "an admin cannot suspend their own account")
        r = client.patch(
            f"/api/v1/admin/users/{id_super}",
            json={"system_role": PLATFORM_ROLE_ADMIN},
            headers=h_super,
        )
        check(r.status_code == 400, "an admin cannot demote their own account")

        # The reachable route to stripping the last super admin is another admin
        # suspending them, because a platform admin may suspend but may not
        # demote. That must be refused too, or the portal can be locked shut.
        r = client.post(f"/api/v1/admin/users/{id_super}/suspend", headers=h_admin)
        check(r.status_code == 409,
              "the last active super admin cannot be suspended by another admin")
        r = client.get("/api/v1/admin/overview", headers=h_admin)
        check(r.status_code == 200, "the super admin account is still usable")

        # Once a second super admin exists, the guard stops blocking, which
        # proves it is a real precondition and not a blanket refusal.
        client.patch(
            f"/api/v1/admin/users/{id_viewer}",
            json={"system_role": PLATFORM_ROLE_SUPER_ADMIN},
            headers=h_super,
        )
        r = client.post(f"/api/v1/admin/users/{id_super}/suspend", headers=h_admin)
        check(r.status_code == 200,
              "a super admin may be suspended once another one exists")
        client.post(f"/api/v1/admin/users/{id_super}/reactivate", headers=h_admin)

        print("\n7) The audit log records what happened")
        r = client.get("/api/v1/admin/audit", headers=h_super)
        check(r.status_code == 200, "the audit log is readable")
        body = r.json()
        check(body["total"] > 0, "the audit log has entries")
        actions = {entry["action"] for entry in body["items"]}
        check("auth.login" in actions, "successful logins are recorded")
        check("admin.user.suspend" in actions, "a suspension is recorded")
        check("admin.user.reactivate" in actions, "a reactivation is recorded")
        check("admin.user.update" in actions, "a role change is recorded")

        r = client.get(
            "/api/v1/admin/audit", params={"action": "admin.user.suspend"},
            headers=h_super,
        )
        check(r.status_code == 200 and r.json()["total"] >= 1,
              "the audit log filters by action")
        suspends = r.json()["items"]
        check(
            any(e["metadata"].get("target_email") == "plain@example.com" for e in suspends),
            "the entry records which account was targeted",
        )
        check(
            any(e["metadata"].get("reason") == "testing enforcement" for e in suspends),
            "the entry records why the account was suspended",
        )
        check(
            all(e["resource"] == "user" for e in suspends),
            "the entry names the resource it acted on",
        )
        updates = client.get(
            "/api/v1/admin/audit", params={"action": "admin.user.update"},
            headers=h_super,
        ).json()["items"]
        check(
            any("system_role" in e["metadata"].get("changes", []) for e in updates),
            "a role change is recorded as a role change",
        )

        r = client.get(
            "/api/v1/admin/audit", params={"result": "failure"}, headers=h_super
        )
        check(r.status_code == 200, "the audit log filters by result")
        r = client.get(
            "/api/v1/admin/audit", params={"search": "plain@example.com"},
            headers=h_super,
        )
        check(r.status_code == 200 and r.json()["total"] >= 1,
              "the audit log searches by actor email")

        # A failed login by someone who never had a session is the row that
        # matters most, and it has no user_id to hang off.
        client.post(
            "/api/auth/login", json={"email": "ghost@example.com", "password": "wrong"}
        )
        r = client.get(
            "/api/v1/admin/audit",
            params={"action": "auth.login.failed"},
            headers=h_super,
        )
        failed = r.json()["items"]
        check(len(failed) >= 1, "a failed login attempt is recorded")
        check(failed[0]["user_id"] is None,
              "a failed login has no user, because nobody signed in")
        check(failed[0]["actor_email"] == "ghost@example.com",
              "a failed login still records the attempted identity")

        r = client.get("/api/v1/admin/audit", headers=h_admin)
        check(r.status_code == 200, "a platform admin can read the audit log")
        r = client.get("/api/v1/admin/audit", headers=h_org)
        check(r.status_code == 403, "a non-staff member cannot read the audit log")

        print("\n8) The audit log cannot be edited from the admin API")
        paths = app.openapi()["paths"]
        write_methods = {
            method.upper()
            for path, ops in paths.items()
            if path.startswith("/api/v1/admin/audit")
            for method in ops
            if method.upper() not in {"GET", "HEAD", "OPTIONS"}
        }
        check(not write_methods,
              "no POST/PUT/PATCH/DELETE route exists for audit entries")

        db = SessionLocal()
        try:
            rows = db.query(AuditLog).all()
            check(len(rows) > 0, "entries are really persisted in the database")
            check(all(row.action for row in rows), "every entry names an action")
        finally:
            db.close()

        print("\n9) Operational views expose metadata, never dataset contents")
        # A real row has to exist here. Asserting only the status code of a list
        # endpoint proves nothing about the serializer, which is how a wrong
        # column name survives a green suite and only fails in the browser.
        db = SessionLocal()
        try:
            owner_id = db.query(User.id).filter(User.email == "plain@example.com").scalar()
            db.add(
                Dataset(
                    user_id=owner_id,
                    original_filename="admin_visible.csv",
                    storage_path="data/admin_visible.csv",
                    file_type="csv",
                    row_count=42,
                    column_count=3,
                    status="analyzed",
                )
            )
            db.commit()
        finally:
            db.close()

        r = client.get("/api/v1/admin/datasets", headers=h_super)
        check(r.status_code == 200, "the dataset admin view loads")
        rows = r.json()["items"]
        check(len(rows) >= 1, "the dataset admin view returns at least one row")
        item = next(
            (d for d in rows if d["original_filename"] == "admin_visible.csv"), None
        )
        check(item is not None, "the dataset appears in the admin view")
        check(item["created_at"] is not None,
              "a dataset reports when it was uploaded")
        check(item["row_count"] == 42, "the row count is serialized")
        check(item["column_count"] == 3, "the column count is serialized")
        check(item["status"] == "analyzed", "the status is serialized")
        check("storage_path" not in item,
              "the dataset view exposes no filesystem path")

        r = client.get("/api/v1/admin/organizations", headers=h_super)
        check(r.status_code == 200, "the organization admin view loads")
        check(any(o["id"] == org_id for o in r.json()["items"]),
              "the organization appears in the admin view")
        item = next(o for o in r.json()["items"] if o["id"] == org_id)
        check(item["member_count"] >= 1, "organization member count is reported")
        check("storage_path" not in item,
              "the organization view exposes no filesystem path")

        r = client.get("/api/v1/admin/overview", headers=h_super)
        check(r.status_code == 200, "the overview aggregates real numbers")
        overview = r.json()
        check(overview["total_users"] >= 4, "overview counts the users")
        check(overview["organizations"] >= 1, "overview counts the organizations")
        check(overview["platform_staff"] >= 2, "overview counts the platform staff")
        check(overview["active_users"] == overview["total_users"] - overview["suspended_users"],
              "active + suspended accounts account for every user")

        r = client.get("/api/v1/admin/overview/alerts", headers=h_super)
        check(r.status_code == 200, "the alert panel loads")
        check(isinstance(r.json()["alerts"], list) and r.json()["alerts"],
              "the alert panel always reports something")
        check(all(a.get("level") in {"danger", "warning", "info"} for a in r.json()["alerts"]),
              "alerts carry a known severity")

        print("\n10) Pagination is clamped")
        r = client.get(
            "/api/v1/admin/users", params={"page_size": 5000}, headers=h_super
        )
        check(r.status_code == 422, "an oversized page size is rejected outright")
        r = client.get("/api/v1/admin/users", params={"page": 0}, headers=h_super)
        check(r.status_code == 422, "a zero page is rejected outright")
        r = client.get("/api/v1/admin/users", params={"page_size": 2}, headers=h_super)
        check(len(r.json()["items"]) <= 2, "the page size is honoured")
        check(r.json()["total"] >= 4, "the total reflects all matches, not the page")

        print("\n11) Unknown accounts and empty updates are handled")
        r = client.patch(
            "/api/v1/admin/users/999999", json={"full_name": "Ghost"},
            headers=h_super,
        )
        check(r.status_code == 404, "patching an unknown user returns 404")
        r = client.patch(f"/api/v1/admin/users/{id_admin}", json={}, headers=h_super)
        check(r.status_code == 400, "an empty update is refused rather than silently ok")

    print(f"\nALL ADMIN TESTS PASSED ({PASSED} checks)")
    return 0


def test_admin_portal() -> None:
    """pytest entry point: same run as ``python tests/admin_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
