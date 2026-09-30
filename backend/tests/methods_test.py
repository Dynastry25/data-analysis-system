"""Methods of Analysis: the catalogue, its stage plans, and the analyses added
on top of it (logistic, Poisson, Cronbach's alpha, Kaplan-Meier and the rest of
the guide's second wave).

These tests check the guide against itself: every method the catalogue claims is
implemented must be dispatched by the engine, every stage plan must be a dense
ordered sequence, and the new statistics must reproduce values that can be
worked out by hand.

Run it with:  python tests/methods_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="methods_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "methods-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.statflow import methods, stats_engine  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def close(actual, expected, tolerance=1e-6) -> bool:
    return actual is not None and abs(float(actual) - float(expected)) <= float(tolerance)


def raises_analysis_error(frame, analysis_type, parameters, message) -> None:
    """Assert an invalid request is refused with a clear error, not a crash."""
    try:
        stats_engine.run_analysis(frame, analysis_type, parameters)
    except stats_engine.AnalysisError:
        check(True, message)
        return
    check(False, message)


# --------------------------------------------------------------- catalogue


def test_catalogue() -> None:
    print("1) The Methods of Analysis catalogue")
    check(
        len(methods.METHODS) >= 140,
        f"the guide is fully catalogued ({len(methods.METHODS)} methods)",
    )
    check(
        len(methods.CATEGORIES) >= 15, f"{len(methods.CATEGORIES)} method families"
    )

    keys = [row["key"] for row in methods.METHODS]
    check(len(keys) == len(set(keys)), "every method key is unique")
    check(
        all(row["category"] in methods.CATEGORY_KEYS for row in methods.METHODS),
        "every method belongs to a known category",
    )

    for field in (
        "label",
        "label_en",
        "label_sw",
        "purpose",
        "when_to_use",
        "dv",
        "variables",
        "assumptions",
        "outputs",
        "requires",
    ):
        missing = [row["key"] for row in methods.METHODS if not row.get(field)]
        check(not missing, f"every method states '{field}' (missing: {missing[:3]})")

    # The stage plan is derived from the method, so it is asserted on the rows
    # the API actually returns rather than on the raw module table.
    catalog_rows = methods.method_catalog()["methods"]
    missing_plan = [row["key"] for row in catalog_rows if not row.get("stage_plan")]
    check(not missing_plan, f"every method resolves a stage plan (missing: {missing_plan[:3]})")

    # Not every method needs an alternative (descriptive statistics has none),
    # but every method that makes an assumption needs a way out of it.
    without_alternative = [
        row["key"]
        for row in methods.METHODS
        if not row["alternatives"] and len(row["assumptions"]) > 2
    ]
    check(
        len(without_alternative) < len(methods.METHODS) // 4,
        f"methods with assumptions nearly always name an alternative "
        f"({len(without_alternative)} do not)",
    )

    check(len(methods.DV_GUIDE) >= 8, "the dependent-variable guide is present")
    check(len(methods.GOAL_GUIDE) >= 10, "the research-goal guide is present")
    check(len(methods.CHECKLIST) == 10, "the analysis checklist has 10 steps")
    check(len(methods.COMMON_MISTAKES) >= 8, "common mistakes are listed")
    check(
        len(methods.SELECTION_QUESTIONS) == 3,
        "the three selection questions guide the choice",
    )

    # catalog() is used rather than the raw handler table because the second wave
    # in app.statflow.advanced registers itself on import, and catalog() is what
    # makes sure that import has happened.
    stats_engine.catalog()
    missing_engines = [
        row["key"]
        for row in methods.implemented_methods()
        if row["engine"] not in stats_engine.ANALYSIS_HANDLERS
    ]
    check(
        not missing_engines,
        f"implemented methods are all dispatched (missing: {missing_engines})",
    )
    check(
        sorted(stats_engine.catalog()[i]["analysis_type"] for i in range(len(stats_engine.catalog()))) == methods.engine_keys(),
        "the catalogue and the engine agree on the analysis list",
    )
    check(
        len(methods.implemented_methods()) >= 25,
        f"{len(methods.implemented_methods())} methods are backed by real maths",
    )
    check(
        any(not row["implemented"] for row in methods.METHODS),
        "methods without an engine are still catalogued and labelled as such",
    )


def test_stage_plans() -> None:
    print("\n2) Stage plans follow the chosen method")
    base = methods.stage_plan(methods.method("descriptive"))
    check(
        [stage["key"] for stage in base][:3] == ["lengo", "data", "vigezo"],
        "every plan opens with the question, the data and the variables",
    )
    check(base[-1]["key"] == "tafsiri", "every plan ends with interpretation and reporting")
    check(
        [stage["order"] for stage in base] == list(range(1, len(base) + 1)),
        "stage order numbers are dense and start at 1",
    )

    # The plan must change with the method: that is the point of the feature.
    logistic = methods.stage_plan(methods.method("logistic_regression"))
    survey = methods.stage_plan(methods.method("weighted_analysis"))
    time_series = methods.stage_plan(methods.method("arima"))
    check(
        [stage["key"] for stage in logistic] != [stage["key"] for stage in base],
        "a method with extra stages gets a longer plan than a plain one",
    )
    check(
        "assumptions" in [stage["key"] for stage in logistic],
        "logistic regression has an explicit assumptions stage",
    )
    check(
        "design" in [stage["key"] for stage in survey],
        "a survey method adds a design stage",
    )
    check(
        "stationarity" in [stage["key"] for stage in time_series],
        "a time-series method adds a stationarity stage",
    )
    check(
        len(logistic) > len(base),
        "adding stages lengthens the plan instead of replacing steps",
    )

    # The plan carries the method's own content, not generic filler.
    assumption_stage = next(stage for stage in logistic if stage["key"] == "assumptions")
    check(
        assumption_stage["checks"] == methods.method("logistic_regression")["assumptions"],
        "the assumptions stage lists this method's own assumptions",
    )
    check(
        "assumptions" not in [stage["key"] for stage in base],
        "descriptive statistics gets no assumptions stage: it has none to check",
    )
    variables_stage = next(stage for stage in time_series if stage["key"] == "vigezo")
    check(
        variables_stage["fields"] == methods.method("arima")["requires"],
        "the variables stage asks for the parameters the method declares",
    )
    run_stage = next(stage for stage in logistic if stage["key"] == "endesha")
    check(bool(run_stage["outputs"]), "the run stage lists the outputs to expect")
    interpretation = next(stage for stage in logistic if stage["key"] == "tafsiri")
    check(
        bool(interpretation["alternatives"]),
        "the interpretation stage names what to switch to if assumptions fail",
    )

    for category in ("regression", "timeseries", "causal", "survey", "reliability"):
        plans = [methods.stage_plan(row) for row in methods.methods_for_category(category)]
        check(
            all(plan and plan[-1]["key"] == "tafsiri" for plan in plans),
            f"every {category} method ends with a reporting stage",
        )

    catalog = methods.method_catalog()
    check(
        len(catalog["stage_plans"]) < len(methods.METHODS),
        "identical stage plans are stored once and shared, not duplicated",
    )
    check(
        all(catalog["stage_plans"].values()),
        f"all {len(catalog['stage_plans'])} shared stage plans are populated",
    )


def test_method_lookup() -> None:
    print("\n3) Looking a method up")
    found = methods.method("one_way_anova")
    check(found is not None, "one-way ANOVA is in the catalogue")
    check(found["engine"] == "one_way_anova", "it maps to the engine analysis type")
    check(bool(found["assumptions"]), "ANOVA lists its assumptions")
    check(
        "kruskal" in " ".join(found["alternatives"]).lower(),
        "ANOVA names its non-parametric alternative (Kruskal-Wallis)",
    )
    check(
        "eta" in found["outputs"].lower() or "f-statistic" in found["outputs"].lower(),
        "ANOVA lists the outputs the guide requires (F, eta-squared)",
    )
    check(methods.method("does_not_exist") is None, "an unknown key returns None")
    for category in methods.CATEGORY_KEYS:
        check(
            len(methods.methods_for_category(category)) > 0,
            f"category '{category}' has methods",
        )


def test_logistic_regression() -> None:
    print("\n4) Logistic regression")
    rng = np.random.default_rng(11)
    n = 600
    x = rng.normal(0, 1, n)
    z = rng.normal(0, 1, n)
    # Data simulated from a known log-odds, so the coefficient has a true value.
    log_odds = -0.5 + 0.9 * x - 0.4 * z
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(-log_odds))).astype(int)
    frame = pd.DataFrame({"x": x, "z": z, "bought": y})

    result = stats_engine.run_analysis(
        frame, "logistic_regression", {"target": "bought", "features": ["x", "z"]}
    )
    terms = {row["term"]: row for row in result["estimate"]["coefficients"]}
    # Sampling noise means the estimate is judged against its own standard error,
    # not against the simulated value to three decimals: the true coefficient
    # has to sit within a couple of SEs of the estimate.
    for term, truth in (("x", 0.9), ("z", -0.4)):
        row = terms[term]
        distance = abs(row["beta"] - truth)
        check(
            distance < 3 * row["standard_error"],
            f"the log-odds for {term} recovers the simulated {truth} within 3 SE "
            f"(estimate {row['beta']}, SE {row['standard_error']})",
        )
        check(
            close(row["odds_ratio"], np.exp(row["beta"]), 1e-6),
            f"the odds ratio for {term} is the exponential of its log-odds",
        )
    check(terms["x"]["odds_ratio"] > 1, "a positive effect gives an odds ratio above 1")
    check(terms["x"]["p_value"] < 0.01, "a real effect is significant")
    check(
        result["diagnostics"]["auc"] > 0.7,
        f"AUC shows good discrimination (got {result['diagnostics']['auc']})",
    )
    check(0.0 <= result["diagnostics"]["accuracy"] <= 1.0, "accuracy is a probability")
    matrix = result["diagnostics"]["confusion_matrix"]
    check(
        matrix["true_positive"] + matrix["false_positive"]
        + matrix["true_negative"] + matrix["false_negative"] == n,
        "the confusion matrix accounts for every row",
    )
    check(0.0 <= result["effect_size"]["value"] <= 1.0, "McFadden pseudo R2 is in range")
    check(
        terms["x"]["or_ci_lower"] < terms["x"]["odds_ratio"] < terms["x"]["or_ci_upper"],
        "the odds ratio sits inside its confidence interval",
    )
    check(len(result["tables"]["roc"]["fpr"]) > 10, "a ROC curve is returned for plotting")
    check(result["status"] == "success", "the status is success")

    # A perfect predictor triggers the separation warning instead of crashing.
    separated = stats_engine.run_analysis(
        frame.assign(perfect=y),
        "logistic_regression",
        {"target": "bought", "features": ["perfect"]},
    )
    check(isinstance(separated["warnings"], list), "separation still returns a standard result")

    raises_analysis_error(
        frame, "logistic_regression", {"target": "bought", "features": []},
        "features are required",
    )
    raises_analysis_error(
        frame, "logistic_regression", {"target": "x", "features": ["z"]},
        "a non-binary target is rejected",
    )


def poisson_draws(rates: np.ndarray, seed: int) -> np.ndarray:
    """Poisson draws by inversion, so the test needs no scipy."""
    rng = np.random.default_rng(seed)
    draws = np.empty(rates.shape[0], dtype=float)
    for index, rate in enumerate(rates):
        threshold = np.exp(-rate)
        total = 1.0
        count = 0
        while True:
            total *= rng.random()
            count += 1
            if total <= threshold:
                break
        draws[index] = float(count - 1)
    return draws


def overdispersed_counts(rate: float, size: int, seed: int) -> np.ndarray:
    """Gamma-Poisson counts: a Poisson whose rate itself varies row to row.

    The mixture is what overdispersion actually is, and unlike simply scaling
    the Poisson rate it keeps the marginal mean where the reader expects it.
    """
    rng = np.random.default_rng(seed)
    latent = rng.gamma(shape=1.2, scale=rate / 1.2, size=size)
    return poisson_draws(latent, seed=seed + 1)


def test_poisson_regression() -> None:
    print("\n5) Poisson regression")
    # Counts drawn at a rate proportional to exposure, as the guide describes.
    exposure = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0] * 25)
    frame = pd.DataFrame({"person_years": exposure, "treated": np.repeat([0, 1], 100)})
    frame["cases"] = poisson_draws(1.5 * exposure, seed=4)

    result = stats_engine.run_analysis(
        frame,
        "poisson_regression",
        {"target": "cases", "features": ["treated"], "exposure": "person_years"},
    )
    terms = {row["term"]: row for row in result["estimate"]["coefficients"]}
    check(
        close(terms["const"]["rate_ratio"], 1.5, 0.2),
        f"the baseline rate is 1.5 cases per unit exposure (got {terms['const']['rate_ratio']})",
    )
    check(
        close(terms["treated"]["rate_ratio"], 1.0, 0.3),
        "a null treatment effect gives a rate ratio near 1",
    )
    check(
        result["diagnostics"]["dispersion_ratio"] is not None,
        "the dispersion ratio is reported (the equidispersion check)",
    )
    check(
        len(result["tables"]["observed_vs_fitted"]["observed"]) == len(frame),
        "observed and fitted counts are both returned",
    )
    check(result["status"] == "success", "the status is success")

    # Overdispersion must be detected: that is the guide's central warning.
    # Fitted counts are held constant here, so the Pearson dispersion ratio is
    # a fair test of equidispersion.
    flat = frame.assign(py=1.0, treated=0.0, cases=overdispersed_counts(4.0, len(frame), 6))
    noisy = stats_engine.run_analysis(
        flat, "poisson_regression", {"target": "cases", "features": ["treated"]}
    )
    check(
        noisy["diagnostics"]["dispersion_ratio"] > 1.5,
        f"the dispersion ratio detects overdispersion (got {noisy['diagnostics']['dispersion_ratio']})",
    )
    check(
        any("Negative Binomial" in warning for warning in noisy["warnings"]),
        "overdispersion warns the reader to switch to Negative Binomial",
    )
    check(
        not any("Negative Binomial" in warning for warning in result["warnings"]),
        "well-behaved equidispersion data raises no such warning",
    )

    # Too many zeros must be caught as well.
    many_zeros = frame.assign(
        cases=np.where(np.arange(len(frame)) % 5 == 0, 0.0, frame["cases"])
    )
    zero_heavy = stats_engine.run_analysis(
        many_zeros, "poisson_regression", {"target": "cases", "features": ["treated"]}
    )
    check(
        any("zero-inflated" in warning.lower() for warning in zero_heavy["warnings"]),
        "excess zeros warn the reader to consider a zero-inflated model",
    )

    raises_analysis_error(
        frame,
        "poisson_regression",
        {"target": "cases", "features": ["treated"], "exposure": "nope"},
        "an unknown exposure column is rejected",
    )
    raises_analysis_error(
        frame, "poisson_regression", {"target": "cases", "features": []},
        "features are required",
    )


def test_cronbach_alpha() -> None:
    print("\n6) Cronbach's alpha")
    frame = pd.DataFrame(
        {
            "i1": [5, 4, 4, 3, 5, 2, 4, 5],
            "i2": [5, 4, 4, 3, 5, 2, 4, 5],
            "i3": [4, 4, 3, 2, 4, 1, 3, 4],
            "i4": [5, 5, 4, 3, 5, 2, 5, 4],
            "i5": [4, 3, 4, 2, 5, 1, 4, 5],
        }
    )
    result = stats_engine.run_analysis(
        frame, "cronbach_alpha", {"items": list(frame.columns)}
    )
    # alpha = k/(k-1) * (1 - sum(item variances) / total variance), by hand:
    item_variances = sum(frame[column].var(ddof=1) for column in frame.columns)
    total_variance = frame.sum(axis=1).var(ddof=1)
    k = frame.shape[1]
    expected = k / (k - 1) * (1 - item_variances / total_variance)
    check(
        close(result["estimate"]["cronbach_alpha"], expected),
        f"alpha matches the formula worked out by hand (got {result['estimate']['cronbach_alpha']})",
    )
    check(
        result["estimate"]["cronbach_alpha"] > 0.9,
        "highly consistent items score above 0.9",
    )
    check(len(result["tables"]["items"]) == k, "every item gets its own row")
    check(
        all("alpha_if_deleted" in row for row in result["tables"]["items"]),
        "alpha-if-deleted is reported for each item",
    )
    check(result["estimate"]["omega"] is not None, "an omega estimate is reported alongside")
    check(
        all(
            row["item_rest_correlation"] is not None
            for row in result["tables"]["items"]
        ),
        "item-rest correlations are reported",
    )

    # Unrelated items must score badly and say so.
    rng = np.random.default_rng(3)
    noise = pd.DataFrame(rng.integers(1, 6, size=(80, 5)), columns=list("abcde"))
    poor = stats_engine.run_analysis(noise, "cronbach_alpha", {"items": list(noise.columns)})
    check(poor["estimate"]["cronbach_alpha"] < 0.3, "random items give a low alpha")
    check(bool(poor["warnings"]), "a low alpha raises a warning")
    check(
        "0.7" in " ".join(poor["warnings"]),
        "the warning quotes the 0.7 threshold the guide sets",
    )

    raises_analysis_error(
        frame, "cronbach_alpha", {"items": ["i1"]}, "a single item is rejected"
    )
    raises_analysis_error(
        frame, "cronbach_alpha", {"items": ["i1", "i1"]},
        "listing the same item twice is rejected",
    )


def test_kaplan_meier() -> None:
    print("\n7) Kaplan-Meier and the log-rank test")
    # A textbook curve: 12/13 survive t=1, then 9/11 survive t=2.
    frame = pd.DataFrame(
        {
            "t": [1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 8, 10],
            "e": [1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        }
    )
    result = stats_engine.run_analysis(
        frame, "kaplan_meier", {"time_column": "t", "event_column": "e"}
    )
    steps = {
        row["time"]: (row["survival"], row["at_risk"])
        for row in result["tables"]["curve"]
    }
    check(close(steps[1.0][0], 12 / 13, 1e-4), f"survival at t=1 is 12/13 (got {steps[1.0][0]})")
    check(
        close(steps[2.0][0], 12 / 13 * 9 / 11, 1e-4),
        f"survival at t=2 is 12/13 * 9/11 (got {steps[2.0][0]})",
    )
    check(close(steps[2.0][1], 11), "11 subjects remain at risk at t=2")
    check(
        close(result["estimate"]["median_survival"], 7.0),
        f"the median survival is 7 (got {result['estimate']['median_survival']})",
    )
    check(result["estimate"]["events"] == 7, "7 events were observed")
    check(result["estimate"]["censored"] == 6, "6 observations were censored")
    check(
        all(
            0.0 <= row["ci_lower"] <= row["survival"] <= row["ci_upper"] <= 1.0
            for row in result["tables"]["curve"]
        ),
        "the confidence band brackets the survival estimate",
    )
    check(result["status"] == "success", "the status is success")

    # Two groups with clearly different outcomes must separate on the log-rank test.
    rng = np.random.default_rng(5)
    grouped = pd.DataFrame(
        {
            "t": np.concatenate([rng.exponential(20, 80), rng.exponential(6, 80)]).round(2),
            "e": (rng.random(160) < 0.7).astype(int),
            "arm": ["good"] * 80 + ["poor"] * 80,
        }
    )
    compared = stats_engine.run_analysis(
        grouped,
        "kaplan_meier",
        {"time_column": "t", "event_column": "e", "group_column": "arm"},
    )
    check(
        compared["test"]["p_value"] < 0.01,
        f"clearly different groups separate on the log-rank test (p={compared['test']['p_value']})",
    )
    check(compared["test"]["statistic"] > 0, "the log-rank statistic is positive")
    check(
        set(compared["estimate"]["group_median_survival"]) == {"good", "poor"},
        "a median survival is reported for each group",
    )
    check(
        any(key.startswith("curve_") for key in compared["tables"]),
        "a separate survival curve is drawn per group",
    )

    # No events at all is a data problem, and must be reported as one.
    censored_only = stats_engine.run_analysis(
        pd.DataFrame({"t": [1, 2, 3, 4], "e": [0, 0, 0, 0]}),
        "kaplan_meier",
        {"time_column": "t", "event_column": "e"},
    )
    check(
        censored_only["status"] == "insufficient_data",
        "a curve with no events is flagged rather than faked",
    )
    check(bool(censored_only["warnings"]), "the reader is told why there is no curve")

    raises_analysis_error(
        frame, "kaplan_meier", {"time_column": "t"},
        "a missing event column is rejected",
    )
    raises_analysis_error(
        frame.assign(e=None),
        "kaplan_meier",
        {"time_column": "t", "event_column": "e"},
        "a missing event flag is rejected rather than treated as censored",
    )
    raises_analysis_error(
        frame.assign(e=["low", "mid", "high", "low", "mid", "high", "low", "mid", "high", "low", "mid", "high", "low"]),
        "kaplan_meier",
        {"time_column": "t", "event_column": "e"},
        "an event column with three categories is rejected",
    )
    # A single-category event column is a real possibility (nobody had the
    # event), and it must reach the no-events path rather than being faked.
    all_censored = stats_engine.run_analysis(
        frame.assign(e=["low"] * 13),
        "kaplan_meier",
        {"time_column": "t", "event_column": "e"},
    )
    check(
        all_censored["status"] == "insufficient_data",
        "an event column with no events reaches the no-events path",
    )
    raises_analysis_error(
        frame,
        "kaplan_meier",
        {"time_column": "t", "event_column": "t"},
        "using the same column for time and event is rejected",
    )


def test_second_wave() -> None:
    print("\n9) The second wave: mcnemar, z, two-way ANOVA, ordinal logit")
    rng = np.random.default_rng(3)
    n = 600

    # McNemar on a paired table built so the exact answer is known by hand.
    paired = pd.concat(
        [
            pd.DataFrame({"before": ["a"] * 30, "after": ["b"] * 30}),   # 30 flip a->b
            pd.DataFrame({"before": ["a"] * 20, "after": ["a"] * 20}),   # 20 agree
            pd.DataFrame({"before": ["b"] * 10, "after": ["a"] * 10}),   # 10 flip b->a
        ],
        ignore_index=True,
    )
    result = stats_engine.run_analysis(
        paired, "mcnemar", {"before_column": "before", "after_column": "after"}
    )
    check(result["estimate"]["changed_to_second"] == 30, "30 pairs moved from 'a' to 'b'")
    check(result["estimate"]["changed_to_first"] == 10, "10 pairs moved from 'b' to 'a'")
    check(result["estimate"]["agreements"] == 20, "20 pairs agreed")
    check(result["estimate"]["discordant"] == 40, "40 discordant pairs")
    # (|30-10| - 1)^2 / 40 = 361/40 with the continuity correction.
    check(
        close(result["test"]["statistic"], (30 - 10 - 1) ** 2 / 40, 1e-4),
        f"the corrected chi-square matches (30-10-1)^2/40 (got {result['test']['statistic']})",
    )
    check(result["test"]["p_value"] < 0.01, "the change is significant")
    identical = stats_engine.run_analysis(
        paired.assign(before="a", after="a"),
        "mcnemar",
        {"before_column": "before", "after_column": "after"},
    )
    check(
        identical["status"] == "invalid_request",
        "a table where nobody disagrees is reported as carrying no information",
    )
    check(
        bool(identical["warnings"]),
        "that case explains why there is no statistic",
    )

    # One-sample z against a known mean and a known standard deviation.
    values = pd.DataFrame({"v": rng.normal(10, 2, 400)})
    at_mean = stats_engine.run_analysis(
        values, "one_sample_z_test", {"value_column": "v", "mu": 10.0, "sigma": 2.0}
    )
    check(at_mean["test"]["p_value"] > 0.2, "a sample at the reference mean is not significant")
    check(not at_mean["warnings"], "a known sigma produces no caveat")
    away = stats_engine.run_analysis(
        values, "one_sample_z_test", {"value_column": "v", "mu": 8.0, "sigma": 2.0}
    )
    check(away["test"]["p_value"] < 0.001, "two units below the reference mean is significant")
    unknown_sd = stats_engine.run_analysis(
        values, "one_sample_z_test", {"value_column": "v", "mu": 10.0}
    )
    check(
        any("t-test" in warning for warning in unknown_sd["warnings"]),
        "an unknown population SD says so and points at the t-test",
    )


    # Two-way ANOVA on data with known main effects and a known interaction.
    first = rng.normal(0, 1, n)
    factor_a = rng.choice(["x", "y"], n)
    factor_b = rng.choice(["p", "q"], n)
    outcome = (
        5.0
        + 2.0 * first
        + (factor_a == "x") * 1.5
        + (factor_b == "p") * 1.0
        + ((factor_a == "x") & (factor_b == "p")) * 2.0
        + rng.normal(0, 1, n)
    )
    anova_frame = pd.DataFrame(
        {"y": outcome, "a": first, "fa": factor_a, "fb": factor_b}
    )
    anova = stats_engine.run_analysis(
        anova_frame,
        "two_way_anova",
        {"value_column": "y", "group_column": "fa", "second_group_column": "fb"},
    )
    terms = {row["term"]: row for row in anova["estimate"]["terms"]}
    check(
        [row["term"] for row in anova["estimate"]["terms"]]
        == ["factor_a", "factor_b", "interaction"],
        "the guide's two main effects and the interaction are all reported",
    )
    check(terms["factor_a"]["significant"], "a planted main effect A is detected")
    check(terms["factor_b"]["significant"], "a planted main effect B is detected")
    check(terms["interaction"]["significant"], "a planted interaction is detected")
    check(
        all(row["degrees_of_freedom"] > 0 for row in anova["estimate"]["terms"]),
        "every term has positive degrees of freedom",
    )
    # The planted means average to 5 + 0.75 + 0.5 + 0.5 = 6.75: the two main
    # effects contribute half their size each way, and the interaction likewise.
    check(
        close(anova["estimate"]["grand_mean"], 6.75, 0.2),
        f"the grand mean matches the planted effects (got {anova['estimate']['grand_mean']})",
    )
    raises_analysis_error(
        anova_frame, "two_way_anova",
        {"value_column": "y", "group_column": "fa", "second_group_column": "fa"},
        "the same column used as both factors is rejected",
    )

    # Ordinal logit on data simulated from a known proportional-odds model.
    predictor = rng.normal(0, 1, 3000)
    linear = 0.3 + 1.2 * predictor
    lower = 1.0 / (1.0 + np.exp(-(-0.5 - linear)))
    upper = 1.0 / (1.0 + np.exp(-(0.6 - linear)))
    probabilities = np.column_stack([lower, upper - lower, 1.0 - upper])
    draws = rng.random(3000)
    levels = (draws[:, None] > probabilities.cumsum(axis=1)).sum(axis=1)
    ordinal = pd.DataFrame({"grade": levels, "score": predictor})
    fitted = stats_engine.run_analysis(
        ordinal, "ordinal_logit", {"target": "grade", "features": ["score"]}
    )
    slope = next(
        row for row in fitted["estimate"]["coefficients"] if row["term"] == "score"
    )
    check(
        abs(slope["beta"] - 1.2) < 0.2,
        f"the slope recovers the simulated 1.2 (got {slope['beta']})",
    )
    check(slope["p_value"] < 0.01, "the recovered effect is significant")
    check(len(fitted["estimate"]["thresholds"]) == 2, "3 categories give 2 thresholds")
    check(
        fitted["estimate"]["thresholds"][0] < fitted["estimate"]["thresholds"][1],
        "the thresholds increase, as an ordered outcome requires",
    )
    check(
        fitted["diagnostics"]["assumption"] == "proportional odds",
        "the assumption is named in the output",
    )
    raises_analysis_error(
        ordinal.assign(grade=(levels > 1).astype(int)),
        "ordinal_logit",
        {"target": "grade", "features": ["score"]},
        "a two-category outcome is rejected by the ordinal model",
    )


def test_probit_and_lpm() -> None:
    print("\n10) Probit and the linear probability model")
    rng = np.random.default_rng(11)
    n = 2500

    # Draw a binary outcome from a known logit, then fit a probit. The two
    # coefficients are not the same numbers -- probit measures the latent
    # normal index rather than log-odds -- but they must be the same sign and
    # a clearly non-zero slope must come back.
    predictor = rng.normal(0, 1, n)
    odds = -0.5 + 1.2 * predictor
    binary = (rng.random(n) < 1.0 / (1.0 + np.exp(-odds))).astype(int)
    frame = pd.DataFrame({"y": binary, "x": predictor})

    probit_fit = stats_engine.run_analysis(
        frame, "probit", {"target": "y", "features": ["x"]}
    )
    rows = {row["term"]: row for row in probit_fit["estimate"]["coefficients"]}
    check("x" in rows and "const" in rows, "probit reports an intercept and the slope")
    check(rows["x"]["beta"] > 0.1, "probit recovers the sign of the planted effect")
    check(rows["x"]["p_value"] < 0.001, "the planted effect is significant")
    check(
        rows["x"]["beta"] < 1.2,
        f"the probit slope sits below the logit 1.2 it came from (got {rows['x']['beta']})",
    )
    check(
        probit_fit["effect_size"]["value"] is not None
        and 0.0 <= probit_fit["effect_size"]["value"] < 0.5,
        f"McFadden R2 is a fraction in range (got {probit_fit['effect_size']['value']})",
    )
    check(
        probit_fit["diagnostics"]["log_likelihood"] < 0,
        "a log-likelihood is negative; the linear form would be positive",
    )

    # A pure-noise outcome must not manufacture a pseudo-R2.
    noise = (rng.random(n) < 0.5).astype(int)
    noise_fit = stats_engine.run_analysis(
        pd.DataFrame({"y": noise, "x": rng.normal(0, 1, n)}),
        "probit",
        {"target": "y", "features": ["x"]},
    )
    check(
        abs(noise_fit["effect_size"]["value"]) < 0.02,
        f"a null model reports no explanatory power (got {noise_fit['effect_size']['value']})",
    )
    raises_analysis_error(
        pd.DataFrame({"y": np.arange(40.0), "x": rng.normal(0, 1, 40)}),
        "probit",
        {"target": "y", "features": ["x"]},
        "a continuous outcome is refused rather than split at some arbitrary point",
    )

    # The LPM is OLS, so on a genuine 0/1 outcome it must reproduce the
    # textbook slope cov(x,y)/var(x) exactly. The outcome is drawn from a
    # linear probability model, which is the case the guide says LPM suits.
    predicted = np.clip(0.40 + 0.20 * predictor, 0.01, 0.99)
    lpm_outcome = (rng.random(n) < predicted).astype(int)
    lpm_frame = pd.DataFrame({"y": lpm_outcome, "x": predictor})
    lpm = stats_engine.run_analysis(
        lpm_frame, "linear_probability_model", {"target": "y", "features": ["x"]}
    )
    # cov/var with the ddof=0 convention the OLS estimator actually uses.
    manual_slope = float(
        np.mean((predictor - predictor.mean()) * (lpm_outcome - lpm_outcome.mean()))
        / np.mean((predictor - predictor.mean()) ** 2)
    )
    manual_intercept = float(lpm_outcome.mean() - manual_slope * predictor.mean())
    lpm_rows = {row["term"]: row for row in lpm["estimate"]["coefficients"]}
    # Coefficients are rounded to 6 decimals on the way out, so the tolerance
    # has to allow for that rather than demanding full float equality.
    check(
        close(lpm_rows["x"]["beta"], manual_slope, 1e-6),
        f"the LPM slope is cov(x,y)/var(x) (got {lpm_rows['x']['beta']})",
    )
    check(
        close(lpm_rows["const"]["beta"], manual_intercept, 1e-6),
        "the LPM intercept is mean(y) - slope*mean(x)",
    )
    check(
        lpm_rows["x"]["beta"] > 0,
        "the planted positive effect keeps its sign through the 0/1 draw",
    )
    check(
        lpm["diagnostics"]["durbin_watson"] is not None,
        "the LPM reports the Durbin-Watson statistic its assumptions call for",
    )
    check(
        bool(lpm["warnings"]),
        "an LPM predicting outside 0-1 says so instead of hiding it",
    )
    # The LPM is heteroscedastic by construction: the error variance is
    # p(1-p), which the homoskedastic formula pretends is one constant. So the
    # robust SE is the one that matters, and it is checked here against the
    # delta-method value sum_i p_i(1-p_i)(x_i-xbar)^2 under a square root, over
    # n. On this data the naive SE is the larger, and wrongly so, one.
    naive = {row["term"]: row["standard_error"] for row in lpm["estimate"]["coefficients"]}
    robust = {row["term"]: row["standard_error"] for row in lpm["tables"]["coefficients_hc3"]}
    check(
        close(robust["x"], float(np.sqrt(np.sum(predicted * (1 - predicted) * (predictor - predictor.mean()) ** 2)) / n), 0.05),
        f"the robust slope SE matches the delta method (got {robust['x']})",
    )
    check(
        robust["x"] < naive["x"],
        "and it corrects the naive SE downwards, which is the bias the LPM has",
    )
    raises_analysis_error(
        pd.DataFrame({"y": np.arange(40.0), "x": rng.normal(0, 1, 40)}),
        "linear_probability_model",
        {"target": "y", "features": ["x"]},
        "the LPM also refuses a continuous outcome",
    )

    # A two-level text column is encoded against the requested positive class.
    labels = pd.DataFrame(
        {"grp": ["a"] * 200 + ["b"] * 200, "x": np.concatenate([np.zeros(200), np.ones(200)])}
    )
    labelled = stats_engine.run_analysis(
        labels,
        "linear_probability_model",
        {"target": "grp", "features": ["x"], "positive_category": "b"},
    )
    labelled_rows = {row["term"]: row for row in labelled["estimate"]["coefficients"]}
    check(
        close(labelled_rows["x"]["beta"], 1.0, 0.05),
        f"'b' is encoded as 1, giving a slope near 1 (got {labelled_rows['x']['beta']})",
    )
    flipped = stats_engine.run_analysis(
        labels,
        "linear_probability_model",
        {"target": "grp", "features": ["x"], "positive_category": "a"},
    )
    flipped_rows = {row["term"]: row for row in flipped["estimate"]["coefficients"]}
    check(
        flipped_rows["x"]["beta"] < 0,
        "asking for the other positive class flips the sign, as it must",
    )


def test_negative_binomial() -> None:
    print("\n11) Negative binomial: overdispersed counts")
    rng = np.random.default_rng(5)
    n = 1500

    # Simulate from a known NB: mean exp(0.6 + 0.8x), alpha = 0.5. Recovering
    # alpha is the real test -- the mean parameters are what a Poisson would
    # also estimate, so they cannot tell the two models apart.
    predictor = rng.normal(0, 1, n)
    mean = np.exp(0.6 + 0.8 * predictor)
    r = 1.0 / 0.5
    counts = rng.negative_binomial(r, r / (r + mean)).astype(float)
    frame = pd.DataFrame({"y": counts, "x": predictor})
    result = stats_engine.run_analysis(
        frame, "negative_binomial", {"target": "y", "features": ["x"]}
    )
    rows = {row["term"]: row for row in result["estimate"]["coefficients"]}
    check(
        abs(result["estimate"]["alpha"] - 0.5) < 0.15,
        f"alpha recovers the planted 0.5 (got {result['estimate']['alpha']})",
    )
    check(
        abs(rows["x"]["beta"] - 0.8) < 0.15,
        f"the slope recovers the planted 0.8 (got {rows['x']['beta']})",
    )
    check(rows["x"]["p_value"] < 0.01, "the planted effect is significant")
    check(
        rows["x"]["exp"] is not None and abs(rows["x"]["exp"] - np.exp(rows["x"]["beta"])) < 1e-4,
        "the reported effect is the incidence rate ratio, exp(beta)",
    )
    check(result["test"]["p_value"] < 0.01, "the LR test rejects the Poisson")
    check(
        result["diagnostics"]["pearson_dispersion"] is not None,
        "the Pearson dispersion is reported as a goodness-of-fit measure",
    )

    # An exposure offset must not change the slope, only the intercept.
    exposure = np.where(predictor > 0, 3.0, 1.0)
    offset_counts = rng.negative_binomial(r, r / (r + mean * exposure)).astype(float)
    offset = stats_engine.run_analysis(
        pd.DataFrame({"y": offset_counts, "x": predictor, "e": exposure}),
        "negative_binomial",
        {"target": "y", "features": ["x"], "exposure_column": "e"},
    )
    offset_rows = {row["term"]: row for row in offset["estimate"]["coefficients"]}
    check(
        abs(offset_rows["x"]["beta"] - 0.8) < 0.15,
        f"the offset leaves the slope alone (got {offset_rows['x']['beta']})",
    )
    check(
        offset["diagnostics"]["raw_var_over_mean"] is None,
        "the raw variance-to-mean ratio is withheld when an offset is in play",
    )
    check(
        bool(offset["diagnostics"]["raw_var_over_mean_note"]),
        "and it says why rather than just showing a blank",
    )
    raises_analysis_error(
        pd.DataFrame({"y": offset_counts, "x": predictor, "e": np.zeros(n)}),
        "negative_binomial",
        {"target": "y", "features": ["x"], "exposure_column": "e"},
        "a non-positive exposure is rejected",
    )

    # Genuinely equidispersed counts put the maximum on the Poisson boundary.
    # That is a real property of the model, not a failed fit, and the warning
    # has to say so rather than claiming the optimiser let the user down.
    poisson_counts = rng.poisson(4.0, 900).astype(float)
    equi = stats_engine.run_analysis(
        pd.DataFrame({"y": poisson_counts, "x": rng.normal(0, 1, 900)}),
        "negative_binomial",
        {"target": "y", "features": ["x"]},
    )
    check(
        equi["test"]["p_value"] > 0.05,
        "the LR test does not reject the Poisson on equidispersed counts",
    )
    check(
        equi["estimate"]["alpha"] < 0.2,
        f"alpha collapses towards zero (got {equi['estimate']['alpha']})",
    )
    check(
        any("Poisson" in warning for warning in equi["warnings"]),
        "the output recommends the Poisson rather than crying 'did not converge'",
    )
    check(
        not any("converge" in warning for warning in equi["warnings"]),
        "a boundary solution is not mislabelled as an optimiser failure",
    )

    # Counts have to be counts. These values are genuinely fractional, not
    # whole numbers with a decimal point, so they must be refused.
    raises_analysis_error(
        pd.DataFrame({"y": np.linspace(0.0, 7.0, 30), "x": rng.normal(0, 1, 30)}),
        "negative_binomial",
        {"target": "y", "features": ["x"]},
        "a fractional outcome is refused",
    )
    raises_analysis_error(
        pd.DataFrame({"y": np.linspace(-5, 5, 30), "x": rng.normal(0, 1, 30)}),
        "negative_binomial",
        {"target": "y", "features": ["x"]},
        "a negative outcome is refused",
    )



def test_tobit_ridge_quantile() -> None:
    print("\n12) Tobit, ridge/lasso and quantile regression")
    rng = np.random.default_rng(4)

    # --- Tobit on a right-censored (ceilinged) outcome -------------------
    n = 1500
    predictor = rng.normal(0, 1, n)
    latent = 1.0 + 2.0 * predictor + rng.normal(0, 1.0, n)
    ceiling = 4.0
    observed = np.minimum(latent, ceiling)
    frame = pd.DataFrame({"y": observed, "x": predictor})

    tobit_fit = stats_engine.run_analysis(
        frame, "tobit",
        {"target": "y", "features": ["x"], "threshold": ceiling, "censor_type": "right"},
    )
    tobit_rows = {row["term"]: row for row in tobit_fit["estimate"]["coefficients"]}
    check(
        abs(tobit_rows["const"]["beta"] - 1.0) < 0.2 and abs(tobit_rows["x"]["beta"] - 2.0) < 0.2,
        "Tobit recovers the latent coefficients that OLS hides",
    )
    check(
        abs(tobit_fit["estimate"]["sigma"] - 1.0) < 0.2,
        f"and the latent error sd (got {tobit_fit['estimate']['sigma']})",
    )
    # OLS on the same data is biased towards the ceiling; that is the point of
    # the method, so it is asserted rather than assumed.
    ols = np.linalg.lstsq(
        np.column_stack([np.ones(n), predictor]), observed, rcond=None
    )[0]
    check(
        abs(ols[1] - 2.0) > abs(tobit_rows["x"]["beta"] - 2.0),
        "and OLS on the same data is measurably further from the truth",
    )
    check(
        tobit_fit["estimate"]["censored_observations"] == int((observed >= ceiling - 1e-9).sum()),
        "the censored count is reported",
    )
    check(
        len(tobit_fit["estimate"]["expected_observed"]) == 2,
        "the expected *observed* value is reported alongside the latent mean",
    )
    check(
        any("latent" in note for note in [tobit_fit["estimate"]["latent_mean_note"]]),
        "and the output says the two are not the same thing",
    )
    # Left censoring must work too, with its own tail.
    floor = -1.0
    floored = np.maximum(latent, floor)
    left = stats_engine.run_analysis(
        pd.DataFrame({"y": floored, "x": predictor}),
        "tobit",
        {"target": "y", "features": ["x"], "threshold": floor, "censor_type": "left"},
    )
    left_rows = {row["term"]: row for row in left["estimate"]["coefficients"]}
    check(
        abs(left_rows["x"]["beta"] - 2.0) < 0.2,
        f"left censoring uses the other tail correctly (got {left_rows['x']['beta']})",
    )
    raises_analysis_error(
        frame, "tobit", {"target": "y", "features": ["x"]},
        "a Tobit with no threshold is refused, because it cannot be guessed",
    )
    raises_analysis_error(
        frame, "tobit",
        {"target": "y", "features": ["x"], "threshold": 1e9, "censor_type": "right"},
        "a threshold that censors nothing is refused rather than fitted",
    )

    # --- ridge / lasso ----------------------------------------------------
    m, p = 300, 12
    wide = rng.normal(size=(m, p))
    truth = np.array([3.0, -2.0, 1.5] + [0.0] * (p - 3))
    noisy = wide @ truth + rng.normal(0, 1.0, m)
    wide_frame = pd.DataFrame({"y": noisy})
    for column in range(p):
        wide_frame["x%d" % column] = wide[:, column]
    features = ["x%d" % column for column in range(p)]

    lasso = stats_engine.run_analysis(
        wide_frame,
        "ridge_lasso",
        {"target": "y", "features": features, "penalty": "lasso", "seed": 11},
    )
    check(
        lasso["estimate"]["penalty"] == "lasso",
        "the requested penalty is reported back",
    )
    check(
        len(lasso["diagnostics"]["cv_rmse_by_alpha"]) > 1,
        "the penalty was chosen by a cross-validated search, not fixed",
    )
    check(
        lasso["estimate"]["alpha"] > 0,
        "and the chosen penalty is a real penalty, not zero",
    )
    lasso_rows = {row["term"]: row for row in lasso["estimate"]["coefficients"]}
    check(
        abs(lasso_rows["x0"]["beta"] - 3.0) < 0.6,
        f"the true coefficient survives (got {lasso_rows['x0']['beta']})",
    )
    check(
        abs(lasso_rows["x1"]["beta"] + 2.0) < 0.6,
        f"including a negative one (got {lasso_rows['x1']['beta']})",
    )
    check(
        any("zero" in warning for warning in lasso["warnings"]),
        "the variables the penalty removed are named",
    )
    ridge = stats_engine.run_analysis(
        wide_frame,
        "ridge_lasso",
        {"target": "y", "features": features, "penalty": "ridge", "seed": 11},
    )
    ridge_nonzero = sum(
        1 for row in ridge["estimate"]["standardised_coefficients"]
        if abs(row["value"]) > 1e-10
    )
    check(
        ridge_nonzero == p,
        f"ridge shrinks but never zeroes (got {ridge_nonzero} of {p})",
    )
    check(
        any("prediction" in warning for warning in lasso["warnings"]),
        "the output says the coefficients are for prediction, not inference",
    )
    # The same seed must give the same answer.
    repeat = stats_engine.run_analysis(
        wide_frame,
        "ridge_lasso",
        {"target": "y", "features": features, "penalty": "lasso", "seed": 11},
    )
    check(
        repeat["estimate"]["alpha"] == lasso["estimate"]["alpha"],
        "a seeded run is reproducible",
    )
    raises_analysis_error(
        wide_frame, "ridge_lasso", {"target": "y", "features": features, "penalty": "lasso", "l1_ratio": 5},
        "an out-of-range l1_ratio is refused",
    )

    # --- quantile regression ---------------------------------------------
    # The median fit must agree with OLS, and the tails must not.
    k = 800
    qx = rng.normal(0, 1, k)
    qy = 1.0 + 1.0 * qx + (0.5 + 0.4 * np.abs(qx)) * rng.normal(0, 1, k)
    quantiles = stats_engine.run_analysis(
        pd.DataFrame({"y": qy, "x": qx}),
        "quantile_regression",
        {"target": "y", "features": ["x"], "quantiles": [0.1, 0.5, 0.9]},
    )
    fits = {fit["quantile"]: fit for fit in quantiles["estimate"]["fits"]}
    check(sorted(fits) == [0.1, 0.5, 0.9], "one fit per requested quantile")
    median = {row["term"]: row["beta"] for row in fits[0.5]["coefficients"]}
    ols_slope = float(np.polyfit(qx, qy, 1)[0])
    check(
        abs(median["x"] - ols_slope) < 0.15,
        f"the median fit matches the OLS slope (got {median['x']} vs {ols_slope})",
    )
    # Intercepts must rise with tau: that ordering is the whole result.
    intercepts = [
        {row["term"]: row["beta"] for row in fits[q]["coefficients"]}["const"]
        for q in (0.1, 0.5, 0.9)
    ]
    check(
        intercepts[0] < intercepts[1] < intercepts[2],
        f"the fitted quantiles are ordered low to high ({intercepts})",
    )
    # The defining property: the share of observations falling *below* a
    # fitted tau line is tau itself. This tests the fit against the data
    # directly, without having to match a conditional quantile computed on a
    # different slice of x to the x the line is evaluated at.
    for tau in (0.1, 0.5, 0.9):
        line = {
            row["term"]: row["beta"] for row in fits[tau]["coefficients"]
        }
        below = float(np.mean(qy <= line["const"] + line["x"] * qx))
        check(
            abs(below - tau) < 0.05,
            f"about {tau:.0%} of the data falls below the fitted tau={tau} line (got {below:.3f})",
        )
    for fit in (fits[0.1], fits[0.5], fits[0.9]):
        row = next(r for r in fit["coefficients"] if r["term"] == "x")
        check(
            row["standard_error"] is not None and row["standard_error"] > 0,
            "each quantile reports a usable standard error",
        )
    raises_analysis_error(
        pd.DataFrame({"y": qy, "x": qx}),
        "quantile_regression",
        {"target": "y", "features": ["x"], "quantiles": [0.0, 0.5]},
        "a quantile outside (0, 1) is refused",
    )



def test_zero_inflated_and_hurdle() -> None:
    print("\n13) Zero-inflated and hurdle count models")
    rng = np.random.default_rng(8)
    n = 2500
    predictor = rng.normal(0, 1, n)

    def truncated_poisson(rate, generator):
        """Pois(rate) conditioned on being positive, by rejection."""
        out = generator.poisson(rate).astype(float)
        zero = out == 0
        tries = 0
        while zero.any() and tries < 60:
            out[zero] = generator.poisson(rate[zero]).astype(float)
            zero = out == 0
            tries += 1
        return out

    # --- zero-inflated: 30% structural zeros on top of a real count process
    structural = rng.random(n) < 0.30
    rate = np.exp(0.3 + 0.9 * predictor)
    counts = np.where(structural, 0.0, rng.poisson(rate)).astype(float)
    zi = stats_engine.run_analysis(
        pd.DataFrame({"y": counts, "x": predictor}),
        "zero_inflated",
        {"target": "y", "features": ["x"]},
    )
    check(
        abs(zi["estimate"]["inflation_probability_at_reference"] - 0.30) < 0.08,
        f"the inflation probability recovers the planted 0.30 "
        f"(got {zi['estimate']['inflation_probability_at_reference']})",
    )
    zi_count = {row["term"]: row["beta"] for row in zi["estimate"]["count_coefficients"]}
    check(
        abs(zi_count["const"] - 0.3) < 0.2 and abs(zi_count["x"] - 0.9) < 0.2,
        f"and the count process keeps its own coefficients ({zi_count})",
    )
    check(
        len(zi["estimate"]["count_coefficients"])
        == len(zi["estimate"]["inflation_coefficients"]),
        "both coefficient blocks are reported, as the two-process model requires",
    )
    check(
        zi["test"]["p_value"] < 0.01 and zi["test"]["statistic"] > 0,
        "Vuong's test detects the extra component, with a positive z",
    )

    # The negative control is the important one: with no structural zeros the
    # model must collapse to the plain fit and say so, rather than inventing a
    # point mass to soak up ordinary sampling noise.
    plain = rng.poisson(rate).astype(float)
    zi_plain = stats_engine.run_analysis(
        pd.DataFrame({"y": plain, "x": predictor}),
        "zero_inflated",
        {"target": "y", "features": ["x"]},
    )
    check(
        zi_plain["estimate"]["inflation_probability_at_reference"] < 0.05,
        f"with no structural zeros the inflation collapses "
        f"(got {zi_plain['estimate']['inflation_probability_at_reference']})",
    )
    check(
        not zi_plain["test"]["significant"],
        "and Vuong's test does not reject the plain model",
    )
    check(
        any("not supported" in warning for warning in zi_plain["warnings"]),
        "and the output says the point mass is not warranted",
    )
    zi_count_plain = {
        row["term"]: row["beta"] for row in zi_plain["estimate"]["count_coefficients"]
    }
    check(
        abs(zi_count_plain["x"] - 0.9) < 0.2,
        "the count coefficients still recover the truth when there is no inflation",
    )

    # --- hurdle: a zero process, then a count process truncated at zero -----
    m = 4000
    hurdle_x = rng.normal(0, 1, m)
    probability = 1.0 / (1.0 + np.exp(-(-0.4 + 0.8 * hurdle_x)))
    hurdle_rate = np.exp(0.6 + 0.5 * hurdle_x)
    hurdle_counts = np.where(
        rng.random(m) < probability,
        truncated_poisson(hurdle_rate, rng),
        0.0,
    )
    fit = stats_engine.run_analysis(
        pd.DataFrame({"y": hurdle_counts, "x": hurdle_x}),
        "hurdle",
        {"target": "y", "features": ["x"]},
    )
    # "At the reference" means the first row of the design, which is the
    # intercept only -- the first row of the *predictor sample*, which need not
    # be zero. The probability there is computed from the true model so the
    # comparison is against the right number.
    expected_probability = float(
        1.0 / (1.0 + np.exp(-(-0.4 + 0.8 * hurdle_x[0])))
    )
    check(
        abs(fit["estimate"]["probability_positive_at_reference"] - expected_probability) < 0.05,
        f"the hurdle recovers the probability of a non-zero count "
        f"(got {fit['estimate']['probability_positive_at_reference']}, "
        f"expected {expected_probability})",
    )
    count = {row["term"]: row["beta"] for row in fit["estimate"]["count_coefficients"]}
    zero = {
        row["term"]: row["beta"] for row in fit["estimate"]["zero_process_coefficients"]
    }
    # The count part is the discriminating test: a zero-inflated likelihood
    # written into the hurdle fit shifts these and leaves the zero process
    # looking fine, so both blocks are checked.
    check(
        abs(count["const"] - 0.6) < 0.1 and abs(count["x"] - 0.5) < 0.1,
        f"the truncated count process recovers its coefficients ({count})",
    )
    check(
        abs(zero["const"] + 0.4) < 0.1 and abs(zero["x"] - 0.8) < 0.1,
        f"and so does the zero process ({zero})",
    )
    check(
        fit["estimate"]["expected_mean_at_reference"] is not None,
        "the implied unconditional mean is reported, not just the two parts",
    )
    check(
        any("truncat" in note for note in [fit["estimate"]["truncation_note"]]),
        "and the output warns the two coefficient blocks are not comparable with an "
        "untruncated model's",
    )
    raises_analysis_error(
        pd.DataFrame({"y": counts, "x": predictor}),
        "hurdle",
        {"target": "y", "features": ["x"], "distribution": "gaussian"},
        "an unknown count distribution is refused",
    )



def test_reliability_statistics() -> None:
    print("\n14) Reliability: omega, kappa, Fleiss and the ICC")
    rng = np.random.default_rng(1)

    # --- McDonald's omega, against theory ----------------------------------
    # Four items each = theta + noise with equal loadings, so the item
    # reliability is 1/(1+0.09) = 0.917 and omega should land near 0.98.
    theta = rng.normal(0, 1, 300)
    consistent = np.column_stack(
        [theta + rng.normal(0, 0.3, 300) for _ in range(4)]
    )
    columns = ["i1", "i2", "i3", "i4"]
    omega = stats_engine.run_analysis(
        pd.DataFrame(consistent, columns=columns), "mcdonalds_omega", {"columns": columns}
    )
    check(
        0.90 < omega["estimate"]["omega_total"] <= 1.0,
        f"omega is high for consistent items (got {omega['estimate']['omega_total']})",
    )
    check(
        omega["estimate"]["cronbach_alpha"] is not None,
        "Cronbach's alpha is reported alongside for comparison",
    )
    noise = rng.normal(0, 1, (300, 4))
    noise_columns = ["a", "b", "c", "d"]
    omega_noise = stats_engine.run_analysis(
        pd.DataFrame(noise, columns=noise_columns),
        "mcdonalds_omega",
        {"columns": noise_columns},
    )
    check(
        omega_noise["estimate"]["omega_total"] < 0.6,
        f"and low for items with no common factor (got {omega_noise['estimate']['omega_total']})",
    )

    # --- Cohen's kappa, against a hand-worked table ------------------------
    # [[45, 5], [15, 35]]: observed 0.80, expected 0.5*0.6 + 0.5*0.4 = 0.5,
    # so kappa = 0.3/0.5 = 0.6 exactly.
    table = pd.DataFrame(
        {"a": ["y"] * 50 + ["n"] * 50, "b": ["y"] * 45 + ["n"] * 5 + ["y"] * 15 + ["n"] * 35}
    )
    kappa = stats_engine.run_analysis(
        table, "cohens_kappa", {"row_column": "a", "column_column": "b"}
    )
    check(close(kappa["estimate"]["kappa"], 0.6, 1e-6), f"kappa is 0.6 on the worked table (got {kappa['estimate']['kappa']})")
    check(close(kappa["estimate"]["observed_agreement"], 0.8, 1e-6), "observed agreement is 0.8")
    check(close(kappa["estimate"]["expected_agreement"], 0.5, 1e-6), "chance agreement is 0.5")
    perfect = pd.DataFrame({"a": ["y", "n", "y", "n"], "b": ["y", "n", "y", "n"]})
    perfect_kappa = stats_engine.run_analysis(
        perfect, "cohens_kappa", {"row_column": "a", "column_column": "b"}
    )
    check(
        close(perfect_kappa["estimate"]["kappa"], 1.0, 1e-9),
        "and 1.0 when the raters agree exactly",
    )
    # A table where almost everything is in the diagonal is kappa's paradox:
    # the observed agreement is high but kappa is pulled down by the
    # prevalence, and the output has to say so rather than just reporting a
    # small number that looks like a failure.
    skewed = pd.DataFrame({"a": ["y"] * 95 + ["n"] * 5, "b": ["y"] * 90 + ["n"] * 5 + ["y"] * 5})
    paradox = stats_engine.run_analysis(
        skewed, "cohens_kappa", {"row_column": "a", "column_column": "b"}
    )
    check(
        paradox["estimate"]["observed_agreement"] > paradox["estimate"]["kappa"],
        "high agreement with a low kappa is the prevalence effect",
    )
    check(
        any("paradox" in warning for warning in paradox["warnings"]),
        "and the output names it instead of leaving the reader to guess",
    )

    # --- Fleiss' kappa -----------------------------------------------------
    # Six subject patterns repeated: two unanimous and four split 2-1, giving
    # per-subject agreement (1 + 1 + 4*(2/6)) / 6 = 0.5556.
    patterns = [[1, 1, 1], [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 1], [1, 0, 1]] * 10
    ratings = pd.DataFrame(
        [{"r1": t[0], "r2": t[1], "r3": t[2]} for t in patterns]
    )
    fleiss = stats_engine.run_analysis(
        ratings, "fleiss_kappa", {"columns": ["r1", "r2", "r3"]}
    )
    check(
        close(fleiss["estimate"]["observed_agreement"], 5.0 / 9.0, 1e-6),
        f"Fleiss' observed agreement is 0.5556 (got {fleiss['estimate']['observed_agreement']})",
    )
    check(
        fleiss["sample_size"] == 60,
        "and all 60 subjects take part",
    )

    # --- ICC ---------------------------------------------------------------
    perfect_icc = stats_engine.run_analysis(
        pd.DataFrame({"t1": list(range(1, 11)), "t2": list(range(1, 11))}),
        "icc",
        {"columns": ["t1", "t2"]},
    )
    check(
        close(perfect_icc["estimate"]["icc_single"], 1.0, 1e-9),
        "identical ratings give an ICC of 1",
    )
    check(
        perfect_icc["estimate"]["f_statistic"] is None,
        "and the F test is marked not applicable rather than reported as a number",
    )
    truth = rng.normal(0, 1, 200)
    noisy = np.column_stack([truth + rng.normal(0, 1, 200) for _ in range(2)])
    icc = stats_engine.run_analysis(
        pd.DataFrame(noisy, columns=["a", "b"]), "icc", {"columns": ["a", "b"]}
    )
    # True ICC = 1/(1+1) = 0.5 for a single rater; the mean of two is 2/3.
    check(
        abs(icc["estimate"]["icc_single"] - 0.5) < 0.05,
        f"the single-rater ICC matches its 0.5 (got {icc['estimate']['icc_single']})",
    )
    check(
        abs(icc["estimate"]["icc_average_of_k"] - 2.0 / 3.0) < 0.05,
        f"and the two-rater average matches 0.667 (got {icc['estimate']['icc_average_of_k']})",
    )
    check(
        icc["estimate"]["icc_average_of_k"] > icc["estimate"]["icc_single"],
        "the averaged reliability is the larger of the two, as it must be",
    )
    check(
        icc["estimate"]["confidence_interval"] is None,
        "no confidence interval is quoted rather than a wrong one",
    )
    raises_analysis_error(
        pd.DataFrame({"a": [1, 2, 3, 4, 5]}), "icc", {"columns": ["a"]},
        "a single column is refused: the ICC needs at least two ratings",
    )



def test_join_clean_and_analyse() -> None:
    print("\n15) Merge, append, drop columns, and analysing the result")
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={
                "email": "prepare@test.local",
                "password": "PrepareTest123!",
                "full_name": "Prepare Tester",
            },
        )
        token = client.post(
            "/api/auth/login",
            json={"email": "prepare@test.local", "password": "PrepareTest123!"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        def upload(name: str, csv_text: str) -> int:
            response = client.post(
                "/api/datasets/upload",
                files={"file": (name, csv_text.encode("utf-8"), "text/csv")},
                headers=headers,
            )
            check(response.status_code == 201, f"{name} uploads")
            return int(response.json()["dataset_id"])

        # Two household files that overlap on the holding id: one holds the
        # yield, the other the region. The merge is what makes the yield
        # analysable against a region.
        yields_csv = (
            "Holding ID,Maize Harvest (kg)\n1,10\n2,20\n3,30\n4,40\n"
        )
        regions_csv = "Holding ID,Region\n2,B\n3,C\n4,D\n5,E\n"
        left_id = upload("yields.csv", yields_csv)
        right_id = upload("regions.csv", regions_csv)

        # The catalogue has to advertise which operations need a second dataset,
        # or the UI renders a form with no way to pick one.
        catalog = client.get(
            "/api/v1/datasets/operations/catalog", headers=headers
        ).json()
        by_type = {row["type"]: row for row in catalog}
        check("merge" in by_type and "append" in by_type, "merge and append are in the catalogue")
        check("drop_columns" in by_type, "and so is removing a column")
        check(
            by_type["merge"].get("needs_other_dataset") is True,
            "the catalogue says merge needs a second dataset",
        )
        check(
            by_type["drop_columns"].get("needs_other_dataset") is False,
            "and that drop_columns does not",
        )

        # --- merge on the shared key ---------------------------------------
        merged = client.post(
            f"/api/v1/datasets/{left_id}/join",
            json={
                "operation_type": "merge",
                "other_dataset_id": right_id,
                "configuration": {
                    "left_on": ["Holding ID"],
                    "right_on": ["Holding ID"],
                    "how": "left",
                },
            },
            headers=headers,
        )
        check(merged.status_code == 200, f"the merge succeeds (got {merged.status_code})")
        body = merged.json()
        check(body["row_count"] == 4, f"a left join keeps all 4 households (got {body['row_count']})")
        check(body["column_count"] == 3, f"and adds the region column (got {body['column_count']})")
        check(
            body["summary"]["rows_after"] == 4,
            "the summary reports the resulting row count, not just the version id",
        )
        new_version = body["version"]

        # The original must be untouched: that is the promise of versions.
        original = client.get(
            f"/api/v1/datasets/{left_id}/versions/1", headers=headers
        ).json()["version"]
        check(
            original["row_count"] == 4 and original["column_count"] == 2,
            f"version 1 still has its original shape after the merge "
            f"({original['row_count']}x{original['column_count']})",
        )

        # A join with itself is refused rather than producing a cartesian blow-up.
        selfjoin = client.post(
            f"/api/v1/datasets/{left_id}/join",
            json={
                "operation_type": "merge",
                "other_dataset_id": left_id,
                "configuration": {"left_on": ["Holding ID"]},
            },
            headers=headers,
        )
        check(selfjoin.status_code == 400, "merging a dataset with itself is refused")

        bad_key = client.post(
            f"/api/v1/datasets/{left_id}/join",
            json={
                "operation_type": "merge",
                "other_dataset_id": right_id,
                "configuration": {"left_on": ["No Such Column"]},
            },
            headers=headers,
        )
        check(bad_key.status_code == 400, "an unknown key column is refused")

        # --- drop a column, then analyse the cleaned version ----------------
        dropped = client.post(
            f"/api/v1/datasets/{left_id}/transform",
            json={
                "operation_type": "drop_columns",
                "dataset_version": new_version,
                "configuration": {"columns": ["Region"]},
            },
            headers=headers,
        )
        check(dropped.status_code == 200, "a column can be removed")
        check(
            dropped.json()["column_count"] == 2,
            f"and the new version has one column fewer (got {dropped.json()['column_count']})",
        )
        cleaned_version = dropped.json()["version"]

        # This is the point of the whole feature: the cleaned data is what the
        # analysis engine reads.
        analysis = client.post(
            f"/api/v1/datasets/{left_id}/analysis",
            json={
                "analysis_type": "descriptive",
                "dataset_version": cleaned_version,
                "parameters": {"columns": ["Maize Harvest (kg)"]},
                "save": False,
            },
            headers=headers,
        )
        check(
            analysis.status_code == 200,
            f"the cleaned version can be analysed (got {analysis.status_code})",
        )
        if analysis.status_code == 200:
            result = analysis.json()["result"]
            stats = result["estimate"]["variables"]["Maize Harvest (kg)"]
            check(
                float(stats["mean"]) == 25.0,
                f"and the analysis reads the cleaned values (mean {stats['mean']}, want 25)",
            )
            check(
                result["sample_size"] == 4,
                f"with the row count intact (got {result['sample_size']})",
            )
            check(
                "Region" not in result["estimate"]["variables"],
                "and the dropped column is really gone from the analysed data",
            )

        # The original version must still be analysable on its own terms.
        before = client.post(
            f"/api/v1/datasets/{left_id}/analysis",
            json={
                "analysis_type": "descriptive",
                "dataset_version": 1,
                "parameters": {"columns": ["Maize Harvest (kg)"]},
                "save": False,
            },
            headers=headers,
        )
        check(before.status_code == 200, "the original version still analyses")
        if before.status_code == 200:
            check(
                float(
                    before.json()["result"]["estimate"]["variables"]["Maize Harvest (kg)"]["mean"]
                ) == 25.0,
                "and reports the same mean, proving the versions are separate",
            )

        # --- append ----------------------------------------------------------
        # The extra file deliberately has a column the first one lacks, so the
        # append has to fill it with missing values rather than dropping it --
        # and has to say so.
        extra_id = upload("extra.csv", "Holding ID,Maize Harvest (kg),Irrigated\n9,50,1\n")
        appended = client.post(
            f"/api/v1/datasets/{left_id}/join",
            json={
                "operation_type": "append",
                "other_dataset_id": extra_id,
                "dataset_version": 1,
                "configuration": {},
            },
            headers=headers,
        )
        check(appended.status_code == 200, "the append succeeds")
        check(
            appended.json()["row_count"] == 5,
            f"stacking adds the rows (got {appended.json()['row_count']}, want 5)",
        )
        check(
            appended.json()["column_count"] == 3,
            f"and unions the columns rather than discarding the new one (got {appended.json()['column_count']}, want 3)",
        )
        check(
            any("Irrigated" in warning for warning in appended.json()["warnings"]),
            "and warns that the new column is missing for the original rows",
        )

        # The lineage has to record the join, or the audit trail is incomplete.
        history = client.get(
            f"/api/v1/datasets/{left_id}/operations", headers=headers
        ).json()
        types = [row["type"] for row in history["operations"]]
        check("merge" in types, "the merge is recorded in the operation history")
        check("append" in types, "and so is the append")
        check("drop_columns" in types, "and the column removal")


def test_api_surface() -> None:

    # The context manager runs the app's startup, which is what creates the
    # tables; a bare TestClient would query a database that does not exist yet.
    with TestClient(app) as client:
        assert_authenticated_endpoints(client)


def assert_authenticated_endpoints(client: TestClient) -> None:
    print("\n8) The catalogue is served over the API")
    check(
        client.get("/api/v1/analysis/methods").status_code == 401,
        "the method catalogue requires authentication",
    )

    client.post(
        "/api/auth/register",
        json={
            "email": "methods@test.local",
            "password": "MethodsTest123!",
            "full_name": "Methods Tester",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "methods@test.local", "password": "MethodsTest123!"},
    )
    check(login.status_code == 200, "a test user can sign in")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/v1/analysis/methods", headers=headers)
    check(response.status_code == 200, "GET /analysis/methods returns 200")
    payload = response.json()
    check(
        payload["counts"]["methods"] == len(methods.METHODS),
        "the endpoint reports the same method count as the module",
    )
    check(
        len(payload["methods"]) == len(methods.METHODS), "every method is serialised"
    )
    check(bool(payload["stage_plans"]), "stage plans travel with the catalogue")
    check(
        bool(payload["dv_guide"]) and bool(payload["goal_guide"]),
        "both selection tables travel with the catalogue",
    )
    check(
        all(row.get("assumptions") for row in payload["methods"]),
        "the serialised methods include their assumptions",
    )

    detail = client.get("/api/v1/analysis/methods/logistic_regression", headers=headers)
    check(detail.status_code == 200, "a single method can be fetched by key")
    check(
        len(detail.json()["stages"]) >= 7,
        "the method detail includes its stage plan",
    )
    check(
        any(stage["key"] == "assumptions" for stage in detail.json()["stages"]),
        "the logistic stage plan includes the assumptions stage",
    )

    missing = client.get("/api/v1/analysis/methods/not_a_method", headers=headers)
    check(missing.status_code == 404, "an unknown method key returns 404")

    types = client.get("/api/v1/analysis/types", headers=headers)
    check(types.status_code == 200, "the analysis-type catalog still works")
    check(
        len(types.json()) == len(stats_engine.ANALYSIS_HANDLERS),
        "the type catalog matches the number of implemented analyses",
    )


def main() -> int:
    test_catalogue()
    test_stage_plans()
    test_method_lookup()
    test_logistic_regression()
    test_poisson_regression()
    test_cronbach_alpha()
    test_kaplan_meier()
    test_second_wave()
    test_probit_and_lpm()
    test_negative_binomial()
    test_tobit_ridge_quantile()
    test_zero_inflated_and_hurdle()
    test_reliability_statistics()
    test_join_clean_and_analyse()
    test_api_surface()
    print(f"\nALL METHODS TESTS PASSED ({PASSED} checks)")
    return 0


def test_methods_catalogue() -> None:
    """pytest entry point: same run as ``python tests/methods_test.py``."""
    main()


if __name__ == "__main__":
    import contextlib
    import traceback

    log_path = Path(__file__).resolve().parent.parent / "methods_test_out.log"
    exit_code = 0
    with log_path.open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                exit_code = main()
            except Exception:  # noqa: BLE001 - report any failure to the log
                traceback.print_exc()
                exit_code = 1
                print("\nMETHODS TEST FAILED")

    output = log_path.read_text(encoding="utf-8").splitlines()
    print("\n".join(output[-45:]))
    sys.exit(exit_code)




