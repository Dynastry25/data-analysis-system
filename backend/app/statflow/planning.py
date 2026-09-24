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

from app.statflow import stats_engine
from app.services.data_service import to_jsonable

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

    if text.str.len().max() <= 32:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.9:
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
        if predictor_levels == 2:
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
    if small_cells and "fisher_exact" in alternatives:
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
        predictor = None

    outcome_profile = describe_variable(frame, outcome)
    outcome_type = outcome_profile["semantic_type"]
    predictor_profile = describe_variable(frame, predictor) if predictor else None
    predictor_type = predictor_profile["semantic_type"] if predictor_profile else "none"
    predictor_levels = int(predictor_profile["unique_count"]) if predictor_profile else 0

    candidates = candidate_methods(
        outcome_type, predictor_type, predictor_levels, intent=intent
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
        for candidate in candidates:
            if candidate["analysis_type"] == str(requested_method):
                recommended = candidate
                reason = (
                    f"Using the requested method {candidate['label']}; the engine still "
                    "reports its assumptions and the alternative candidates"
                )
                break

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







