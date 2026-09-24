"""End-to-end smoke test for the Data Analysis Platform API.

Runs the whole journey against a *temporary* database and storage folder
(so it never touches your real data):

    register -> login -> upload CSV -> profile -> clean (versions)
    -> unified statistics -> charts -> export (xlsx + pdf) -> download -> delete

Run it with:  python tests/smoke_test.py
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict

import pandas as pd
import numpy as np

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dap_smoke_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "smoke-test-secret-key"

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


def build_sample_csv(path: Path) -> Path:
    """Create a dataset that contains duplicates and missing values on purpose."""
    frame = pd.DataFrame(
        {
            "order_id": list(range(1, 181)),
            "region": (["Dar es Salaam", "Arusha", "Mwanza", "Dodoma"] * 45),
            "units": [((index * 7) % 23) + 1 for index in range(180)],
            "unit_price": [
                round(1000 + (index % 37) * 250.5, 2) for index in range(180)
            ],
            "order_date": pd.date_range("2025-01-01", periods=180, freq="D").astype(str),
            "paid": (["true", "false"] * 90),
        }
    )
    frame["sales"] = (frame["units"] * frame["unit_price"]).round(2)
    frame.loc[5:9, "unit_price"] = None
    frame.loc[20:24, "region"] = None
    frame = pd.concat([frame, frame.iloc[:5]], ignore_index=True)
    frame.to_csv(path, index=False)
    return path


def main() -> int:
    csv_path = build_sample_csv(TEST_ROOT / "sales_sample.csv")
    print(f"Test workspace: {TEST_ROOT}\n")

    with TestClient(app) as client:
        print("1) Auth")
        register = client.post(
            "/api/auth/register",
            json={
                "full_name": "Asha Mwangi",
                "email": "asha@example.com",
                "password": "secret123",
            },
        )
        check(register.status_code == 201, f"register returns 201 ({register.status_code})")
        check(register.json()["email"] == "asha@example.com", "register echoes the email")

        duplicate_user = client.post(
            "/api/auth/register",
            json={
                "full_name": "Asha Mwangi",
                "email": "asha@example.com",
                "password": "secret123",
            },
        )
        check(duplicate_user.status_code == 400, "duplicate email is rejected")

        bad_login = client.post(
            "/api/auth/login", json={"email": "asha@example.com", "password": "wrong"}
        )
        check(bad_login.status_code == 401, "wrong password is rejected")

        login = client.post(
            "/api/auth/login", json={"email": "asha@example.com", "password": "secret123"}
        )
        check(login.status_code == 200, "login succeeds")
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        check(
            client.get("/api/datasets").status_code == 401,
            "dataset list without a token returns 401",
        )

        print("\n2) Upload + preview + profile")
        with csv_path.open("rb") as handle:
            upload = client.post(
                "/api/datasets/upload",
                files={"file": (csv_path.name, handle, "text/csv")},
                headers=headers,
            )
        check(upload.status_code == 201, f"upload returns 201 ({upload.status_code})")
        upload_data = upload.json()
        dataset_id = upload_data["dataset_id"]
        check(upload_data["row_count"] == 185, "185 rows stored (180 + 5 duplicates)")
        check(upload_data["column_count"] == 7, "7 columns detected")
        missing_by_column = {
            column["name"]: column["missing_count"] for column in upload_data["columns"]
        }
        check(missing_by_column["unit_price"] == 5, "missing values counted for unit_price")

        bad_upload = client.post(
            "/api/datasets/upload",
            files={"file": ("notes.docx", b"MZ fake document", "application/pdf")},
            headers=headers,
        )
        check(bad_upload.status_code == 400, "unsupported file type is rejected")

        corrupted = client.post(
            "/api/datasets/upload",
            files={"file": ("broken.xlsx", b"this is not a real spreadsheet", "application/octet-stream")},
            headers=headers,
        )
        check(corrupted.status_code == 400, "corrupted spreadsheet is rejected")
        user_storage = TEST_ROOT / "storage" / "1"
        leaked = [
            path
            for path in user_storage.rglob("*")
            if path.is_file() and path.parent.name != str(dataset_id)
        ]
        check(leaked == [], "failed upload leaves no storage leak")

        detail = client.get(f"/api/datasets/{dataset_id}", headers=headers)
        check(detail.status_code == 200, "dataset detail returns 200")
        check(len(detail.json()["preview_rows"]) == 20, "preview returns 20 rows")

        profile = client.get(f"/api/datasets/{dataset_id}/profile", headers=headers)
        check(profile.status_code == 200, "profile returns 200")
        profile_columns = {item["name"]: item for item in profile.json()["columns"]}
        check(profile_columns["sales"]["data_type"] == "numeric", "sales detected numeric")
        check(profile_columns["region"]["data_type"] == "text", "region detected text")
        check(profile_columns["order_date"]["data_type"] == "date", "order_date detected date")

        print("\n3) Cleaning + transforms (versioned operations, audit trail)")
        clean_duplicates = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={"operation_type": "drop_duplicates", "configuration": {}},
            headers=headers,
        )
        check(clean_duplicates.status_code == 200, "drop_duplicates returns 200")
        check(
            clean_duplicates.json()["summary"]["duplicate_rows_removed"] == 5,
            "5 duplicate rows removed",
        )
        check(clean_duplicates.json()["row_count"] == 180, "row count updated to 180")
        check(
            clean_duplicates.json()["version"] == 2,
            "cleaning created dataset version 2",
        )

        fill_missing = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "fill_missing",
                "configuration": {"column": "unit_price", "strategy": "mean"},
            },
            headers=headers,
        )
        check(fill_missing.status_code == 200, "fill_missing (mean) returns 200")
        missing_summary = fill_missing.json()["summary"]
        filled_unit_price = missing_summary.get("columns_filled", {}).get(
            "unit_price", {}
        )
        check(
            filled_unit_price.get("missing_before", 0)
            - filled_unit_price.get("missing_after", 0)
            == 5,
            "5 missing unit_price values filled",
        )

        fill_category = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "fill_missing",
                "configuration": {
                    "column": "region",
                    "strategy": "constant",
                    "value": "Unknown",
                },
            },
            headers=headers,
        )
        check(fill_category.status_code == 200, "fill_missing (value) returns 200")

        convert = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "cast_types",
                "configuration": {"column": "paid", "target_type": "boolean"},
            },
            headers=headers,
        )
        check(convert.status_code == 200, "cast_types to boolean returns 200")
        check(convert.json()["version"] == 5, "each operation created a new version")

        bad_clean = client.post(
            f"/api/v1/datasets/{dataset_id}/clean",
            json={
                "operation_type": "select_columns",
                "configuration": {"columns": ["ghost"]},
            },
            headers=headers,
        )
        check(bad_clean.status_code == 400, "cleaning an unknown column is rejected")

        history = client.get(
            f"/api/v1/datasets/{dataset_id}/operations", headers=headers
        )
        check(
            len(history.json()["operations"]) == 4,
            "operations history has 4 entries (audit trail)",
        )
        check(
            history.json()["current_version"] == 5,
            "dataset is on version 5 after the cleaning chain",
        )

        print("\n4) Statistics (unified engine)")
        descriptive = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={"analysis_type": "descriptive", "parameters": {}},
            headers=headers,
        )
        check(descriptive.status_code == 200, "descriptive returns 200")
        descriptive_result = descriptive.json()["result"]
        stats = descriptive_result["tables"]["descriptive"]
        sales_stats = next(item for item in stats if item["variable"] == "sales")
        # Reproduce the cleaning chain the API applied: dedupe, then fill the
        # missing unit_price values with the mean of the remaining rows.
        cleaned_frame = pd.read_csv(csv_path).drop_duplicates().reset_index(drop=True)
        cleaned_frame["unit_price"] = cleaned_frame["unit_price"].fillna(
            cleaned_frame["unit_price"].mean()
        )
        expected_mean = float(cleaned_frame["sales"].mean())
        check(
            abs(sales_stats["mean"] - expected_mean) < 0.01,
            f"mean of sales matches pandas ({sales_stats['mean']:.2f})",
        )
        check(sales_stats["median"] is not None, "median is returned")
        check(
            descriptive_result["sample_size"] == 180,
            "stats used the cleaned row count (180)",
        )

        pearson = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "pearson",
                "parameters": {"x": "units", "y": "sales"},
            },
            headers=headers,
        )
        check(pearson.status_code == 200, "pearson correlation returns 200")
        pearson_result = pearson.json()["result"]
        estimate = pearson_result["estimate"]
        check(
            abs(estimate["correlation"]) <= 1.0,
            "correlation estimate is within [-1, 1]",
        )
        check(
            pearson_result["effect_size"]["interpretation"] == estimate["strength"],
            "effect size interpretation matches the strength",
        )
        check(
            pearson_result["tables"]["scatter"]["x_label"] == "units",
            "scatter table keeps the axis labels",
        )

        regression = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "linear_regression",
                "parameters": {"target": "sales", "features": ["units", "unit_price"]},
            },
            headers=headers,
        )
        check(regression.status_code == 200, "linear_regression returns 200")
        regression_result = regression.json()["result"]
        # Independently refit the same model with numpy to verify the numbers.
        feature_matrix = cleaned_frame[["units", "unit_price"]].to_numpy(dtype=float)
        target_values = cleaned_frame["sales"].to_numpy(dtype=float)
        design = np.column_stack([np.ones(target_values.shape[0]), feature_matrix])
        expected_coefficients, *_ = np.linalg.lstsq(design, target_values, rcond=None)
        expected_predictions = design @ expected_coefficients
        ss_residual = float(((target_values - expected_predictions) ** 2).sum())
        ss_total = float(((target_values - target_values.mean()) ** 2).sum())
        expected_r_squared = 1.0 - ss_residual / ss_total
        check(
            abs(regression_result["estimate"]["r_squared"] - expected_r_squared) < 1e-4,
            f"R-squared matches numpy ({regression_result['estimate']['r_squared']:.4f})",
        )
        coefficients = {
            row["variable"]: row["estimate"]
            for row in regression_result["tables"]["coefficients"]
        }
        check(
            abs(coefficients["units"] - expected_coefficients[1]) < 1e-4,
            "units coefficient matches numpy",
        )
        check(
            abs(coefficients["unit_price"] - expected_coefficients[2]) < 1e-4,
            "unit_price coefficient matches numpy",
        )

        t_test = client.post(
            f"/api/v1/datasets/{dataset_id}/analysis",
            json={
                "analysis_type": "welch_t_test",
                "parameters": {"value_column": "sales", "group_column": "paid"},
            },
            headers=headers,
        )
        check(t_test.status_code == 200, "welch_t_test returns 200")
        test_result = t_test.json()["result"]
        check(0.0 <= test_result["test"]["p_value"] <= 1.0, "p-value is between 0 and 1")
        check(
            "Welch" in str(test_result["test"]["method"]),
            "Welch two-sample t-test used for a two-group column",
        )

        analysis_list = client.get(
            f"/api/v1/datasets/{dataset_id}/analysis", headers=headers
        )
        check(len(analysis_list.json()) == 4, "4 analysis runs stored")
        analysis_ids = [item["analysis_id"] for item in analysis_list.json()]
        single = client.get(f"/api/v1/analysis/{analysis_ids[0]}", headers=headers)
        check(single.status_code == 200, "GET /v1/analysis/{id} returns 200")

        print("\n5) Charts")
        bar = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={
                "chart_type": "bar",
                "config": {"x": "region", "y": "sales", "aggregate": "sum"},
            },
            headers=headers,
        )
        check(bar.status_code == 200, "bar chart returns 200")
        bar_series = bar.json()["chart_data"]["series"][0]
        check(len(bar_series["x"]) == 5, "bar chart has 5 regions (4 + 'Unknown')")
        check(len(bar_series["y"]) == 5, "bar chart has 5 values")

        line = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={
                "chart_type": "line",
                "config": {"x": "order_date", "y": "sales", "aggregate": "mean"},
            },
            headers=headers,
        )
        check(line.status_code == 200, "line chart returns 200")

        grouped = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={
                "chart_type": "bar",
                "config": {"x": "region", "y": "sales", "group_by": "paid"},
            },
            headers=headers,
        )
        check(grouped.status_code == 200, "grouped bar chart returns 200")
        check(len(grouped.json()["chart_data"]["series"]) == 2, "one series per group")

        scatter = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={"chart_type": "scatter", "config": {"x": "units", "y": "sales"}},
            headers=headers,
        )
        check(scatter.status_code == 200, "scatter chart returns 200")

        histogram = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={"chart_type": "histogram", "config": {"x": "sales", "bins": 12}},
            headers=headers,
        )
        check(histogram.status_code == 200, "histogram returns 200")

        bad_chart = client.post(
            f"/api/datasets/{dataset_id}/charts",
            json={"chart_type": "bar", "config": {"x": "region", "y": "order_date"}},
            headers=headers,
        )
        check(bad_chart.status_code == 400, "chart with a non-numeric Y column is rejected")

        charts = client.get(f"/api/datasets/{dataset_id}/charts", headers=headers)
        chart_ids = [item["chart_id"] for item in charts.json()]
        check(len(chart_ids) == 5, "5 charts stored")
        check(
            client.get(f"/api/charts/{chart_ids[0]}", headers=headers).status_code == 200,
            "GET /charts/{id} returns 200",
        )

        print("\n6) Export + download")
        export = client.post(
            f"/api/datasets/{dataset_id}/export",
            json={
                "format": "xlsx",
                "include_analysis_ids": analysis_ids,
                "include_chart_ids": chart_ids,
            },
            headers=headers,
        )
        check(export.status_code == 202, "export is accepted for processing")
        report_id = export.json()["report_id"]

        status_response = client.get(f"/api/reports/{report_id}/status", headers=headers)
        check(status_response.status_code == 200, "report status endpoint returns 200")

        download = client.get(f"/api/reports/{report_id}/download", headers=headers)
        check(download.status_code == 200, "xlsx report downloads")
        check(download.content[:2] == b"PK", "xlsx report is a real workbook (zip magic)")
        check(
            "spreadsheetml" in download.headers["content-type"],
            "xlsx content-type is correct",
        )

        pdf_export = client.post(
            f"/api/datasets/{dataset_id}/export",
            json={
                "format": "pdf",
                "include_analysis_ids": analysis_ids,
                "include_chart_ids": chart_ids,
            },
            headers=headers,
        )
        check(pdf_export.status_code == 202, "pdf export is accepted")
        pdf_download = client.get(
            f"/api/reports/{pdf_export.json()['report_id']}/download", headers=headers
        )
        check(pdf_download.status_code == 200, "pdf report downloads")
        check(pdf_download.content[:4] == b"%PDF", "pdf report is a real PDF")

        reports = client.get(f"/api/datasets/{dataset_id}/reports", headers=headers)
        check(len(reports.json()) == 2, "both reports listed for the dataset")

        bad_export = client.post(
            f"/api/datasets/{dataset_id}/export",
            json={"format": "xlsx", "include_analysis_ids": [999999]},
            headers=headers,
        )
        check(bad_export.status_code == 400, "export with unknown analysis ids is rejected")

        print("\n7) Privacy between users")
        client.post(
            "/api/auth/register",
            json={
                "full_name": "Juma Ally",
                "email": "juma@example.com",
                "password": "secret123",
            },
        )
        other_token = client.post(
            "/api/auth/login",
            json={"email": "juma@example.com", "password": "secret123"},
        ).json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        check(
            client.get(f"/api/datasets/{dataset_id}", headers=other_headers).status_code
            == 403,
            "another user cannot read the dataset (403)",
        )
        check(
            client.get("/api/datasets", headers=other_headers).json() == [],
            "another user sees an empty dataset list",
        )
        check(
            client.get(
                f"/api/reports/{report_id}/download", headers=other_headers
            ).status_code
            == 404,
            "another user cannot download the report",
        )

        print("\n8) Additional file formats (JSON / TSV / TXT / Parquet)")
        formats_frame = pd.DataFrame(
            {
                "name": ["Aina", "Baraka", "Chausiku", "Doto", "Emili"],
                "score": [12.5, 9.0, None, 15.5, 11.0],
                "active": ["true", "false", "true", "false", "true"],
            }
        )
        extra_files: Dict[str, Path] = {
            ".json": TEST_ROOT / "extra.json",
            ".tsv": TEST_ROOT / "extra.tsv",
            ".txt": TEST_ROOT / "extra.txt",
            ".parquet": TEST_ROOT / "extra.parquet",
        }
        formats_frame.to_json(extra_files[".json"], orient="records")
        formats_frame.to_csv(extra_files[".tsv"], index=False, sep="\t")
        formats_frame.to_csv(extra_files[".txt"], index=False)
        formats_frame.to_parquet(extra_files[".parquet"], index=False)

        for extension, path in extra_files.items():
            with path.open("rb") as handle:
                loaded = client.post(
                    "/api/datasets/upload",
                    files={"file": (path.name, handle, "application/octet-stream")},
                    headers=headers,
                )
            check(
                loaded.status_code == 201,
                f"upload .{extension.lstrip('.')} returns 201 ({loaded.status_code})",
            )
            extra_id = loaded.json()["dataset_id"]
            check(
                loaded.json()["row_count"] == 5,
                f".{extension.lstrip('.')} uploaded with 5 rows",
            )
            detail = client.get(f"/api/datasets/{extra_id}", headers=headers)
            check(
                detail.status_code == 200 and len(detail.json()["preview_rows"]) == 5,
                f".{extension.lstrip('.')} preview reads back correctly",
            )
            # Exercises the version store reading the new format through
            # ``ensure_base_version`` -> ``read_dataframe``.
            versioned = client.post(
                f"/api/v1/datasets/{extra_id}/clean",
                json={"operation_type": "drop_duplicates", "configuration": {}},
                headers=headers,
            )
            check(
                versioned.status_code == 200 and versioned.json()["version"] == 2,
                f".{extension.lstrip('.')} supports versioned cleaning",
            )
            client.delete(f"/api/datasets/{extra_id}", headers=headers)

        print("\n9) Delete dataset")
        delete = client.delete(f"/api/datasets/{dataset_id}", headers=headers)
        check(delete.status_code == 200, "delete returns 200")
        check(
            client.get(f"/api/datasets/{dataset_id}", headers=headers).status_code == 404,
            "deleted dataset is gone",
        )
    print(f"\nALL SMOKE TESTS PASSED ({PASSED} checks)")
    return 0


def test_full_journey() -> None:
    """pytest entry point: same whole-journey run as ``python tests/smoke_test.py``."""
    main()


if __name__ == "__main__":
    # Write the full log to a file (PowerShell hides native stdout when a process
    # exits non-zero) and echo the tail so the result is visible in the terminal.
    import contextlib
    import traceback

    log_path = Path(__file__).resolve().parent.parent / "smoke_test_out.log"
    exit_code = 0
    with log_path.open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                exit_code = main()
            except Exception:  # noqa: BLE001 - report any failure to the log
                traceback.print_exc()
                exit_code = 1
                print("\nSMOKE TEST FAILED")

    output = log_path.read_text(encoding="utf-8").splitlines()
    print("\n".join(output[-40:]))
    sys.exit(exit_code)
