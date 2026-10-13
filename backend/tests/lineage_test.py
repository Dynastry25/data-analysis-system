"""Source-to-analysis lineage (improvement plan 3.2).

"Where did this number come from?" deserves an answer that does not
stop at "an analysis". These tests pin the whole chain: the uploaded
file, the version each operation produced (with its row and column
deltas against the parent), and the analyses that ran on each exact
version -- including that two runs on different versions are two
different answers, which is the question the view exists to make
visible.

The tests go through the HTTP API, because the lineage is only
meaningful as the records the platform actually wrote: upload, clean
(a new immutable version), analyse twice (once on each version), then
read the chain back.

Run it with:  python tests/lineage_test.py
"""

import io
import os
import sys
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="lineage_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "lineage-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


CSV = "value,group\n10,a\n12,a\n11,a\n9,b\n8,b\n7,b\n10,a\n"


def main() -> int:
    print("SOURCE-TO-ANALYSIS LINEAGE TESTS")
    with TestClient(app) as client:
        # A per-file email: every test module shares one database once
        # the engine binds, so a shared address is a duplicate-user
        # failure rather than a test of anything.
        client.post(
            "/api/auth/register",
            json={
                "full_name": "Asha Mwangi",
                "email": "lineage.asha@example.com",
                "password": "secret123",
            },
        )
        token = client.post(
            "/api/auth/login",
            json={"email": "lineage.asha@example.com", "password": "secret123"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        uploaded = client.post(
            "/api/datasets/upload",
            files={"file": ("trials.csv", io.BytesIO(CSV.encode()), "text/csv")},
            headers=headers,
        )
        check(uploaded.status_code == 201, "the upload is stored")
        dataset_id = uploaded.json()["dataset_id"]

        # One analysis on the file exactly as uploaded.
        first = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "welch_t_test",
                "parameters": {"value_column": "value", "group_column": "group"},
                "dataset_version": 1,
                "save": True,
            },
            headers=headers,
        )
        check(first.status_code == 200, "an analysis runs on the original version")

        # A cleaning step, which writes a NEW immutable version.
        cleaned = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "drop_duplicates",
                "configuration": {"keep": "first"},
            },
            headers=headers,
        )
        check(cleaned.status_code == 200, "the cleaning step writes v2")
        check(cleaned.json()["version"] == 2, "the new version is v2")

        # The same analysis on the cleaned version: same question,
        # different data, different answer.
        second = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "welch_t_test",
                "parameters": {"value_column": "value", "group_column": "group"},
                "save": True,
            },
            headers=headers,
        )
        check(second.status_code == 200, "the same analysis runs on v2")

        lineage = client.get(
            f"/api/v1/datasets/{dataset_id}/lineage", headers=headers
        ).json()

        print("\n1) The chain starts at the file that was uploaded")
        dataset = lineage["dataset"]
        check(dataset["name"] == "trials.csv", "the source is named")
        check(dataset["current_version"] == 2, "the current version is v2")
        check(lineage["totals"]["versions"] == 2, "two versions exist")
        check(lineage["totals"]["operations"] == 1, "one operation produced them")
        check(lineage["totals"]["analyses"] == 2, "two analyses were run")

        print("\n2) Each version says what produced it and what it holds")
        v1, v2 = lineage["versions"]
        check(v1["version"] == 1, "the chain reads v1 first")
        check(v1["produced_by"] is None, "v1 is the uploaded file itself")
        check(v1["row_delta"] is None, "the upload has no parent to differ from")
        check(v1["is_current"] is False, "v1 is not the current version")

        check(v2["produced_by"]["type"] == "drop_duplicates", "v2 names its operation")
        check(v2["row_delta"] == -1, "v2 carries its row delta against the parent")
        check(v2["is_current"] is True, "v2 is the current version")

        print("\n3) Each version holds the results computed from it")
        check(
            [run["id"] for run in v1["analyses"]] == [first.json()["analysis_id"]],
            "the analysis on the original version sits on v1",
        )
        check(
            [run["id"] for run in v2["analyses"]] == [second.json()["analysis_id"]],
            "the analysis on the cleaned version sits on v2",
        )
        check(
            all(run["analysis_type"] == "welch_t_test" for run in v1["analyses"] + v2["analyses"]),
            "both runs record which analysis they are",
        )
        check(
            v1["result_count"] == 1 and v2["result_count"] == 1,
            "each version counts the results under it",
        )

        print("\n4) A result that ran nowhere else is still told apart")
        # The two runs answered the same question on different data; the
        # lineage is what makes that difference visible at a glance.
        check(
            v1["row_count"] == 7 and v2["row_count"] == 6,
            "the versions carry the shapes the two runs actually saw",
        )

        print("\n5) A reader who cannot see the dataset is refused")
        other = client.post(
            "/api/auth/register",
            json={
                "full_name": "Juma Ally",
                "email": "lineage.juma@example.com",
                "password": "secret123",
            },
        )
        check(other.status_code == 201, "a second user is registered")
        other_token = client.post(
            "/api/auth/login",
            json={"email": "lineage.juma@example.com", "password": "secret123"},
        ).json()["access_token"]
        refused = client.get(
            f"/api/v1/datasets/{dataset_id}/lineage",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        check(
            refused.status_code == 403,
            "another user's lineage is not readable",
        )

    print(f"\nALL LINEAGE TESTS PASSED ({PASSED} checks)")
    return 0


def test_lineage() -> None:
    """pytest entry point: same run as ``python tests/lineage_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
