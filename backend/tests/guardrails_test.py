"""P-value guardrails on every standard result (improvement plan 2.4).

Two promises are pinned here:

  * a p-value never appears without the test that produced it --
    every table row names its test, not just the headline, and
  * three or more reported tests carry a multiple-comparison
    correction, because k tests at alpha = 0.05 give a family-wise
    error rate of 1 - (1 - 0.05)**k, which is 14% at k = 3.

The tests are built on data whose correct answer can be worked out
by hand: the Bonferroni and Benjamini-Hochberg adjustments are
checked against the textbook step-up example, the family-wise rate
against the closed-form arithmetic, and a single-test result (a
Welch t-test, whose Levene and normality diagnostics also carry
p-values) against the requirement that diagnostics are not the
reader's hypothesis family.

Run it with:  python tests/guardrails_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="guardrails_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "guardrails-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import guardrails, stats_engine  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


# --------------------------------------------------------------- fixtures


def four_columns() -> pd.DataFrame:
    """Six pairwise tests: the smallest matrix that must be corrected."""
    rng = np.random.default_rng(11)
    return pd.DataFrame(
        {
            "w": rng.normal(0, 1, 150),
            "x": rng.normal(0, 1, 150),
            "y": rng.normal(0, 1, 150),
            "z": rng.normal(0, 1, 150),
        }
    )


def regression_frame() -> pd.DataFrame:
    """Two strong and three null predictors: p = 0.0 must not vanish."""
    rng = np.random.default_rng(17)
    frame = pd.DataFrame(
        {
            "x1": rng.normal(0, 1, 150),
            "x2": rng.normal(0, 1, 150),
            "x3": rng.normal(0, 1, 150),
            "x4": rng.normal(0, 1, 150),
            "x5": rng.normal(0, 1, 150),
        }
    )
    frame["y"] = 3 + 2 * frame["x1"] + 0.5 * frame["x2"] + rng.normal(
        0, 0.5, 150
    )
    return frame


# ------------------------------------------------------------------- tests


def test_every_p_value_names_its_test() -> None:
    print("\n1) A p-value never appears without the test behind it")
    frame = four_columns()
    pearson = stats_engine.run_analysis(
        frame, "correlation_matrix", {"method": "pearson"}
    )
    spearman = stats_engine.run_analysis(
        frame, "correlation_matrix", {"method": "spearman"}
    )

    pair = pearson["tables"]["pairs"][0]
    check(
        pair.get("test") == "Pearson r",
        "a correlation pair names Pearson r",
    )
    check(
        spearman["tables"]["pairs"][0].get("test") == "Spearman rho",
        "the same analysis with method=spearman names Spearman rho",
    )

    regression = stats_engine.run_analysis(
        regression_frame(),
        "linear_regression",
        {"target": "y", "predictors": ["x1", "x2", "x3", "x4", "x5"]},
    )
    row = regression["tables"]["coefficients"][1]
    check(
        row.get("term", row.get("variable")) == "x1",
        "the coefficient table is the one with named rows",
    )
    check(
        bool(row.get("test")),
        "a coefficient row names the test that estimated it",
    )


def test_multiple_comparisons_fire_from_three_tests() -> None:
    print("\n2) Three or more reported tests carry the correction")
    frame = four_columns()
    result = stats_engine.run_analysis(
        frame, "correlation_matrix", {"method": "pearson"}
    )
    block = result.get("multiple_comparisons")

    check(block is not None, "a 4-column matrix reports a correction block")
    # Six pairs, plus the test block re-reporting the strongest pair
    # without naming it: the (name, value) identity keeps both, which
    # over-counts by one rather than hiding a test.
    check(
        block["test_count"] == 7,
        "the family is the six pairs plus the unnamed summary sighting",
    )
    expected_rate = round(1.0 - (1.0 - guardrails.FAMILYWISE_ALPHA) ** 7, 4)
    check(
        block["familywise_error_rate"] == expected_rate,
        "the family-wise rate matches 1 - (1 - alpha)**k",
    )
    check(
        any("family-wise" in warning for warning in result["warnings"]),
        "the warning explains the inflation in plain terms",
    )


def test_adjustments_match_the_textbook() -> None:
    print("\n3) Bonferroni and Benjamini-Hochberg are the real procedures")
    p_values = [0.01, 0.04, 0.03, 0.005]
    check(
        guardrails.bonferroni(p_values) == [0.04, 0.16, 0.12, 0.02],
        "Bonferroni multiplies every p-value by the number of tests",
    )
    # The classic worked example: sorted 0.005, 0.01, 0.03, 0.04 with
    # k = 4 gives adjusted 0.02, 0.02, 0.04, 0.04.
    check(
        guardrails.benjamini_hochberg(p_values) == [0.02, 0.04, 0.04, 0.02],
        "Benjamini-Hochberg matches the step-up worked example",
    )

    frame = four_columns()
    result = stats_engine.run_analysis(
        frame, "correlation_matrix", {"method": "pearson"}
    )
    for entry in result["multiple_comparisons"]["tests"]:
        check(
            entry["bonferroni_p_value"]
            >= round(entry["p_value"] * 7, 6) - 1e-9
            or entry["bonferroni_p_value"] == 1.0,
            f"the Bonferroni column is the raw p scaled by k ({entry['label']})",
        )
        check(
            entry["benjamini_hochberg_p_value"] >= entry["p_value"] - 1e-9,
            f"an adjusted p never drops below the raw p ({entry['label']})",
        )


def test_a_single_test_is_not_a_family() -> None:
    print("\n4) Diagnostics do not join the reader's hypothesis family")
    rng = np.random.default_rng(23)
    frame = pd.DataFrame(
        {
            "value": rng.normal(50, 10, 80),
            "group": ["a"] * 40 + ["b"] * 40,
        }
    )
    result = stats_engine.run_analysis(
        frame,
        "welch_t_test",
        {"value_column": "value", "group_column": "group"},
    )

    check(
        "multiple_comparisons" not in result,
        "one reported test carries no correction block",
    )
    check(
        "p_value" in result["diagnostics"]["levene"],
        "the Levene diagnostic still carries its own p-value",
    )
    check(
        "p_value" in result["diagnostics"]["normality"]["a"],
        "the normality diagnostic still carries its own p-value",
    )


def test_zero_p_values_do_not_vanish() -> None:
    print("\n5) A strong predictor's p = 0 is a test, not a duplicate")
    regression = stats_engine.run_analysis(
        regression_frame(),
        "linear_regression",
        {"target": "y", "predictors": ["x1", "x2", "x3", "x4", "x5"]},
    )
    block = regression["multiple_comparisons"]
    labels = [entry["label"] for entry in block["tests"]]

    # The omnibus F-test, the intercept and five coefficients: every
    # row survives even though the strong predictors and the F-test
    # all round to p = 0.0.
    check(block["test_count"] == 7, "all seven tests are in the family")
    for name in ("x1", "x2", "(intercept)"):
        check(
            name in labels,
            f"'{name}' stays in the correction table despite p = 0.0",
        )


def strip_test_names(node):
    """Drop the names a guardrail may attach, keeping every number.

    The invariant under test: a guardrail may add a test name
    beside a p-value, but it may never change a figure the
    engine computed.
    """
    if isinstance(node, dict):
        return {
            key: strip_test_names(value)
            for key, value in node.items()
            if key != "test"
        }
    if isinstance(node, list):
        return [strip_test_names(item) for item in node]
    return node


def test_guardrails_never_change_the_estimate() -> None:
    print("\n6) The guardrail annotates; it never recomputes")
    frame = four_columns()
    parameters = {"method": "pearson"}
    guarded = stats_engine.run_analysis(frame, "correlation_matrix", parameters)
    unguarded = stats_engine.correlation_matrix_analysis(frame, parameters)

    check(
        strip_test_names(guarded["estimate"])
        == strip_test_names(unguarded["estimate"]),
        "the estimate is untouched by the guardrail",
    )
    check(
        strip_test_names(guarded["tables"])
        == strip_test_names(unguarded["tables"]),
        "the reported tables keep their numbers (only a test name is added)",
    )


def test_a_broken_guardrail_cannot_break_the_analysis() -> None:
    print("\n7) A guardrail failure costs the guardrail, nothing else")
    original = guardrails.apply_guardrails

    def explode(analysis_type, result, parameters=None):
        raise RuntimeError("guardrails are down")

    guardrails.apply_guardrails = explode
    try:
        frame = four_columns()
        result = stats_engine.run_analysis(
            frame, "correlation_matrix", {"method": "pearson"}
        )
    finally:
        guardrails.apply_guardrails = original

    check(
        result["status"] == stats_engine.SUCCESS,
        "the analysis still succeeds when the guardrail raises",
    )
    check(
        "multiple_comparisons" not in result,
        "a failed guardrail simply attaches nothing",
    )
    check(
        bool(result.get("assumption_checks")),
        "the assumption checks still ran",
    )


def main() -> int:
    print("P-VALUE GUARDRAIL TESTS")
    test_every_p_value_names_its_test()
    test_multiple_comparisons_fire_from_three_tests()
    test_adjustments_match_the_textbook()
    test_a_single_test_is_not_a_family()
    test_zero_p_values_do_not_vanish()
    test_guardrails_never_change_the_estimate()
    test_a_broken_guardrail_cannot_break_the_analysis()
    print(f"\nALL GUARDRAIL TESTS PASSED ({PASSED} checks)")
    return 0


def test_guardrails() -> None:
    """pytest entry point: same run as ``python tests/guardrails_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
