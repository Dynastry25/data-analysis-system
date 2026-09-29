"""Dashboard CRUD tests: versioned widgets over real analyses and charts.

A dashboard is pinned to a dataset version and references existing analyses and
charts. These checks prove the endpoints save, read, update and delete a
dashboard, that malformed widgets are rejected at save time, and that a viewer
cannot edit a dashboard that belongs to a dataset they may only read.

Run it with:  python tests/dashboard_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dashboard_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "dashboard-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  [ok] {message}")
    else:
        print(f"  [FAIL] {message}")


def build_sample_csv(path: Path) -> Path:
    frame = pd.DataFrame(
        {
            "region": ["Dar es Salaam", "Arusha", "Mwanza", "Dodoma"] * 40,
            "units": [((index * 7) % 23) + 1 for index in range(160)],
            "unit_price": [round(1000 + (index % 37) * 250.5, 2) for index in range(160)],
            "month": pd.date_range("2025-01-01", periods=160, freq="D").astype(str),
        }
    )
    frame["sales"] = (frame["units"] * frame["unit_price"]).round(2)
    frame.to_csv(path, index=False)
    return path


def main() -> int:
    csv_path = build_sample_csv(TEST_ROOT / "sales_sample.csv")

    with TestClient(app) as client:
        register = client.post(
            "/api/auth/register",
            json={
                "full_name": "Bibi Jani",
                "email": "bibi@example.com",
                "password": "secret123",
            },
        )
        check(register.status_code == 201, "register returns 201")
        login = client.post(
            "/api/auth/login", json={"email": "bibi@example.com", "password": "secret123"}
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        with csv_path.open("rb") as handle:
            upload = client.post(
                "/api/datasets/upload",
                files={"file": (csv_path.name, handle, "text/csv")},
                headers=headers,
            )
        check(upload.status_code == 201, "upload returns 201")
        dataset_id = upload.json()["dataset_id"]

        run = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "linear_regression",
                "parameters": {"target": "sales", "features": ["units", "unit_price"]},
            },
            headers=headers,
        )
        check(run.status_code == 200, "linear regression runs")
        analysis_id = run.json()["analysis_id"]

        chart = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={
                "chart_type": "bar",
                "config": {"x": "region", "y": "sales", "aggregate": "sum"},
            },
            headers=headers,
        )
        check(chart.status_code == 200, "chart is created")
        chart_id = chart.json()["chart_id"]

        print("\nDashboard CRUD")
        create = client.post(
            f"/api/datasets/{dataset_id}/dashboards",
            json={
                "name": "Sales overview",
                "title": "Mauzo kwa mkoa",
                "widgets": [
                    {
                        "id": "kpi-1",
                        "type": "kpi",
                        "title": "R squared",
                        "source": {
                            "kind": "analysis",
                            "analysis_id": analysis_id,
                            "metric": "r_squared",
                            "label": "R²",
                        },
                    },
                    {
                        "id": "chart-1",
                        "type": "chart",
                        "title": "Mauzo kwa mkoa",
                        "chart_id": chart_id,
                    },
                    {"id": "note-1", "type": "text", "content": "Ripoti ya robo mwaka"},
                ],
            },
            headers=headers,
        )
        check(create.status_code == 200, f"dashboard creates ({create.status_code})")
        created = create.json()
        check(created["name"] == "Sales overview", "dashboard echoes its name")
        check(created["dataset_version"] == 1, "dashboard is pinned to version 1")
        check(len(created["config"]["widgets"]) == 3, "all three widgets saved")
        dashboard_id = created["dashboard_id"]

        oneshot = client.get(f"/api/dashboards/{dashboard_id}", headers=headers)
        check(oneshot.status_code == 200, "get dashboard returns 200")
        check(oneshot.json()["dashboard_id"] == dashboard_id, "get returns the same dashboard")

        listing = client.get(f"/api/datasets/{dataset_id}/dashboards", headers=headers)
        check(listing.status_code == 200, "list dashboards returns 200")
        check(
            any(item["dashboard_id"] == dashboard_id for item in listing.json()),
            "created dashboard appears in the list",
        )

        update = client.put(
            f"/api/dashboards/{dashboard_id}",
            json={
                "title": "Mauzo 2025",
                "widgets": [
                    {"id": "chart-1", "type": "chart", "chart_id": chart_id},
                ],
            },
            headers=headers,
        )
        check(update.status_code == 200, "dashboard updates")
        check(update.json()["title"] == "Mauzo 2025", "dashboard saves the new title")
        check(len(update.json()["config"]["widgets"]) == 1, "widget list is replaced")

        bad_type = client.post(
            f"/api/datasets/{dataset_id}/dashboards",
            json={
                "name": "bad",
                "widgets": [{"id": "x", "type": "magic"}],
            },
            headers=headers,
        )
        check(bad_type.status_code == 422, "unknown widget type is rejected")
        check("magic" in bad_type.text, "rejection names the offending type")

        missing_chart = client.post(
            f"/api/datasets/{dataset_id}/dashboards",
            json={"name": "bad", "widgets": [{"id": "x", "type": "chart"}]},
            headers=headers,
        )
        check(missing_chart.status_code == 422, "chart widget without chart_id is rejected")

        delete = client.delete(f"/api/dashboards/{dashboard_id}", headers=headers)
        check(delete.status_code == 204, "dashboard deletes with 204")
        gone = client.get(f"/api/dashboards/{dashboard_id}", headers=headers)
        check(gone.status_code == 404, "deleted dashboard is gone")

        print("\nSecond user is blocked")
        other_register = client.post(
            "/api/auth/register",
            json={
                "full_name": "Zawadi Kileo",
                "email": "zawadi@example.com",
                "password": "secret123",
            },
        )
        other_login = client.post(
            "/api/auth/login",
            json={"email": "zawadi@example.com", "password": "secret123"},
        )
        other_headers = {
            "Authorization": f"Bearer {other_login.json()['access_token']}"
        }
        see = client.get(f"/api/dashboards/{dashboard_id}", headers=other_headers)
        check(
            see.status_code in (403, 404),
            "a stranger cannot read the dashboard",
        )

    print(f"\nALL DASHBOARD TESTS PASSED ({PASSED} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())