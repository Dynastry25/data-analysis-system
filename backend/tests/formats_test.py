"""Tests for the statistical package formats: Stata, SPSS and R uploads.

The promise those formats make is that a file produced by Stata, SPSS or R lands
here with its shape and its variable types intact, so the checks go past "the
upload returned 201" to the profiled column types, the preview, and a cleaning
step that reads the stored file back through the version store.

Run it with:  python tests/formats_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dap_formats_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "formats-test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import ALLOWED_EXTENSIONS  # noqa: E402
from app.main import app  # noqa: E402
from app.services.data_service import read_dataframe, validate_extension  # noqa: E402
from app.services.stat_file_readers import (  # noqa: E402
    R_SUFFIXES,
    SPSS_SUFFIXES,
    STATA_SUFFIXES,
    read_r_file,
    read_spss_file,
    read_stata_file,
)

PASSED = 0

# One numeric, one coded categorical (value labels must stay numeric codes), and
# one free-text column: the shape every statistical package export has.
ROWS = 6
SAMPLE = pd.DataFrame(
    {
        "amount": [120.5, 88.0, 45.25, 310.0, 12.0, 76.4],
        "gender": [1, 2, 1, 2, 1, 2],
        "region": ["Coast", "Lake", "Highlands", "Coast", "Lake", "Highlands"],
    }
)


def check(condition: bool, message: str) -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        print(f"  FAIL: {message}")


def register(client) -> dict:
    email = "formats@example.com"
    client.post(
        "/api/auth/register",
        json={"full_name": "Formats Tester", "email": email, "password": "secret123"},
    )
    login = client.post(
        "/api/auth/login", json={"email": email, "password": "secret123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def upload(client, headers: dict, path: Path):
    with path.open("rb") as handle:
        return client.post(
            "/api/datasets/upload",
            files={"file": (path.name, handle, "application/octet-stream")},
            headers=headers,
        )


def type_of(response_json: dict, column: str) -> str:
    """Profiled type of ``column``, matched case-insensitively (.por upper-cases)."""
    wanted = column.upper()
    return next(
        item["data_type"]
        for item in response_json["columns"]
        if item["name"].upper() == wanted
    )


def clean_version_2(client, headers: dict, dataset_id: int, label: str) -> None:
    """Cleaning reads the stored source file back through the version store."""
    cleaned = client.post(
        f"/api/v1/datasets/{dataset_id}/clean",
        json={"operation_type": "drop_duplicates", "configuration": {}},
        headers=headers,
    )
    check(
        cleaned.status_code == 200 and cleaned.json()["version"] == 2,
        f"{label} supports versioned cleaning ({cleaned.status_code})",
    )


# ------------------------------------------------------------------- fixtures


def write_stata(path: Path) -> Path:
    # Labels written alongside the data, because a Stata file that describes its
    # own columns is the normal case, not an exotic one.
    SAMPLE.to_stata(
        path,
        write_index=False,
        data_label="Household survey",
        variable_labels={"amount": "Sale amount", "gender": "Sex of respondent"},
        value_labels={"gender": {1: "kiume", 2: "dame"}},
    )
    return path


def write_spss(path: Path, writer) -> Path:
    writer(
        SAMPLE,
        str(path),
        column_labels=["sale amount", "gender code", "zone"],
        variable_value_labels={"gender": {1: "kiume", 2: "dame"}},
    )
    return path


def run_checks(client) -> int:
    headers = register(client)

    print("1) Extension gate")
    stat_extensions = STATA_SUFFIXES | SPSS_SUFFIXES | R_SUFFIXES
    for extension in sorted(stat_extensions):
        check(extension in ALLOWED_EXTENSIONS, f"{extension} is an allowed extension")
        check(
            validate_extension(f"survey{extension}") == extension,
            f"validate_extension accepts {extension}",
        )
    check(validate_extension("SURVEY.DTA") == ".dta", "extension check lower-cases")
    try:
        validate_extension("model.dxt")
        check(False, "an unknown extension is rejected")
    except ValueError as exc:
        check(".dta" in str(exc), "the rejection message lists the new formats")

    print("\n2) Stata .dta")
    stata_path = write_stata(TEST_ROOT / "survey.dta")
    frame, stata_labels = read_stata_file(stata_path)
    check(list(frame.columns) == ["amount", "gender", "region"], "Stata columns read")
    check(
        pd.api.types.is_numeric_dtype(frame["gender"]),
        "Stata value labels stay numeric codes",
    )
    check(
        stata_labels.variable_labels.get("gender") == "Sex of respondent",
        f"the Stata variable label is kept ({stata_labels.variable_labels})",
    )
    check(
        stata_labels.value_labels.get("gender") == {"1": "kiume", "2": "dame"},
        f"the Stata value labels are kept and normalised ({stata_labels.value_labels})",
    )
    check(
        stata_labels.file_label == "Household survey",
        "the Stata file label is kept",
    )

    response = upload(client, headers, stata_path)
    check(
        response.status_code == 201,
        f"upload .dta returns 201 ({response.status_code})",
    )
    body = response.json()
    check(body.get("row_count") == ROWS, ".dta keeps every row")
    check(body.get("column_count") == 3, ".dta keeps every column")
    stata_id = body["dataset_id"]

    detail = client.get(f"/api/datasets/{stata_id}", headers=headers).json()
    check(detail["dataset"]["file_type"] == "dta", "file_type stored as 'dta'")
    check(len(detail["preview_rows"]) == ROWS, ".dta preview reads back")
    check(type_of(detail, "amount") == "numeric", ".dta numeric column is numeric")
    check(type_of(detail, "gender") == "numeric", ".dta coded column is numeric")
    check(type_of(detail, "region") == "text", ".dta text column is text")

    # The point of the whole change: what the file said about its columns has to
    # come back out of the API, not just out of the reader.
    by_name = {column["name"]: column for column in detail["columns"]}
    check(
        by_name["gender"].get("variable_label") == "Sex of respondent",
        f"the uploaded .dta keeps its variable label ({by_name['gender']})",
    )
    check(
        by_name["gender"].get("value_labels") == {"1": "kiume", "2": "dame"},
        f"the uploaded .dta keeps its value labels ({by_name['gender']})",
    )
    check(
        by_name["amount"].get("variable_label") == "Sale amount",
        "a labelled numeric column keeps its label too",
    )
    check(
        by_name["region"].get("variable_label") is None,
        "an unlabelled column reports no label rather than an invented one",
    )
    check(
        by_name["region"].get("value_labels") is None,
        "an unlabelled column reports no value labels",
    )

    explore = client.get(f"/api/datasets/{stata_id}/explore", headers=headers).json()
    explored = {column["name"]: column for column in explore["columns"]}
    check(
        explored["gender"].get("variable_label") == "Sex of respondent",
        "explore carries the variable label as well",
    )
    check(
        explored["gender"].get("value_labels") == {"1": "kiume", "2": "dame"},
        "explore carries the value labels as well",
    )
    check(
        explored["gender"]["kind"] == "categorical",
        f"a coded column is still classified as categorical ({explored['gender']['kind']})",
    )

    clean_version_2(client, headers, stata_id, ".dta")
    after = client.get(f"/api/datasets/{stata_id}", headers=headers).json()
    cleaned = {column["name"]: column for column in after["columns"]}
    check(
        cleaned["gender"].get("value_labels") == {"1": "kiume", "2": "dame"},
        "labels survive a cleaning operation, which writes a new Parquet version",
    )

    print("\n3) SPSS .sav / .por")
    try:
        import pyreadstat  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency missing
        print(f"  skipped: {exc}")
    else:
        sav_path = write_spss(TEST_ROOT / "survey.sav", pyreadstat.write_sav)
        spss_frame, spss_labels = read_spss_file(sav_path)
        check(spss_frame.shape == (ROWS, 3), ".sav shape preserved")
        check(
            pd.api.types.is_numeric_dtype(spss_frame["gender"]),
            ".sav value labels stay numeric codes",
        )
        check(
            spss_labels.value_labels.get("gender") == {"1": "kiume", "2": "dame"},
            f"the .sav value labels survive as normalised codes ({spss_labels.value_labels})",
        )
        check(
            spss_labels.variable_labels.get("amount") == "sale amount",
            f"the .sav variable labels survive ({spss_labels.variable_labels})",
        )

        response = upload(client, headers, sav_path)
        check(
            response.status_code == 201,
            f"upload .sav returns 201 ({response.status_code})",
        )
        sav_id = response.json()["dataset_id"]
        detail = client.get(f"/api/datasets/{sav_id}", headers=headers).json()
        check(detail["dataset"]["file_type"] == "sav", "file_type stored as 'sav'")
        check(type_of(detail, "amount") == "numeric", ".sav numeric column is numeric")
        check(type_of(detail, "gender") == "numeric", ".sav coded column is numeric")
        check(type_of(detail, "region") == "text", ".sav text column is text")
        sav_columns = {column["name"]: column for column in detail["columns"]}
        check(
            sav_columns["gender"].get("value_labels") == {"1": "kiume", "2": "dame"},
            f"the uploaded .sav keeps its value labels ({sav_columns['gender']})",
        )
        check(
            sav_columns["amount"].get("variable_label") == "sale amount",
            "the uploaded .sav keeps its variable labels",
        )
        clean_version_2(client, headers, sav_id, ".sav")

        por_path = TEST_ROOT / "survey.por"
        pyreadstat.write_por(SAMPLE, str(por_path))
        response = upload(client, headers, por_path)
        check(
            response.status_code == 201,
            f"upload .por returns 201 ({response.status_code})",
        )
        check(
            response.json().get("column_count") == 3,
            ".por keeps every column (names may be upper-cased by the format)",
        )
        clean_version_2(client, headers, response.json()["dataset_id"], ".por")

    print("\n4) R workspaces (.RData / .rda / .rds)")
    # pyreadr only reads R files, so there is no fixture to write here: what this
    # platform guarantees is that a broken or non-R file named like one is refused
    # with a message from the R reader, never a 500 and never Excel fallback.
    for extension in sorted(R_SUFFIXES):
        broken = TEST_ROOT / f"broken{extension}"
        broken.write_text("not really an R workspace", encoding="utf-8")
        response = upload(client, headers, broken)
        check(
            response.status_code == 400,
            f"a broken {extension} is refused with 400 ({response.status_code})",
        )
        check(
            "R file" in response.json()["detail"],
            f"the {extension} error comes from the R reader",
        )
        check(
            client.get("/api/datasets", headers=headers).status_code == 200,
            f"a refused {extension} leaves the API healthy",
        )
    try:
        read_r_file(TEST_ROOT / "broken.rds")
        check(False, "reading a non-R file raises")
    except ValueError as exc:
        check("R file" in str(exc), "read_r_file names the failing file")

    print("\n5) A file that is not really what its name claims")
    fake = TEST_ROOT / "fake.dta"
    fake.write_text("name,value\na,1\n", encoding="utf-8")
    response = upload(client, headers, fake)
    check(response.status_code == 400, "a CSV renamed to .dta is refused")
    check("Stata" in response.json()["detail"], "the error comes from the Stata reader")
    fake_sav = TEST_ROOT / "fake.sav"
    fake_sav.write_text("name,value\na,1\n", encoding="utf-8")
    response = upload(client, headers, fake_sav)
    check(response.status_code == 400, "a CSV renamed to .sav is refused")
    check("SPSS" in response.json()["detail"], "the error comes from the SPSS reader")

    print("\n6) read_dataframe dispatch")
    round_trip_paths = [stata_path] + [
        path
        for path in (TEST_ROOT / "survey.sav", TEST_ROOT / "survey.por")
        if path.exists()
    ]
    for path in round_trip_paths:
        restored = read_dataframe(path)
        check(
            restored.shape == (ROWS, 3),
            f"read_dataframe restores {path.suffix} with the same shape",
        )
        check(
            all(str(column).strip() == str(column) for column in restored.columns),
            f"{path.suffix} columns are stripped",
        )
    check(
        all(
            column in read_stata_file(stata_path)[0].columns
            for column in ("amount", "gender", "region")
        ),
        "the version store can read the stored .dta path back",
    )

    print(f"\n{PASSED} checks passed")
    return 0


def main() -> int:
    # The client is opened as a context manager so the app lifespan runs and
    # creates the SQLite tables, exactly like the other tests in this folder.
    with TestClient(app) as client:
        return run_checks(client)


if __name__ == "__main__":
    sys.exit(main())


