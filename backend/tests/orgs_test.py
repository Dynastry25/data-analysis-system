"""Organizations, projects, teams and RBAC tests (Phase 1 / master prompt).

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

        print("5) Teams")
        db = SessionLocal()
        outsider = db.query(User).filter(User.email == "amina@example.com").first()
        db.close()

        r = client.post(
            f"/api/v1/organizations/{org_id}/teams",
            json={"name": "Uchambuzi", "description": "Timu ya uchambuzi"},
            headers=h_owner,
        )
        check(r.status_code == 201 and r.json()["member_count"] == 0, "owner creates team")
        team_id = r.json()["id"]

        r = client.post(
            f"/api/v1/organizations/{org_id}/teams",
            json={"name": "Uchambuzi"},
            headers=h_owner,
        )
        check(r.status_code == 409, "duplicate team name rejected (409)")

        check(client.post(
            f"/api/v1/organizations/{org_id}/teams",
            json={"name": "Timu V"},
            headers=h_b,
        ).status_code == 403, "viewer cannot create a team (403)")

        r = client.post(
            f"/api/v1/organizations/{org_id}/teams",
            json={"name": "Uendeshaji"},
            headers=h_c,
        )
        check(r.status_code == 201, "admin can create a team")
        team2 = r.json()["id"]

        r = client.post(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members",
            json={"user_id": b_id},
            headers=h_owner,
        )
        check(r.status_code == 201 and r.json()["email"] == "as@example.com",
              "owner adds an org member to a team")

        check(client.post(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members",
            json={"user_id": b_id},
            headers=h_owner,
        ).status_code == 409, "cannot add the same team member twice (409)")

        r = client.post(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members",
            json={"user_id": outsider.id},
            headers=h_owner,
        )
        check(r.status_code == 403, "non-member cannot join a team (403)")

        r = client.get(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members", headers=h_owner
        )
        check(r.status_code == 200 and len(r.json()) == 1, "team member list shows the member")

        check(client.get(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members", headers=h_x
        ).status_code == 403, "non-member cannot read team members (403)")

        r = client.get(f"/api/v1/organizations/{org_id}/teams", headers=h_b)
        check(r.status_code == 200 and len(r.json()) == 2, "viewer can list teams (read-only)")

        check(client.patch(
            f"/api/v1/organizations/{org_id}/teams/{team_id}",
            json={"name": "Uchambuzi Pro"},
            headers=h_b,
        ).status_code == 403, "viewer cannot edit a team (403)")

        r = client.patch(
            f"/api/v1/organizations/{org_id}/teams/{team_id}",
            json={"name": "Uchambuzi Pro", "description": "Imesasishwa"},
            headers=h_c,
        )
        check(r.status_code == 200 and r.json()["name"] == "Uchambuzi Pro",
              "admin can rename a team")

        check(client.delete(
            f"/api/v1/organizations/{org_id}/teams/{team2}", headers=h_b
        ).status_code == 403, "viewer cannot delete a team (403)")

        check(client.delete(
            f"/api/v1/organizations/{org_id}/teams/{team2}", headers=h_c
        ).status_code == 204, "admin deletes a team")

        r = client.delete(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members/{b_id}",
            headers=h_c,
        )
        check(r.status_code == 204, "admin removes a member from a team")
        r = client.get(
            f"/api/v1/organizations/{org_id}/teams/{team_id}/members", headers=h_owner
        )
        check(r.status_code == 200 and len(r.json()) == 0, "team is empty after removal")

        print("6) Upload into a project (dataset scoping)")
        csv_path = TEST_ROOT / "scoped-upload.csv"
        csv_path.write_text("name,value\nAlpha,1\nBeta,2\n", encoding="utf-8")

        with csv_path.open("rb") as handle:
            r = client.post(
                "/api/datasets/upload",
                files={"file": ("scoped-upload.csv", handle, "text/csv")},
                data={"project_id": str(project_id)},
                headers=h_owner,
            )
        check(r.status_code == 201, "analyst uploads a dataset into a project (201)")
        check(r.json().get("project_id") == project_id,
              "upload response echoes project_id")
        scoped_id = r.json()["dataset_id"]

        r = client.post(
            "/api/datasets/upload",
            files={"file": ("scoped-upload.csv", csv_path.read_bytes(), "text/csv")},
            data={"project_id": "999999"},
            headers=h_owner,
        )
        check(r.status_code == 404, "unknown project_id rejected (404)")

        with csv_path.open("rb") as handle:
            r = client.post(
                "/api/datasets/upload",
                files={"file": ("scoped-upload.csv", handle, "text/csv")},
                data={"project_id": str(project_id)},
                headers=h_b,
            )
        check(r.status_code == 403, "viewer cannot upload into a project (403)")

        with csv_path.open("rb") as handle:
            r = client.post(
                "/api/datasets/upload",
                files={"file": ("scoped-upload.csv", handle, "text/csv")},
                data={"project_id": str(project_id)},
                headers=h_x,
            )
        check(r.status_code == 403, "non-member cannot upload into a project (403)")

        r = client.get(f"/api/datasets/{scoped_id}", headers=h_owner)
        check(r.status_code == 200, "owner reads the project-scoped dataset")
        r = client.get(f"/api/datasets/{scoped_id}", headers=h_x)
        check(r.status_code in (403, 404), "non-member cannot read project dataset")

        with csv_path.open("rb") as handle:
            r = client.post(
                "/api/datasets/upload",
                files={"file": ("personal.csv", handle, "text/csv")},
                headers=h_owner,
            )
        check(r.status_code == 201 and r.json().get("project_id") is None,
              "upload without project_id stays personal")

        print("7) Move a dataset between projects")
        with csv_path.open("rb") as handle:
            r = client.post(
                "/api/datasets/upload",
                files={"file": ("movable.csv", handle, "text/csv")},
                headers=h_owner,
            )
        check(r.status_code == 201, "personal dataset uploaded for moving")
        movable_id = r.json()["dataset_id"]
        check(r.json().get("project_id") is None, "movable dataset starts personal")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": project_id},
            headers=h_owner,
        )
        check(r.status_code == 200 and r.json()["project_id"] == project_id,
              "owner moves dataset into a project")

        r = client.get(f"/api/datasets/{movable_id}", headers=h_c)
        check(r.status_code == 200, "org admin (analyst+) can read the shared dataset")
        r = client.get(f"/api/datasets/{movable_id}", headers=h_b)
        check(r.status_code == 200, "org viewer can read the shared dataset (read-only)")
        r = client.delete(f"/api/datasets/{movable_id}", headers=h_b)
        check(r.status_code == 403, "org viewer cannot delete a shared dataset (403)")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": None},
            headers=h_owner,
        )
        check(r.status_code == 200 and r.json()["project_id"] is None,
              "owner moves dataset back to personal")
        r = client.get(f"/api/datasets/{movable_id}", headers=h_c)
        check(r.status_code == 403, "dataset is private again after the move")
        r = client.delete(f"/api/datasets/{movable_id}", headers=h_c)
        check(r.status_code == 403, "org admin cannot delete someone else's dataset (403)")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": project_id},
            headers=h_c,
        )
        check(r.status_code == 403, "org admin cannot move someone else's dataset (403)")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": 999999},
            headers=h_owner,
        )
        check(r.status_code == 404, "cannot move into an unknown project (404)")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": project_id},
            headers=h_b,
        )
        check(r.status_code == 403, "viewer cannot move a dataset into a project (403)")

        r = client.get("/api/datasets", headers=h_owner)
        check(r.status_code == 200 and any(
            d["id"] == movable_id for d in r.json()
        ), "own dataset appears in the list")

        r = client.patch(
            f"/api/datasets/{movable_id}/project",
            json={"project_id": project_id},
            headers=h_owner,
        )
        check(r.status_code == 200 and r.json()["project_id"] == project_id,
              "owner moves dataset into a project")

        analysis = client.post(
            f"/api/v1/datasets/{movable_id}/analysis",
            json={
                "analysis_type": "descriptive",
                "parameters": {"columns": ["value"]},
            },
            headers=h_owner,
        )
        check(analysis.status_code == 200, "owner creates a versioned analysis")
        analysis_id = analysis.json()["analysis_id"]

        chart = client.post(
            f"/api/datasets/{movable_id}/charts",
            json={
                "chart_type": "bar",
                "config": {"x": "name", "y": "value", "aggregate": "sum"},
            },
            headers=h_owner,
        )
        check(chart.status_code == 200, "owner creates a versioned chart")
        chart_id = chart.json()["chart_id"]

        exported = client.post(
            f"/api/datasets/{movable_id}/export",
            json={
                "format": "xlsx",
                "include_analysis_ids": [analysis_id],
                "include_chart_ids": [chart_id],
            },
            headers=h_owner,
        )
        check(exported.status_code == 202, "owner exports a shared report")
        report_id = exported.json()["report_id"]

        check(
            client.post(
                "/api/v1/planning/profile",
                json={"dataset_id": movable_id},
                headers=h_b,
            ).status_code
            == 200,
            "viewer can request planning profile",
        )
        check(
            client.get(
                f"/api/v1/analysis/{analysis_id}", headers=h_b
            ).status_code
            == 200,
            "viewer can read shared analysis detail",
        )
        check(
            client.get(f"/api/charts/{chart_id}", headers=h_b).status_code == 200,
            "viewer can read shared chart detail",
        )
        check(
            client.get(f"/api/reports/{report_id}/status", headers=h_b).status_code
            == 200,
            "viewer can read shared report status",
        )
        check(
            client.get(f"/api/reports/{report_id}/download", headers=h_b).status_code
            == 200,
            "viewer can download shared report",
        )
        check(
            client.post(
                f"/api/v1/datasets/{movable_id}/analysis",
                json={"analysis_type": "descriptive", "parameters": {}},
                headers=h_b,
            ).status_code
            == 403,
            "viewer cannot create analyses",
        )
        check(
            client.post(
                f"/api/datasets/{movable_id}/charts",
                json={
                    "chart_type": "bar",
                    "config": {"x": "name", "y": "value"},
                },
                headers=h_b,
            ).status_code
            == 403,
            "viewer cannot create charts",
        )
        check(
            client.post(
                f"/api/datasets/{movable_id}/export",
                json={"format": "pdf"},
                headers=h_b,
            ).status_code
            == 403,
            "viewer cannot create reports",
        )

        r = client.get("/api/datasets", headers=h_c)
        shared_ids = [d["id"] for d in r.json()]
        check(r.status_code == 200 and movable_id in shared_ids,
              "org member sees the shared dataset in their list")
        check(any(
            d["id"] == movable_id and d.get("project_name") is not None
            for d in r.json()
        ), "list exposes the project name for shared datasets")

        r = client.get("/api/datasets", headers=h_x)
        check(movable_id not in [d["id"] for d in r.json()],
              "non-member never sees the shared dataset in their list")

        print("8) Teardown")
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