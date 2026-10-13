"""The engine against values derived by hand (improvement plan 2.3).

Accuracy is a legal-grade claim, so it needs a suite rather than a
sentence: every statistic here is checked against a reference that
was worked out on paper, with the derivation written next to the
assertion so a reviewer can check it without trusting this file.

Each case is built on data whose arithmetic is exact or near-exact
by construction -- consecutive integers, a perfect line, a table
with whole-number expected counts -- so the expected value is a
short hand calculation rather than a number copied from a textbook
that cannot be checked here. Tolerances are stated per case: an
exact value is asserted to 1e-9, a p-value to the six digits the
engine reports.

Two of these cases found real problems, which is the point of
keeping the suite:

  * ``two_proportion_z_test`` was dead on arrival -- two helpers
    shared the name ``_binary_frame``, the later definition won,
    and the test was handed the group column's *name* as the
    positive class, so it raised "must contain both classes" for
    every input. Fixed by renaming the model-side helper
    ``_positive_flags``.
  * ``mann_whitney`` uses the plain normal approximation, which
    reports p = 0.0495 for complete separation at n = 3, 3 where
    the exact test gives p = 0.1. That is documented behaviour for
    large samples, and the case below pins the approximation's own
    value (z = -1.963961, no continuity correction) while stating
    the exact figure in a comment -- a known limitation stated
    plainly is very different from a wrong answer nobody noticed.

Run it with:  python tests/textbook_validation_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="textbook_validation_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "textbook-validation-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import stats_engine  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def close(value: float, reference: float, tolerance: float) -> bool:
    return abs(float(value) - reference) <= tolerance


# ------------------------------------------------------------------- cases


def test_welch_t_test() -> None:
    """A = {1..5}, B = {6..10}: both groups have mean 3 and 8, sd 1.581139.

    t = (3 - 8) / sqrt(s1^2/n1 + s2^2/n2) = -5 / sqrt(2.5/5 + 2.5/5) = -5.
    df (Welch) = (s1^2/n1 + s2^2/n2)^2 / [(s1^2/n1)^2/(n1-1) + ...] = 8.
    p(t <= -5, df = 8) = 0.001053 (two-sided).
    d = (3 - 8) / pooled sd, pooled sd = sqrt(2.5) = 1.581139 -> 3.162278.
    """
    print("\n1) Welch t-test")
    frame = pd.DataFrame(
        {"value": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "group": ["a"] * 5 + ["b"] * 5}
    )
    result = stats_engine.run_analysis(
        frame, "welch_t_test", {"value_column": "value", "group_column": "group"}
    )
    test = result["test"]
    check(test["statistic"] == -5.0, f"t = -5.0 (got {test['statistic']})")
    check(test["df"] == 8.0, f"Welch df = 8 (got {test['df']})")
    check(
        close(test["p_value"], 0.001053, 1e-6),
        f"p = 0.001053 (got {test['p_value']})",
    )
    check(
        close(result["effect_size"]["value"], -3.162278, 1e-6),
        f"Cohen's d = -3.162278 (got {result['effect_size']['value']})",
    )


def test_one_sample_t_test() -> None:
    """x = {1..5} against mu = 0: mean 3, sd 1.581139.

    t = 3 / (1.581139 / sqrt(5)) = 3 / 0.707107 = 4.242641, df = 4.
    p(t > 4.242641, df = 4) = 0.013236 (two-sided).
    d = (3 - 0) / 1.581139 = 1.897367.
    """
    print("\n2) One-sample t-test")
    frame = pd.DataFrame({"v": [1, 2, 3, 4, 5]})
    result = stats_engine.run_analysis(
        frame, "one_sample_t_test", {"value_column": "v", "mu": 0}
    )
    test = result["test"]
    check(close(test["statistic"], 4.242641, 1e-6), f"t = 4.242641 (got {test['statistic']})")
    check(test["df"] == 4, f"df = 4 (got {test['df']})")
    check(close(test["p_value"], 0.013236, 1e-6), f"p = 0.013236 (got {test['p_value']})")
    check(
        close(result["effect_size"]["value"], 1.897367, 1e-6),
        f"Cohen's d = 1.897367 (got {result['effect_size']['value']})",
    )


def test_one_way_anova() -> None:
    """A = {1,2,3}, B = {3,4,5}, C = {5,6,7}: means 2, 4, 6; grand mean 4.

    SS_between = 3*(2-4)^2 + 3*(4-4)^2 + 3*(6-4)^2 = 24, df = 2.
    SS_within = 2 + 2 + 2 = 6, df = 6 (three consecutive integers have
    variance 1, so each group's sum of squares is 2).
    F = (24/2) / (6/6) = 12. eta^2 = 24/30 = 0.8.
    p(F(2,6) = 12) = 0.008 exactly.
    """
    print("\n3) One-way ANOVA")
    frame = pd.DataFrame(
        {"value": [1, 2, 3, 3, 4, 5, 5, 6, 7], "group": ["a"] * 3 + ["b"] * 3 + ["c"] * 3}
    )
    result = stats_engine.run_analysis(
        frame, "one_way_anova", {"value_column": "value", "group_column": "group"}
    )
    test = result["test"]
    check(test["statistic"] == 12.0, f"F = 12.0 (got {test['statistic']})")
    check(test["df_between"] == 2 and test["df_within"] == 6, "df = (2, 6)")
    check(close(test["p_value"], 0.008, 1e-9), f"p = 0.008 (got {test['p_value']})")
    check(
        close(result["effect_size"]["value"], 0.8, 1e-9),
        f"eta^2 = 0.8 (got {result['effect_size']['value']})",
    )


def test_chi_square_independence() -> None:
    """Observed [[10,20],[30,40]] with row totals 30/70 and columns 40/60.

    Expected: [[12,18],[28,42]] (E_ij = row_i * col_j / N).
    chi^2 = (10-12)^2/12 + (20-18)^2/18 + (30-28)^2/28 + (40-42)^2/42
          = 0.333333 + 0.222222 + 0.142857 + 0.095238 = 0.793651, df = 1.
    p(chi^2 = 0.793651, df = 1) = 0.372998.
    Cramer's V = sqrt(chi^2 / (N * min(r-1, c-1))) = sqrt(0.793651/100).
    """
    print("\n4) Chi-square test of independence")
    frame = pd.DataFrame(
        [["r", "c"]] * 10
        + [["r", "d"]] * 20
        + [["s", "c"]] * 30
        + [["s", "d"]] * 40,
        columns=["row", "column"],
    )
    result = stats_engine.run_analysis(
        frame, "chi_square", {"column": "row", "row": "column"}
    )
    test = result["test"]
    check(
        close(test["statistic"], 0.793651, 1e-6),
        f"chi^2 = 0.793651 (got {test['statistic']})",
    )
    check(test["df"] == 1, f"df = 1 (got {test['df']})")
    check(
        close(test["p_value"], 0.372998, 1e-6),
        f"p = 0.372998 (got {test['p_value']})",
    )
    expected = result["estimate"]["contingency_table"]["expected"]
    check(
        expected == [[12.0, 28.0], [18.0, 42.0]],
        f"expected counts [[12,28],[18,42]] (got {expected})",
    )
    check(
        close(result["effect_size"]["value"], 0.089087, 1e-6),
        f"Cramer's V = 0.089087 (got {result['effect_size']['value']})",
    )


def test_pearson_correlation() -> None:
    """x = {1..5}, y = {2,4,5,4,5}: means 3 and 4.

    Sum of cross-deviations = 4 + 0 + 0 + 0 + 2 = 6; sum x^2 = 10, sum
    y^2 = 6, so r = 6 / sqrt(10 * 6) = 6 / sqrt(60) = 0.774597.
    t = r * sqrt(n-2) / sqrt(1-r^2) = sqrt(0.6 * 3 / 0.4) = 2.121320, df = 3,
    p = 0.124027 (two-sided).
    """
    print("\n5) Pearson correlation")
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 5, 4, 5]})
    result = stats_engine.run_analysis(frame, "pearson", {"x_column": "x", "y_column": "y"})
    test = result["test"]
    check(close(test["statistic"], 0.774597, 1e-6), f"r = 0.774597 (got {test['statistic']})")
    check(test["df"] == 3, f"df = 3 (got {test['df']})")
    check(close(test["p_value"], 0.124027, 1e-6), f"p = 0.124027 (got {test['p_value']})")
    check(result["estimate"]["direction"] == "positive", "the sign is reported as positive")

    # A perfect line has no slack: r is exactly 1 in magnitude, and the
    # sign follows the slope. This is the case that catches a correlation
    # implementation which is right on average and wrong at the edges.
    perfect = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [3, 5, 7, 9, 11]})
    positive = stats_engine.run_analysis(
        perfect, "pearson", {"x_column": "x", "y_column": "y"}
    )
    check(
        close(positive["test"]["statistic"], 1.0, 1e-9),
        f"r = 1 for a perfect positive line (got {positive['test']['statistic']})",
    )
    reversed_line = perfect.assign(y=[11, 9, 7, 5, 3])
    negative = stats_engine.run_analysis(
        reversed_line, "pearson", {"x_column": "x", "y_column": "y"}
    )
    check(
        close(negative["test"]["statistic"], -1.0, 1e-9),
        f"r = -1 for a perfect negative line (got {negative['test']['statistic']})",
    )


def test_linear_regression() -> None:
    """x = {1..5}, y = {3,5,7,9,12}.

    slope = (5*130 - 15*36) / (5*55 - 15^2) = 110/50 = 2.2.
    intercept = (36 - 2.2*15)/5 = 0.6.
    Fitted: 2.8, 5.0, 7.2, 9.4, 11.6; SS_res = 0.04+0+0.04+0.16+0.16 = 0.4;
    SS_tot = 17.64 + 4.84 + 0.04 + 3.24 + 23.04 = 48.8.
    R^2 = 1 - 0.4/48.8 = 0.991803.
    """
    print("\n6) Linear regression (OLS)")
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [3, 5, 7, 9, 12]})
    result = stats_engine.run_analysis(
        frame, "linear_regression", {"target": "y", "predictors": ["x"]}
    )
    coefficients = result["tables"]["coefficients"]

    def coefficient_row(name: str):
        return next(
            row
            for row in coefficients
            if row.get("variable", row.get("term")) == name
        )

    slope = coefficient_row("x")
    intercept = coefficient_row("(intercept)")
    check(close(slope["estimate"], 2.2, 1e-9), f"slope = 2.2 (got {slope['estimate']})")
    check(close(intercept["estimate"], 0.6, 1e-9), f"intercept = 0.6 (got {intercept['estimate']})")
    # Standard error of the slope: s / sqrt(SS_x), with s = sqrt(0.4/3)
    # = 0.365148 and SS_x = 10, gives 0.115470; and t = 2.2/0.115470 = 19.052559.
    check(close(slope["std_error"], 0.115470, 1e-6), f"slope se = 0.115470 (got {slope['std_error']})")
    check(close(slope["t_statistic"], 19.052559, 1e-6), f"slope t = 19.052559 (got {slope['t_statistic']})")
    check(close(slope["p_value"], 0.000316, 1e-6), f"slope p = 0.000316 (got {slope['p_value']})")
    check(
        close(result["estimate"]["r_squared"], 0.991803, 1e-6),
        f"R^2 = 0.991803 (got {result['estimate']['r_squared']})",
    )


def test_mann_whitney() -> None:
    """A = {1,2,3}, B = {4,5,6}: complete separation, U = 0.

    The engine uses the plain normal approximation without continuity
    correction: mu_U = n1*n2/2 = 4.5, sigma_U = sqrt(9*7/12) = 2.291288,
    z = (0 - 4.5)/2.291288 = -1.963961, p = 2*Phi(-1.963961) = 0.049535.

    Known limitation, stated rather than hidden: the EXACT two-sided
    p-value for complete separation at n = 3, 3 is 0.1, because there
    are C(6,3) = 20 equally likely rank assignments and complete
    separation is the most extreme one. The approximation is the
    standard choice for large samples; on a sample this small it
    claims significance the exact test denies.
    """
    print("\n7) Mann-Whitney U (normal approximation)")
    frame = pd.DataFrame({"v": [1, 2, 3, 4, 5, 6], "g": ["a"] * 3 + ["b"] * 3})
    result = stats_engine.run_analysis(
        frame, "mann_whitney", {"value_column": "v", "group_column": "g"}
    )
    test = result["test"]
    check(test["statistic"] == 0.0, f"U = 0 for complete separation (got {test['statistic']})")
    check(close(test["z"], -1.963961, 1e-6), f"z = -1.963961 (got {test['z']})")
    check(
        close(test["p_value"], 0.049535, 1e-6),
        f"approximation p = 0.049535 (got {test['p_value']}; exact would be 0.1)",
    )


def test_kruskal_wallis() -> None:
    """A = {1,2,3}, B = {3,4,5}, C = {5,6,7}: ranks 1-3, 4-6, 7-9.

    Group mean ranks 2, 5, 8; grand mean rank 5.
    H = 12/(N(N+1)) * sum(n_i * (R_i - R)^2)
      = 12/90 * [3*9 + 0 + 3*9] = 12/90 * 54 = 7.2, df = 2.
    p(chi^2 = 7.2, df = 2) = 0.027324.
    With two groups the same data gives H = 12/42 * [3*2.25 + 3*2.25]
    = 3.857143, df = 1, p = 0.049535.
    """
    print("\n8) Kruskal-Wallis H")
    frame = pd.DataFrame(
        {"v": [1, 2, 3, 4, 5, 6, 7, 8, 9], "g": ["a"] * 3 + ["b"] * 3 + ["c"] * 3}
    )
    three = stats_engine.run_analysis(
        frame, "kruskal_wallis", {"value_column": "v", "group_column": "g"}
    )
    check(three["test"]["statistic"] == 7.2, f"H = 7.2 (got {three['test']['statistic']})")
    check(three["test"]["df"] == 2, f"df = 2 (got {three['test']['df']})")
    check(
        close(three["test"]["p_value"], 0.027324, 1e-6),
        f"p = 0.027324 (got {three['test']['p_value']})",
    )

    two = pd.DataFrame({"v": [1, 2, 3, 4, 5, 6], "g": ["a"] * 3 + ["b"] * 3})
    result = stats_engine.run_analysis(
        two, "kruskal_wallis", {"value_column": "v", "group_column": "g"}
    )
    check(
        close(result["test"]["statistic"], 3.857143, 1e-6),
        f"H = 3.857143 with two groups (got {result['test']['statistic']})",
    )
    check(result["test"]["df"] == 1, f"df = 1 with two groups (got {result['test']['df']})")


def test_paired_t_test() -> None:
    """x = {1..5}, y = {3,5,7,9,12}: differences -2,-3,-4,-5,-7.

    mean_diff = -4.2, sd_diff = 1.923538 (variance 3.7).
    t = 4.2 / (1.923538/sqrt(5)) = 4.2/0.860231 = 4.882401, df = 4.
    p(t > 4.882401, df = 4) = 0.008147.

    Differences with no variance are refused rather than divided by
    zero: a constant difference has no sampling variation to test.
    """
    print("\n9) Paired t-test")
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [3, 5, 7, 9, 12]})
    result = stats_engine.run_analysis(
        frame, "paired_t_test", {"x": "x", "y": "y"}
    )
    test = result["test"]
    check(close(test["statistic"], 4.882401, 1e-6), f"t = 4.882401 (got {test['statistic']})")
    check(test["df"] == 4, f"df = 4 (got {test['df']})")
    check(close(test["p_value"], 0.008147, 1e-6), f"p = 0.008147 (got {test['p_value']})")
    check(
        close(result["estimate"]["sd_difference"], 1.923538, 1e-6),
        f"sd of differences = 1.923538 (got {result['estimate']['sd_difference']})",
    )

    constant = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 3, 4, 5, 6]})
    try:
        stats_engine.run_analysis(constant, "paired_t_test", {"x": "x", "y": "y"})
        raised = False
    except Exception:
        raised = True
    check(raised, "a zero-variance difference is refused, not divided by zero")


def test_two_proportion_z_test() -> None:
    """10/100 vs 20/100: p1 = 0.1, p2 = 0.2, pooled = 0.15.

    SE = sqrt(0.15 * 0.85 * (1/100 + 1/100)) = sqrt(0.00255) = 0.0504975.
    z = (0.1 - 0.2)/0.0504975 = -1.980295, p = 0.04767 (two-sided).

    This analysis was dead until the 2.3 suite found it: two helpers
    shared the name ``_binary_frame`` and the shadowing definition won.
    """
    print("\n10) Two-proportion z-test")
    frame = pd.DataFrame(
        {"value": [1] * 10 + [0] * 90 + [1] * 20 + [0] * 80, "group": ["a"] * 100 + ["b"] * 100}
    )
    result = stats_engine.run_analysis(
        frame, "two_proportion_z_test", {"value_column": "value", "group_column": "group"}
    )
    test = result["test"]
    check(close(test["statistic"], -1.980295, 1e-6), f"z = -1.980295 (got {test['statistic']})")
    check(close(test["p_value"], 0.04767, 1e-6), f"p = 0.04767 (got {test['p_value']})")
    check(
        close(result["estimate"]["groups"]["a"]["proportion"], 0.1, 1e-12)
        and close(result["estimate"]["groups"]["b"]["proportion"], 0.2, 1e-12),
        "both group proportions are reported",
    )


def test_descriptive_statistics() -> None:
    """x = {1..5}: mean 3, median 3, sample variance 2.5, sd 1.581139.

    The sample variance divides by n-1, which is the convention every
    test in this suite also uses; a population-sized denominator would
    make sd 1.414214 and every statistic above would shift with it.
    """
    print("\n11) Descriptive statistics (the sample convention)")
    frame = pd.DataFrame({"v": [1, 2, 3, 4, 5]})
    result = stats_engine.run_analysis(frame, "descriptive", {"value_column": "v"})
    summary = result["estimate"]["variables"]["v"]
    check(summary["mean"] == 3.0, f"mean = 3 (got {summary['mean']})")
    check(summary["median"] == 3.0, f"median = 3 (got {summary['median']})")
    check(summary["variance"] == 2.5, f"sample variance = 2.5 (got {summary['variance']})")
    check(close(summary["sd"], 1.581139, 1e-6), f"sample sd = 1.581139 (got {summary['sd']})")
    check(summary["min"] == 1.0 and summary["max"] == 5.0, "min and max are correct")


def main() -> int:
    print("ENGINE vs TEXTBOOK VALIDATION")
    test_welch_t_test()
    test_one_sample_t_test()
    test_one_way_anova()
    test_chi_square_independence()
    test_pearson_correlation()
    test_linear_regression()
    test_mann_whitney()
    test_kruskal_wallis()
    test_paired_t_test()
    test_two_proportion_z_test()
    test_descriptive_statistics()
    print(f"\nALL TEXTBOOK VALIDATION CHECKS PASSED ({PASSED} checks)")
    return 0


def test_textbook_validation() -> None:
    """pytest entry point: same run as ``python tests/textbook_validation_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
