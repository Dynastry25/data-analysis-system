"""One-click remediation of the Validate findings (improvement plan 3.1).

The Validate stage already says what is wrong with a file; these
tests pin that the fix is one reviewable action, and that it obeys
the two rules that make automation safe to trust:

  * nothing is mutated -- the fixes are the ordinary cleaning
    operations, so the caller writes a NEW immutable version and
    the original file stays exactly as uploaded, and
  * a judgment the engine cannot make is offered, never applied --
    negative values and identifier columns get a button but stay
    out of the default click, and a half-empty column is opt-in.

Data whose correct answer can be worked out by hand: a file with a
repeated header, a blank column, an empty column, a constant
column and three duplicated rows has exactly five findings, and
after the default click exactly one informational finding is left.

Run it with:  python tests/remediation_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="remediation_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "remediation-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.validation_service import validate_frame  # noqa: E402
from app.statflow import remediation  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


# --------------------------------------------------------------- fixtures


def dirty_frame() -> pd.DataFrame:
    """A repeated header, a blank column, an empty column, a constant
    column and three duplicated rows -- five findings, by hand."""
    return pd.DataFrame(
        [
            [25, "1000", "a", 1, None],
            [31, "2000", "b", 1, None],
            [25, "1000", "a", 1, None],
            [31, "2000", "b", 1, None],
            [47, "4000", "c", 1, None],
            [25, "1000", "a", 1, None],
        ],
        columns=["age", "age", "Unnamed: 0", "salary", "half_empty"],
    )


def codes_of(report: dict) -> list:
    return [issue["code"] for issue in report.get("issues") or []]


# ------------------------------------------------------------------- tests


def test_every_finding_offers_the_right_button() -> None:
    print("\n1) The buttons match the findings, and say what they fix")
    report = validate_frame(dirty_frame())
    buttons = remediation.remediable_fixes(report)

    check(
        [button["code"] for button in buttons]
        == [
            "duplicate_column_names",
            "column_all_missing",
            "blank_column_names",
            "constant_column",
            "zero_variance",
            "duplicate_rows",
            "numeric_stored_as_text",
        ],
        "one button per remediable finding, in the report's order",
    )
    check(
        all(button["message"] for button in buttons),
        "each button carries the finding text it fixes",
    )


def test_a_judgment_finding_is_never_in_the_default_click() -> None:
    print("\n2) A judgment gets a button but not the default click")
    frame = pd.DataFrame({"value": [1, -2, 3], "id": [1, 2, 3]})
    report = validate_frame(frame)

    codes = codes_of(report)
    check("negative_values" in codes, "the file reaches the negative-value finding")
    check(
        not any(button["code"] == "negative_values" for button in remediation.remediable_fixes(report)),
        "negative values get no fix button at all",
    )

    # Half-empty: the finding is real but the fix is a judgment, so it
    # is offered and stays out of the default set.
    half = pd.DataFrame(
        {"thin": [1, 2, None, None, None], "full": [1, 2, 3, 4, 5]}
    )
    half_report = validate_frame(half)
    thin = [
        button
        for button in remediation.remediable_fixes(half_report)
        if button["code"] == "column_mostly_missing"
    ]
    check(len(thin) == 1, "a half-empty column offers its own button")
    check(not thin[0]["default"], "and it is not in the default set")
    default_result = remediation.remediate_frame(half, half_report)
    check(
        "thin" in default_result["frame"].columns,
        "the default click leaves the half-empty column alone",
    )
    opt_in = remediation.remediate_frame(
        half, half_report, [{"code": "column_mostly_missing"}]
    )
    check(
        "thin" not in opt_in["frame"].columns,
        "asking for it by code fixes exactly that",
    )


def test_the_default_click_cleans_the_file() -> None:
    print("\n3) One click over the mundane findings, in a safe order")
    frame = dirty_frame()
    report = validate_frame(frame)
    result = remediation.remediate_frame(frame, report)

    check(result["changed"], "something was fixed")
    check(result["rows_before"] == 6 and result["rows_after"] == 3,
          "three duplicated rows are gone")
    check(result["columns_before"] == 5 and result["columns_after"] == 3,
          "the empty and constant columns are gone")
    after = validate_frame(result["frame"])
    check(after["verdict"] == "warnings", "the file is analysable afterwards")
    check(codes_of(after) == ["numeric_stored_as_text", "likely_identifier"],
          "the text-number column and the identifier note remain")

    columns = list(result["frame"].columns)
    check(columns == ["age", "age_2", "column_3"],
          "the repeated 'age' became 'age_2' and the blank name became 'column_3'")
    check(
        result["frame"]["age_2"].tolist() == ["1000", "2000", "4000"],
        "the renamed column kept its values",
    )
    check(
        result["frame"]["column_3"].tolist() == ["a", "b", "c"],
        "the column that had no name kept its values too",
    )

    # The finding named 'age' when two columns were called 'age', so it
    # could not say which one it meant. It is reported as needing the
    # names fixed first -- and after they are, the finding is unambiguous.
    cast_skips = [
        item for item in result["skipped"] if item["code"] == "numeric_stored_as_text"
    ]
    check(bool(cast_skips), "the ambiguous text-number finding is reported, not guessed")
    check(
        "jina linalojirudia" in cast_skips[0]["reason"],
        "the reason says the repeated names must be fixed first",
    )
    second = remediation.remediate_frame(result["frame"], after)
    check(
        any(item["code"] == "numeric_stored_as_text" for item in second["applied"]),
        "on the renamed file the same finding casts cleanly",
    )
    check(
        pd.api.types.is_numeric_dtype(second["frame"]["age_2"]),
        "and the column is numeric after the second click",
    )


def test_names_are_generated_without_colliding() -> None:
    print("\n4) A generated name never takes a real column's name")
    frame = pd.DataFrame(
        [[1, 2, 3], [4, 5, 6]],
        columns=["age", "age", "age_2"],
    )
    report = validate_frame(frame)
    result = remediation.remediate_frame(frame, report)
    columns = [str(name) for name in result["frame"].columns]

    check(columns.count("age_2") == 1, "the second 'age' could not steal 'age_2'")
    check(columns == ["age", "age_2_2", "age_2"],
          "the second 'age' became 'age_2_2' instead")
    check(
        result["frame"]["age_2"].tolist() == [3, 6],
        "the real 'age_2' kept its own values",
    )
    check(
        result["frame"]["age_2_2"].tolist() == [2, 5],
        "and the renamed second column kept its values",
    )

    # And a spreadsheet-generated name gets a positional one, which
    # also checks against the names already in the file.
    blank = pd.DataFrame([[1, 2]], columns=["Unnamed: 0", "column_1"])
    blank_result = remediation.remediate_frame(
        blank, validate_frame(blank), [{"code": "blank_column_names"}]
    )
    blank_columns = [str(name) for name in blank_result["frame"].columns]
    check(blank_columns == ["column_1_2", "column_1"],
          "a blank name steps around the column that already owns 'column_1'")


def test_a_text_number_column_is_cast_with_a_reported_loss() -> None:
    print("\n5) Text numbers become numbers, and the loss is stated")
    # 97 of 100 parse, which is enough for the finding to fire: the
    # column is a number column that arrived as text.
    frame = pd.DataFrame(
        {
            "amount": ["10"] * 97 + ["bad-1", "bad-2", "bad-3"],
            "label": ["row"] * 100,
        }
    )
    report = validate_frame(frame)
    check("numeric_stored_as_text" in codes_of(report), "the finding fires")

    # The cast alone, so the loss is measured against the column as
    # it arrived rather than against a frame later fixes reshaped.
    result = remediation.remediate_frame(
        frame, report, [{"code": "numeric_stored_as_text"}]
    )
    column = result["frame"]["amount"]
    check(pd.api.types.is_numeric_dtype(column), "the column is numeric afterwards")
    check(int(column.isna().sum()) == 3, "the unparseable values became missing, not invented")
    cast = result["applied"][0]["summary"]["casts"][0]
    check(cast["values_became_missing"] == 3, "the cast reports the values it lost")
    check(
        any("could not be read" in warning for warning in result["applied"][0]["warnings"]),
        "the reader is told which values were lost",
    )


def test_a_stale_button_is_reported_not_ignored() -> None:
    print("\n6) A fix that no longer applies says so")
    frame = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    report = validate_frame(frame)

    result = remediation.remediate_frame(
        frame, report, [{"code": "constant_column", "column": "gone"}]
    )
    check(not result["changed"], "nothing was written")
    check(result["skipped"] and result["skipped"][0]["reason"],
          "the stale request is reported with a reason, not silently dropped")

    unknown = remediation.remediate_frame(frame, report, [{"code": "not_a_code"}])
    check(
        unknown["skipped"][0]["code"] == "not_a_code",
        "an unknown code is reported too",
    )


def main() -> int:
    print("REMEDIATION TESTS")
    test_every_finding_offers_the_right_button()
    test_a_judgment_finding_is_never_in_the_default_click()
    test_the_default_click_cleans_the_file()
    test_names_are_generated_without_colliding()
    test_a_text_number_column_is_cast_with_a_reported_loss()
    test_a_stale_button_is_reported_not_ignored()
    print(f"\nALL REMEDIATION TESTS PASSED ({PASSED} checks)")
    return 0


def test_remediation() -> None:
    """pytest entry point: same run as ``python tests/remediation_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
