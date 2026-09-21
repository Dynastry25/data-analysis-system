"""End-to-end smoke test for the Data Analysis Platform API.

Runs the whole MVP journey against a *temporary* database and storage folder
(so it never touches your real data):

    register -> login -> upload CSV -> profile -> clean -> analyse
    -> charts -> export (xlsx + pdf) -> download -> delete

Run it with:  python tests/smoke_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

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
            files={"file": ("notes.txt", b"not,a,dataset", "text/plain")},
            headers=headers,
        )
        check(bad_upload.status_code == 400, "unsupported file type is rejected")

        detail = client.get(f"/api/datasets/{dataset_id}", headers=headers)
        check(detail.status_code == 200, "dataset detail returns 200")
        check(len(detail.json()["preview_rows"]) == 20, "preview returns 20 rows")

        profile = client.get(f"/api/datasets/{dataset_id}/profile", headers=headers)
        check(profile.status_code == 200, "profile returns 200")
        profile_columns = {item["name"]: item for item in profile.json()["columns"]}
        check(profile_columns["sales"]["data_type"] == "numeric", "sales detected numeric")
        check(profile_columns["region"]["data_type"] == "text", "region detected text")
        check(profile_columns["order_date"]["data_type"] == "date", "order_date detected date")

        print("\n3) Cleaning (with audit trail)")
        clean_duplicates = client.post(
            f"/api/datasets/{dataset_id}/clean",
            json={"action_type": "drop_duplicates", "parameters": {}},
            headers=headers,
        )
        check(clean_duplicates.status_code == 200, "drop_duplicates returns 200")
        check(
            clean_duplicates.json()["applied_action"]["duplicate_rows_removed"] == 5,
            "5 duplicate rows removed",
        )
        check(clean_duplicates.json()["row_count"] == 180, "row count updated to 180")

        fill_missing = client.post(
            f"/api/datasets/{dataset_id}/clean",
            json={
                "action_type": "fill_missing",
                "parameters": {"column": "unit_price", "method": "mean"},
            },
            headers=headers,
        )
        check(fill_missing.status_code == 200, "fill_missing (mean) returns 200")
        check(
            fill_missing.json()["applied_action"]["missing_filled"] == 5,
            "5 missing unit_price values filled",
        )

        fill_category = client.post(
            f"/api/datasets/{dataset_id}/clean",
            json={
                "action_type": "fill_missing",
                "parameters": {"column": "region", "method": "value", "value": "Unknown"},
            },
            headers=headers,
        )
        check(fill_category.status_code == 200, "fill_missing (value) returns 200")

        convert = client.post(
            f"/api/datasets/{dataset_id}/clean",
            json={
                "action_type": "convert_type",
                "parameters": {"column": "paid", "target_type": "boolean"},
            },
            headers=headers,
        )
        check(convert.status_code == 200, "convert_type to boolean returns 200")

        bad_clean = client.post(
            f"/api/datasets/{dataset_id}/clean",
            json={"action_type": "drop_column", "parameters": {"column": "ghost"}},
            headers=headers,
        )
        check(bad_clean.status_code == 400, "cleaning an unknown column is rejected")

        history = client.get(
            f"/api/datasets/{dataset_id}/cleaning-history", headers=headers
        )
        check(len(history.json()) == 4, "cleaning history has 4 entries (audit trail)")

        print("\n4) Statistics")
        descriptive = client.post(
            f"/api/datasets/{dataset_id}/analyze",
            json={"analysis_type": "descriptive_stats", "parameters": {}},
            headers=headers,
        )
        check(descriptive.status_code == 200, "descriptive_stats returns 200")
        stats = descriptive.json()["result_data"]["numeric_stats"]
        sales_stats = next(item for item in stats if item["column"] == "sales")
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
            descriptive.json()["result_data"]["row_count"] == 180,
            "stats used the cleaned row count (180)",
        )

        correlation = client.post(
            f"/api/datasets/{dataset_id}/analyze",
            json={
                "analysis_type": "correlation",
                "parameters": {
                    "columns": ["units", "unit_price", "sales"],
                    "method": "pearson",
                },
            },
            headers=headers,
        )
        check(correlation.status_code == 200, "correlation returns 200")
        matrix = correlation.json()["result_data"]["matrix"]
        check(len(matrix) == 3 and len(matrix[0]) == 3, "3x3 correlation matrix")
        check(abs(matrix[0][0] - 1.0) < 1e-9, "diagonal of the matrix is 1.0")

        regression = client.post(
            f"/api/datasets/{dataset_id}/analyze",
            json={
                "analysis_type": "regression",
                "parameters": {"target": "sales", "features": ["units", "unit_price"]},
            },
            headers=headers,
        )
        check(regression.status_code == 200, "regression returns 200")
        regression_result = regression.json()["result_data"]
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
            abs(regression_result["r_squared"] - expected_r_squared) < 1e-4,
            f"R-squared matches numpy ({regression_result['r_squared']:.4f})",
        )
        check(
            abs(regression_result["coefficients"]["units"] - expected_coefficients[1])
            < 1e-4,
            "units coefficient matches numpy",
        )
        check(
            abs(
                regression_result["coefficients"]["unit_price"]
                - expected_coefficients[2]
            )
            < 1e-4,
            "unit_price coefficient matches numpy",
        )

        t_test = client.post(
            f"/api/datasets/{dataset_id}/analyze",
            json={
                "analysis_type": "hypothesis_test",
                "parameters": {"value_column": "sales", "group_column": "paid"},
            },
            headers=headers,
        )
        check(t_test.status_code == 200, "hypothesis_test returns 200")
        test_result = t_test.json()["result_data"]
        check(0.0 <= test_result["p_value"] <= 1.0, "p-value is between 0 and 1")
        check(
            test_result["test"] == "welch_two_sample_t_test",
            "Welch two-sample t-test used for a two-group column",
        )

        analysis_list = client.get(f"/api/datasets/{dataset_id}/analysis", headers=headers)
        check(len(analysis_list.json()) == 4, "4 analysis results stored")
        analysis_ids = [item["analysis_id"] for item in analysis_list.json()]
        single = client.get(f"/api/analysis/{analysis_ids[0]}", headers=headers)
        check(single.status_code == 200, "GET /analysis/{id} returns 200")

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

        print("\n8) Delete dataset")
        delete = client.delete(f"/api/datasets/{dataset_id}", headers=headers)
        check(delete.status_code == 200, "delete returns 200")
        check(
            client.get(f"/api/datasets/{dataset_id}", headers=headers).status_code == 404,
            "deleted dataset is gone",
        )
    print(f"\nALL SMOKE TESTS PASSED ({PASSED} checks)")
    return 0


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
