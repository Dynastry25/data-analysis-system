"""MVP-19: Unified statistical analysis engine.

Every analysis returns the same *standard result* structure, so the assistant,
report generator and dashboard never have to learn a new shape per method::

    {
      "analysis_type": "welch_t_test",
      "status": "success",
      "sample_size": 158,
      "estimate": {"mean_difference": 12.4, "group_means": {...}},
      "test": {"method": "Welch t-test", "statistic": 2.41, "df": 96.3, "p_value": 0.018},
      "confidence_interval": {"level": 0.95, "lower": 2.1, "upper": 22.7},
      "effect_size": {"name": "cohens_d", "value": 0.38, "interpretation": "small"},
      "diagnostics": {...},
      "warnings": [...],
      "tables": {...},
      "meta": {...}
    }

All mathematics is implemented with numpy + ``statflow.distributions`` (no scipy).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.distributions import (
    chi_square_sf,
    f_sf,
    fisher_z_interval,
    normal_sf,
    student_t_two_sided_p,
    t_critical,
)
from app.services.data_service import to_jsonable

SUCCESS = "success"
INSUFFICIENT = "insufficient_data"
INVALID = "invalid_request"

ANALYSIS_DESCRIPTIONS = {
    "descriptive": "Mean, median, SD, variance, min/max, Q1/Q3 per numeric variable",
    "frequency": "Counts and percentages per category",
    "pearson": "Pearson correlation (r + p-value + CI)",
    "spearman": "Spearman rank correlation (rho + p-value)",
    "welch_t_test": "Welch t-test for two independent groups (difference, p, CI, Cohen's d)",
    "mann_whitney": "Mann-Whitney U (non-parametric two-group test)",
    "chi_square": "Chi-square test of independence (chi2, p, df, Cramer's V)",
    "one_way_anova": "One-way ANOVA (F, p, group means, eta squared)",
    "kruskal_wallis": "Kruskal-Wallis test (non-parametric ANOVA)",
    "linear_regression": "Linear regression (R2, coefficients, SE, t, p, CI, AIC/BIC, Durbin-Watson)",
}


class AnalysisError(ValueError):
    """Invalid or impossible analysis request (mapped to HTTP 400)."""


# ------------------------------------------------------------ result builder


def standard_result(
    analysis_type: str,
    *,
    status: str = SUCCESS,
    sample_size: Optional[int] = None,
    estimate: Optional[Dict[str, Any]] = None,
    test: Optional[Dict[str, Any]] = None,
    confidence_interval: Optional[Dict[str, Any]] = None,
    effect_size: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
    warnings: Optional[Sequence[str]] = None,
    tables: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the standard result structure used by every analysis."""
    return {
        "analysis_type": analysis_type,
        "status": status,
        "sample_size": int(sample_size) if sample_size is not None else None,
        "estimate": to_jsonable(estimate or {}),
        "test": to_jsonable(test) if test else None,
        "confidence_interval": to_jsonable(confidence_interval) if confidence_interval else None,
        "effect_size": to_jsonable(effect_size) if effect_size else None,
        "diagnostics": to_jsonable(diagnostics or {}),
        "warnings": [str(warning) for warning in (warnings or [])],
        "tables": to_jsonable(tables or {}),
        "meta": {
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **(meta or {}),
        },
    }


def _round(value: Any, digits: int = 6) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return round(number, digits)


def _effect_label(value: float, small: float, medium: float, large: float) -> str:
    magnitude = abs(value)
    if magnitude < small:
        return "negligible"
    if magnitude < medium:
        return "small"
    if magnitude < large:
        return "medium"
    return "large"


# ------------------------------------------------------------------- helpers


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise AnalysisError(
            f"Column '{column}' does not exist. Available: {', '.join(map(str, frame.columns))}"
        )
    return pd.to_numeric(frame[column], errors="coerce")


def require_column(frame: pd.DataFrame, column: Optional[str], label: str) -> str:
    if not column:
        raise AnalysisError(f"Parameter '{label}' is required")
    if column not in frame.columns:
        raise AnalysisError(
            f"Column '{column}' does not exist. Available: {', '.join(map(str, frame.columns))}"
        )
    return str(column)


def paired_values(
    frame: pd.DataFrame, x_column: str, y_column: str
) -> Tuple[np.ndarray, np.ndarray]:
    """Complete (x, y) pairs as float arrays."""
    values = pd.DataFrame(
        {
            "x": numeric_series(frame, x_column).to_numpy(dtype=float),
            "y": numeric_series(frame, y_column).to_numpy(dtype=float),
        }
    ).dropna()
    return values["x"].to_numpy(dtype=float), values["y"].to_numpy(dtype=float)


def group_samples(
    frame: pd.DataFrame, group_column: str, value_column: str
) -> Dict[str, np.ndarray]:
    """Numeric samples per category of ``group_column``."""
    if group_column not in frame.columns:
        raise AnalysisError(f"Column '{group_column}' does not exist")
    values = pd.DataFrame(
        {
            "group": frame[group_column].astype("string").fillna("<missing>"),
            "value": numeric_series(frame, value_column).to_numpy(dtype=float),
        }
    ).dropna(subset=["value"])
    samples: Dict[str, np.ndarray] = {}
    for label, chunk in values.groupby("group", dropna=False):
        samples[str(label)] = chunk["value"].to_numpy(dtype=float)
    return samples


def descriptives(values: np.ndarray) -> Dict[str, Any]:
    """Mean, median, SD, variance, min/max, Q1/Q3 (+ skewness/kurtosis)."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    count = int(array.size)
    if count == 0:
        return {"count": 0}
    mean = float(array.mean())
    sd = float(array.std(ddof=1)) if count > 1 else 0.0
    result: Dict[str, Any] = {
        "count": count,
        "mean": _round(mean),
        "median": _round(np.median(array)),
        "sd": _round(sd),
        "variance": _round(sd**2),
        "std_error": _round(sd / np.sqrt(count)) if count > 0 and sd > 0 else 0.0,
        "min": _round(array.min()),
        "q1": _round(np.quantile(array, 0.25)),
        "q3": _round(np.quantile(array, 0.75)),
        "max": _round(array.max()),
        "sum": _round(array.sum()),
    }
    if sd > 0 and count > 2:
        centred = array - mean
        result["skewness"] = _round(float((centred**3).mean() / sd**3))
        result["kurtosis"] = _round(float((centred**4).mean() / sd**4 - 3.0))
    else:
        result["skewness"] = 0.0
        result["kurtosis"] = 0.0
    return result


def mean_ci(
    values: np.ndarray, level: float = 0.95
) -> Optional[Tuple[float, float]]:
    """Confidence interval for a mean."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size < 2:
        return None
    sd = float(array.std(ddof=1))
    if sd == 0:
        return (float(array.mean()), float(array.mean()))
    standard_error = sd / np.sqrt(array.size)
    critical = t_critical(array.size - 1, level)
    mean = float(array.mean())
    return (mean - critical * standard_error, mean + critical * standard_error)


def normality_diagnostics(values: np.ndarray) -> Dict[str, Any]:
    """Jarque-Bera test + skew/kurtosis based flags (evidence, not a decision)."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    count = int(array.size)
    if count < 8:
        return {
            "test": "jarque_bera",
            "sample_size": count,
            "p_value": None,
            "skewness": None,
            "kurtosis": None,
            "flag": "sample_too_small",
        }
    mean = float(array.mean())
    sd = float(array.std(ddof=1))
    if sd == 0:
        return {
            "test": "jarque_bera",
            "sample_size": count,
            "p_value": None,
            "skewness": 0.0,
            "kurtosis": 0.0,
            "flag": "zero_variance",
        }
    centred = array - mean
    skewness = float((centred**3).mean() / sd**3)
    kurtosis = float((centred**4).mean() / sd**4 - 3.0)
    statistic = count / 6.0 * (skewness**2 + kurtosis**2 / 4.0)
    p_value = chi_square_sf(statistic, 2)
    return {
        "test": "jarque_bera",
        "sample_size": count,
        "statistic": _round(statistic),
        "p_value": _round(p_value),
        "skewness": _round(skewness),
        "kurtosis": _round(kurtosis),
        "flag": "non_normal" if p_value < 0.05 else "consistent_with_normal",
    }


def outlier_diagnostics(values: np.ndarray) -> Dict[str, Any]:
    """Potential outliers with the 1.5 * IQR rule."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size < 4:
        return {"rule": "iqr_1.5", "count": 0, "percentage": 0.0}
    q1, q3 = np.quantile(array, 0.25), np.quantile(array, 0.75)
    iqr = float(q3 - q1)
    low, high = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
    count = int(np.sum((array < low) | (array > high)))
    return {
        "rule": "iqr_1.5",
        "lower_fence": _round(low),
        "upper_fence": _round(high),
        "count": count,
        "percentage": _round(count / array.size * 100, 2),
    }


def outlier_share(values: np.ndarray) -> float:
    diagnostics = outlier_diagnostics(values)
    return float(diagnostics.get("percentage") or 0.0)


def anova_f(samples: Sequence[np.ndarray]) -> Dict[str, Any]:
    """Classic one-way ANOVA (F, df, p, group means, sums of squares)."""
    clean = [np.asarray(sample, dtype=float) for sample in samples if len(sample) > 0]
    if len(clean) < 2:
        raise AnalysisError("ANOVA needs at least two groups with data")
    lengths = np.array([sample.size for sample in clean], dtype=float)
    means = np.array([sample.mean() for sample in clean], dtype=float)
    grand_mean = float(np.concatenate(clean).mean())
    ss_between = float(np.sum(lengths * (means - grand_mean) ** 2))
    ss_within = float(
        np.sum([((sample - sample.mean()) ** 2).sum() for sample in clean])
    )
    df_between = len(clean) - 1
    df_within = int(lengths.sum() - len(clean))
    if df_within <= 0 or ss_within <= 0:
        raise AnalysisError("Not enough within-group variation to run this test")
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    f_value = ms_between / ms_within if ms_within > 0 else 0.0
    total_ss = ss_between + ss_within
    return {
        "F": float(f_value),
        "df_between": int(df_between),
        "df_within": df_within,
        "p_value": float(f_sf(f_value, df_between, df_within)),
        "ss_between": ss_between,
        "ss_within": ss_within,
        "ms_between": ms_between,
        "ms_within": ms_within,
        "grand_mean": grand_mean,
        "n": int(lengths.sum()),
        "groups": len(clean),
        "eta_squared": ss_between / total_ss if total_ss > 0 else 0.0,
        "omega_squared": max(
            0.0,
            (ss_between - df_between * ms_within) / (total_ss + ms_within),
        ),
    }


def levene_test(samples: Sequence[np.ndarray]) -> Optional[Dict[str, Any]]:
    """Levene's test (median centred) for equality of variances."""
    clean = [
        np.asarray(sample, dtype=float)
        for sample in samples
        if np.asarray(sample, dtype=float).size >= 2
    ]
    if len(clean) < 2:
        return None
    deviations = [np.abs(sample - np.median(sample)) for sample in clean]
    try:
        result = anova_f(deviations)
    except AnalysisError:
        return None
    return {
        "test": "levene_median",
        "statistic": _round(result["F"]),
        "df_between": result["df_between"],
        "df_within": result["df_within"],
        "p_value": _round(result["p_value"]),
        "flag": "unequal_variances"
        if result["p_value"] < 0.05
        else "equal_variances",
    }


def _rank_with_ties(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average").to_numpy(dtype=float)


def correlation_test(x: np.ndarray, y: np.ndarray, method: str) -> Dict[str, Any]:
    """Pearson or Spearman correlation with a t-based p-value."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size != y.size or x.size < 3:
        raise AnalysisError("Need at least 3 complete pairs for a correlation")
    if np.std(x) == 0 or np.std(y) == 0:
        raise AnalysisError("One of the columns has zero variance, correlation undefined")

    if method == "spearman":
        r = float(np.corrcoef(_rank_with_ties(x), _rank_with_ties(y))[0, 1])
    else:
        r = float(np.corrcoef(x, y)[0, 1])

    r = min(max(r, -1.0), 1.0)
    n = int(x.size)
    if abs(r) >= 1.0:
        p_value = 0.0
    else:
        t_statistic = r * np.sqrt((n - 2) / (1 - r**2))
        p_value = student_t_two_sided_p(float(t_statistic), n - 2)
    return {"r": r, "n": n, "p_value": float(p_value), "df": n - 2}


def cohens_d(group_a: np.ndarray, group_b: np.ndarray) -> Optional[float]:
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    if a.size < 2 or b.size < 2:
        return None
    pooled_variance = (
        (a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)
    ) / (a.size + b.size - 2)
    if pooled_variance <= 0:
        return 0.0
    return float((a.mean() - b.mean()) / np.sqrt(pooled_variance))


def mann_whitney_u(group_a: np.ndarray, group_b: np.ndarray) -> Dict[str, Any]:
    """Mann-Whitney U with tie correction and a normal approximation."""
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    if a.size < 2 or b.size < 2:
        raise AnalysisError("Both groups need at least 2 observations")
    combined = np.concatenate([a, b])
    ranks = _rank_with_ties(combined)
    rank_a = ranks[: a.size].sum()
    n_a, n_b = int(a.size), int(b.size)
    u_a = rank_a - n_a * (n_a + 1) / 2.0
    u_statistic = min(u_a, n_a * n_b - u_a)

    mean_u = n_a * n_b / 2.0
    _, counts = np.unique(combined, return_counts=True)
    tie_sum = float(np.sum(counts**3 - counts))
    total = n_a + n_b
    variance_u = (
        n_a * n_b / 12.0 * ((total + 1) - tie_sum / (total * (total - 1)))
        if total > 1
        else 0.0
    )
    if variance_u <= 0:
        raise AnalysisError("Cannot compute the U statistic (no variation in ranks)")
    z = (u_statistic - mean_u) / np.sqrt(variance_u)
    return {
        "U": float(u_statistic),
        "z": float(z),
        "p_value": float(2.0 * normal_sf(abs(z))),
        "rank_biserial": float(1.0 - (2.0 * u_statistic) / (n_a * n_b)),
        "n_a": n_a,
        "n_b": n_b,
    }


def kruskal_wallis(samples: Sequence[np.ndarray]) -> Dict[str, Any]:
    """Kruskal-Wallis H test with tie correction."""
    clean = [np.asarray(sample, dtype=float) for sample in samples if len(sample) > 0]
    if len(clean) < 2:
        raise AnalysisError("Kruskal-Wallis needs at least two groups with data")
    combined = np.concatenate(clean)
    total = int(combined.size)
    ranks = _rank_with_ties(combined)
    offset = 0
    rank_sums: List[float] = []
    for sample in clean:
        rank_sums.append(float(ranks[offset : offset + sample.size].sum()))
        offset += sample.size

    h_statistic = 12.0 / (total * (total + 1)) * sum(
        rank_sum**2 / sample.size for rank_sum, sample in zip(rank_sums, clean)
    ) - 3.0 * (total + 1)

    _, counts = np.unique(combined, return_counts=True)
    tie_sum = float(np.sum(counts**3 - counts))
    if total > 1 and tie_sum > 0:
        correction = 1.0 - tie_sum / (total**3 - total)
        if correction > 0:
            h_statistic /= correction

    df = len(clean) - 1
    return {
        "H": float(h_statistic),
        "df": int(df),
        "p_value": float(chi_square_sf(h_statistic, df)),
        "epsilon_squared": float(h_statistic / ((total**2 - 1) / (total + 1)))
        if total > 1
        else 0.0,
        "n": total,
        "groups": len(clean),
    }


def cramers_v(chi_square: float, n: int, rows: int, columns: int) -> Optional[float]:
    denominator = n * max(1, min(rows - 1, columns - 1))
    if denominator <= 0:
        return None
    return float(np.sqrt(chi_square / denominator))


def durbin_watson(residuals: np.ndarray) -> Optional[float]:
    array = np.asarray(residuals, dtype=float)
    if array.size < 3:
        return None
    denominator = float(np.sum(array**2))
    if denominator == 0:
        return None
    return float(np.sum(np.diff(array) ** 2) / denominator)


def fisher_exact_2x2(table: np.ndarray) -> Dict[str, Any]:
    """Two-sided Fisher exact test for a 2x2 table (hypergeometric sum)."""
    from math import comb

    a, b = int(table[0][0]), int(table[0][1])
    c, d = int(table[1][0]), int(table[1][1])
    row1, row2 = a + b, c + d
    col1 = a + c
    total = row1 + row2
    if total == 0:
        raise AnalysisError("The contingency table is empty")

    def probability(value: int) -> float:
        return comb(row1, value) * comb(row2, col1 - value) / comb(total, col1)

    lower = max(0, col1 - row2)
    upper = min(row1, col1)
    observed = probability(a)
    p_value = sum(
        probability(value)
        for value in range(lower, upper + 1)
        if probability(value) <= observed + 1e-12
    )
    return {
        "p_value": float(min(max(p_value, 0.0), 1.0)),
        "observed": [[a, b], [c, d]],
        "odds_ratio": float((a * d) / (b * c)) if b * c > 0 else None,
    }


def ols_fit(
    x_matrix: np.ndarray, y_values: np.ndarray, feature_names: Sequence[str]
) -> Dict[str, Any]:
    """Least squares regression with standard errors, t, p, CI, AIC/BIC, DW."""
    x_matrix = np.asarray(x_matrix, dtype=float)
    y_values = np.asarray(y_values, dtype=float)
    n, k = x_matrix.shape
    parameters = k + 1  # + intercept
    if n <= parameters:
        raise AnalysisError(
            f"Not enough complete rows ({n}) for {parameters} parameters, "
            "clean missing values or remove features"
        )

    design = np.column_stack([np.ones(n), x_matrix])
    coefficients, *_ = np.linalg.lstsq(design, y_values, rcond=None)
    fitted = design @ coefficients
    residuals = y_values - fitted
    rss = float(np.sum(residuals**2))
    tss = float(np.sum((y_values - y_values.mean()) ** 2))
    if tss <= 0:
        raise AnalysisError("The target column has zero variance")

    degrees_of_freedom = n - parameters
    sigma_squared = rss / degrees_of_freedom
    try:
        covariance = sigma_squared * np.linalg.pinv(design.T @ design)
        standard_errors = np.sqrt(np.diag(covariance))
    except np.linalg.LinAlgError:  # pragma: no cover - degenerate design
        standard_errors = np.full(parameters, np.nan)

    r_squared = 1.0 - rss / tss
    adjusted_r_squared = 1.0 - (1.0 - r_squared) * (n - 1) / degrees_of_freedom
    critical = t_critical(degrees_of_freedom, 0.95)

    rows: List[Dict[str, Any]] = []
    names = ["(intercept)", *feature_names]
    for index, name in enumerate(names):
        estimate = float(coefficients[index])
        standard_error = float(standard_errors[index])
        if np.isfinite(standard_error) and standard_error > 0:
            t_statistic = estimate / standard_error
            p_value = student_t_two_sided_p(t_statistic, degrees_of_freedom)
            lower = estimate - critical * standard_error
            upper = estimate + critical * standard_error
        else:
            t_statistic, p_value, lower, upper = None, None, None, None
        rows.append(
            {
                "variable": name,
                "estimate": _round(estimate),
                "std_error": _round(standard_error),
                "t_statistic": _round(t_statistic),
                "p_value": _round(p_value),
                "ci_lower": _round(lower),
                "ci_upper": _round(upper),
            }
        )

    if k > 0 and 0 < r_squared < 1:
        f_statistic = (r_squared / k) / ((1 - r_squared) / degrees_of_freedom)
        f_p_value = f_sf(f_statistic, k, degrees_of_freedom)
    else:
        f_statistic, f_p_value = 0.0, 1.0

    mean_squared_residual = rss / n
    aic = (
        n * np.log(mean_squared_residual) + 2 * parameters
        if mean_squared_residual > 0
        else None
    )
    bic = (
        n * np.log(mean_squared_residual) + parameters * np.log(n)
        if mean_squared_residual > 0
        else None
    )
    return {
        "n": n,
        "parameters": parameters,
        "intercept": _round(float(coefficients[0])),
        "coefficients": rows,
        "r_squared": _round(r_squared),
        "adjusted_r_squared": _round(adjusted_r_squared),
        "f_statistic": _round(f_statistic),
        "f_p_value": _round(f_p_value),
        "f_df1": k,
        "f_df2": degrees_of_freedom,
        "residual_standard_error": _round(np.sqrt(sigma_squared)),
        "rss": _round(rss),
        "aic": _round(aic),
        "bic": _round(bic),
        "durbin_watson": _round(durbin_watson(residuals)),
        "residuals": residuals,
        "fitted": fitted,
    }


def descriptive_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    requested = parameters.get("columns")
    warnings: List[str] = []
    if requested:
        columns = [str(column) for column in requested if column in frame.columns]
        missing_columns = [column for column in requested if column not in frame.columns]
        if missing_columns:
            warnings.append(f"Columns not found: {', '.join(missing_columns)}")
    else:
        columns = [
            str(column)
            for column in frame.columns
            if pd.to_numeric(frame[column], errors="coerce").notna().sum() > 0
        ]
    if not columns:
        raise AnalysisError("No numeric columns found to describe")

    variables: Dict[str, Any] = {}
    table: List[Dict[str, Any]] = []
    total_missing = 0
    for column in columns:
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        values = numeric.dropna().to_numpy(dtype=float)
        missing = int(series.isna().sum() + numeric.isna().sum() - series.isna().sum())
        total_missing += max(missing, 0)
        stats = descriptives(values)
        stats["missing"] = max(missing, 0)
        stats["variable"] = column
        stats["confidence_interval_95"] = to_jsonable(mean_ci(values))
        variables[column] = stats
        table.append(stats)

    return standard_result(
        "descriptive",
        sample_size=int(frame.shape[0]),
        estimate={"variables": variables},
        diagnostics={
            "missing_cells": total_missing,
            "columns_described": len(variables),
        },
        warnings=warnings,
        tables={"descriptive": table},
    )


def frequency_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    requested = parameters.get("columns") or parameters.get("column")
    columns = [str(column) for column in (requested or [])]
    if not columns:
        columns = [
            str(column)
            for column in frame.columns
            if frame[column].nunique(dropna=True) <= 50
        ][:5]
    if not columns:
        raise AnalysisError("No categorical columns found for a frequency table")

    warnings: List[str] = []
    tables: Dict[str, Any] = {}
    for column in columns:
        if column not in frame.columns:
            warnings.append(f"Column '{column}' does not exist, skipped")
            continue
        counts = frame[column].value_counts(dropna=False)
        total = int(counts.sum())
        rows = [
            {
                "category": to_jsonable(category),
                "count": int(count),
                "percentage": _round(int(count) / total * 100, 2) if total else 0.0,
            }
            for category, count in counts.items()
        ]
        tables[column] = rows
        if len(rows) > 20:
            warnings.append(
                f"'{column}' has {len(rows)} categories, consider grouping rare ones"
            )
        if any(row["category"] is None for row in rows):
            warnings.append(
                f"'{column}' has missing values shown as a separate category"
            )

    return standard_result(
        "frequency",
        sample_size=int(frame.shape[0]),
        estimate={"variables": list(tables)},
        diagnostics={"tables": len(tables)},
        warnings=warnings,
        tables={"frequency": tables},
    )


def correlation_analysis_v2(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Pearson or Spearman correlation with CI and diagnostics."""
    method = str(parameters.get("method") or "pearson").lower()
    if method not in {"pearson", "spearman"}:
        raise AnalysisError("method must be 'pearson' or 'spearman'")

    x_column = require_column(
        frame, parameters.get("x") or parameters.get("x_column"), "x"
    )
    y_column = require_column(
        frame, parameters.get("y") or parameters.get("y_column"), "y"
    )
    if x_column == y_column:
        raise AnalysisError("Choose two different columns")

    x_values, y_values = paired_values(frame, x_column, y_column)
    if x_values.size < 3:
        raise AnalysisError("Need at least 3 complete pairs for a correlation")

    level = float(parameters.get("confidence_level") or 0.95)
    result = correlation_test(x_values, y_values, method)
    r = float(result["r"])
    n = int(result["n"])
    interval = fisher_z_interval(r, n, level)

    x_normality = normality_diagnostics(x_values)
    y_normality = normality_diagnostics(y_values)
    outliers_x = outlier_share(x_values)
    outliers_y = outlier_share(y_values)

    warnings: List[str] = []
    if n < 30:
        warnings.append(f"Only {n} complete pairs, the estimate is unstable")
    if max(outliers_x, outliers_y) > 5:
        warnings.append(
            f"About {max(outliers_x, outliers_y):.1f}% of values are potential outliers "
            "(1.5*IQR rule)"
        )
    if method == "pearson" and (
        x_normality.get("flag") == "non_normal" or y_normality.get("flag") == "non_normal"
    ):
        warnings.append(
            "Pearson assumes roughly normal variables; Spearman (rank based) is a "
            "robust alternative"
        )

    magnitude = abs(r)
    strength = (
        "strong" if magnitude >= 0.7 else "moderate" if magnitude >= 0.4 else "weak"
    )
    if magnitude < 0.2:
        strength = "negligible"

    return standard_result(
        "spearman" if method == "spearman" else "pearson",
        sample_size=n,
        estimate={
            "correlation": _round(r),
            "method": method,
            "direction": "positive" if r >= 0 else "negative",
            "strength": strength,
            "x": x_column,
            "y": y_column,
        },
        test={
            "method": "Pearson r" if method == "pearson" else "Spearman rho",
            "statistic": _round(r),
            "df": result["df"],
            "p_value": _round(result["p_value"]),
            "alpha": 0.05,
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]) if interval else None,
            "upper": _round(interval[1]) if interval else None,
        },
        effect_size={
            "name": "r" if method == "pearson" else "rho",
            "value": _round(r),
            "interpretation": strength,
        },
        diagnostics={
            "complete_pairs": n,
            "missing_pairs": int(frame.shape[0] - n),
            "normality_x": x_normality,
            "normality_y": y_normality,
            "outliers_x_percentage": _round(outliers_x, 2),
            "outliers_y_percentage": _round(outliers_y, 2),
        },
        warnings=warnings,
        tables={
            "scatter": {
                "x": [to_jsonable(value) for value in x_values[:500]],
                "y": [to_jsonable(value) for value in y_values[:500]],
                "x_label": x_column,
                "y_label": y_column,
            }
        },
    )


def _two_group_samples(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[str, str, Dict[str, np.ndarray]]:
    value_column = require_column(
        frame, parameters.get("value_column") or parameters.get("value"), "value_column"
    )
    group_column = require_column(
        frame, parameters.get("group_column") or parameters.get("group"), "group_column"
    )
    samples = group_samples(frame, group_column, value_column)
    samples = {label: values for label, values in samples.items() if values.size > 0}
    if len(samples) < 2:
        raise AnalysisError(
            f"'{group_column}' needs at least two groups with numeric values"
        )
    if len(samples) > 2:
        ordered = sorted(samples.items(), key=lambda item: item[1].size, reverse=True)
        samples = dict(ordered[:2])
    labels = list(samples.keys())
    return labels[0], labels[1], samples


def welch_t_test_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Welch's t-test: mean difference, p-value, CI and Cohen's d."""
    label_a, label_b, samples = _two_group_samples(frame, parameters)
    a, b = samples[label_a], samples[label_b]
    if a.size < 2 or b.size < 2:
        raise AnalysisError("Each group needs at least 2 observations")

    mean_a, mean_b = float(a.mean()), float(b.mean())
    var_a, var_b = float(a.var(ddof=1)), float(b.var(ddof=1))
    n_a, n_b = int(a.size), int(b.size)
    denominator = float(np.sqrt(var_a / n_a + var_b / n_b))
    if denominator == 0:
        raise AnalysisError("Both groups have zero variance, the t-test is undefined")

    difference = mean_a - mean_b
    t_statistic = difference / denominator
    df = (var_a / n_a + var_b / n_b) ** 2 / (
        (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
    )
    level = float(parameters.get("confidence_level") or 0.95)
    critical = t_critical(df, level)
    alternative = str(parameters.get("alternative") or "two-sided").lower()

    if alternative == "two-sided":
        p_value = student_t_two_sided_p(float(t_statistic), df)
    elif alternative in {"greater", "less"}:
        from app.statflow.distributions import student_t_sf

        upper = student_t_sf(float(t_statistic), df)
        p_value = upper if alternative == "greater" else 1.0 - upper
    else:
        raise AnalysisError("alternative must be 'two-sided', 'greater' or 'less'")

    d_value = cohens_d(a, b) or 0.0
    variance_ratio = (
        max(var_a, var_b) / min(var_a, var_b) if min(var_a, var_b) > 0 else None
    )
    levene = levene_test([a, b])
    normality_a = normality_diagnostics(a)
    normality_b = normality_diagnostics(b)

    warnings: List[str] = []
    if min(n_a, n_b) < 30:
        warnings.append(
            f"Smallest group has only {min(n_a, n_b)} observations, results are approximate"
        )
    if levene and levene.get("flag") == "unequal_variances":
        warnings.append(
            "Variances differ between groups (Levene p < 0.05); Welch's correction "
            "is already applied"
        )
    if outlier_share(a) > 5 or outlier_share(b) > 5:
        warnings.append("Potential outliers detected in at least one group (1.5*IQR)")
    if (
        normality_a.get("flag") == "non_normal"
        or normality_b.get("flag") == "non_normal"
    ):
        warnings.append(
            "At least one group looks non-normal; Mann-Whitney U is the robust alternative"
        )

    return standard_result(
        "welch_t_test",
        sample_size=n_a + n_b,
        estimate={
            "group_means": {label_a: _round(mean_a), label_b: _round(mean_b)},
            "mean_difference": _round(difference),
            "group_sd": {
                label_a: _round(np.sqrt(var_a)),
                label_b: _round(np.sqrt(var_b)),
            },
            "group_sizes": {label_a: n_a, label_b: n_b},
        },
        test={
            "method": "Welch two-sample t-test",
            "statistic": _round(t_statistic),
            "df": _round(df, 3),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "alternative": alternative,
            "significant": bool(p_value < 0.05),
            "grouping": f"{label_a} vs {label_b}",
        },
        confidence_interval={
            "level": level,
            "lower": _round(difference - critical * denominator),
            "upper": _round(difference + critical * denominator),
            "of": "mean difference",
        },
        effect_size={
            "name": "cohens_d",
            "value": _round(d_value),
            "interpretation": _effect_label(d_value, 0.2, 0.5, 0.8),
        },
        diagnostics={
            "variance_ratio": _round(variance_ratio),
            "levene": levene,
            "normality": {label_a: normality_a, label_b: normality_b},
            "outliers_percentage": {
                label_a: _round(outlier_share(a), 2),
                label_b: _round(outlier_share(b), 2),
            },
        },
        warnings=warnings,
        tables={
            "groups": [
                {"group": label_a, **descriptives(a)},
                {"group": label_b, **descriptives(b)},
            ]
        },
    )


def mann_whitney_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Mann-Whitney U: non-parametric comparison of two groups (medians)."""
    label_a, label_b, samples = _two_group_samples(frame, parameters)
    a, b = samples[label_a], samples[label_b]
    result = mann_whitney_u(a, b)

    warnings: List[str] = []
    if min(a.size, b.size) < 8:
        warnings.append(
            "Small groups: the normal approximation for the U statistic is rough"
        )
    rank_biserial = float(result["rank_biserial"])
    return standard_result(
        "mann_whitney",
        sample_size=int(a.size + b.size),
        estimate={
            "median_group_a": _round(np.median(a)),
            "median_group_b": _round(np.median(b)),
            "median_difference": _round(float(np.median(a) - np.median(b))),
            "grouping": f"{label_a} vs {label_b}",
        },
        test={
            "method": "Mann-Whitney U (normal approximation, tie corrected)",
            "statistic": _round(result["U"]),
            "z": _round(result["z"]),
            "p_value": _round(result["p_value"]),
            "alpha": 0.05,
            "significant": bool(result["p_value"] < 0.05),
        },
        effect_size={
            "name": "rank_biserial",
            "value": _round(rank_biserial),
            "interpretation": _effect_label(rank_biserial, 0.1, 0.3, 0.5),
        },
        diagnostics={
            "group_sizes": {label_a: int(a.size), label_b: int(b.size)},
            "normality": {
                label_a: normality_diagnostics(a),
                label_b: normality_diagnostics(b),
            },
        },
        warnings=warnings,
        tables={
            "groups": [
                {"group": label_a, **descriptives(a)},
                {"group": label_b, **descriptives(b)},
            ]
        },
    )


def chi_square_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Chi-square test of independence (+ Cramer's V, expected counts)."""
    row_column = require_column(
        frame,
        parameters.get("row_column") or parameters.get("x") or parameters.get("row"),
        "row_column",
    )
    column_column = require_column(
        frame,
        parameters.get("column_column")
        or parameters.get("y")
        or parameters.get("column"),
        "column_column",
    )
    if row_column == column_column:
        raise AnalysisError("Choose two different categorical columns")

    working = frame[[row_column, column_column]].copy()
    working[row_column] = working[row_column].astype("string").fillna("<missing>")
    working[column_column] = working[column_column].astype("string").fillna("<missing>")
    table = pd.crosstab(working[row_column], working[column_column])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise AnalysisError("Both columns need at least two categories")

    observed = table.to_numpy(dtype=float)
    total = float(observed.sum())
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi_square = float(
            np.nansum(
                np.where(expected > 0, (observed - expected) ** 2 / expected, 0.0)
            )
        )
    df = (table.shape[0] - 1) * (table.shape[1] - 1)
    p_value = chi_square_sf(chi_square, df)
    v_value = cramers_v(chi_square, int(total), table.shape[0], table.shape[1])

    warnings: List[str] = []
    small_expected = int(np.sum(expected < 5))
    if small_expected:
        warnings.append(
            f"{small_expected} of {expected.size} cells have an expected count below 5"
        )

    fisher = None
    if table.shape == (2, 2) and (
        small_expected > 0 or str(parameters.get("method") or "").lower() == "fisher"
    ):
        fisher = fisher_exact_2x2(observed)
        warnings.append(
            "2x2 table with small expected counts: Fisher's exact test is reported too "
            f"(p = {fisher['p_value']:.4f})"
        )

    return standard_result(
        "chi_square",
        sample_size=int(total),
        estimate={
            "row_variable": row_column,
            "column_variable": column_column,
            "contingency_table": {
                "index": [str(value) for value in table.index],
                "columns": [str(value) for value in table.columns],
                "observed": [[_round(value, 2) for value in row] for row in observed],
                "expected": [[_round(value, 2) for value in row] for row in expected],
            },
            "row_percentages": [
                {
                    "category": str(index),
                    **{
                        str(column): _round(
                            observed[i][j] / observed[i].sum() * 100, 2
                        )
                        for j, column in enumerate(table.columns)
                    },
                }
                for i, index in enumerate(table.index)
            ],
        },
        test={
            "method": "Pearson chi-square test of independence",
            "statistic": _round(chi_square),
            "df": int(df),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
            "fisher_exact_p_value": _round(fisher["p_value"]) if fisher else None,
        },
        effect_size={
            "name": "cramers_v",
            "value": _round(v_value),
            "interpretation": _effect_label(v_value or 0.0, 0.1, 0.3, 0.5),
        },
        diagnostics={
            "rows": int(table.shape[0]),
            "columns": int(table.shape[1]),
            "cells_with_expected_below_5": small_expected,
            "minimum_expected": _round(float(expected.min())),
        },
        warnings=warnings,
        tables={"contingency": to_jsonable(observed.astype(int).tolist())},
    )


def anova_analysis(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """One-way ANOVA: F, p, group means, eta squared (+ Levene, normality)."""
    value_column = require_column(
        frame, parameters.get("value_column") or parameters.get("value"), "value_column"
    )
    group_column = require_column(
        frame, parameters.get("group_column") or parameters.get("group"), "group_column"
    )
    samples = group_samples(frame, group_column, value_column)
    samples = {
        label: values for label, values in samples.items() if values.size >= 2
    }
    if len(samples) < 2:
        raise AnalysisError(
            "ANOVA needs at least two groups with 2+ numeric values each"
        )
    if len(samples) > 30:
        raise AnalysisError(
            f"'{group_column}' has {len(samples)} groups, too many for a one-way ANOVA. "
            "Group rare categories first."
        )

    result = anova_f(list(samples.values()))
    levene = levene_test(list(samples.values()))
    normality = {label: normality_diagnostics(values) for label, values in samples.items()}

    warnings: List[str] = []
    if min(values.size for values in samples.values()) < 5:
        warnings.append("Some groups have fewer than 5 observations")
    if levene and levene.get("flag") == "unequal_variances":
        warnings.append(
            "Variances differ between groups (Levene p < 0.05); consider Welch ANOVA "
            "or Kruskal-Wallis"
        )
    if any(item.get("flag") == "non_normal" for item in normality.values()):
        warnings.append(
            "At least one group looks non-normal; Kruskal-Wallis is the robust alternative"
        )

    return standard_result(
        "one_way_anova",
        sample_size=int(result["n"]),
        estimate={
            "group_means": {
                label: _round(values.mean()) for label, values in samples.items()
            },
            "grand_mean": _round(result["grand_mean"]),
            "groups": len(samples),
            "value_variable": value_column,
            "grouping_variable": group_column,
        },
        test={
            "method": "One-way ANOVA",
            "statistic": _round(result["F"]),
            "df_between": result["df_between"],
            "df_within": result["df_within"],
            "p_value": _round(result["p_value"]),
            "alpha": 0.05,
            "significant": bool(result["p_value"] < 0.05),
        },
        confidence_interval=None,
        effect_size={
            "name": "eta_squared",
            "value": _round(result["eta_squared"]),
            "omega_squared": _round(result["omega_squared"]),
            "interpretation": _effect_label(result["eta_squared"], 0.01, 0.06, 0.14),
        },
        diagnostics={
            "sums_of_squares": {
                "between": _round(result["ss_between"]),
                "within": _round(result["ss_within"]),
            },
            "levene": levene,
            "normality": normality,
        },
        warnings=warnings,
        tables={
            "groups": [
                {"group": label, **descriptives(values)}
                for label, values in samples.items()
            ]
        },
    )


def kruskal_wallis_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Kruskal-Wallis H test (non-parametric one-way ANOVA)."""
    value_column = require_column(
        frame, parameters.get("value_column") or parameters.get("value"), "value_column"
    )
    group_column = require_column(
        frame, parameters.get("group_column") or parameters.get("group"), "group_column"
    )
    samples = group_samples(frame, group_column, value_column)
    samples = {label: values for label, values in samples.items() if values.size > 0}
    if len(samples) < 2:
        raise AnalysisError("Kruskal-Wallis needs at least two groups with data")

    result = kruskal_wallis(list(samples.values()))
    warnings: List[str] = []
    if min(values.size for values in samples.values()) < 5:
        warnings.append("Some groups have fewer than 5 observations")
    return standard_result(
        "kruskal_wallis",
        sample_size=int(result["n"]),
        estimate={
            "median_by_group": {
                label: _round(np.median(values)) for label, values in samples.items()
            },
            "groups": len(samples),
        },
        test={
            "method": "Kruskal-Wallis H (rank based)",
            "statistic": _round(result["H"]),
            "df": result["df"],
            "p_value": _round(result["p_value"]),
            "alpha": 0.05,
            "significant": bool(result["p_value"] < 0.05),
        },
        effect_size={
            "name": "epsilon_squared",
            "value": _round(result["epsilon_squared"]),
            "interpretation": _effect_label(
                result["epsilon_squared"], 0.01, 0.06, 0.14
            ),
        },
        diagnostics={"group_sizes": {label: int(values.size) for label, values in samples.items()}},
        warnings=warnings,
        tables={
            "groups": [
                {"group": label, **descriptives(values)}
                for label, values in samples.items()
            ]
        },
    )


def linear_regression_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Linear regression with SE, t, p, CI, R2, adjusted R2, AIC/BIC, Durbin-Watson."""
    target = require_column(
        frame, parameters.get("target") or parameters.get("y"), "target"
    )
    features = [
        str(feature)
        for feature in (parameters.get("features") or parameters.get("x") or [])
        if str(feature) in frame.columns and str(feature) != target
    ]
    if not features:
        features = [
            str(column)
            for column in frame.columns
            if str(column) != target
            and pd.to_numeric(frame[column], errors="coerce").notna().sum() > 0
        ]
    if not features:
        raise AnalysisError("Regression needs at least one numeric feature column")

    data = pd.DataFrame(
        {
            "target": pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float),
            **{
                feature: pd.to_numeric(frame[feature], errors="coerce").to_numpy(
                    dtype=float
                )
                for feature in features
            },
        }
    ).dropna()
    if data.shape[0] <= len(features) + 1:
        raise AnalysisError(
            "Not enough complete rows to fit this regression, clean missing values first"
        )

    y_values = data["target"].to_numpy(dtype=float)
    x_matrix = data[features].to_numpy(dtype=float)
    fit = ols_fit(x_matrix, y_values, features)

    warnings: List[str] = []
    dropped = int(frame.shape[0] - data.shape[0])
    if dropped:
        warnings.append(f"{dropped} row(s) were dropped because of missing values")
    if fit["durbin_watson"] is not None and fit["durbin_watson"] < 1.5:
        warnings.append(
            "Durbin-Watson below 1.5 suggests positive autocorrelation in the residuals"
        )
    if fit["n"] < 10 * len(features):
        warnings.append(
            "Fewer than 10 observations per feature: the model may be overfitted"
        )
    normality = normality_diagnostics(fit["residuals"])
    if normality.get("flag") == "non_normal":
        warnings.append(
            "Residuals look non-normal (Jarque-Bera p < 0.05): check outliers and "
            "model specification"
        )

    equation = f"{target} = {fit['intercept']:.4f} " + " ".join(
        f"{row['estimate']:+.4f}*{row['variable']}" for row in fit["coefficients"][1:]
    )

    return standard_result(
        "linear_regression",
        sample_size=int(fit["n"]),
        estimate={
            "target": target,
            "features": features,
            "equation": equation,
            "r_squared": fit["r_squared"],
            "adjusted_r_squared": fit["adjusted_r_squared"],
            "intercept": fit["intercept"],
        },
        test={
            "method": "Ordinary least squares",
            "statistic": fit["f_statistic"],
            "df1": fit["f_df1"],
            "df2": fit["f_df2"],
            "p_value": fit["f_p_value"],
            "alpha": 0.05,
            "significant": bool((fit["f_p_value"] or 1.0) < 0.05),
        },
        effect_size={
            "name": "r_squared",
            "value": fit["r_squared"],
            "interpretation": _effect_label(fit["r_squared"] or 0.0, 0.02, 0.13, 0.26),
        },
        diagnostics={
            "residual_standard_error": fit["residual_standard_error"],
            "aic": fit["aic"],
            "bic": fit["bic"],
            "durbin_watson": fit["durbin_watson"],
            "residual_normality": normality,
            "rows_dropped": dropped,
            "outliers_percentage": _round(outlier_share(y_values), 2),
        },
        warnings=warnings,
        tables={"coefficients": fit["coefficients"]},
        meta={"target": target, "features": features},
    )


# ------------------------------------------------------------------- dispatch

ANALYSIS_HANDLERS: Dict[str, Any] = {
    "descriptive": descriptive_analysis,
    "frequency": frequency_analysis,
    "pearson": lambda frame, parameters: correlation_analysis_v2(
        frame, {**parameters, "method": "pearson"}
    ),
    "spearman": lambda frame, parameters: correlation_analysis_v2(
        frame, {**parameters, "method": "spearman"}
    ),
    "welch_t_test": welch_t_test_analysis,
    "mann_whitney": mann_whitney_analysis,
    "chi_square": chi_square_analysis,
    "one_way_anova": anova_analysis,
    "kruskal_wallis": kruskal_wallis_analysis,
    "linear_regression": linear_regression_analysis,
}

REQUIRED_PARAMETERS = {
    "descriptive": ["columns (optional)"],
    "frequency": ["columns or column (optional)"],
    "pearson": ["x", "y"],
    "spearman": ["x", "y"],
    "welch_t_test": ["value_column", "group_column"],
    "mann_whitney": ["value_column", "group_column"],
    "chi_square": ["row_column", "column_column"],
    "one_way_anova": ["value_column", "group_column"],
    "kruskal_wallis": ["value_column", "group_column"],
    "linear_regression": ["target", "features"],
}


def catalog() -> List[Dict[str, Any]]:
    """Available analyses plus the parameters each one expects."""
    return [
        {
            "analysis_type": analysis_type,
            "description": ANALYSIS_DESCRIPTIONS.get(analysis_type, ""),
            "requires": REQUIRED_PARAMETERS.get(analysis_type, []),
        }
        for analysis_type in ANALYSIS_HANDLERS
    ]


def run_analysis(
    frame: pd.DataFrame, analysis_type: str, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Run one analysis and always return the standard result structure."""
    handler = ANALYSIS_HANDLERS.get(str(analysis_type))
    if handler is None:
        raise AnalysisError(
            "Unknown analysis_type. Allowed: " + ", ".join(sorted(ANALYSIS_HANDLERS))
        )
    if frame.shape[0] < 3:
        return standard_result(
            str(analysis_type),
            status=INSUFFICIENT,
            sample_size=int(frame.shape[0]),
            warnings=["The dataset version has fewer than 3 rows"],
            meta={"parameters": parameters},
        )
    return handler(frame, parameters or {})












