"""MVP-20: Statistical Recommendation & Validation engine.

Turns "what am I looking at?" into "what should I run, and is it safe to run?".

    variables -> semantic types -> candidate methods -> diagnostics
              -> statistical recommendation -> (optional) analysis engine

The engine never hides assumptions: normality / outlier flags are *evidence* and
warnings, never a silent decision (documented requirement of MVP-20).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.statflow import methods, stats_engine
from app.services.data_service import looks_like_dates, to_jsonable

SEMANTIC_NUMERIC = "numeric"
SEMANTIC_CATEGORICAL = "categorical"
SEMANTIC_BOOLEAN = "boolean"
SEMANTIC_DATETIME = "datetime"
SEMANTIC_TEXT = "text"


class PlanningError(ValueError):
    """Invalid planning request (mapped to HTTP 400)."""


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def semantic_type(series: pd.Series) -> str:
    """Classify a column into numeric | categorical | boolean | datetime | text."""
    non_null = series.dropna()
    if non_null.empty:
        return SEMANTIC_TEXT

    if pd.api.types.is_bool_dtype(series):
        return SEMANTIC_BOOLEAN
    if pd.api.types.is_numeric_dtype(series):
        return SEMANTIC_NUMERIC
    if pd.api.types.is_datetime64_any_dtype(series):
        return SEMANTIC_DATETIME

    converted = pd.to_numeric(non_null, errors="coerce")
    if converted.notna().mean() == 1.0:
        return SEMANTIC_NUMERIC

    text = non_null.astype(str).str.strip()
    lowered = text.str.lower()
    boolean_like = {"true", "false", "yes", "no", "0", "1", "ndiyo", "hapana"}
    if set(lowered.unique()) <= boolean_like:
        return SEMANTIC_BOOLEAN

    if text.str.len().max() <= 32 and looks_like_dates(non_null, threshold=0.9):
        return SEMANTIC_DATETIME

    unique = int(non_null.nunique())
    if unique <= max(20, int(non_null.size * 0.05)):
        return SEMANTIC_CATEGORICAL
    return SEMANTIC_TEXT


def describe_variable(frame: pd.DataFrame, column: str) -> Dict[str, Any]:
    """Missing %, unique count, sample size and characteristics of one variable."""
    series = frame[column]
    sample_size = int(series.shape[0])
    missing = int(series.isna().sum())
    non_null = series.dropna()
    kind = semantic_type(series)

    description: Dict[str, Any] = {
        "name": str(column),
        "semantic_type": kind,
        "pandas_dtype": str(series.dtype),
        "sample_size": sample_size,
        "non_missing": int(non_null.size),
        "missing_count": missing,
        "missing_percentage": round(missing / sample_size * 100, 2)
        if sample_size
        else 0.0,
        "unique_count": int(non_null.nunique()),
    }

    if kind == SEMANTIC_NUMERIC:
        values = pd.to_numeric(non_null, errors="coerce").dropna().to_numpy(dtype=float)
        stats = stats_engine.descriptives(values)
        description["characteristics"] = {
            "mean": stats.get("mean"),
            "sd": stats.get("sd"),
            "skewness": stats.get("skewness"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "distinct_values": int(len(np.unique(values))),
            "is_binary_like": bool(len(np.unique(values)) == 2),
            "normality": stats_engine.normality_diagnostics(values),
            "outliers": stats_engine.outlier_diagnostics(values),
        }
    else:
        counts = non_null.astype(str).value_counts()
        description["characteristics"] = {
            "levels": [str(value) for value in counts.index[:10]],
            "level_count": int(counts.shape[0]),
            "top_category": str(counts.index[0]) if not counts.empty else None,
            "top_percentage": round(float(counts.iloc[0]) / float(non_null.size) * 100, 2)
            if non_null.size and not counts.empty
            else None,
            "is_binary": bool(counts.shape[0] == 2),
            "rare_levels_below_5_percent": int(
                np.sum(counts / max(int(non_null.size), 1) < 0.05)
            ),
        }
    # The distinct values of a low-cardinality column, promoted to the top level.
    #
    # The studio needs these so a "type the value" field can become a select:
    # the positive class of a binary target, the event value, the two levels a
    # 0/1 column really has. Without them the only way to pick one is to type
    # it exactly right, and a wrong guess fails deep inside the engine instead
    # of at the point of choosing. Capped so a column with thousands of
    # distinct values does not ship its whole domain to the browser.
    distinct = int(non_null.nunique())
    description["levels"] = (
        [str(value) for value in non_null.astype(str).unique()[:20]]
        if 0 < distinct <= 20
        else None
    )
    return description


def profile_dataset(
    frame: pd.DataFrame, parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Variable detection + dataset level diagnostics (POST /planning/profile)."""
    parameters = parameters or {}
    variables = [describe_variable(frame, str(column)) for column in frame.columns]

    by_type: Dict[str, List[str]] = {}
    for variable in variables:
        by_type.setdefault(variable["semantic_type"], []).append(variable["name"])

    warnings: List[str] = []
    with_missing = [variable for variable in variables if variable["missing_count"] > 0]
    if frame.shape[0] < 30:
        warnings.append(f"Only {frame.shape[0]} rows: most tests will be underpowered")
    if with_missing:
        warnings.append(
            f"{len(with_missing)} variable(s) contain missing values "
            "(clean them first for reproducible results)"
        )
    if not by_type.get(SEMANTIC_NUMERIC):
        warnings.append("No numeric variable detected: only frequency tables are possible")
    if not (
        by_type.get(SEMANTIC_CATEGORICAL)
        or by_type.get(SEMANTIC_BOOLEAN)
        or by_type.get(SEMANTIC_DATETIME)
    ):
        warnings.append(
            "No grouping/time variable detected: comparative and time analyses need "
            "at least one categorical or datetime column"
        )

    return {
        "status": "ok",
        "sample_size": int(frame.shape[0]),
        "variable_count": int(frame.shape[1]),
        "variables": variables,
        "variables_by_type": by_type,
        "dataset_diagnostics": {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
            "cells_missing_percentage": round(
                float(frame.isna().sum().sum()) / max(frame.size, 1) * 100, 2
            ),
            "complete_rows": int(frame.dropna().shape[0]),
            "duplicate_rows": int(frame.duplicated().sum()),
        },
        "warnings": warnings,
        "meta": {"parameters": to_jsonable(parameters)},
    }


# ---------------------------------------------------------- variable matching


def find_variable(
    frame: pd.DataFrame, reference: Optional[str]
) -> Optional[str]:
    """Resolve a (possibly fuzzy) variable reference to an actual column name."""
    if not reference:
        return None
    text = str(reference).strip()
    if text in frame.columns:
        return text

    normalised = normalize_name(text)
    for column in frame.columns:
        if normalize_name(column) == normalised:
            return str(column)

    candidates = [
        str(column)
        for column in frame.columns
        if normalised and normalised in normalize_name(column)
    ]
    if len(candidates) == 1:
        return candidates[0]

    tokens = [token for token in re.split(r"[^a-z0-9]+", text.lower()) if len(token) > 2]
    scored: List[tuple[int, str]] = []
    for column in frame.columns:
        column_text = normalize_name(column)
        score = sum(1 for token in tokens if token in column_text)
        if score:
            scored.append((score, str(column)))
    if scored:
        scored.sort(key=lambda item: (-item[0], len(item[1])))
        if len(scored) == 1 or scored[0][0] > scored[1][0]:
            return scored[0][1]
    return None


# ------------------------------------------------------------ candidate methods

METHOD_SPECS: Dict[str, Dict[str, Any]] = {
    "pearson": {
        "label": "Pearson correlation",
        "family": "association",
        "assumes": [
            "linear relationship",
            "roughly normal variables",
            "no extreme outliers",
        ],
        "output": "r, p-value, CI",
    },
    "spearman": {
        "label": "Spearman rank correlation",
        "family": "association",
        "assumes": ["monotonic relationship", "works for skewed or ordinal data"],
        "output": "rho, p-value",
    },
    "linear_regression": {
        "label": "Linear regression",
        "family": "prediction",
        "assumes": [
            "linear relationship",
            "independent errors",
            "constant error variance",
        ],
        "output": "R2, coefficients, SE, t, p, CI, AIC/BIC, Durbin-Watson",
    },
    "welch_t_test": {
        "label": "Welch t-test",
        "family": "comparison",
        "assumes": ["two independent groups", "roughly normal outcome (or n >= 30)"],
        "output": "mean difference, p, CI, Cohen's d",
    },
    "mann_whitney": {
        "label": "Mann-Whitney U",
        "family": "comparison",
        "assumes": ["two independent groups", "no normality requirement"],
        "output": "U, z, p, rank-biserial effect size",
    },
    "one_way_anova": {
        "label": "One-way ANOVA",
        "family": "comparison",
        "assumes": [
            "3+ independent groups",
            "roughly normal outcome",
            "equal variances",
        ],
        "output": "F, p, group means, eta squared",
    },
    "kruskal_wallis": {
        "label": "Kruskal-Wallis",
        "family": "comparison",
        "assumes": ["3+ independent groups", "no normality requirement"],
        "output": "H, p, epsilon squared",
    },
    "chi_square": {
        "label": "Chi-square test of independence",
        "family": "association",
        "assumes": ["two categorical variables", "expected counts >= 5 in most cells"],
        "output": "chi2, df, p, Cramer's V",
    },
    "fisher_exact": {
        "label": "Fisher's exact test",
        "family": "association",
        "assumes": ["two binary variables", "exact test for small samples"],
        "output": "exact p-value, odds ratio",
    },
    "descriptive": {
        "label": "Descriptive statistics",
        "family": "description",
        "assumes": ["numeric variable"],
        "output": "mean, median, SD, variance, min/max, Q1/Q3",
    },
    "frequency": {
        "label": "Frequency table",
        "family": "description",
        "assumes": ["categorical variable"],
        "output": "counts and percentages",
    },
    "time_series_trend": {
        "label": "Time-series trend",
        "family": "temporal",
        "assumes": ["datetime axis with enough time points"],
        "output": "trend over time (visualisation layer)",
    },
}


def _candidate(analysis_type: str, reason: str, priority: int) -> Dict[str, Any]:
    spec = METHOD_SPECS[analysis_type]
    return {
        "analysis_type": analysis_type,
        "label": spec["label"],
        "family": spec["family"],
        "reason": reason,
        "assumes": spec["assumes"],
        "output": spec["output"],
        "priority": priority,
    }


def candidate_methods(
    outcome_type: str,
    predictor_type: str,
    predictor_levels: int,
    *,
    outcome_levels: Optional[int] = None,
    intent: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Rules that map semantic types to statistically valid candidate methods."""
    candidates: List[Dict[str, Any]] = []
    numeric_outcome = outcome_type == SEMANTIC_NUMERIC
    categorical_outcome = outcome_type in {SEMANTIC_CATEGORICAL, SEMANTIC_BOOLEAN}
    grouping_predictor = predictor_type in {SEMANTIC_CATEGORICAL, SEMANTIC_BOOLEAN}

    if numeric_outcome and predictor_type == SEMANTIC_NUMERIC:
        candidates.append(_candidate("pearson", "Both variables are numeric", 1))
        candidates.append(
            _candidate("linear_regression", "Numeric outcome allows prediction", 2)
        )
        candidates.append(
            _candidate("spearman", "Rank based alternative for skewed data", 3)
        )
    elif numeric_outcome and grouping_predictor and predictor_levels == 2:
        candidates.append(
            _candidate("welch_t_test", "Numeric outcome compared between two groups", 1)
        )
        candidates.append(
            _candidate("mann_whitney", "Non-parametric alternative for two groups", 2)
        )
    elif numeric_outcome and grouping_predictor and predictor_levels >= 3:
        candidates.append(
            _candidate(
                "one_way_anova", f"Numeric outcome across {predictor_levels} groups", 1
            )
        )
        candidates.append(
            _candidate("kruskal_wallis", "Non-parametric alternative for 3+ groups", 2)
        )
    elif categorical_outcome and grouping_predictor:
        candidates.append(
            _candidate("chi_square", "Two categorical variables: independence test", 1)
        )
        if predictor_levels == 2 and outcome_levels == 2:
            candidates.append(
                _candidate(
                    "fisher_exact", "Exact test that stays valid when cells are small", 2
                )
            )
    elif numeric_outcome and predictor_type == SEMANTIC_DATETIME:
        candidates.append(
            _candidate("time_series_trend", "Numeric measurement over time", 1)
        )
    elif numeric_outcome:
        candidates.append(
            _candidate("descriptive", "Single numeric variable: describe it first", 1)
        )
    elif categorical_outcome:
        candidates.append(
            _candidate("frequency", "Single categorical variable: its distribution", 1)
        )

    if intent == "prediction" and predictor_type == SEMANTIC_NUMERIC:
        for candidate in candidates:
            if candidate["analysis_type"] == "linear_regression":
                candidate["priority"] = 0
    if intent == "association":
        for candidate in candidates:
            if candidate["analysis_type"] in {"pearson", "spearman"}:
                candidate["priority"] -= 1
    candidates.sort(key=lambda item: item["priority"])
    return candidates


# ---------------------------------------------------------------- diagnostics


def _issue(severity: str, message: str, variable: Optional[str] = None) -> Dict[str, Any]:
    return {"severity": severity, "message": message, "variable": variable}


def pair_diagnostics(
    frame: pd.DataFrame,
    outcome: str,
    predictor: str,
    outcome_type: str,
    predictor_type: str,
) -> Dict[str, Any]:
    """Missingness, sample size, group sizes, normality, variance and outliers."""
    issues: List[Dict[str, Any]] = []
    outcome_series = frame[outcome]
    predictor_series = frame[predictor]

    outcome_missing = round(float(outcome_series.isna().mean() * 100), 2)
    predictor_missing = round(float(predictor_series.isna().mean() * 100), 2)
    if outcome_missing > 20:
        issues.append(
            _issue(
                "warning",
                f"'{outcome}' is missing in {outcome_missing}% of the rows",
                outcome,
            )
        )
    if predictor_missing > 20:
        issues.append(
            _issue(
                "warning",
                f"'{predictor}' is missing in {predictor_missing}% of the rows",
                predictor,
            )
        )

    diagnostics: Dict[str, Any] = {
        "sample_size": int(frame.shape[0]),
        "outcome_missing_percentage": outcome_missing,
        "predictor_missing_percentage": predictor_missing,
    }

    numeric_outcome = outcome_type == SEMANTIC_NUMERIC
    grouping = predictor_type in {SEMANTIC_CATEGORICAL, SEMANTIC_BOOLEAN}
    normality: Dict[str, Any] = {}

    if numeric_outcome:
        clean = (
            pd.to_numeric(outcome_series, errors="coerce").dropna().to_numpy(dtype=float)
        )
        normality = stats_engine.normality_diagnostics(clean)
        outliers = stats_engine.outlier_diagnostics(clean)
        diagnostics["outcome_descriptives"] = stats_engine.descriptives(clean)
        diagnostics["normality"] = normality
        diagnostics["outliers"] = outliers
        if normality.get("flag") == "non_normal":
            issues.append(
                _issue(
                    "info",
                    f"'{outcome}' looks non-normal (Jarque-Bera p = "
                    f"{normality.get('p_value')}): a rank based test may fit better",
                    outcome,
                )
            )
        if float(outliers.get("percentage") or 0) > 5:
            issues.append(
                _issue(
                    "info",
                    f"{outliers['count']} potential outliers in '{outcome}' (1.5*IQR)",
                    outcome,
                )
            )

    if numeric_outcome and predictor_type == SEMANTIC_NUMERIC:
        pairs = pd.DataFrame(
            {
                "x": pd.to_numeric(predictor_series, errors="coerce").to_numpy(
                    dtype=float
                ),
                "y": pd.to_numeric(outcome_series, errors="coerce").to_numpy(dtype=float),
            }
        ).dropna()
        diagnostics["complete_pairs"] = int(pairs.shape[0])
        diagnostics["predictor_descriptives"] = stats_engine.descriptives(
            pairs["x"].to_numpy(dtype=float)
        )
        diagnostics["predictor_normality"] = stats_engine.normality_diagnostics(
            pairs["x"].to_numpy(dtype=float)
        )
        if pairs.shape[0] < 30:
            issues.append(
                _issue(
                    "warning",
                    f"Only {pairs.shape[0]} complete pairs: estimates will be unstable",
                )
            )
        if (
            diagnostics["predictor_normality"].get("flag") == "non_normal"
            and normality.get("flag") == "non_normal"
        ):
            issues.append(
                _issue(
                    "info",
                    "Both variables look non-normal: Spearman is the robust choice",
                )
            )

    elif numeric_outcome and grouping:
        samples = stats_engine.group_samples(frame, predictor, outcome)
        sizes = {label: int(values.size) for label, values in samples.items()}
        diagnostics["group_sizes"] = sizes
        diagnostics["group_count"] = len(sizes)
        diagnostics["group_means"] = {
            label: stats_engine.descriptives(values).get("mean")
            for label, values in samples.items()
        }
        diagnostics["group_normality"] = {
            label: stats_engine.normality_diagnostics(values)
            for label, values in samples.items()
        }
        diagnostics["levene"] = stats_engine.levene_test(list(samples.values()))
        if sizes and min(sizes.values()) < 5:
            issues.append(
                _issue(
                    "warning",
                    "At least one group has fewer than 5 observations",
                    predictor,
                )
            )
        if sizes and max(sizes.values()) > 5 * min(sizes.values()):
            issues.append(_issue("info", "Group sizes are very unbalanced", predictor))
        if (
            diagnostics["levene"]
            and diagnostics["levene"].get("flag") == "unequal_variances"
        ):
            issues.append(
                _issue(
                    "info",
                    "Variances differ between groups (Levene p = "
                    f"{diagnostics['levene'].get('p_value')})",
                    outcome,
                )
            )
        if any(
            item.get("flag") == "non_normal"
            for item in diagnostics["group_normality"].values()
        ):
            issues.append(
                _issue(
                    "info",
                    "At least one group looks non-normal: a rank based test is safer",
                    outcome,
                )
            )
    elif outcome_type in {SEMANTIC_CATEGORICAL, SEMANTIC_BOOLEAN} and grouping:
        table = pd.crosstab(
            frame[outcome].astype("string").fillna("<missing>"),
            frame[predictor].astype("string").fillna("<missing>"),
        )
        expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / max(
            float(table.to_numpy().sum()), 1.0
        )
        diagnostics["table_shape"] = [int(table.shape[0]), int(table.shape[1])]
        diagnostics["cells_with_expected_below_5"] = int(np.sum(expected < 5))
        if diagnostics["cells_with_expected_below_5"]:
            issues.append(
                _issue(
                    "info",
                    f"{diagnostics['cells_with_expected_below_5']} cell(s) have an "
                    "expected count below 5: prefer Fisher's exact test",
                )
            )

    diagnostics["issues"] = issues
    return diagnostics


# ------------------------------------------------------------- assumptions

ASSUMPTION_PASS = "pass"
ASSUMPTION_WARN = "warn"
ASSUMPTION_FAIL = "fail"
ASSUMPTION_NA = "not_applicable"

# Only assumptions we can actually evidence from pair_diagnostics are reported.
# A check is never claimed as passing on the strength of the method's prose
# description alone, because the UI presents these as engine verdicts.
NORMALITY_SENSITIVE = {"pearson", "linear_regression", "welch_t_test", "one_way_anova"}
OUTLIER_SENSITIVE = {"pearson", "linear_regression"}
EQUAL_VARIANCE_REQUIRED = {"one_way_anova"}
GROUPED_METHODS = {"welch_t_test", "mann_whitney", "one_way_anova", "kruskal_wallis"}


def _check(
    name: str,
    status: str,
    detail: str,
    evidence: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if evidence:
        item["evidence"] = evidence
    return item


def assumption_checks(
    analysis_type: str, diagnostics: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Evidence-backed PASS/WARN checks for the recommended method.

    The Analysis Studio shows these next to the method, so the verdicts are
    computed here rather than in the UI: the statistical engine stays the only
    place that judges whether data satisfies an assumption.
    """
    checks: List[Dict[str, Any]] = []

    sample_size = int(diagnostics.get("sample_size") or 0)
    if sample_size < 3:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_FAIL,
                f"Only {sample_size} valid observation(s); this test needs at least 3.",
            )
        )
    elif sample_size < 30:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_WARN,
                f"{sample_size} observations: estimates will be unstable below 30.",
            )
        )
    else:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_PASS,
                f"{sample_size} observations is enough for a stable estimate.",
            )
        )

    missing = max(
        float(diagnostics.get("outcome_missing_percentage") or 0.0),
        float(diagnostics.get("predictor_missing_percentage") or 0.0),
    )
    if missing > 20:
        checks.append(
            _check(
                "Missing values",
                ASSUMPTION_WARN,
                f"{missing}% of rows are missing in at least one variable.",
            )
        )
    else:
        checks.append(
            _check(
                "Missing values",
                ASSUMPTION_PASS,
                f"At most {missing}% missing, so the analysed subset stays representative.",
            )
        )

    if analysis_type in NORMALITY_SENSITIVE:
        normality = diagnostics.get("normality") or {}
        group_normality = diagnostics.get("group_normality") or {}
        failed = [
            label
            for label, item in group_normality.items()
            if item.get("flag") == "non_normal"
        ]
        if failed:
            checks.append(
                _check(
                    "Normality",
                    ASSUMPTION_WARN,
                    "At least one group looks non-normal: a rank based test is safer.",
                    ", ".join(failed),
                )
            )
        elif normality and normality.get("flag") == "non_normal":
            checks.append(
                _check(
                    "Normality",
                    ASSUMPTION_WARN,
                    "The outcome looks non-normal: a rank based test may fit better.",
                    f"Jarque-Bera p = {normality.get('p_value')}",
                )
            )
        elif normality:
            checks.append(
                _check(
                    "Normality",
                    ASSUMPTION_PASS,
                    "The outcome is consistent with a normal distribution.",
                    f"Jarque-Bera p = {normality.get('p_value')}",
                )
            )
        else:
            checks.append(
                _check(
                    "Normality",
                    ASSUMPTION_NA,
                    "This test does not assume a normal outcome.",
                )
            )
    else:
        checks.append(
            _check(
                "Normality",
                ASSUMPTION_NA,
                "This method does not require a normal outcome.",
            )
        )

    if analysis_type in OUTLIER_SENSITIVE:
        outliers = diagnostics.get("outliers") or {}
        count = int(outliers.get("count") or 0)
        percentage = float(outliers.get("percentage") or 0.0)
        if percentage > 5:
            checks.append(
                _check(
                    "Outliers",
                    ASSUMPTION_WARN,
                    f"{count} potential outliers ({percentage}%) may distort the result.",
                    "1.5 x IQR rule",
                )
            )
        else:
            checks.append(
                _check(
                    "Outliers",
                    ASSUMPTION_PASS,
                    f"Only {count} potential outlier(s) ({percentage}%).",
                    "1.5 x IQR rule",
                )
            )
    else:
        checks.append(
            _check(
                "Outliers",
                ASSUMPTION_NA,
                "This method is not sensitive to extreme values.",
            )
        )

    if analysis_type in EQUAL_VARIANCE_REQUIRED:
        levene = diagnostics.get("levene") or {}
        if levene.get("flag") == "unequal_variances":
            checks.append(
                _check(
                    "Equal variance",
                    ASSUMPTION_WARN,
                    "Group variances differ; Welch's t-test is the safe alternative.",
                    f"Levene p = {levene.get('p_value')}",
                )
            )
        else:
            checks.append(
                _check(
                    "Equal variance",
                    ASSUMPTION_PASS,
                    "Group variances look comparable.",
                    f"Levene p = {levene.get('p_value')}",
                )
            )
    elif analysis_type == "welch_t_test":
        checks.append(
            _check(
                "Equal variance",
                ASSUMPTION_NA,
                "Welch's t-test does not assume equal variances.",
            )
        )
    else:
        checks.append(
            _check(
                "Equal variance",
                ASSUMPTION_NA,
                "This comparison does not rest on equal group variances.",
            )
        )

    if analysis_type in GROUPED_METHODS and diagnostics.get("group_sizes"):
        sizes = diagnostics["group_sizes"]
        smallest = min(sizes.values())
        if smallest < 5:
            checks.append(
                _check(
                    "Group sizes",
                    ASSUMPTION_FAIL,
                    f"The smallest group has only {smallest} observation(s); at least 5 are needed.",
                    ", ".join(f"{label}: {size}" for label, size in sizes.items()),
                )
            )
        else:
            checks.append(
                _check(
                    "Group sizes",
                    ASSUMPTION_PASS,
                    f"All {len(sizes)} groups have at least {smallest} observations.",
                )
            )

    if analysis_type == "chi_square":
        below = int(diagnostics.get("cells_with_expected_below_5") or 0)
        if below:
            checks.append(
                _check(
                    "Expected counts",
                    ASSUMPTION_WARN,
                    f"{below} cell(s) have an expected count below 5: prefer Fisher's exact test.",
                )
            )
        else:
            checks.append(
                _check(
                    "Expected counts",
                    ASSUMPTION_PASS,
                    "Every cell has an expected count of at least 5.",
                )
            )
    elif analysis_type == "fisher_exact":
        checks.append(
            _check(
                "Expected counts",
                ASSUMPTION_NA,
                "An exact test needs no minimum expected count.",
            )
        )

    return checks


# ------------------------------------------------- interpretation, in plain language

# Family-level guidance on what a result does and does not license.
#
# The "does not mean" row is the one that earns its place: every one of these is
# the mistake a non-specialist reader actually makes, and the engine is the only
# part of the product positioned to catch it.
_FAMILY_GUIDANCE: Dict[str, Dict[str, str]] = {
    "description": {
        "claim": "Huu ni muhtasari wa data uliyo nazo, si jaribio dhidi ya hypothesis.",
        "does_not_mean": "Haiwezi kukwambia kama tofauti ni ya kweli au ya bahati — haipimi kitu chochote dhidi ya wastani wa jamii.",
    },
    "comparison": {
        "claim": "Makundi yanalinganishwa kwa wastani/mgawanyo, na p inaonyesha ikiwa tofauti inaweza kutokea kwa bahati.",
        "does_not_mean": "p kubwa haimaanishi makundi ni sawa kabisa — inaweza kuwa sample ni ndogo.",
    },
    "association": {
        "claim": "Inapima nguvu na mwelekeo wa uhusiano kati ya vigezo viwili.",
        "does_not_mean": "Uhusiano si ushahidi wa sababu. Kigezo cha tatu kinaweza kusababisha vyote viwili.",
    },
    "regression": {
        "claim": "Inaonyesha jinsi Y inavyobadilika X ikibadilika, ukidhibiti vigezo vingine.",
        "does_not_mean": "Kurahisisha: coefficients ni uhusiano, si athari ya kisababu, isipokuwa muundo wa data unaiwezesha.",
    },
    "ml": {
        "claim": "Model inayoweza kutabiri, na usahihi wake unaonyeshwa kama confusion matrix au metrics.",
        "does_not_mean": "Usahihi kwenye data ya mafunzo si usahihi wa dunia halisi. Hakikishi accuracy inatumia data isiyofunzwa.",
    },
    "timeseries": {
        "claim": "Inaonyesha mwenendo na mizunguko kwa wakati, na inaweza kutabiri siku zijazo.",
        "does_not_mean": "Mwenendo wa zamani haudumu mile mile. Mabadiliko ya muktadha yanaweza kuuvunja.",
    },
    "survey": {
        "claim": "Matokeo yana uzito wa sampuli, kwa hiyo yanawakilishia watu wengi kuliko waliokubalika kujibu.",
        "does_not_mean": "Uzito haukosei upendeleo wa kuchagua — watu waliokataa kujibu wanaweza kutofautiana.",
    },
    "bayesian": {
        "claim": "Inatoa uwezekano wa moja kwa moja, ukiwezesha maarifa yako ya awali kuingizwa.",
        "does_not_mean": "Hakuna orthogonal 'p-value' hapa — credits ni uwezekano, si kiwango cha mkasa.",
    },
    "causal": {
        "claim": "Inajaribu kutenga athari ya kisababu, si uhusiano tu.",
        "does_not_mean": "Matokeo yanategemea sana dhana za utambulisho zilizowekwa. Hali mbaya ya uainishaji inaweza kupindua kila kitu.",
    },
    "survival": {
        "claim": "Inapima muda hadi tukio, ikiruhusu data iliyokatwa (censored).",
        "does_not_mean": "Kiwango cha hatari kinadumu daima — kinaweza kubadilika kwa wakati au kwa watu.",
    },
    "panel": {
        "claim": "Inazingatia watu/muda, ikitenga mabadiliko yaliyojumuisha kutoka yaliyo binafsi.",
        "does_not_mean": "Inahitaji data ya mara kwa mara kwa watu wale wale; watu walioingia/kuondoka wanaweza kupunguza nguvu.",
    },
    "multivariate": {
        "claim": "Inachunguza vigezo vingi kwa pamoja, ikizingatia kwamba vinahusiana.",
        "does_not_mean": "Muundo uliopatikana si sababu — ni mpangilio wa kiasa unaofaa kuitikia.",
    },
    "mixed": {
        "claim": "Inachanganya mifano tofauti au vigezo vya aina mseto, kwa hiyo muundo unahitaji kuchaguliwa kwa bidii.",
        "does_not_mean": "Mchanganyiko usioeleweka unaweza kuficha tofauti halisi au kuunda zisizokuwa.",
    },
    "clustering": {
        "claim": "Inagawa vitu vinavyofanana, bila kuwapa maana.",
        "does_not_mean": "Makundi ni yaliyopatikana, si yaliyo halisi. Majina yanapaswa kuwekwa na binadamu.",
    },
    "efficiency": {
        "claim": "Inapima uwezo wa kitu kufanya kazi, mara nyingi kwa kulinganisha njia mbalimbali.",
        "does_not_mean": "Ufanisi hausemi juu ya uadilifu — kitu chenye ufanisi mkubwa kinaweza kuwa cha udanganyifu.",
    },
    "reliability": {
        "claim": "Inapima uthabiti wa kipimo, la sivyo inaweza kurudiwa.",
        "does_not_mean": "Uthabiti si uhalali — kitu kinaweza kupima kikomo kwa uthabiti bila kupima kile kinachotakiwa.",
    },
    "spatial": {
        "claim": "Inaonyesha pembejeo za kijiografia na mifumo ya eneo.",
        "does_not_mean": "Uhusiano wa eneo si uhusiano wa watu — unaweza kuwa mgawanyo wa kiuchumi.",
    },
    "nlp": {
        "claim": "Inavyo maandishi yenye mpangilio wa kiasa, ikiruhusu kuhesabu mada na hisia.",
        "does_not_mean": "Mikakati ya lugha inaweza kukosa mazingatio, kwa hiyo hakiki mifano kwa mkono.",
    },
    "qualitative": {
        "claim": "Inatoa mpangilio wa mifano iliyochaguliwa kwa ajili ya kuelewa, si kwa ajili ya kupima.",
        "does_not_mean": "Si sampuli ya kuwakilisha — mifano haipaswi kuchukuliwa kama asilimia.",
    },
}

# A generic fallback for families not named above.
_FAMILY_GUIDANCE_DEFAULT = {
    "claim": "Matokeo haya yamehesabiwa na engine kwa njia iliyowekwa kwa method hii.",
    "does_not_mean": "Hakikishi mbinu inafaa data yako kabla ya kuitumia kwa maamuzi makubwa.",
}


def interpret_result(
    analysis_type: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Plain-language reading of a completed analysis, in the reader's own terms.

    Every sentence is derived from the numbers that are actually on screen, and
    the family-level guidance says which inferential licence the method does and
    does not grant -- the mistake a non-specialist makes is nearly always one of
    those two, not arithmetic.

    ``next_steps`` is deliberate: guidance that only says "be careful" leaves the
    reader nowhere to go. Each step is something they can act on from the result
    in front of them.
    """
    guidance = _FAMILY_GUIDANCE.get(
        _family_for(analysis_type), _FAMILY_GUIDANCE_DEFAULT
    )

    sentences: List[str] = [guidance["claim"]]

    test = result.get("test") or {}
    p_value = test.get("p_value") if isinstance(test, dict) else None
    significant = test.get("significant") if isinstance(test, dict) else None
    if significant is True:
        sentences.append(
            "Tofauti au uhusiano huonekana ni wa kweli kwenye data hii, si bahati tu "
            "(kwa kiwango cha uhakika kilichowekwa)."
        )
    elif significant is False:
        sentences.append(
            "Hatuna ushahidi wa kutosha kusema tofauti au uhusiano upo. Hii inaweza "
            "kumaanisha hakuna tofauti, au kwamba sample ni ndogo kuisadia."
        )
    elif p_value is None:
        sentences.append(
            "Method hii haitoi p-value, kwa hiyo usome makadirio na vipimo vya "
            "uhakika badala yake."
        )

    effect = result.get("effect_size") or {}
    effect_value = (
        effect.get("value")
        if isinstance(effect, dict) and effect.get("value") is not None
        else None
    )
    if effect_value is not None:
        band = effect.get("interpretation") if isinstance(effect, dict) else None
        sentences.append(
            f"Ukubwa wa athari ni {effect_value!r}"
            + (f" — {band}" if band else "")
            + ". Huu ndio uzito wa matokeo katika ulimwengu halisi, tofauti na p-value."
        )

    ci = result.get("confidence_interval") or {}
    if isinstance(ci, dict) and ci.get("lower") is not None and ci.get("upper") is not None:
        level = int(round(float(ci.get("level") or 0.95) * 100))
        sentences.append(
            f"Kwa kiwango cha {level}%, thamani halisi inaweza kuwa kati ya "
            f"{ci.get('lower')} na {ci.get('upper')}."
        )

    sample_size = result.get("sample_size")
    if isinstance(sample_size, int) and sample_size < 30:
        sentences.append(
            f"Sample ni ndogo (n = {sample_size}): chukulia matokeo haya kama ya "
            "kuchunguza, si ya kuthibitisha."
        )

    warnings = result.get("warnings") or []
    if warnings:
        sentences.append(
            f"Engine imetoa tahadhari {len(warnings)} kuhusu data hii; ziko kwenye "
            "ukurasa wa matokeo."
        )

    checks = result.get("assumption_checks") or []
    failing = [c for c in checks if isinstance(c, dict) and c.get("status") == "fail"]
    if failing:
        sentences.append(
            f"Vigezo {len(failing)} vya method havipotikani na data hii, kwa hiyo "
            "matokeo yanapaswa kusomwa kwa tahadhari."
        )

    limitations: List[str] = [guidance["does_not_mean"]]
    for name in _assumptions_for(analysis_type):
        limitations.append(f"Unapaswa kuthibitisha: {name}.")

    next_steps: List[str] = []
    if failing:
        alternatives = _alternatives_for(analysis_type)
        if alternatives:
            names = ", ".join(alternatives)
            next_steps.append(f"Jaribu njia mbadala inayostahili: {names}.")
        next_steps.append(
            "Safisha data (ondoa missing/outliers) auongeza sample, kisha rudia."
        )
    if significant is False and sample_size is not None and sample_size < 30:
        next_steps.append(
            "Ongeza data kabla ya kuhitimisha — p kubwa kwa sample ndogo si ushahidi wa kutokuwepo."
        )
    if analysis_type in ("descriptive", "frequency"):
        next_steps.append(
            "Endelea kwenye uchambuzi unaolingana (mfano t-test, ANOVA, regression) baada ya kuelezea data."
        )
    if not next_steps:
        next_steps.append(
            "Hamisha matokeo kwenye ripoti, kisha jadili na watu wanaohusika."
        )

    return {
        "summary": " ".join(sentences),
        "meaning": guidance["claim"],
        "does_not_mean": guidance["does_not_mean"],
        "limitations": limitations,
        "next_steps": next_steps,
        "evidence": _evidence_for(result),
    }


def _family_for(analysis_type: str) -> str:
    found = methods.method(_method_key_for(analysis_type))
    return str((found or {}).get("family") or "other")


def _method_key_for(analysis_type: str) -> str:
    """The catalogue key whose ``engine`` is this analysis type."""
    for key in methods.engine_keys():
        record = methods.method(key)
        if record and record.get("engine") == analysis_type:
            return key
    return analysis_type


def _assumptions_for(analysis_type: str) -> List[str]:
    found = methods.method(_method_key_for(analysis_type))
    if not found:
        return []
    items = found.get("assumptions") or []
    return [str(item) for item in items if "hakuna" not in str(item).lower()]


def _alternatives_for(analysis_type: str) -> List[str]:
    found = methods.method(_method_key_for(analysis_type))
    if not found:
        return []
    keys = [str(item) for item in (found.get("alternatives") or [])]
    labels = []
    for key in keys:
        record = methods.method(key)
        if record:
            labels.append(str(record.get("label_sw") or record.get("label") or key))
    return labels


def _evidence_for(result: Dict[str, Any]) -> List[str]:
    """Every number the interpretation leans on, so a reader can check it.

    Deduplicated against the effect size: a correlation's test method already
    reads "Pearson r", so repeating it under the effect-size row would list the
    same number twice and imply two pieces of evidence.
    """
    evidence: List[str] = []
    if result.get("sample_size") is not None:
        evidence.append(f"n = {result['sample_size']}")
    test = result.get("test") or {}
    effect = result.get("effect_size") or {}
    effect_name = effect.get("name") if isinstance(effect, dict) else None
    if isinstance(test, dict):
        if test.get("statistic") is not None:
            evidence.append(f"{test.get('method') or 'statistic'} = {test.get('statistic')}")
        if test.get("p_value") is not None:
            evidence.append(f"p = {test.get('p_value')}")
    if isinstance(effect, dict) and effect.get("value") is not None:
        label = effect_name or "effect"
        # The test row already carries this number when the names coincide.
        if not any(f"= {effect.get('value')}" in item for item in evidence):
            evidence.append(f"{label} = {effect.get('value')}")
    ci = result.get("confidence_interval") or {}
    if isinstance(ci, dict) and ci.get("lower") is not None:
        evidence.append(f"CI = [{ci.get('lower')}, {ci.get('upper')}]")
    return evidence


# ------------------------------------------------- assumptions, for a direct run

# A shared vocabulary of the hypotheses each statistic rests on, used by methods
# that arrive without a recommendation alongside them.
#
# The recommendation path already has checks, because it passes through
# `pair_diagnostics`. A direct run does not: `run_analysis` dispatches to a
# handler and never sees which columns the reader chose, so its result carries
# warnings but no verdict on whether the data meets the method's assumptions.

def analysis_assumption_checks(
    analysis_type: str, frame: pd.DataFrame, columns: List[str]
) -> List[Dict[str, Any]]:
    """Evidence-backed assumption checks for an analysis the reader configured by hand.

    The recommendation path already carries checks, because it passes through
    `pair_diagnostics`. A direct run does not: `run_analysis` is dispatched to a
    handler and never sees which columns the reader chose, so a result produced
    this way has a warnings list but no verdict on whether the data meets the
    method's assumptions -- the one thing the whole engine is arranged to report.

    Rather than thread a column contract through every handler, this reads the
    columns back out of the parameters the reader actually sent, and reuses the
    same primitives the recommendation path uses. It only reports what it can
    evidence from the data, so the verdicts mean the same thing either way.

    `columns` is the list of columns the analysis actually consumed, in frame
    order; it is never empty when the analysis ran on something.
    """
    checks: List[Dict[str, Any]] = []
    sample_size = int(frame.shape[0])

    if sample_size < 3:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_FAIL,
                f"Only {sample_size} valid observation(s); this test needs at least 3.",
            )
        )
    elif sample_size < 30:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_WARN,
                f"{sample_size} observations: estimates will be unstable below 30.",
            )
        )
    else:
        checks.append(
            _check(
                "Sample size",
                ASSUMPTION_PASS,
                f"{sample_size} observations is enough for a stable estimate.",
            )
        )

    # Missingness across the columns the analysis actually read. Reading a column
    # the analysis did not use would report a warning the reader cannot act on.
    used = [column for column in columns if column in frame.columns]
    if not used:
        return checks
    missing = max(
        float(frame[column].isna().mean() * 100) for column in used
    )
    worst = max(used, key=lambda column: float(frame[column].isna().mean()))
    if missing > 20:
        checks.append(
            _check(
                "Missing values",
                ASSUMPTION_WARN,
                f"'{worst}' is missing in {missing}% of the rows, so the analysed subset is smaller than the dataset.",
            )
        )
    else:
        checks.append(
            _check(
                "Missing values",
                ASSUMPTION_PASS,
                f"At most {missing}% missing, so the analysed subset stays representative.",
            )
        )

    if analysis_type not in NORMALITY_SENSITIVE:
        checks.append(
            _check(
                "Normality",
                ASSUMPTION_NA,
                "This method does not require a normal outcome.",
            )
        )
        return checks

    numerics = [
        column
        for column in used
        if semantic_type(frame[column]) == SEMANTIC_NUMERIC
    ]
    if not numerics:
        checks.append(
            _check(
                "Normality",
                ASSUMPTION_NA,
                "No numeric column in this analysis, so there is no distribution to check.",
            )
        )
        return checks

    # The outcome is the numeric column; with several, the first is representative
    # and saying so is more honest than silently checking only one of them.
    outcome = numerics[0]
    where = "" if len(numerics) == 1 else f" (checking '{outcome}')"
    clean = pd.to_numeric(frame[outcome], errors="coerce").dropna()
    normality = stats_engine.normality_diagnostics(clean.to_numpy(dtype=float))
    if normality.get("flag") == "non_normal":
        checks.append(
            _check(
                "Normality",
                ASSUMPTION_WARN,
                f"The outcome looks non-normal{where}: a rank based test may fit better.",
                f"Jarque-Bera p = {normality.get('p_value')}",
            )
        )
    else:
        checks.append(
            _check(
                "Normality",
                ASSUMPTION_PASS,
                f"The outcome is consistent with a normal distribution{where}.",
                f"Jarque-Bera p = {normality.get('p_value')}",
            )
        )

    if analysis_type not in GROUPED_METHODS:
        return checks

    # A grouped comparison: the group is the categorical column among those used.
    groups = [
        column
        for column in used
        if semantic_type(frame[column])
        in {SEMANTIC_CATEGORICAL, SEMANTIC_BOOLEAN}
    ]
    if not groups:
        checks.append(
            _check(
                "Group sizes",
                ASSUMPTION_NA,
                "No grouping column in this analysis, so there are no groups to size.",
            )
        )
        return checks

    grouping = groups[0]
    samples = stats_engine.group_samples(
        frame, grouping, outcome
    )
    sizes = {label: int(values.size) for label, values in samples.items()}
    smallest = min(sizes.values()) if sizes else 0
    if smallest < 5:
        checks.append(
            _check(
                "Group sizes",
                ASSUMPTION_FAIL,
                f"The smallest group of '{grouping}' has only {smallest} observation(s); at least 5 are needed.",
                ", ".join(f"{label}: {size}" for label, size in sizes.items()),
            )
        )
    else:
        checks.append(
            _check(
                "Group sizes",
                ASSUMPTION_PASS,
                f"All {len(sizes)} groups of '{grouping}' have at least {smallest} observations.",
            )
        )

    if analysis_type in EQUAL_VARIANCE_REQUIRED and sizes:
        levene = stats_engine.levene_test(list(samples.values()))
        flag = (levene or {}).get("flag")
        if flag == "unequal_variances":
            checks.append(
                _check(
                    "Equal variance",
                    ASSUMPTION_WARN,
                    f"Variances differ between groups of '{grouping}': Welch's ANOVA is the safer choice.",
                    f"Levene p = {levene.get('p_value')}",
                )
            )
        else:
            checks.append(
                _check(
                    "Equal variance",
                    ASSUMPTION_PASS,
                    f"Group variances of '{grouping}' look comparable.",
                    f"Levene p = {(levene or {}).get('p_value')}",
                )
            )

    return checks


def columns_used(parameters: Dict[str, Any], frame: pd.DataFrame) -> List[str]:
    """The columns an analysis consumed, recovered from the parameters it was given.

    `run_analysis` dispatches to a handler and does not know which parameters are
    column names, so this reads them back: any parameter that names a real column
    of this frame is one the analysis read. Order follows the frame, not the
    parameters, so the same call always produces the same list.
    """
    mentioned: List[str] = []
    for value in (parameters or {}).values():
        if isinstance(value, str):
            if value in frame.columns:
                mentioned.append(value)
        elif isinstance(value, (list, tuple)):
            mentioned.extend(
                item
                for item in value
                if isinstance(item, str) and item in frame.columns
            )
    ordered = [column for column in frame.columns if column in set(mentioned)]
    return ordered


def assumption_checks_for_result(
    analysis_type: str, frame: pd.DataFrame, parameters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Assumption checks for a stored standard result.

    A thin wrapper over `analysis_assumption_checks` that resolves the columns
    first, so callers that hold a result and the parameters that produced it do
    not have to know how the two are related.
    """
    return analysis_assumption_checks(
        analysis_type, frame, columns_used(parameters, frame)
    )


ANALYSIS_PARAMETER_MAP = {
    "welch_t_test": lambda outcome, predictor: {
        "value_column": outcome,
        "group_column": predictor,
    },
    "mann_whitney": lambda outcome, predictor: {
        "value_column": outcome,
        "group_column": predictor,
    },
    "one_way_anova": lambda outcome, predictor: {
        "value_column": outcome,
        "group_column": predictor,
    },
    "kruskal_wallis": lambda outcome, predictor: {
        "value_column": outcome,
        "group_column": predictor,
    },
    "pearson": lambda outcome, predictor: {"x": predictor, "y": outcome},
    "spearman": lambda outcome, predictor: {"x": predictor, "y": outcome},
    "linear_regression": lambda outcome, predictor: {
        "target": outcome,
        "features": [predictor],
    },
    "chi_square": lambda outcome, predictor: {
        "row_column": outcome,
        "column_column": predictor,
    },
    "fisher_exact": lambda outcome, predictor: {
        "row_column": outcome,
        "column_column": predictor,
        "method": "fisher",
    },
    "descriptive": lambda outcome, predictor: {"columns": [outcome]},
    "frequency": lambda outcome, predictor: {"columns": [outcome]},
}


def analysis_parameters(
    analysis_type: str, outcome: str, predictor: Optional[str]
) -> Dict[str, Any]:
    builder = ANALYSIS_PARAMETER_MAP.get(analysis_type)
    if builder is None:
        return {}
    return builder(outcome, predictor)


def _resolve_reference(
    frame: pd.DataFrame, reference: Optional[str], label: str
) -> str:
    resolved = find_variable(frame, reference)
    if resolved is None:
        available = ", ".join(str(column) for column in frame.columns)
        raise PlanningError(
            f"Could not find the {label} variable '{reference}' in this dataset. "
            f"Available variables: {available}"
        )
    return resolved


def _pick_recommendation(
    candidates: List[Dict[str, Any]], diagnostics: Dict[str, Any]
) -> Tuple[Dict[str, Any], str]:
    """Choose the recommended method and explain why (assumption aware)."""
    if not candidates:
        raise PlanningError(
            "No statistical method matches these variable types in the MVP engine"
        )

    issues = diagnostics.get("issues") or []
    non_normal = any(
        "non-normal" in str(issue.get("message", "")) for issue in issues
    )
    small_groups = any(
        "fewer than 5" in str(issue.get("message", "")) for issue in issues
    )
    small_cells = bool(diagnostics.get("cells_with_expected_below_5"))

    alternatives = {candidate["analysis_type"]: candidate for candidate in candidates}
    preferred = candidates[0]

    if non_normal or small_groups:
        for robust in ("kruskal_wallis", "mann_whitney", "spearman", "fisher_exact"):
            if robust in alternatives:
                return (
                    alternatives[robust],
                    f"{alternatives[robust]['label']} is recommended because the "
                    "diagnostics show non-normal data or very small groups, and this "
                    "method does not rely on normality",
                )
    if (
        small_cells
        and diagnostics.get("table_shape") == [2, 2]
        and "fisher_exact" in alternatives
    ):
        return (
            alternatives["fisher_exact"],
            "Fisher's exact test is recommended because some expected cell counts are "
            "below 5",
        )
    return (
        preferred,
        f"{preferred['label']} is the best match for the detected variable types "
        f"({str(preferred['reason']).lower()})",
    )


def recommend(
    frame: pd.DataFrame, parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Semantic types -> candidates -> diagnostics -> recommendation (+ optional run)."""
    parameters = parameters or {}
    intent = (parameters.get("intent") or "").lower() or None
    if intent not in {None, "difference", "association", "prediction", "distribution"}:
        raise PlanningError(
            "intent must be one of: difference, association, prediction, distribution"
        )

    outcome_reference = (
        parameters.get("outcome")
        or parameters.get("value_column")
        or parameters.get("y")
    )
    predictor_reference = (
        parameters.get("predictor")
        or parameters.get("group_column")
        or parameters.get("variable")
        or parameters.get("x")
    )

    if not outcome_reference and predictor_reference:
        raise PlanningError(
            "Give the outcome variable too, for example {\"outcome\": \"income\", "
            "\"predictor\": \"gender\"}"
        )

    outcome = _resolve_reference(frame, outcome_reference, "outcome")
    predictor = (
        _resolve_reference(frame, predictor_reference, "predictor")
        if predictor_reference
        else None
    )
    if predictor == outcome:
        raise PlanningError("Outcome and predictor must be different variables.")

    outcome_profile = describe_variable(frame, outcome)
    outcome_type = outcome_profile["semantic_type"]
    predictor_profile = describe_variable(frame, predictor) if predictor else None
    predictor_type = predictor_profile["semantic_type"] if predictor_profile else "none"
    predictor_levels = int(predictor_profile["unique_count"]) if predictor_profile else 0

    candidates = candidate_methods(
        outcome_type,
        predictor_type,
        predictor_levels,
        outcome_levels=int(outcome_profile["unique_count"]),
        intent=intent,
    )
    diagnostics = (
        pair_diagnostics(frame, outcome, predictor, outcome_type, predictor_type)
        if predictor
        else {
            "sample_size": int(frame.shape[0]),
            "issues": [],
            "normality": outcome_profile["characteristics"].get("normality"),
            "outliers": outcome_profile["characteristics"].get("outliers"),
        }
    )

    recommended, reason = _pick_recommendation(candidates, diagnostics)
    requested_method = parameters.get("method")
    if requested_method:
        requested = str(requested_method)
        matching = next(
            (
                candidate
                for candidate in candidates
                if candidate["analysis_type"] == requested
            ),
            None,
        )
        if matching is None:
            valid = ", ".join(candidate["analysis_type"] for candidate in candidates)
            raise PlanningError(
                f"Requested method '{requested}' is not valid for these variables. "
                f"Valid methods: {valid}"
            )
        recommended = matching
        reason = (
            f"Using the requested method {recommended['label']}; the engine still "
            "reports its assumptions and the alternative candidates"
        )

    if frame.shape[0] < 3:
        validation_status = "blocked"
    elif any(
        issue["severity"] == "warning" for issue in diagnostics.get("issues", [])
    ):
        validation_status = "warning"
    else:
        validation_status = "ok"

    plan_parameters = analysis_parameters(
        recommended["analysis_type"], outcome, predictor
    )
    response: Dict[str, Any] = {
        "question": parameters.get("question"),
        "intent": intent,
        "variables": {"outcome": outcome_profile, "predictor": predictor_profile},
        "diagnostics": diagnostics,
        "candidates": candidates,
        "recommendation": {
            "analysis_type": recommended["analysis_type"],
            "label": recommended["label"],
            "family": recommended["family"],
            "parameters": plan_parameters,
            "why": reason,
            "assumptions": recommended["assumes"],
            "output": recommended["output"],
            "assumption_checks": assumption_checks(
                recommended["analysis_type"], diagnostics
            ),
            "alternatives": [
                {
                    "analysis_type": candidate["analysis_type"],
                    "label": candidate["label"],
                    "reason": candidate["reason"],
                }
                for candidate in candidates
                if candidate["analysis_type"] != recommended["analysis_type"]
            ],
        },
        "validation": {
            "status": validation_status,
            "issues": diagnostics.get("issues", []),
        },
        "meta": {"parameters": to_jsonable(parameters)},
    }

    if parameters.get("run"):
        analysis_type = recommended["analysis_type"]
        if analysis_type in stats_engine.ANALYSIS_HANDLERS:
            response["result"] = stats_engine.run_analysis(
                frame, analysis_type, plan_parameters
            )
        else:
            response["result"] = None
            response["validation"]["issues"].append(
                _issue(
                    "info",
                    f"'{recommended['label']}' belongs to the visualisation layer and "
                    "has no numeric output in the MVP engine yet",
                )
            )
    return response







