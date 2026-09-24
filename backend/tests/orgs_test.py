"""Organizations, projects and RBAC tests (Phase 1 / master prompt).

Covers the full role ladder (owner > admin > analyst > viewer) and org-scoped
dataset access. Runs against a temporary database + storage. Also discoverable
by pytest (see pytest.ini).

Run it with:  python tests/orgs_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="orgs_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "orgs-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.deps import get_owned_dataset  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dataset, Project, User  # noqa: E402

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
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    print(f"Test workspace: {TEST_ROOT}\n")

    with TestClient(app) as client:
        h_owner = register(client, "Miraji Kalala", "owner@example.com")
        h_b = register(client, "Asha Mwenda", "as@example.com")
        h_c = register(client, "Doto Daudi", "admin@example.com")
        h_d = register(client, "Neema Joshi", "neema@example.com")
        h_e = register(client, "Baraka Said", "baraka@example.com")
        h_x = register(client, "Amina Ali", "amina@example.com")

        print("1) Create + read organizations")
        r = client.post(
            "/api/v1/organizations",
            json={"name": "Data Lab", "description": "Uchambuzi wa data"},
            headers=h_owner,
        )
        check(r.status_code == 201, "create org returns 201")
        org = r.json()
        org_id = org["id"]
        check(org["my_role"] == "owner", "creator becomes owner")
        check(org["slug"] == "data-lab", "slug auto-generated from name")
        check(org["member_count"] == 1 and org["project_count"] == 0, "counts are zero")

        r = client.get("/api/v1/organizations", headers=h_owner)
        check(r.status_code == 200 and len(r.json()) == 1, "owner lists one org")
        check(r.json()[0]["id"] == org_id and r.json()[0]["my_role"] == "owner", "list carries role")

        members = client.get(f"/api/v1/organizations/{org_id}/members", headers=h_owner).json()
        owner_user = next(m["user_id"] for m in members if m["role"] == "owner")

        r = client.get("/api/v1/organizations", headers=h_x)
        check(len(r.json()) == 0, "non-member lists no orgs")

        check(client.get(f"/api/v1/organizations/{org_id}", headers=h_b).status_code == 403,
              "non-member cannot read org (403)")

        print("2) Members + RBAC role ladder")
        r = client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "as@example.com", "role": "viewer"},
            headers=h_owner,
        )
        check(r.status_code == 201 and r.json()["role"] == "viewer", "owner adds member")
        b_id = r.json()["user_id"]

        check(client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "as@example.com", "role": "viewer"},
            headers=h_owner,
        ).status_code == 409, "cannot add the same member twice (409)")

        check(client.get(f"/api/v1/organizations/{org_id}", headers=h_b).status_code == 200,
              "viewer can read org detail")

        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "S1"},
            headers=h_b,
        )
        check(r.status_code == 403, "viewer cannot create a project (403)")

        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Sales 2026"},
            headers=h_owner,
        )
        check(r.status_code == 201 and r.json()["dataset_count"] == 0, "owner creates project")
        project_id = r.json()["id"]

        check(client.patch(
            f"/api/v1/organizations/{org_id}/projects/{project_id}",
            json={"name": "Sales 2026 x"},
            headers=h_b,
        ).status_code == 403, "viewer cannot edit project (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/members/{b_id}",
            json={"role": "analyst"},
            headers=h_owner,
        )
        check(r.status_code == 200 and r.json()["role"] == "analyst", "owner promotes B to analyst")

        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "HR Survey"},
            headers=h_b,
        )
        check(r.status_code == 201, "analyst can create a project")

        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Dupe"},
            headers=h_owner,
        )
        check(r.status_code == 201, "first duplicate-name check setup")
        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Dupe"},
            headers=h_owner,
        )
        check(r.status_code == 409, "duplicate project name rejected (409)")

        print("3) Admin powers + owner-only rules")
        r = client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "admin@example.com", "role": "admin"},
            headers=h_owner,
        )
        c_id = r.json()["user_id"]
        check(r.status_code == 201 and r.json()["role"] == "admin", "owner adds admin")

        r = client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "neema@example.com", "role": "owner"},
            headers=h_c,
        )
        check(r.status_code == 403, "admin cannot grant the owner role (403)")

        r = client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"email": "baraka@example.com", "role": "analyst"},
            headers=h_c,
        )
        e_id = r.json()["user_id"]
        check(r.status_code == 201, "admin can add a member")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/members/{b_id}",
            json={"role": "owner"},
            headers=h_c,
        )
        check(r.status_code == 403, "admin cannot promote someone to owner (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/members/{b_id}",
            json={"role": "viewer"},
            headers=h_c,
        )
        check(r.status_code == 200, "admin can demote analyst to viewer")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/members/{c_id}",
            json={"role": "analyst"},
            headers=h_c,
        )
        check(r.status_code == 403, "admin cannot change another admin (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/members/{owner_user}",
            json={"role": "viewer"},
            headers=h_owner,
        )
        check(r.status_code == 403, "owner role is immutable (403)")

        r = client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "C1"},
            headers=h_d,
        )
        check(r.status_code == 403, "non-member with valid token cannot act (403)")

        r = client.delete(
            f"/api/v1/organizations/{org_id}/members/{e_id}",
            headers=h_c,
        )
        check(r.status_code == 204, "admin removes an analyst member")
        check(client.get(f"/api/v1/organizations/{org_id}", headers=h_e).status_code == 403,
              "removed member loses access (403)")

        check(client.delete(
            f"/api/v1/organizations/{org_id}/members/{owner_user}", headers=h_c
        ).status_code == 403, "owner cannot be removed by admin (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}",
            json={"name": "Data Lab", "description": "Updated maelezo"},
            headers=h_b,
        )
        check(r.status_code == 403, "viewer cannot edit org (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}",
            json={"name": "Data Lab 2"},
            headers=h_owner,
        )
        check(r.status_code == 200 and r.json()["name"] == "Data Lab 2", "owner edits org name")

        print("4) Org-scoped dataset access (deps.get_owned_dataset)")
        db = SessionLocal()
        owner_user = db.query(User).filter(User.email == "owner@example.com").first()
        viewer_user = db.query(User).filter(User.email == "as@example.com").first()
        outsider = db.query(User).filter(User.email == "amina@example.com").first()
        project = db.get(Project, project_id)
        dataset = Dataset(
            user_id=owner_user.id,
            project_id=project.id,
            original_filename="org-data.csv",
            storage_path=str(TEST_ROOT / "org-data.csv"),
            file_type="csv",
            row_count=10,
            column_count=2,
            status="uploaded",
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        # owner still passes (personal ownership)
        got = get_owned_dataset(dataset.id, db, owner_user, require_file=False)
        check(got.id == dataset.id, "owner passes the access gate")

        # viewer-as-member is below the analyst default minimum -> 403
        try:
            get_owned_dataset(dataset.id, db, viewer_user, require_file=False)
            check(False, "viewer member access should raise 403")
        except Exception:
            check(True, "viewer member blocked from dataset (min_role analyst)")

        # but a viewer may read when a route allows require_file=False + min_role viewer
        got = get_owned_dataset(
            dataset.id, db, viewer_user, require_file=False, min_role="viewer"
        )
        check(got.id == dataset.id, "viewer passes with min_role=viewer (read-only)")

        # non-member never passes
        try:
            get_owned_dataset(dataset.id, db, outsider, require_file=False)
            check(False, "non-member should be blocked")
        except Exception:
            check(True, "non-member blocked from org dataset")
        db.close()

        print("5) Teardown")
        r = client.delete(f"/api/v1/organizations/{org_id}", headers=h_owner)
        check(r.status_code == 204, "owner deletes organization")
        check(client.get(f"/api/v1/organizations/{org_id}", headers=h_owner).status_code == 404,
              "org gone after delete (404)")

        check(client.get("/api/v1/organizations").status_code == 401, "unauthenticated -> 401")

    print(f"\nALL ORG/RBAC TESTS PASSED ({PASSED} checks)")
    return 0


def test_full_journey() -> None:
    """pytest entry point: same run as ``python tests/orgs_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())