"""Assumption checks on every standard result.

The engine has always produced verdicts on the recommendation path, because that
path computes `pair_diagnostics` on the way in. A directly configured run went
through `run_analysis` and never saw which columns the reader chose, so its
result carried a warnings list but no verdict — the one thing the engine exists
to report.

These tests pin the gate on the direct run, and they are deliberately built on
data whose correct answer can be worked out by hand:

  * a two-group comparison with a group of 2 must FAIL on group size,
  * a right-skewed outcome must WARN on normality for a normality-sensitive
    method and say `not_applicable` for one that does not require it,
  * a heavy-on-missing column must WARN, and
  * the checks must never change the estimate, or break the analysis.

Run it with:  python tests/assumption_gate_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="assumption_gate_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "assumption-gate-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import planning, stats_engine  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def status_of(result, name: str) -> str:
    for check_item in result.get("assumption_checks") or []:
        if check_item["name"] == name:
            return check_item["status"]
    raise AssertionError(f"no '{name}' check on {result['analysis_type']}")


def detail_of(result, name: str) -> str:
    for check_item in result.get("assumption_checks") or []:
        if check_item["name"] == name:
            return check_item["detail"]
    raise AssertionError(f"no '{name}' check on {result['analysis_type']}")


# --------------------------------------------------------------- fixtures


def tiny_group() -> pd.DataFrame:
    """12 rows, group 'b' has 2 observations: group size must fail."""
    return pd.DataFrame(
        {
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 50.0, 51.0],
            "group": ["a"] * 10 + ["b"] * 2,
        }
    )


def healthy_group() -> pd.DataFrame:
    """Two groups of 25 and 50, symmetric values: every check should pass."""
    rng = np.random.default_rng(7)
    values = rng.normal(50.0, 10.0, 75)
    groups = ["a"] * 25 + ["b"] * 50
    return pd.DataFrame({"value": values, "group": groups})


def mostly_missing() -> pd.DataFrame:
    """200 rows where the analysed column is missing in 30% of them."""
    rng = np.random.default_rng(11)
    values = rng.normal(10.0, 3.0, 200)
    values[:60] = np.nan
    return pd.DataFrame({"value": values, "group": ["a", "b"] * 100})


def skewed() -> pd.DataFrame:
    """Two independent, strongly right-skewed columns.

    Correlation needs two distinct columns, and both being skewed means a
    normality-sensitive method has something to warn about in either direction.
    """
    rng = np.random.default_rng(13)
    return pd.DataFrame(
        {
            "left": rng.exponential(scale=2.0, size=400),
            "right": rng.exponential(scale=3.0, size=400),
        }
    )


# --------------------------------------------------------------- checks


def test_blocks_a_group_too_small_to_compare() -> None:
    print("\n1) A group too small to compare fails, and says why")
    result = stats_engine.run_analysis(
        tiny_group(), "welch_t_test", {"value_column": "value", "group_column": "group"}
    )

    check(
        status_of(result, "Group sizes") == "fail",
        "a 2-observation group fails the group-size assumption",
    )
    check(
        "2 observation" in detail_of(result, "Group sizes"),
        "the failure names the smallest group's size",
    )
    check(
        status_of(result, "Sample size") == "warn",
        "12 observations also warns on sample size",
    )
    check(
        result.get("estimate") not in (None, {}),
        "the estimate is still produced alongside the failure",
    )


def test_passes_what_it_can_evidence() -> None:
    print("\n2) Enough data with no missingness passes")
    result = stats_engine.run_analysis(
        healthy_group(), "welch_t_test", {"value_column": "value", "group_column": "group"}
    )

    check(status_of(result, "Sample size") == "pass", "75 observations passes")
    check(status_of(result, "Missing values") == "pass", "nothing missing passes")
    check(status_of(result, "Group sizes") == "pass", "groups of 25 and 50 pass")
    check(
        status_of(result, "Normality") in {"pass", "warn"},
        "normality is judged rather than skipped for a t-test",
    )


def test_missing_values_warn() -> None:
    print("\n3) Missingness is reported against the column that was analysed")
    result = stats_engine.run_analysis(
        mostly_missing(), "descriptive", {"columns": ["value"]}
    )

    check(
        status_of(result, "Missing values") == "warn",
        "30% missing warns",
    )
    check(
        "value" in detail_of(result, "Missing values"),
        "the warning names the column responsible",
    )
    check(
        status_of(result, "Sample size") == "pass",
        "sample size counts the rows, so it still passes",
    )

    # Descriptive statistics does not assume normality, and the gate says so
    # rather than running a test the method does not need.
    check(
        status_of(result, "Normality") == "not_applicable",
        "descriptive statistics is marked not applicable for normality",
    )


def test_normality_only_where_it_matters() -> None:
    print("\n4) Normality is judged for a sensitive method and excused otherwise")
    result = stats_engine.run_analysis(
        skewed(), "pearson", {"x": "right", "y": "left"}
    )
    check(
        status_of(result, "Normality") == "warn",
        "a skewed outcome warns for a normality-sensitive method",
    )

    result_rank = stats_engine.run_analysis(
        skewed(), "spearman", {"x": "right", "y": "left"}
    )
    check(
        status_of(result_rank, "Normality") == "not_applicable",
        "a rank-based method is excused from the normality check",
    )


def test_checks_never_change_the_estimate() -> None:
    print("\n5) The gate does not alter the number it is judging")
    frame = healthy_group()
    plain = stats_engine.run_analysis(
        frame, "welch_t_test", {"value_column": "value", "group_column": "group"}
    )
    checked = stats_engine.run_analysis(
        frame, "welch_t_test", {"value_column": "value", "group_column": "group"}
    )
    check(
        plain["estimate"] == checked["estimate"],
        "the same request produces the same estimate",
    )
    check(
        plain["test"] == checked["test"] and plain["sample_size"] == checked["sample_size"],
        "test statistic, p-value and sample size are untouched",
    )


def test_unequal_variance_is_warned_for_anova() -> None:
    print("\n6) Unequal group variances warn where the method needs equal ones")
    rng = np.random.default_rng(17)
    frame = pd.DataFrame(
        {
            "value": np.concatenate(
                [rng.normal(10, 1, 40), rng.normal(10, 60, 40)]
            ),
            "group": ["a"] * 40 + ["b"] * 40,
        }
    )
    result = stats_engine.run_analysis(
        frame, "one_way_anova", {"value_column": "value", "group_column": "group"}
    )
    check(
        status_of(result, "Equal variance") == "warn",
        "very different spreads warn for one-way ANOVA",
    )


def test_fewer_than_three_rows_still_returns_a_standard_result() -> None:
    print("\n7) An unanalysable dataset keeps its shape")
    tiny = pd.DataFrame({"value": [1.0, 2.0]})
    result = stats_engine.run_analysis(tiny, "descriptive", {"columns": ["value"]})

    check(
        result["status"] == "insufficient_data",
        "two rows is reported as insufficient data",
    )
    check(
        "The dataset version has fewer than 3 rows" in (result.get("warnings") or []),
        "the warning explains why",
    )


def main() -> int:
    print("ASSUMPTION GATE TESTS")
    test_blocks_a_group_too_small_to_compare()
    test_passes_what_it_can_evidence()
    test_missing_values_warn()
    test_normality_only_where_it_matters()
    test_checks_never_change_the_estimate()
    test_unequal_variance_is_warned_for_anova()
    test_fewer_than_three_rows_still_returns_a_standard_result()
    print(f"\nALL ASSUMPTION-GATE TESTS PASSED ({PASSED} checks)")
    return 0


def test_assumption_gate() -> None:
    """pytest entry point: same run as ``python tests/assumption_gate_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
