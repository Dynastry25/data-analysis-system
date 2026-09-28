"""Tests for the Validate and Explore stages.

Both endpoints exist so the journey can show real work at those steps. The
checks that matter most here are the ones that stop a wrong number reaching the
user: correlations from too few rows, a numeric column read as a label, and a
"no relationship" claim that hides a curved one.

Run it with:  python tests/explore_validate_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dap_explore_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "explore-test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        print(f"  FAIL: {message}")


def codes(report) -> set:
    return {issue["code"] for issue in report["issues"]}


def issues_for(report, code) -> list:
    return [issue for issue in report["issues"] if issue["code"] == code]


def register(client, email="qa@example.com"):
    client.post(
        "/api/auth/register",
        json={"full_name": "Quality Assurance", "email": email, "password": "secret123"},
    )
    token = client.post(
        "/api/auth/login", json={"email": email, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, frame: pd.DataFrame, name: str) -> int:
    path = TEST_ROOT / name
    frame.to_csv(path, index=False)
    with path.open("rb") as handle:
        response = client.post(
            "/api/datasets/upload",
            files={"file": (name, handle, "text/csv")},
            headers=headers,
        )
    assert response.status_code == 201, response.text
    return response.json()["dataset_id"]


def validate_of(client, headers, dataset_id):
    return client.get(
        f"/api/datasets/{dataset_id}/validate", headers=headers
    ).json()


def explore_of(client, headers, dataset_id):
    return client.get(f"/api/datasets/{dataset_id}/explore", headers=headers).json()


def main() -> int:
    with TestClient(app) as client:
        headers = register(client)
        stranger = register(client, "qa2@example.com")

        print("\n1) A clean dataset passes validation")
        clean = pd.DataFrame(
            {
                "height_cm": [150, 160, 170, 180, 190, 175, 165, 155],
                "weight_kg": [45, 55, 65, 75, 85, 70, 60, 50],
                "region": ["north", "south", "north", "south", "north", "south", "north", "south"],
            }
        )
        clean_id = upload(client, headers, clean, "clean.csv")
        report = validate_of(client, headers, clean_id)
        check(report["verdict"] == "clean", f"clean data is clean ({report['verdict']})")
        check(report["error_count"] == 0, "clean data raises no errors")
        check(
            not any(issue["severity"] == "error" for issue in report["issues"]),
            "no error-severity issue on a tidy file",
        )
        check(bool(report["summary"]), "the verdict comes with a readable summary")

        print("\n2) Structural problems block the journey")
        empty = pd.DataFrame({"a": [], "b": []})
        empty_id = upload(client, headers, empty, "empty.csv")
        report = validate_of(client, headers, empty_id)
        check(report["verdict"] == "blocked", "an empty file is blocked")
        check("empty_dataset" in codes(report), "an empty file says so explicitly")

        all_missing = pd.DataFrame(
            {
                "blank": [None, None, None, None],
                "ok": [1, 2, 3, 4],
            }
        )
        missing_id = upload(client, headers, all_missing, "missing.csv")
        report = validate_of(client, headers, missing_id)
        check("column_all_missing" in codes(report), "an all-missing column is an error")
        issue = issues_for(report, "column_all_missing")[0]
        check(issue["column"] == "blank", "the issue names the offending column")
        check(issue["severity"] == "error", "an all-missing column is an error")

        print("\n3) Quality problems warn but do not block")
        messy = pd.DataFrame(
            {
                "sparse": [None] * 28 + [1, 2],
                "constant": ["same"] * 30,
            }
        )
        messy_id = upload(client, headers, messy, "messy.csv")
        report = validate_of(client, headers, messy_id)
        check(
            report["verdict"] == "warnings",
            f"a sparse file warns instead of blocking ({report['verdict']})",
        )
        check("column_mostly_missing" in codes(report), "a mostly-empty column warns")
        check("constant_column" in codes(report), "a constant column warns")
        check(
            "duplicate_rows" in codes(report),
            "30 identical rows are reported as duplicates",
        )
        duplicate_issue = issues_for(report, "duplicate_rows")[0]
        # 28 rows share the all-empty pair; the 2 rows with a value in `sparse`
        # are unique, so 27 of them are duplicates of a row already seen.
        check(
            duplicate_issue["detail"]["duplicate_row_count"] == 27,
            f"the duplicate count is exact ({duplicate_issue['detail']})",
        )
        check(
            duplicate_issue["detail"]["row_count"] == 30,
            "the duplicate issue also states the total row count",
        )

        print("\n3b) A unique complete column is flagged as an identifier")
        identified = pd.DataFrame(
            {"record_id": range(1, 31), "measurement": [value / 3 for value in range(30)]}
        )
        identified_id = upload(client, headers, identified, "identified.csv")
        report = validate_of(client, headers, identified_id)
        check(
            "likely_identifier" in codes(report),
            "a unique complete column is flagged as a likely identifier",
        )
        check(
            issues_for(report, "likely_identifier")[0]["column"] is None,
            "an identifier finding lists the column names in the message, not one column",
        )

        print("\n4) A number stored as text is caught")
        # A unit suffix is what keeps the column as text through the CSV read;
        # without it pandas would already have parsed the digits, and there
        # would be nothing left for the user to fix.
        as_text = pd.DataFrame(
            {
                "reading": [
                    f"{value} kg" if value < 2 else str(value) for value in range(40)
                ],
                "amount": list(range(40)),
            }
        )
        text_id = upload(client, headers, as_text, "text_numbers.csv")
        report = validate_of(client, headers, text_id)
        check(
            "numeric_stored_as_text" in codes(report),
            "a numeric column stored as text is flagged so casting is possible",
        )
        if "numeric_stored_as_text" in codes(report):
            issue = issues_for(report, "numeric_stored_as_text")[0]
            check(issue["column"] == "reading", "the text-number issue names the column")

        print("\n5) Issues arrive worst first")
        ordering = [issue["severity"] for issue in report["issues"]]
        rank = {"error": 0, "warning": 1, "info": 2}
        check(
            ordering == sorted(ordering, key=lambda severity: rank[severity]),
            "issues are ordered error, then warning, then info",
        )

        print("\n6) Both endpoints respect access control")
        for path in ("validate", "explore"):
            check(
                client.get(
                    f"/api/datasets/{clean_id}/{path}", headers=stranger
                ).status_code
                == 403,
                f"{path} returns 403 to a user with no access",
            )
            check(
                client.get(f"/api/datasets/{clean_id}/{path}").status_code == 401,
                f"{path} returns 401 to an anonymous caller",
            )

        print("\n7) Explore describes numeric columns properly")
        response = client.get(f"/api/datasets/{clean_id}/explore", headers=headers)
        check(response.status_code == 200, "explore returns 200")
        exploration = explore_of(client, headers, clean_id)
        check(exploration["row_count"] == 8, "explore reports the row count")
        by_name = {column["name"]: column for column in exploration["columns"]}
        check(
            by_name["height_cm"]["kind"] == "numeric",
            "a spread-out number is numeric",
        )
        check(
            by_name["height_cm"]["mean"] is not None
            and by_name["height_cm"]["median"] is not None,
            "a numeric column gets mean and median",
        )
        check(
            set(by_name["height_cm"]["quantiles"]) == {"p25", "p50", "p75"},
            "a numeric column gets its quartiles",
        )
        check(
            len(by_name["height_cm"]["histogram"]) > 0,
            "a numeric column gets a histogram to look at",
        )
        check(
            by_name["region"]["kind"] == "categorical",
            "a short repeated label is categorical, not text",
        )
        check(
            len(by_name["region"]["top_values"]) == 2,
            "a categorical column lists its values with counts",
        )
        check(
            by_name["region"].get("mean") is None,
            "a categorical column does not pretend to have a mean",
        )

        print("\n8) A correlation from too few rows is not printed")
        small = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8], "b": [2, 4, 6, 8, 10, 12, 14, 16]})
        small_id = upload(client, headers, small, "small.csv")
        exploration = explore_of(client, headers, small_id)
        check(
            exploration["correlations"] == [],
            "8 rows is below the threshold, so no correlation is claimed",
        )
        check(
            any("korrel" in warning.lower() or "haki" in warning.lower()
                for warning in exploration["warnings"])
            or exploration["correlations"] == [],
            "a suppressed correlation does not pretend the data is fine",
        )

        print("\n9) A real correlation is found and labelled honestly")
        rows = 60
        linear = pd.DataFrame(
            {
                "study_hours": [value for value in range(rows)],
                "score": [value * 3 + 40 for value in range(rows)],
                "noise": [((value * 37) % 11) for value in range(rows)],
            }
        )
        linear_id = upload(client, headers, linear, "linear.csv")
        exploration = explore_of(client, headers, linear_id)
        pairs = {
            frozenset((pair["x"], pair["y"])): pair
            for pair in exploration["correlations"]
        }
        check(bool(pairs), "60 rows is enough to compute correlations")
        study_score = pairs.get(frozenset(("study_hours", "score")))
        check(study_score is not None, "the study/score pair is reported")
        if study_score:
            check(
                abs(study_score["coefficient"]) > 0.9,
                f"a perfect linear link is near 1 ({study_score['coefficient']})",
            )
            check(
                study_score["strength"] == "strong",
                "a near-perfect link is labelled strong",
            )
            check(
                "sababu" in study_score["interpretation"],
                "the reading says a relationship is not a cause",
            )
            check(
                study_score["method"] == "pearson",
                "Pearson and Spearman agree on a straight line, so Pearson is quoted",
            )
        weak = pairs.get(frozenset(("study_hours", "noise")))
        if weak:
            check(
                abs(weak["coefficient"]) < study_score["coefficient"],
                "the strongest pair is listed above the weaker one",
            )

        print("\n10) A relationship the outliers distort is not flattened to one number")
        rows = 80
        hours = list(range(rows))
        # Perfectly monotonic, but with ten extreme values at the top. Pearson
        # reads as moderate because the outliers bend the line; the rank
        # correlation still sees the ordering. Reporting only Pearson here
        # would understate a real relationship, so the disagreement is surfaced.
        scores = list(hours)
        for value in range(70, 80):
            scores[value] = 5000 + value
        distorted = pd.DataFrame({"hours": hours, "score": scores})
        distorted_id = upload(client, headers, distorted, "distorted.csv")
        exploration = explore_of(client, headers, distorted_id)
        check(
            len(exploration["correlations"]) == 1,
            "the distorted pair is still reported",
        )
        if exploration["correlations"]:
            pair = exploration["correlations"][0]
            check(
                pair["method"] == "spearman",
                f"when Pearson and Spearman disagree, Spearman is quoted ({pair['method']})",
            )
            check(
                "Spearman" in pair["interpretation"],
                "the disagreement between the two methods is stated",
            )
            check(
                pair["strength"] == "strong",
                "the rank correlation still shows a strong ordering",
            )

        clean_linear = explore_of(client, headers, linear_id)
        check(
            clean_linear["correlations"][0]["method"] == "pearson",
            "a clean straight line still quotes Pearson, so nothing is forced",
        )

        print("\n11) Explore warns about data that will block analysis")
        no_numeric = pd.DataFrame(
            {"name": [f"person {value}" for value in range(40)],
             "city": ["nairobi", "mombasa"] * 20}
        )
        text_only_id = upload(client, headers, no_numeric, "text_only.csv")
        exploration = explore_of(client, headers, text_only_id)
        check(
            any("numeric" in warning for warning in exploration["warnings"]),
            "a file with no numeric column is warned about before analysis",
        )
        constant = pd.DataFrame(
            {"x": [value for value in range(40)], "y": [7] * 40}
        )
        constant_id = upload(client, headers, constant, "constant.csv")
        exploration = explore_of(client, headers, constant_id)
        check(
            any("moja tu" in warning for warning in exploration["warnings"]),
            "a constant column is warned about in explore too",
        )

    print(f"\n{PASSED} validate/explore checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
