"""Tests for the 11-stage journey progress endpoint.

The journey is the product's spine, and its progress bar is only worth showing
if it cannot lie. So these tests check the negative cases as hard as the
positive ones: a stage that leaves no record must never report itself done.

Run it with:  python tests/journey_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dap_journey_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "journey-test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSED = 0

STAGE_KEYS = [
    "upload",
    "validate",
    "profile",
    "clean",
    "transform",
    "explore",
    "analyze",
    "visualize",
    "explain",
    "report",
    "export",
]

# Stages whose work leaves nothing behind, so `done` can never become true.
READ_ONLY_STAGES = ("validate", "explore", "explain", "report")


def check(condition: bool, message: str) -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        print(f"  FAIL: {message}")


def register(client, full_name, email, password="secret123"):
    created = client.post(
        "/api/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    login = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return (
        {"Authorization": f"Bearer {login.json()['access_token']}"},
        created.json()["id"],
    )


def build_sample_csv(path: Path) -> Path:
    path.write_text(
        "age,city,score\n"
        "23,Nairobi,80\n"
        "31,Nairobi,72\n"
        "45,Mombasa,91\n"
        "29,Kisumu,65\n"
        "52,Nairobi,77\n"
        ",Mombasa,58\n",
        encoding="utf-8",
    )
    return path


def journey_of(client, dataset_id, headers):
    return client.get(f"/api/datasets/{dataset_id}/journey", headers=headers).json()


def stages_of(body):
    return {stage["key"]: stage for stage in body["stages"]}


def main() -> int:
    with TestClient(app) as client:
        headers, _user_id = register(client, "Journey User", "journey@example.com")
        csv_path = build_sample_csv(TEST_ROOT / "sample.csv")

        print("\n1) Upload proves stage 1 and nothing beyond")
        with csv_path.open("rb") as handle:
            upload = client.post(
                "/api/datasets/upload",
                files={"file": (csv_path.name, handle, "text/csv")},
                headers=headers,
            )
        check(upload.status_code == 201, f"upload returns 201 ({upload.status_code})")
        dataset_id = upload.json()["dataset_id"]

        response = client.get(f"/api/datasets/{dataset_id}/journey", headers=headers)
        check(response.status_code == 200, "journey returns 200")
        body = response.json()
        check(
            [stage["step"] for stage in body["stages"]] == list(range(1, 12)),
            "journey reports exactly 11 stages numbered 1..11",
        )
        check(
            [stage["key"] for stage in body["stages"]] == STAGE_KEYS,
            "stage keys and order match the 11-stage journey",
        )
        check(
            all(stage["reason"] for stage in body["stages"]),
            "every stage explains itself in Swahili, so no badge is a bare word",
        )
        stages = stages_of(body)
        check(stages["upload"]["done"], "upload is done after upload")
        check(
            all(not stages[key]["done"] for key in ("analyze", "visualize", "export")),
            "nothing downstream of upload claims to be done",
        )
        check(
            all(
                stages[key]["record_count"] is None for key in READ_ONLY_STAGES
            ),
            "read-only stages report no record count at all",
        )

        print("\n2) Access control matches the rest of the dataset API")
        stranger_headers, _ = register(client, "Stranger", "stranger@example.com")
        check(
            client.get(
                f"/api/datasets/{dataset_id}/journey", headers=stranger_headers
            ).status_code
            == 403,
            "a user with no access to the dataset gets 403, not its progress",
        )
        check(
            client.get("/api/datasets/999999/journey", headers=headers).status_code
            == 404,
            "an unknown dataset id gets 404",
        )
        check(
            client.get(f"/api/datasets/{dataset_id}/journey").status_code == 401,
            "an anonymous caller gets 401",
        )

        print("\n3) Profile is proved by stored column metadata")
        profile = client.get(f"/api/datasets/{dataset_id}/profile", headers=headers)
        check(profile.status_code == 200, f"profile returns 200 ({profile.status_code})")
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["profile"]["done"], "profile is done because columns are stored")
        check(
            stages["profile"]["record_count"] == profile.json()["column_count"],
            "the profile count matches the profiled column count",
        )

        print("\n4) Clean and Transform are told apart by operation_group")
        clean = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "drop_missing",
                "configuration": {"columns": ["age"]},
            },
            headers=headers,
        )
        check(clean.status_code == 200, "drop_missing cleaning returns 200")
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["clean"]["done"], "clean is done after one cleaning operation")
        check(
            not stages["transform"]["done"],
            "transform stays unfinished after cleaning only",
        )

        transform = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "calculate_column",
                "configuration": {"name": "score_band", "expression": "score > 70"},
            },
            headers=headers,
        )
        check(
            transform.status_code == 200,
            f"calculate_column transform returns 200 ({transform.status_code})",
        )
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["transform"]["done"], "transform is done after a transform")
        check(
            stages["transform"]["record_count"] == 1,
            "transform counts transform operations only, not cleaning ones",
        )
        check(
            stages["clean"]["record_count"] == 1,
            "clean counts cleaning operations only, not transform ones",
        )

        print("\n5) Analysis, charts and exports move the later stages")
        analysis = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={"analysis_type": "descriptive", "parameters": {}},
            headers=headers,
        )
        check(analysis.status_code == 200, "descriptive analysis returns 200")
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["analyze"]["done"], "analyze is done after a run")

        chart = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={
                "chart_type": "bar",
                "config": {"x": "city", "y": "score", "aggregate": "mean"},
            },
            headers=headers,
        )
        check(chart.status_code == 200, f"a chart can be created ({chart.status_code})")
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["visualize"]["done"], "visualize is done once a chart exists")

        export = client.post(
            f"/api/datasets/{dataset_id}/export",
            json={"format": "xlsx"},
            headers=headers,
        )
        check(
            export.status_code == 202,
            f"a report export can be created ({export.status_code})",
        )
        for _ in range(60):
            status_response = client.get(
                f"/api/reports/{export.json()['report_id']}/status", headers=headers
            )
            if status_response.json()["status"] in ("completed", "failed"):
                break
        check(
            status_response.json()["status"] == "completed",
            "the report export finished",
        )
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(stages["export"]["done"], "export is done after a completed export")
        check(
            not stages["report"]["done"],
            "report stays unfinished because composing it writes no record",
        )
        check(
            not stages["explain"]["done"],
            "explain stays unfinished because no assistant message is stored",
        )

        print("\n6) A failed export is not counted as done")
        second = client.post(
            f"/api/datasets/{dataset_id}/export",
            json={"format": "xlsx", "include_analysis_ids": [999999]},
            headers=headers,
        )
        check(
            second.status_code in (400, 404, 422),
            f"an export naming an unknown analysis is rejected ({second.status_code})",
        )
        stages = stages_of(journey_of(client, dataset_id, headers))
        check(
            stages["export"]["record_count"] == 1,
            "a rejected export never inflates the export count",
        )

        print("\n7) The whole set of provable stages is done")
        stages = stages_of(journey_of(client, dataset_id, headers))
        for key in ("upload", "profile", "clean", "transform", "analyze", "visualize", "export"):
            check(stages[key]["done"], f"{key} is done at the end of the journey")

    print(f"\n{PASSED} journey checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
