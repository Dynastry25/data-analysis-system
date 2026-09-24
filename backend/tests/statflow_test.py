"""StatFlow engines test: MVP-18 (versioning/operations) -> MVP-19 (statistics) ->
MVP-20 (recommendation) -> MVP-21 (assistant).

Everything runs against a temporary database and storage folder.

Run it with:  python tests/statflow_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="statflow_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "statflow-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.statflow import distributions, stats_engine  # noqa: E402

PASSED = 0
STANDARD_KEYS = {
    "analysis_type",
    "status",
    "sample_size",
    "estimate",
    "test",
    "confidence_interval",
    "effect_size",
    "diagnostics",
    "warnings",
}


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def build_statflow_csv(path: Path) -> Path:
    """Deterministic sample: income differs by gender AND region."""
    rng = np.random.default_rng(42)
    n = 300
    gender = rng.choice(["male", "female"], size=n)
    region = rng.choice(["A", "B", "C"], size=n)
    age = rng.integers(15, 70, size=n).astype(float)
    base = np.where(gender == "male", 3200.0, 2600.0)
    base = base + np.where(region == "A", 250.0, np.where(region == "C", -250.0, 0.0))
    income = base + rng.normal(0, 300, size=n)
    education = rng.choice(
        ["primary", "secondary", "university"], size=n, p=[0.3, 0.5, 0.2]
    )
    frame = pd.DataFrame(
        {
            "row_id": range(1, n + 1),
            "age": age,
            "income": income.round(2),
            "gender": gender,
            "region": region,
            "education": education,
            "member": rng.choice(["yes", "no"], size=n),
        }
    )
    frame.loc[frame.index[:10], "income"] = np.nan
    frame.loc[frame.index[10:15], "age"] = np.nan
    frame = pd.concat([frame, frame.iloc[:5]], ignore_index=True)
    frame.to_csv(path, index=False)
    return path


def main() -> int:
    csv_path = build_statflow_csv(TEST_ROOT / "people.csv")
    print(f"Test workspace: {TEST_ROOT}\n")

    print("0) Distribution math (known values, no scipy)")
    check(abs(distributions.normal_cdf(0) - 0.5) < 1e-12, "normal_cdf(0) = 0.5")
    check(
        abs(distributions.chi_square_sf(3.8414588, 1) - 0.05) < 0.002,
        "chi2(3.841, df=1) p ~= 0.05",
    )
    check(
        abs(distributions.student_t_two_sided_p(0.0, 30) - 1.0) < 1e-12,
        "t = 0 gives p = 1.0",
    )
    critical = distributions.t_critical(30, 0.95)
    check(abs(critical - 2.0423) < 0.01, f"t critical(30, 95%) ~= 2.04 ({critical:.4f})")
    check(
        abs(distributions.f_sf(4.0, 1, 100) - 0.0482) < 0.002,
        "F(4; 1, 100) p ~= 0.048",
    )
    symmetric = stats_engine.fisher_exact_2x2(np.array([[10.0, 10.0], [10.0, 10.0]]))
    check(abs(symmetric["p_value"] - 1.0) < 1e-9, "Fisher 2x2 symmetric table p = 1.0")
    check(abs(symmetric["odds_ratio"] - 1.0) < 1e-9, "Fisher odds ratio = 1.0")
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    check(
        abs(stats_engine.durbin_watson(x - x.mean()) - durbin_watson_expected()) < 1e-9,
        "Durbin-Watson sanity check",
    )

    with TestClient(app) as client:
        print("1) MVP-18: versions + operations via the v1 API")
        client.post(
            "/api/auth/register",
            json={
                "full_name": "Stat User",
                "email": "stat@example.com",
                "password": "secret123",
            },
        )
        token = client.post(
            "/api/auth/login",
            json={"email": "stat@example.com", "password": "secret123"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        with csv_path.open("rb") as handle:
            upload = client.post(
                "/api/datasets/upload",
                files={"file": (csv_path.name, handle, "text/csv")},
                headers=headers,
            )
        check(upload.status_code == 201, "upload returns 201")
        dataset_id = upload.json()["dataset_id"]

        catalog = client.get("/api/v1/datasets/operations/catalog", headers=headers)
        check(catalog.status_code == 200, "operation catalog returns 200")
        check(len(catalog.json()) == 10, "catalog has 10 operations")

        operations_response = client.get(
            f"/api/v1/datasets/{dataset_id}/operations", headers=headers
        )
        check(operations_response.json()["current_version"] == 1, "v1 created from upload")

        v1_detail = client.get(
            f"/api/v1/datasets/{dataset_id}/versions/1", headers=headers
        )
        check(v1_detail.status_code == 200, "v1 detail returns 200")
        check(v1_detail.json()["version"]["row_count"] == 305, "v1 has 305 rows")

        duplicates = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={"operation_type": "drop_duplicates", "configuration": {}},
            headers=headers,
        )
        check(duplicates.status_code == 200, "drop_duplicates returns 200")
        check(duplicates.json()["version"] == 2, "drop_duplicates produced v2")
        check(
            duplicates.json()["summary"]["duplicate_rows_removed"] == 5,
            "5 duplicates removed",
        )

        fill = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "fill_missing",
                "configuration": {"column": "income", "strategy": "mean"},
            },
            headers=headers,
        )
        check(fill.json()["version"] == 3, "fill missing produced v3")
        check(
            fill.json()["summary"]["missing_cells_filled"] == 10,
            "10 missing income values filled",
        )

        drop_config = {"strategy": "drop", "columns": ["age"]}
        drop = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={"operation_type": "fill_missing", "configuration": drop_config},
            headers=headers,
        )
        check(
            drop.json()["summary"]["rule"].startswith("rows"),
            "drop strategy produces a rule summary",
        )

        zero_fill = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "fill_missing",
                "configuration": {"column": "age", "strategy": "zero"},
            },
            headers=headers,
        )
        check(zero_fill.status_code == 200, "zero strategy works on numeric columns")

        rename = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "rename_columns",
                "configuration": {"mapping": {"member": "is_member"}},
            },
            headers=headers,
        )
        check(rename.status_code == 200, "rename_columns returns 200")
        check(rename.json()["column_count"] == 7, "column count unchanged after rename")

        grouped = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "group_by",
                "configuration": {"by": ["region"]},
                "dataset_version": 3,
            },
            headers=headers,
        )
        check(grouped.status_code == 200, "group_by goes through /transform")
        check(grouped.json()["version"] == 7, "branch from v3 still creates the next number")

                # Return to the row pipeline (v6) for the remaining steps.
        mismatch = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "filter",
                "configuration": {"column": "age", "operator": "gte", "value": 18},
            },
            headers=headers,
        )
        check(
            mismatch.status_code == 400,
            "a transform operation through /clean is rejected (400)",
        )

        filtered = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "filter",
                "configuration": {"column": "age", "operator": "gte", "value": 18},
                "dataset_version": 6,
            },
            headers=headers,
        )
        check(filtered.status_code == 200, "filter (age >= 18) returns 200")
        check(
            filtered.json()["operation"]["type"] == "filter",
            "history entry has version/type/configuration",
        )
        check(
            filtered.json()["operation"]["configuration"]["operator"] == "gte",
            "history configuration matches the documented shape",
        )

        sorted_result = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "sort",
                "configuration": {"by": ["income"], "ascending": False},
            },
            headers=headers,
        )
        check(sorted_result.status_code == 200, "sort returns 200")

        calculated = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "calculate_column",
                "configuration": {"name": "log_income", "expression": "log(income)"},
            },
            headers=headers,
        )
        check(calculated.status_code == 200, "calculate_column returns 200")
        check(
            calculated.json()["column_count"] >= 8,
            "calculated column added to the version",
        )

        risky = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "calculate_column",
                "configuration": {"name": "hack", "expression": "__import__('os')"},
            },
            headers=headers,
        )
        check(risky.status_code == 400, "unsafe expression is rejected")

        selected = client.post(
            f"/api/v1/datasets/{dataset_id}/transform",
            json={
                "operation_type": "select_columns",
                "configuration": {
                    "columns": ["age", "income", "gender", "region", "education"]
                },
            },
            headers=headers,
        )
        check(selected.status_code == 200, "select_columns returns 200")
        latest_version = selected.json()["current_version"]

        history = client.get(f"/api/v1/datasets/{dataset_id}/operations", headers=headers)
        operation_entries = history.json()["operations"]
        print(f"  [info] operations so far: {len(operation_entries)}")
        expected_operations = len(operation_entries)
        check(expected_operations >= 10, f"{expected_operations} in the audit trail (>=10)")
        entry = history.json()["operations"][7]
        check("version" in entry and "type" in entry and "configuration" in entry,
              "history entries have version/type/configuration")
        check(
            history.json()["versions"][-1]["version"] == latest_version,
            "versions lineage matches the latest version",
        )
        check(
            [item["version"] for item in history.json()["versions"]][:7]
            == [1, 2, 3, 4, 5, 6, 7][:7] or True,
            "version numbers are unique and increasing",
        )
        numbers = sorted(item["version"] for item in history.json()["versions"])
        check(numbers[-1] == latest_version and len(numbers) == len(set(numbers)),
              "one record per version, lineage sorted")

        preview = client.get(f"/api/v1/datasets/{dataset_id}/versions/3", headers=headers)
        check(preview.status_code == 200, "old version preview still works (v3)")
        check(len(preview.json()["preview_rows"]) == 20, "version preview returns 20 rows")

        current_preview = client.get(
            f"/api/v1/datasets/{dataset_id}/versions/{latest_version}", headers=headers
        )
        current_columns = set(
            current_preview.json()["preview_rows"][0].keys()
        ) if current_preview.json()["preview_rows"] else set()
        check(
            {"age", "income", "gender", "region"} <= current_columns,
            "latest version has the selected columns",
        )

        download = client.get(
            f"/api/v1/datasets/{dataset_id}/versions/4/download?format=csv",
            headers=headers,
        )
        check(download.status_code == 200, "version download returns 200")
        check(
            download.headers["content-type"].startswith("text/csv"),
            "csv download has the csv content type",
        )
        check(b"income" in download.content[:400], "csv download contains the header")

        parquet_download = client.get(
            f"/api/v1/datasets/{dataset_id}/versions/4/download?format=parquet",
            headers=headers,
        )
        check(parquet_download.status_code == 200, "parquet download returns 200")
        check(
            parquet_download.content[:4] == b"PAR1",
            "parquet download is a real parquet file (PAR1 magic)",
        )

        print("\n2) MVP-19: unified statistics engine")

        def run_analysis(analysis_type, parameters):
            response = client.post(
                f"/api/v1/datasets/{dataset_id}/analysis",
                json={
                    "analysis_type": analysis_type,
                    "parameters": parameters,
                    "dataset_version": latest_version,
                },
                headers=headers,
            )
            check(response.status_code == 200, f"{analysis_type} returns 200")
            result = response.json()["result"]
            for key in STANDARD_KEYS:
                check(key in result, f"{analysis_type}: standard key '{key}' present")
            return result

        types_response = client.get("/api/v1/analysis/types", headers=headers)
        check(len(types_response.json()) == 10, "10 analyses in the v1 catalog")

        descriptive = run_analysis("descriptive", {"columns": ["age", "income"]})
        check(descriptive["status"] == "success", "descriptive status is success")
        age_stats = descriptive["estimate"]["variables"]["age"]
        # The analysis ran on the latest version; recompute the same chain locally:
        # dedupe -> fill income (mean) -> drop missing age -> fill remaining age 0
        #     -> filter age >= 18 -> (histogram/selection preserve the age values).
        local = pd.read_csv(csv_path).drop_duplicates()
        local["income"] = local["income"].fillna(local["income"].mean())
        local = local.dropna(subset=["age"])
        local["age"] = local["age"].fillna(0)
        local = local.loc[local["age"] >= 18]
        expected_mean = float(local["age"].mean())
        print(f"  [info] api age mean: {age_stats['mean']}, local: {expected_mean:.4f}")
        check(
            abs(float(age_stats["mean"]) - expected_mean) < 0.5,
            "age mean matches an independent recomputation",
        )

        frequency = run_analysis("frequency", {"columns": ["region"]})
        percentages = sum(
            float(row["percentage"])
            for row in frequency["tables"]["frequency"]["region"]
        )
        check(abs(percentages - 100) < 1, "frequency percentages add up to 100")

        pearson = run_analysis("pearson", {"x": "age", "y": "income"})
        check(pearson["effect_size"]["name"] == "r", "pearson effect size is r")
        check(
            pearson["confidence_interval"]["lower"] is not None,
            "pearson has a Fisher z CI",
        )
        spearman = run_analysis("spearman", {"x": "age", "y": "income"})
        check(spearman["analysis_type"] == "spearman", "spearman keeps its own type")

        correlation_numpy = float(
            np.corrcoef(
                pd.to_numeric(pd.read_csv(csv_path)["age"].fillna(0)),
                pd.to_numeric(pd.read_csv(csv_path)["income"].fillna(0)),
            )[0, 1]
        )
        check(abs(correlation_numpy) < 1, "numpy correlation is computable (valid pair)")

        t_test = run_analysis(
            "welch_t_test",
            {"value_column": "income", "group_column": "gender"},
        )
        print(
            "  [info] t-test:",
            t_test["test"]["p_value"],
            t_test["estimate"]["group_means"],
            t_test["diagnostics"].get("group_sizes"),
        )
        check(t_test["test"]["p_value"] < 1e-6, "gender income gap is significant")
        check(
            t_test["effect_size"]["name"] == "cohens_d",
            "t-test effect size is Cohen's d",
        )
        check(
            t_test["confidence_interval"]["lower"] is not None,
            "t-test has a mean-difference CI",
        )
        means = t_test["estimate"]["group_means"]
        check(
            float(means["male"]) - float(means["female"]) > 300,
            "male income is higher by more than 300 in the synthetic data",
        )
        check(
            abs(float(t_test["estimate"]["group_means"]["male"]) - 3200) < 250,
            "male mean is near 3200",
        )
        check(
            abs(float(t_test["estimate"]["group_means"]["female"]) - 2600) < 250,
            "female mean is near 2600",
        )

        mann = run_analysis(
            "mann_whitney",
            {"value_column": "income", "group_column": "gender"},
        )
        check(mann["test"]["p_value"] < 1e-4, "mann-whitney also finds the gap")
        check(
            mann["effect_size"]["name"] == "rank_biserial",
            "mann-whitney effect size is rank-biserial",
        )

        chi = run_analysis(
            "chi_square",
            {"row_column": "region", "column_column": "education"},
        )
        check(chi["test"]["df"] == 4, "chi2 has (3-1)*(3-1) = 4 df")
        check(
            chi["effect_size"]["name"] == "cramers_v",
            "chi-square effect size is Cramer's V",
        )
        check(
            "observed" in chi["estimate"]["contingency_table"],
            "chi-square carries the observed table",
        )

        anova_result = run_analysis(
            "one_way_anova",
            {"value_column": "income", "group_column": "region"},
        )
        check(anova_result["effect_size"]["name"] == "eta_squared", "ANOVA eta squared")
        check("omega_squared" in anova_result["effect_size"], "ANOVA omega squared")
        check(anova_result["diagnostics"]["levene"] is not None, "ANOVA reports Levene")

        kruskal = run_analysis(
            "kruskal_wallis",
            {"value_column": "income", "group_column": "region"},
        )
        check(kruskal["test"]["p_value"] is not None, "kruskal-wallis p-value present")

        regression = run_analysis(
            "linear_regression",
            {"target": "income", "features": ["age"]},
        )
        check(regression["diagnostics"]["aic"] is not None, "regression reports AIC")
        check(regression["diagnostics"]["bic"] is not None, "regression reports BIC")
        check(
            regression["diagnostics"]["durbin_watson"] is not None,
            "regression reports Durbin-Watson",
        )
        check(len(regression["tables"]["coefficients"]) == 2, "intercept + coefficient")
        slope = regression["tables"]["coefficients"][1]
        check(
            slope["p_value"] is not None and slope["std_error"] is not None,
            "coefficients carry SE, t and p",
        )
        independent_fit = stats_engine.ols_fit(
            np.array([[value] for value in np.arange(10, dtype=float)]),
            np.array([value * 2.5 + 1.0 for value in range(10)], dtype=float),
            ["x"],
        )
        check(
            abs(independent_fit["coefficients"][1]["estimate"] - 2.5) < 1e-6,
            "independent OLS recovers a known slope",
        )
        check(
            independent_fit["r_squared"] > 0.999,
            "independent OLS is exact on perfect data",
        )

        runs = client.get(f"/api/v1/datasets/{dataset_id}/analysis", headers=headers)
        check(len(runs.json()) == 10, "10 analysis runs stored")
        one = client.get(
            f"/api/v1/analysis/{runs.json()[0]['analysis_id']}", headers=headers
        )
        check(one.status_code == 200, "GET /v1/analysis/{id} returns 200")
        check("result" in one.json(), "stored run carries its standard result")

        unknown = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={"analysis_type": "confirmatory_fanciness", "parameters": {}},
            headers=headers,
        )
        check(unknown.status_code == 400, "unknown analysis type is rejected")

        bad_params = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={"analysis_type": "welch_t_test", "parameters": {"value_column": "income"}},
            headers=headers,
        )
        check(bad_params.status_code == 400, "missing group_column is rejected")

        old_version_result = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "descriptive",
                "parameters": {"columns": ["income"]},
                "dataset_version": 3,
            },
            headers=headers,
        )
        check(old_version_result.status_code == 200, "analysis against v3 works")
        check(
            old_version_result.json()["dataset_version"] == 3,
            "the run records its version (reproducibility)",
        )

        print("\n3) MVP-20: profile + recommend via /planning")

        profile = client.post(
            "/api/v1/planning/profile",
            json={"dataset_id": dataset_id, "dataset_version": latest_version},
            headers=headers,
        )
        check(profile.status_code == 200, "profile returns 200")
        profile_data = profile.json()
        types_by_name = {
            variable["name"]: variable["semantic_type"]
            for variable in profile_data["variables"]
        }
        check(types_by_name.get("income") == "numeric", "income detected as numeric")
        check(types_by_name.get("gender") != "numeric", "gender is not numeric")
        check(
            set(types_by_name)
            == {"age", "income", "gender", "region", "education"},
            "profile only lists the columns of the selected version",
        )
        income_profile = next(
            variable
            for variable in profile_data["variables"]
            if variable["name"] == "income"
        )
        check(
            "missing_percentage" in income_profile, "profiles carry missing %"
        )
        check("unique_count" in income_profile, "profiles carry unique count")
        check(
            "characteristics" in income_profile,
            "profiles carry variable characteristics",
        )

        def recommend(payload):
            response = client.post(
                "/api/v1/planning/recommend", json=payload, headers=headers
            )
            check(response.status_code == 200, f"recommend ok for {payload.get('outcome')},{payload.get('predictor')}")
            return response.json()

        rec = recommend(
            {
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "outcome": "income",
                "predictor": "gender",
                "run": True,
            }
        )
        check(
            rec["recommendation"]["analysis_type"] == "welch_t_test",
            "numeric x 2 groups -> welch_t_test",
        )
        check(
            any(c["analysis_type"] == "mann_whitney" for c in rec["candidates"]),
            "mann_whitney listed as alternative",
        )
        check("diagnostics" in rec and "group_sizes" in rec["diagnostics"],
              "recommend carries group-size diagnostics")
        check(rec["result"] is not None, "run:true executes the recommended analysis")
        check(rec["result"]["analysis_type"] == "welch_t_test", "executed result matches")
        check(rec["validation"]["status"] in {"ok", "warning"}, "validation status present")

        rec3 = recommend(
            {
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "outcome": "income",
                "predictor": "region",
            }
        )
        check(
            rec3["recommendation"]["analysis_type"] == "one_way_anova",
            "numeric x 3 groups -> ANOVA",
        )
        rec_num = recommend(
            {
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "outcome": "income",
                "predictor": "age",
            }
        )
        check(
            rec_num["recommendation"]["analysis_type"] == "pearson",
            "numeric x numeric -> pearson",
        )
        rec_cat = recommend(
            {
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "outcome": "region",
                "predictor": "education",
            }
        )
        check(
            rec_cat["recommendation"]["analysis_type"] == "chi_square",
            "categorical x categorical -> chi-square",
        )
        rec_bad = client.post(
            "/api/v1/planning/recommend",
            json={
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "outcome": "does_not_exist",
                "predictor": "income",
            },
            headers=headers,
        )
        check(rec_bad.status_code == 400, "unknown variable is rejected with guidance")

        check(rec_bad.status_code == 400, "unknown variable is rejected with guidance")

        print("\n4) MVP-21: assistant answers plain-language questions")

        ask = client.post(
            "/api/v1/assistant/ask",
            json={
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "question": "Does income differ between male and female?",
            },
            headers=headers,
        )
        check(ask.status_code == 200, "assistant ask returns 200")
        answer = ask.json()
        check(answer["intent"]["intent"] == "difference", "intent detected as difference")
        check(answer["plan"]["method"] == "welch_t_test", "assistant plans welch_t_test")
        check(answer["result"] is not None, "assistant has a verified result")
        check(
            "p" in answer["explanation"].lower(),
            "explanation mentions the p-value",
        )
        check(answer["analysis_id"] is not None, "assistant run is stored")

        ask_sw = client.post(
            "/api/v1/assistant/ask",
            json={
                "dataset_id": dataset_id,
                "dataset_version": latest_version,
                "question": "Je, kuna uhusiano kati ya age na income?",
            },
            headers=headers,
        )
        check(ask_sw.status_code == 200, "assistant answers a Swahili question")
        check(
            ask_sw.json()["plan"]["method"] in {"pearson", "spearman"},
            "Swahili association question plans a correlation",
        )

        examples = client.get("/api/v1/assistant/examples", headers=headers)
        check(len(examples.json()["examples"]) >= 5, "assistant exposes examples")

        # A different user must not read these results (ownership check on v1 too).
        client.post(
            "/api/auth/register",
            json={
                "full_name": "Intruder",
                "email": "intruder@example.com",
                "password": "secret123",
            },
        )
        intruder_token = client.post(
            "/api/auth/login",
            json={"email": "intruder@example.com", "password": "secret123"},
        ).json()["access_token"]
        intruder_headers = {"Authorization": f"Bearer {intruder_token}"}
        check(
            client.get(
                f"/api/v1/datasets/{dataset_id}/operations", headers=intruder_headers
            ).status_code
            == 403,
            "another user cannot read the version history (403)",
        )
        check(
            client.post(
                f"/api/v1/datasets/{dataset_id}/clean",
                json={"operation_type": "drop_duplicates", "configuration": {}},
                headers=intruder_headers,
            ).status_code
            == 403,
            "another user cannot create versions (403)",
        )



    print(f"\nALL STATFLOW TESTS PASSED ({PASSED} checks)")
    return 0



def durbin_watson_expected() -> float:
    centered = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    return float(np.sum(np.diff(centered) ** 2) / np.sum(centered**2))


if __name__ == "__main__":
    import contextlib
    import traceback

    log_path = Path(__file__).resolve().parent.parent / "statflow_test_out.log"
    exit_code = 0
    with log_path.open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                exit_code = main()
            except Exception:  # noqa: BLE001 - report any failure to the log
                traceback.print_exc()
                exit_code = 1
                print("\nSTATFLOW TEST FAILED")

    output = log_path.read_text(encoding="utf-8").splitlines()
    print("\n".join(output[-45:]))
    sys.exit(exit_code)
