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
from math import lgamma
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.distributions import (
    chi_square_sf,
    f_sf,
    fisher_z_interval,
    normal_ppf,
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
    "correlation_matrix": "Correlation matrix across all numeric columns (r for every pair)",
    "welch_t_test": "Welch t-test for two independent groups (difference, p, CI, Cohen's d)",
    "mann_whitney": "Mann-Whitney U (non-parametric two-group test)",
    "chi_square": "Chi-square test of independence (chi2, p, df, Cramer's V)",
    "one_way_anova": "One-way ANOVA (F, p, group means, eta squared)",
    "kruskal_wallis": "Kruskal-Wallis test (non-parametric ANOVA)",
    "linear_regression": "Linear regression (R2, coefficients, SE, t, p, CI, AIC/BIC, Durbin-Watson)",
    "crosstab": "Contingency table with observed counts, row % and column %",
    "kendall": "Kendall's tau-b with tie correction (z + p-value)",
    "point_biserial": "Point-biserial correlation between a binary and a continuous variable",
    "partial_correlation": "Partial correlation of x and y controlling for other columns",
    "normality_tests": "Jarque-Bera normality test with skewness, kurtosis and a Q-Q read-out",
    "normality_test": "Jarque-Bera normality test (legacy singular name)",
    "one_sample_t_test": "One-sample t-test against a benchmark mean (t, p, CI, Cohen's d)",
    "paired_t_test": "Paired t-test for two measurements of the same units (t, p, CI, dz)",
    "two_proportion_z_test": "Two-proportion z-test (z, p, difference, CI, odds ratio)",
    "wilcoxon_signed_rank": "Wilcoxon signed-rank test for paired data (W, z, p, r)",
    "chi_square_gof": "Chi-square goodness-of-fit (chi2, df, p, standardized residuals)",
    "logistic_regression": "Binary logistic regression (odds ratios, pseudo R2, AUC, confusion matrix)",
    "poisson_regression": "Poisson regression for counts (IRR, z, p, dispersion ratio)",
    "cronbach_alpha": "Cronbach's alpha with item-total correlations and alpha-if-deleted",
    "kaplan_meier": "Kaplan-Meier survival curve, median survival and log-rank test",
    "probit": "Probit regression: coefficients are z-scores on a latent normal index",
    "linear_probability_model": "OLS on a 0/1 outcome, for direct marginal effects",
    "negative_binomial": "Negative binomial GLM for overdispersed counts, reporting incidence rate ratios",
    "zero_inflated": "Zero-inflated Poisson/NB for excess zeros, with a Vuong test of the extra component",
    "hurdle": "Hurdle model: a zero process plus a count process truncated at zero",
    "tobit": "Tobit censored regression, for outcomes observed only past a threshold",
    "ridge_lasso": "Ridge, lasso or elastic net with cross-validated penalty, for prediction",
    "quantile_regression": "Quantile regression at chosen taus, for effects that vary across the distribution",
    "mcdonalds_omega": "McDonald's omega, the data-driven alternative to Cronbach's alpha",
    "cohens_kappa": "Cohen's kappa for two raters, corrected for chance agreement",
    "fleiss_kappa": "Fleiss' kappa for any number of raters",
    "icc": "Intraclass correlation for rating reliability, single and averaged",
    "fisher_exact": "Fisher's exact test, for a 2x2 table with small expected counts",
    "mcnemar": "McNemar's test for paired categorical change in two raters",
    "one_sample_z_test": "One-sample z-test against a known mean and standard deviation",
    "two_way_anova": "Two-way (factorial) ANOVA with main effects and interaction",
    "ordinal_logit": "Proportional-odds logistic regression on an ordered outcome",
}

#: Correlation methods share one implementation; only the label differs.
CORRELATION_METHODS: Dict[str, Dict[str, str]] = {
    "pearson": {
        "analysis_type": "pearson",
        "test": "Pearson r",
        "effect": "r",
        "requires": "two continuous columns",
    },
    "spearman": {
        "analysis_type": "spearman",
        "test": "Spearman rho",
        "effect": "rho",
        "requires": "ordinal or continuous columns",
    },
    "kendall": {
        "analysis_type": "kendall",
        "test": "Kendall tau-b",
        "effect": "tau_b",
        "requires": "ordinal columns (handles ties)",
    },
    "point_biserial": {
        "analysis_type": "point_biserial",
        "test": "Point-biserial r",
        "effect": "r_pb",
        "requires": "one binary column and one continuous column",
    },
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


def _normal_sf_array(z_scores: np.ndarray) -> np.ndarray:
    """Vectorised standard normal upper tail.

    ``distributions.normal_sf`` is deliberately scalar (it is a thin, exact
    wrapper around ``math.erfc``), so a vectorised p-value column needs this.
    The inputs are coefficient tests, so the list comprehension is tiny.
    """
    return np.array(
        [float(normal_sf(abs(float(value)))) for value in np.asarray(z_scores).ravel()],
        dtype=float,
    ).reshape(np.asarray(z_scores).shape)


def _exp_clipped(value: float, limit: float = 700.0) -> float:
    """``exp`` that saturates instead of overflowing to inf.

    A separated logistic fit produces a coefficient of several hundred, and
    ``exp(1.96 * SE)`` on top of that is infinity. An infinite bound in a JSON
    response is worse than a very large one, so the exponent is clipped.
    """
    exponent = float(value)
    if exponent > limit:
        exponent = limit
    elif exponent < -limit:
        exponent = -limit
    return float(np.exp(exponent))


def _two_sided_normal_p(z_scores: np.ndarray) -> np.ndarray:
    """Two-sided p-values for a vector of z statistics."""
    return 2.0 * _normal_sf_array(z_scores)


# The residual plot is drawn from binned means rather than from every row: a
# scatter of 40,000 points is unreadable in a browser and a 2 MB JSON response.
# Binning keeps the shape, which is the thing a residual plot exists to show.
RESIDUAL_PLOT_BINS = 40


def residual_plot(
    fitted: np.ndarray, residuals: np.ndarray
) -> List[Dict[str, Any]]:
    """Binned predicted-vs-residual means, for the residual diagnostic chart.

    Rows are grouped into equal-width bands of the fitted value and each band
    reports its mean prediction, mean residual and the spread of residuals
    inside it. The mean residual per band is what reveals curvature or a
    funnel shape; a single raw residual cannot.

    The residual standard deviation per band is included because a band whose
    spread grows with the prediction is heteroscedasticity, which the mean
    alone would hide.
    """
    fitted = np.asarray(fitted, dtype=float)
    residuals = np.asarray(residuals, dtype=float)
    if fitted.size == 0 or fitted.size != residuals.size:
        return []

    finite = np.isfinite(fitted) & np.isfinite(residuals)
    fitted = fitted[finite]
    residuals = residuals[finite]
    if fitted.size == 0:
        return []

    low, high = float(fitted.min()), float(fitted.max())
    if high <= low:
        # Every prediction is the same number, so there is no x-axis to spread
        # them over. One band is the honest answer.
        bands = [fitted <= high + 1e-12]
    else:
        width = (high - low) / RESIDUAL_PLOT_BINS
        edges = low + width * np.arange(RESIDUAL_PLOT_BINS + 1)
        bands = [
            (fitted >= edges[index]) & (fitted <= edges[index + 1] if index == RESIDUAL_PLOT_BINS - 1 else fitted < edges[index + 1])
            for index in range(RESIDUAL_PLOT_BINS)
        ]

    points: List[Dict[str, Any]] = []
    for mask in bands:
        if not mask.any():
            continue
        band_residuals = residuals[mask]
        points.append(
            {
                "predicted": _round(float(fitted[mask].mean()), 4),
                "residual": _round(float(band_residuals.mean()), 4),
                "residual_sd": _round(float(band_residuals.std(ddof=0)), 4)
                if band_residuals.size > 1
                else 0.0,
                "count": int(band_residuals.size),
            }
        )
    return points


def residual_pattern(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A plain reading of the residual plot: any drift, curvature or widening.

    The binned means are fitted with a weighted quadratic, and the linear and
    squared terms are each lifted against their own standard error. A trend mid
    range is caught by the linear term; a bowl or an arch by the quadratic one.
    A symmetric bowl has a net slope of zero and would be invisible to a line
    alone, so the curvature term is not optional.
    """
    usable = [
        point
        for point in points
        if point.get("predicted") is not None and point.get("residual") is not None
    ]
    n = len(usable)
    if n < 4:
        return {"status": "insufficient", "detail": "Too few bands to read a pattern."}

    x = np.array([float(point["predicted"]) for point in usable])
    y = np.array([float(point["residual"]) for point in usable])
    weights = np.array(
        [max(float(point.get("count") or 1), 1.0) for point in usable],
        dtype=float,
    )
    if float(x.max() - x.min()) <= 0:
        return {
            "status": "insufficient",
            "detail": "All predictions are equal, so there is no spread to check a pattern against.",
        }

    # Weighted least squares: y ~ 1 + x + x^2 on the binned means. "Weighted"
    # matters at the edges, where a band can hold five hundred rows or five;
    # ignoring that would let a single noisy band steer the verdict.
    x_centred = x - float(np.mean(x))
    design = np.column_stack(
        [np.ones(n), x_centred, x_centred**2 - np.mean(x_centred**2)]
    )
    w_sqrt = np.sqrt(weights)
    weighted_design = design * w_sqrt[:, None]
    weighted_y = y * w_sqrt
    coefficients, *_ = np.linalg.lstsq(weighted_design, weighted_y, rcond=None)
    predicted = design @ coefficients
    residual = weighted_y - weighted_design @ coefficients
    df = n - 3
    if df <= 0:
        return {"status": "insufficient", "detail": "Too few bands to read a pattern."}
    sigma_squared = float(np.sum(residual**2) / df)
    covariance = (
        sigma_squared
        * np.linalg.inv(weighted_design.T @ weighted_design)
    )

    def t_value(index: int) -> float:
        standard_error = float(np.sqrt(max(covariance[index, index], 0.0)))
        if standard_error <= 0:
            return 0.0
        return float(coefficients[index] / standard_error)

    linear = coefficients[1]
    curvature = coefficients[2]
    t_linear = t_value(1)
    t_curve = t_value(2)

    drift = abs(t_linear) >= 2.0
    curve = abs(t_curve) >= 2.0

    # Funnel: the residual spread growing with the prediction. The lowest and
    # highest thirds are compared so an edge band or two cannot decide this.
    sds = np.array([float(point.get("residual_sd") or 0.0) for point in usable])
    if n >= 6:
        third = max(int(n / 3), 1)
        low_spread = float(np.mean(sds[:third]))
        high_spread = float(np.mean(sds[-third:]))
        funnel = high_spread >= low_spread * 1.5 and high_spread - low_spread > 0.25
    else:
        low_spread = high_spread = float(np.mean(sds))
        funnel = False
    spread_growth = high_spread - low_spread

    findings = []
    if drift and curve:
        findings.append(
            "residuals both drift and bend across the fitted range, so the line "
            "is missing curvature and the relationship is not linear"
        )
    elif drift:
        findings.append(
            "residuals drift across the fitted range, which suggests an omitted "
            "curve, interaction or threshold in the relationship"
        )
    elif curve:
        findings.append(
            "residuals bend across the fitted range (a clear arch or bowl), which "
            "means a straight line is not describing this relationship"
        )
    if funnel:
        findings.append(
            "residual spread grows with the prediction (heteroscedasticity), so "
            "the standard errors are not constant across the range"
        )

    if findings:
        status = "warn"
        detail = (
            "The residual plot flags: "
            + "; ".join(findings)
            + ". Treat the printed coefficients and their uncertainty with "
            "caution, and compare a robust method or a transform."
        )
    else:
        status = "pass"
        detail = (
            "Residuals sit around zero with no drift, no bend and no widening, "
            "which is what a well-specified linear fit looks like."
        )

    return {
        "status": status,
        "slope": _round(float(linear), 4),
        "t_linear": _round(t_value(1), 4),
        "curvature": _round(float(curvature), 4),
        "t_curvature": _round(t_value(2), 4),
        "spread_growth": _round(float(spread_growth), 4),
        "detail": detail,
    }


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
            "group": frame[group_column].astype("string"),
            "value": numeric_series(frame, value_column).to_numpy(dtype=float),
        }
    ).dropna(subset=["group", "value"])
    samples: Dict[str, np.ndarray] = {}
    for label, chunk in values.groupby("group", dropna=False):
        samples[str(label)] = chunk["value"].to_numpy(dtype=float)
    return samples


def mode_of(array: np.ndarray) -> Tuple[Optional[float], int, bool]:
    """Most frequent value, its frequency, and whether the mode is unique.

    Bimodal (and wider) data has no single mode, so ``mode`` is ``None`` and
    ``unique`` is ``False`` rather than silently picking the smallest tied value.
    """
    if array.size == 0:
        return None, 0, False
    values, counts = np.unique(array, return_counts=True)
    top = int(counts.max())
    winners = values[counts == top]
    if winners.size == 1:
        return float(winners[0]), top, True
    return None, top, False


def descriptives(values: np.ndarray) -> Dict[str, Any]:
    """Mean, median, mode, SD, variance, min/max, Q1/Q3 (+ skewness/kurtosis)."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    count = int(array.size)
    if count == 0:
        return {"count": 0}
    mean = float(array.mean())
    sd = float(array.std(ddof=1)) if count > 1 else 0.0
    mode, mode_count, mode_unique = mode_of(array)
    result: Dict[str, Any] = {
        "count": count,
        "mean": _round(mean),
        "median": _round(np.median(array)),
        "mode": _round(mode) if mode is not None else None,
        "mode_count": mode_count,
        "mode_unique": mode_unique,
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


def kendall_tau_b(x: np.ndarray, y: np.ndarray) -> float:
    """Kendall's tau-b, computed from concordant/discordant pairs with ties."""
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    n = int(a.size)
    if n < 3:
        raise AnalysisError("Need at least 3 complete pairs for Kendall's tau")
    concordant = 0.0
    discordant = 0.0
    ties_x = 0.0
    ties_y = 0.0
    for i in range(n - 1):
        dx = a[i + 1 :] - a[i]
        dy = b[i + 1 :] - b[i]
        product = dx * dy
        concordant += float(np.sum(product > 0))
        discordant += float(np.sum(product < 0))
        ties_x += float(np.sum((dx == 0) & (dy != 0)))
        ties_y += float(np.sum((dy == 0) & (dx != 0)))
    denominator = np.sqrt(
        (concordant + discordant + ties_x) * (concordant + discordant + ties_y)
    )
    if denominator == 0:
        raise AnalysisError("One of the columns has zero variance, tau is undefined")
    return float((concordant - discordant) / denominator)


def correlation_test(x: np.ndarray, y: np.ndarray, method: str) -> Dict[str, Any]:
    """Pearson, Spearman, Kendall or point-biserial correlation with a p-value.

    Spearman/Kendall/point-biserial are computed exactly as the guide defines
    them: ranks for Spearman, concordant/discordant pairs for Kendall, and the
    ordinary Pearson coefficient for the binary-vs-continuous case.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size != y.size or x.size < 3:
        raise AnalysisError("Need at least 3 complete pairs for a correlation")
    if np.std(x) == 0 or np.std(y) == 0:
        raise AnalysisError("One of the columns has zero variance, correlation undefined")

    n = int(x.size)
    if method == "spearman":
        r = float(np.corrcoef(_rank_with_ties(x), _rank_with_ties(y))[0, 1])
    elif method == "kendall":
        tau = kendall_tau_b(x, y)
        variance = 2.0 * (2.0 * n + 5.0) / (9.0 * n * (n - 1.0))
        z_score = tau / np.sqrt(variance) if variance > 0 else 0.0
        return {
            "r": float(min(max(tau, -1.0), 1.0)),
            "n": n,
            "df": n - 2,
            "p_value": float(2.0 * normal_sf(abs(float(z_score)))),
            "z": float(z_score),
        }
    else:
        r = float(np.corrcoef(x, y)[0, 1])

    r = min(max(r, -1.0), 1.0)
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
        "rank_biserial": float(1.0 - (2.0 * u_a) / (n_a * n_b)),
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
    """Correlation (Pearson / Spearman / Kendall / point-biserial) with CI."""
    method = str(parameters.get("method") or "pearson").lower()
    if method not in CORRELATION_METHODS:
        raise AnalysisError(
            "method must be one of " + ", ".join(sorted(CORRELATION_METHODS))
        )
    spec = CORRELATION_METHODS[method]

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
    if method == "point_biserial":
        levels = [int(np.unique(values).size) for values in (x_values, y_values)]
        if 2 not in levels:
            warnings.append(
                "Point-biserial expects one binary (0/1) column; neither column has "
                "exactly two values, so this is an ordinary Pearson r"
            )
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
        spec["analysis_type"],
        sample_size=n,
        estimate={
            "correlation": _round(r),
            "method": method,
            "requires": spec["requires"],
            "direction": "positive" if r >= 0 else "negative",
            "strength": strength,
            "x": x_column,
            "y": y_column,
        },
        test={
            "method": spec["test"],
            "statistic": _round(r),
            "df": result["df"],
            "z": _round(result.get("z")),
            "p_value": _round(result["p_value"]),
            "alpha": 0.05,
            "significant": bool(result["p_value"] < 0.05),
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]) if interval else None,
            "upper": _round(interval[1]) if interval else None,
        },
        effect_size={
            "name": spec["effect"],
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


def correlation_matrix_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Pairwise correlation matrix across every selected numeric column.

    The MVP spec asks for a correlation matrix, which pairwise pearson/spearman
    runs cannot express: this reports every pair at once so a user can spot the
    relationships worth investigating in one pass.
    """
    method = str(parameters.get("method") or "pearson").lower()
    if method not in {"pearson", "spearman"}:
        raise AnalysisError("method must be 'pearson' or 'spearman'")

    requested = parameters.get("columns") or parameters.get("variables") or []
    if requested:
        columns = [str(column) for column in requested]
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise AnalysisError("Columns not found: " + ", ".join(missing))
    else:
        columns = [
            str(column)
            for column in frame.columns
            if pd.api.types.is_numeric_dtype(frame[column])
            and not pd.api.types.is_bool_dtype(frame[column])
        ]
    if len(columns) < 2:
        raise AnalysisError("A correlation matrix needs at least 2 numeric columns")

    # One pairwise-complete pass per column keeps the semantics identical to the
    # two-variable analysis, which drops rows missing either side.
    usable: Dict[str, np.ndarray] = {}
    for column in columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if int(series.notna().sum()) < 3:
            usable[column] = np.array([], dtype=float)
            continue
        usable[column] = series.to_numpy(dtype=float)

    included = [column for column in columns if usable[column].size >= 3]
    if len(included) < 2:
        raise AnalysisError(
            "Need at least 2 columns with 3 or more numeric values for a matrix"
        )

    matrix: List[List[Optional[float]]] = []
    p_matrix: List[List[Optional[float]]] = []
    pairs: List[Dict[str, Any]] = []
    warnings_out: List[str] = []
    best: Optional[Dict[str, Any]] = None

    for i, row_column in enumerate(included):
        row_values: List[Optional[float]] = []
        row_p: List[Optional[float]] = []
        for j, col_column in enumerate(included):
            if i == j:
                row_values.append(1.0)
                row_p.append(None)
                continue
            if j < i:
                row_values.append(matrix[j][i])
                row_p.append(p_matrix[j][i])
                continue
            left, right = usable[row_column], usable[col_column]
            mask = np.isfinite(left) & np.isfinite(right)
            x_values, y_values = left[mask], right[mask]
            if x_values.size < 3:
                row_values.append(None)
                row_p.append(None)
                continue
            try:
                result = correlation_test(x_values, y_values, method)
            except AnalysisError:
                row_values.append(None)
                row_p.append(None)
                continue
            r_value = float(result["r"])
            p_value = float(result["p_value"])
            row_values.append(_round(r_value))
            row_p.append(_round(p_value))
            pairs.append(
                {
                    "x": row_column,
                    "y": col_column,
                    "r": _round(r_value),
                    "n": int(result["n"]),
                    "p_value": _round(p_value),
                    "significant": bool(p_value < 0.05),
                }
            )
            if best is None or abs(r_value) > abs(float(best["r"])):
                best = {
                    "x": row_column,
                    "y": col_column,
                    "r": _round(r_value),
                    "p_value": _round(p_value),
                }
        matrix.append(row_values)
        p_matrix.append(row_p)

    for column in columns:
        if column not in included:
            warnings_out.append(
                f"'{column}' has fewer than 3 numeric values, excluded from the matrix"
            )

    matrix_rows = [
        {"variable": column, **{other: matrix[i][j] for j, other in enumerate(included)}}
        for i, column in enumerate(included)
    ]
    significant_pairs = [pair for pair in pairs if pair["significant"]]
    significant_pairs.sort(key=lambda pair: abs(float(pair["r"])), reverse=True)

    strongest = significant_pairs[0] if significant_pairs else None
    if strongest is None:
        summary = "Hakuna jozi yenye uhusiano muhimu kiotakwimu (p >= 0.05)."
    else:
        direction = "chanya" if float(strongest["r"]) >= 0 else "hasi"
        summary = (
            f"Uhusiano mkubwa zaidi ni {direction} kati ya {strongest['x']} na "
            f"{strongest['y']} (r = {strongest['r']}, p = {strongest['p_value']})."
        )

    return standard_result(
        "correlation_matrix",
        sample_size=int(frame.shape[0]),
        estimate={
            "method": method,
            "columns": included,
            "excluded_columns": [c for c in columns if c not in included],
            "pair_count": len(pairs),
            "significant_pairs": len(significant_pairs),
            "strongest": strongest,
            "variables": {
                column: descriptives(usable[column][np.isfinite(usable[column])])
                for column in included
            },
        },
        test={
            "method": "Pearson r" if method == "pearson" else "Spearman rho",
            "alpha": 0.05,
            "significant": bool(significant_pairs),
            "p_value": strongest["p_value"] if strongest else None,
            "statistic": strongest["r"] if strongest else None,
        },
        diagnostics={
            "matrix_size": len(included),
            "pairs_tested": len(pairs),
            "method": method,
        },
        warnings=warnings_out,
        tables={
            "matrix": matrix_rows,
            "pairs": sorted(pairs, key=lambda pair: abs(float(pair["r"])), reverse=True),
        },
    )


def _missing_group_rows(frame: pd.DataFrame, parameters: Dict[str, Any]) -> int:
    group_column = parameters.get("group_column") or parameters.get("group")
    if not group_column or group_column not in frame.columns:
        return 0
    return int(frame[group_column].isna().sum())


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
        raise AnalysisError(
            f"'{group_column}' has {len(samples)} groups; choose a two-group method "
            "or use a method designed for three or more groups"
        )
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
    dropped_groups = _missing_group_rows(frame, parameters)
    if dropped_groups:
        warnings.append(
            f"{dropped_groups} rows have a missing group label and were excluded from "
            "the comparison"
        )
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
    dropped_groups = _missing_group_rows(frame, parameters)
    if dropped_groups:
        warnings.append(
            f"{dropped_groups} rows have a missing group label and were excluded from "
            "the comparison"
        )
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
    primary_p_value = p_value
    if table.shape == (2, 2) and (
        small_expected > 0 or str(parameters.get("method") or "").lower() == "fisher"
    ):
        fisher = fisher_exact_2x2(observed)
        primary_p_value = fisher["p_value"]
        warnings.append(
            "2x2 table with small expected counts: Fisher's exact test is used as the "
            f"primary p-value (p = {fisher['p_value']:.4f})"
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
            "method": "Fisher's exact test"
            if fisher is not None
            else "Pearson chi-square test of independence",
            "statistic": _round(chi_square),
            "pearson_statistic": _round(chi_square),
            "df": int(df),
            "p_value": _round(primary_p_value),
            "pearson_p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(primary_p_value < 0.05),
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


def fisher_exact_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
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
    working[row_column] = working[row_column].astype("string")
    working[column_column] = working[column_column].astype("string")
    working = working.dropna()
    table = pd.crosstab(working[row_column], working[column_column])
    if table.shape != (2, 2):
        raise AnalysisError("Fisher's exact test requires a 2x2 contingency table")
    observed = table.to_numpy(dtype=int)
    fisher = fisher_exact_2x2(observed)
    odds_ratio = fisher["odds_ratio"]
    return standard_result(
        "fisher_exact",
        sample_size=int(observed.sum()),
        estimate={
            "row_variable": row_column,
            "column_variable": column_column,
            "contingency_table": {
                "index": [str(value) for value in table.index],
                "columns": [str(value) for value in table.columns],
                "observed": observed.tolist(),
            },
        },
        test={
            "method": "Fisher's exact test",
            "p_value": _round(fisher["p_value"]),
            "alpha": 0.05,
            "significant": bool(fisher["p_value"] < 0.05),
        },
        effect_size={
            "name": "odds_ratio",
            "value": _round(odds_ratio) if odds_ratio is not None else None,
            "interpretation": "odds ratio",
        },
        diagnostics={"rows": 2, "columns": 2},
        tables={"contingency": observed.tolist()},
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
    dropped_groups = _missing_group_rows(frame, parameters)
    if dropped_groups:
        warnings.append(
            f"{dropped_groups} rows have a missing group label and were excluded from "
            "the comparison"
        )
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
    dropped_groups = _missing_group_rows(frame, parameters)
    if dropped_groups:
        warnings.append(
            f"{dropped_groups} rows have a missing group label and were excluded from "
            "the comparison"
        )
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

    # Computed once: the plot and the reading of it come from the same points,
    # so the chart can never disagree with the verdict printed under it.
    plot_points = residual_plot(fit["fitted"], fit["residuals"])
    pattern = residual_pattern(plot_points)
    if pattern["status"] == "warn":
        warnings.append(pattern["detail"])

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
            "residual_plot": plot_points,
            "residual_pattern": pattern,
        },
        warnings=warnings,
        tables={"coefficients": fit["coefficients"]},
        meta={"target": target, "features": features},
    )


# ------------------------------------------------- additional v1 analyses
# MVP-22: the methods guide lists far more methods than the first engine
# release implemented. The handlers below add the ones that can be computed
# exactly with numpy + ``statflow.distributions`` (still no scipy).


def _as_float_array(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _positive_class(values: np.ndarray) -> np.ndarray:
    """Boolean array marking the "success" level of a binary column.

    Text levels are matched against the usual affirmative spellings (yes,
    ndiyo, true, 1). If neither level is a known affirmative, the larger
    (second) level counts as success, so 0/1 and no/yes are coded alike.
    """
    text = np.array([str(value).strip().lower() for value in values])
    levels = sorted(set(text))
    affirmative = {"1", "1.0", "yes", "y", "true", "ndiyo", "sawa"}
    for level in levels:
        if level in affirmative:
            return text == level
    if len(levels) < 2:
        return np.ones(text.size, dtype=bool)
    return text == levels[1]


def _binary_frame(
    frame: pd.DataFrame, value_column: str, group_column: str
) -> Tuple[pd.DataFrame, List[str]]:
    working = pd.DataFrame(
        {
            "group": frame[group_column].astype("string"),
            "value": frame[value_column],
        }
    ).dropna()
    if working.empty:
        raise AnalysisError("No complete rows for these two columns")
    working["success"] = _positive_class(working["value"].to_numpy())
    groups = [str(label) for label in working["group"].unique()]
    if len(groups) != 2:
        raise AnalysisError(
            f"'{group_column}' needs exactly two groups, found {len(groups)}"
        )
    return working, groups


def crosstab_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Contingency table with counts, row %, column % and a chi-square read-out."""
    row_column = require_column(
        frame,
        parameters.get("row_column") or parameters.get("row") or parameters.get("x"),
        "row_column",
    )
    column_column = require_column(
        frame,
        parameters.get("column_column")
        or parameters.get("column")
        or parameters.get("y"),
        "column_column",
    )
    if row_column == column_column:
        raise AnalysisError("Choose two different columns")

    working = frame[[row_column, column_column]].copy()
    working[row_column] = working[row_column].astype("string").fillna("<missing>")
    working[column_column] = working[column_column].astype("string").fillna("<missing>")
    table = pd.crosstab(working[row_column], working[column_column])
    observed = table.to_numpy(dtype=float)
    total = float(observed.sum())
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / max(total, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        chi_square = float(
            np.nansum(np.where(expected > 0, (observed - expected) ** 2 / expected, 0.0))
        )
    df = (table.shape[0] - 1) * (table.shape[1] - 1)
    p_value = chi_square_sf(chi_square, df) if df > 0 else None
    v_value = cramers_v(chi_square, int(total), table.shape[0], table.shape[1])
    small_expected = int(np.sum(expected < 5))

    rows = []
    for i, index in enumerate(table.index):
        row_total = observed[i].sum()
        rows.append(
            {
                "category": str(index),
                "count": int(row_total),
                "row_percentage": _round(row_total / total * 100, 2) if total else None,
                **{
                    str(column): int(observed[i][j])
                    for j, column in enumerate(table.columns)
                },
            }
        )

    warnings: List[str] = []
    if small_expected:
        warnings.append(
            f"{small_expected} of {expected.size} cells have an expected count below 5"
        )

    return standard_result(
        "crosstab",
        sample_size=int(total),
        estimate={
            "row_variable": row_column,
            "column_variable": column_column,
            "row_levels": [str(value) for value in table.index],
            "column_levels": [str(value) for value in table.columns],
            "cells": int(observed.size),
            "row_table": rows,
        },
        test={
            "method": "Pearson chi-square (reference)",
            "statistic": _round(chi_square),
            "df": int(df),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value is not None and p_value < 0.05),
        },
        effect_size={
            "name": "cramers_v",
            "value": _round(v_value),
            "interpretation": _effect_label(v_value or 0.0, 0.1, 0.3, 0.5),
        },
        diagnostics={
            "cells_with_expected_below_5": small_expected,
            "minimum_expected": _round(float(expected.min())),
            "note": "Chi-square ni ya marejeo; kwa 2x2 yenye cells ndogo tumia Fisher exact",
        },
        warnings=warnings,
        tables={
            "observed": [[_round(value, 2) for value in row] for row in observed],
            "expected": [[_round(value, 2) for value in row] for row in expected],
        },
        meta={"parameters": {"row_column": row_column, "column_column": column_column}},
    )


def normality_test_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Jarque-Bera normality read-out per numeric column (test + plots)."""
    requested = parameters.get("columns") or parameters.get("column")
    if isinstance(requested, str):
        columns = [requested]
    elif requested:
        columns = [str(column) for column in requested]
    else:
        columns = [
            str(column)
            for column in frame.columns
            if pd.api.types.is_numeric_dtype(frame[column])
        ]
    if not columns:
        raise AnalysisError("No numeric column to test for normality")

    results: Dict[str, Any] = {}
    non_normal: List[str] = []
    warnings: List[str] = []
    for column in columns:
        values = (
            _as_float_array(frame[column]) if column in frame.columns else np.array([])
        )
        if values.size < 8:
            results[column] = {
                "test": "jarque_bera",
                "sample_size": int(values.size),
                "p_value": None,
                "flag": "sample_too_small",
            }
            warnings.append(f"'{column}' has fewer than 8 numeric values")
            continue
        item = normality_diagnostics(values)
        stats = descriptives(values)
        item["outliers_percentage"] = _round(outlier_share(values), 2)
        item["mean"] = stats.get("mean")
        item["median"] = stats.get("median")
        item["sd"] = stats.get("sd")
        item["q1"] = stats.get("q1")
        item["q3"] = stats.get("q3")
        item["min"] = stats.get("min")
        item["max"] = stats.get("max")
        results[column] = item
        if item.get("flag") == "non_normal":
            non_normal.append(column)

    if non_normal:
        warnings.append(
            "Columns that look non-normal: "
            + ", ".join(non_normal)
            + " — consider rank-based or transformed methods"
        )

    first = next(iter(results.values()), {})
    return standard_result(
        "normality_test",
        sample_size=int(frame.shape[0]),
        estimate={
            "columns": columns,
            "non_normal_columns": non_normal,
            "variables": results,
            "verdict": "some columns are not normal"
            if non_normal
            else "no evidence against normality",
        },
        test={
            "method": "Jarque-Bera",
            "statistic": first.get("statistic"),
            "df": 2,
            "p_value": first.get("p_value"),
            "alpha": 0.05,
            "significant": first.get("flag") == "non_normal",
        },
        diagnostics={
            "tests": ["jarque_bera"],
            "note": "n kubwa hukataa normality hata tofauti ndogo: tazama Q-Q plot pia",
        },
        warnings=warnings,
        tables={
            "normality": [{"variable": key, **value} for key, value in results.items()]
        },
        meta={"parameters": {"columns": columns}},
    )


def one_sample_t_test_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """One-sample t-test against a benchmark mean (mu)."""
    value_column = require_column(
        frame, parameters.get("value_column") or parameters.get("value"), "value_column"
    )
    values = _as_float_array(frame[value_column])
    if values.size < 3:
        raise AnalysisError("Need at least 3 numeric values")
    try:
        hypothesized = float(
            parameters.get("mu", parameters.get("test_value", 0.0)) or 0.0
        )
    except (TypeError, ValueError):
        raise AnalysisError("Parameter 'mu' must be a number")

    level = float(parameters.get("confidence_level") or 0.95)
    n = int(values.size)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    if sd == 0:
        raise AnalysisError("The column has zero variance, the t-test is undefined")
    standard_error = sd / np.sqrt(n)
    t_statistic = (mean - hypothesized) / standard_error
    p_value = student_t_two_sided_p(float(t_statistic), n - 1)
    critical = t_critical(n - 1, level)
    interval = (mean - critical * standard_error, mean + critical * standard_error)
    effect = (mean - hypothesized) / sd

    warnings: List[str] = []
    if n < 30:
        warnings.append(
            f"Only {n} observations: the t-test assumes a roughly normal sample"
        )
    diagnostics = normality_diagnostics(values)
    if diagnostics.get("flag") == "non_normal":
        warnings.append(
            "The values look non-normal; check the Q-Q plot or use a rank-based test"
        )

    return standard_result(
        "one_sample_t_test",
        sample_size=n,
        estimate={
            "variable": value_column,
            "mean": _round(mean),
            "sd": _round(sd),
            "standard_error": _round(standard_error),
            "hypothesized_mean": _round(hypothesized),
            "mean_difference": _round(mean - hypothesized),
        },
        test={
            "method": "One-sample t-test",
            "statistic": _round(t_statistic),
            "df": n - 1,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]),
            "upper": _round(interval[1]),
            "description": "CI ya mean (si ya tofauti)",
        },
        effect_size={
            "name": "cohens_d",
            "value": _round(effect),
            "interpretation": _effect_label(effect, 0.2, 0.5, 0.8),
        },
        diagnostics={
            "normality": diagnostics,
            "outliers_percentage": _round(outlier_share(values), 2),
            "median": _round(np.median(values)),
        },
        warnings=warnings,
        tables={"descriptives": descriptives(values)},
        meta={"parameters": {"value_column": value_column, "mu": hypothesized}},
    )


def paired_t_test_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Paired t-test for two measurements of the same units."""
    first_column = require_column(
        frame, parameters.get("x") or parameters.get("first_column"), "x"
    )
    second_column = require_column(
        frame, parameters.get("y") or parameters.get("second_column"), "y"
    )
    if first_column == second_column:
        raise AnalysisError("Choose two different columns")
    first, second = paired_values(frame, first_column, second_column)
    if first.size < 3:
        raise AnalysisError("Need at least 3 complete pairs")
    differences = second - first
    n = int(differences.size)
    mean_difference = float(differences.mean())
    sd_difference = float(differences.std(ddof=1))
    if sd_difference == 0:
        raise AnalysisError("The differences have zero variance, the test is undefined")
    standard_error = sd_difference / np.sqrt(n)
    t_statistic = mean_difference / standard_error
    p_value = student_t_two_sided_p(float(t_statistic), n - 1)
    level = float(parameters.get("confidence_level") or 0.95)
    critical = t_critical(n - 1, level)
    interval = (
        mean_difference - critical * standard_error,
        mean_difference + critical * standard_error,
    )
    dz = mean_difference / sd_difference

    warnings: List[str] = []
    diagnostics = normality_diagnostics(differences)
    if diagnostics.get("flag") == "non_normal":
        warnings.append(
            "The differences look non-normal; Wilcoxon signed-rank is the safer test"
        )
    if n < 30:
        warnings.append(f"Only {n} pairs: results are sensitive to outliers")

    return standard_result(
        "paired_t_test",
        sample_size=n,
        estimate={
            "first_column": first_column,
            "second_column": second_column,
            "mean_first": _round(float(first.mean())),
            "mean_second": _round(float(second.mean())),
            "mean_difference": _round(mean_difference),
            "sd_difference": _round(sd_difference),
            "median_difference": _round(float(np.median(differences))),
        },
        test={
            "method": "Paired t-test",
            "statistic": _round(t_statistic),
            "df": n - 1,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]),
            "upper": _round(interval[1]),
            "description": "CI ya mean difference",
        },
        effect_size={
            "name": "cohens_dz",
            "value": _round(dz),
            "interpretation": _effect_label(dz, 0.2, 0.5, 0.8),
        },
        diagnostics={"normality_of_differences": diagnostics},
        warnings=warnings,
        tables={"differences": descriptives(differences)},
        meta={"parameters": {"x": first_column, "y": second_column}},
    )


def two_proportion_z_test_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Two-proportion z-test between two independent groups."""
    value_column = require_column(
        frame,
        parameters.get("value_column") or parameters.get("value"),
        "value_column",
    )
    group_column = require_column(
        frame, parameters.get("group_column") or parameters.get("group"), "group_column"
    )
    working, groups = _binary_frame(frame, value_column, group_column)
    first_group, second_group = groups[0], groups[1]
    first = working[working["group"] == first_group]
    second = working[working["group"] == second_group]
    n1, n2 = int(first.shape[0]), int(second.shape[0])
    s1, s2 = int(first["success"].sum()), int(second["success"].sum())
    if n1 < 2 or n2 < 2:
        raise AnalysisError("Both groups need at least 2 observations")
    p1, p2 = s1 / n1, s2 / n2
    pooled = (s1 + s2) / (n1 + n2)
    standard_error = np.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if standard_error == 0:
        raise AnalysisError(
            "Both groups have the same proportion (0% or 100%), the z-test is undefined"
        )
    z_score = (p1 - p2) / standard_error
    p_value = 2.0 * normal_sf(abs(float(z_score)))
    level = float(parameters.get("confidence_level") or 0.95)
    critical = normal_ppf(1 - (1 - level) / 2)
    unpooled = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    difference = p1 - p2
    interval = (difference - critical * unpooled, difference + critical * unpooled)
    odds_ratio = (
        (s1 * (n2 - s2)) / ((n1 - s1) * s2) if (n1 - s1) * s2 > 0 else None
    )
    cohens_h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2))

    warnings: List[str] = []
    for group, successes, total in ((first_group, s1, n1), (second_group, s2, n2)):
        if successes < 5 or (total - successes) < 5:
            warnings.append(
                f"'{group}' has fewer than 5 successes or failures; "
                "Fisher's exact test is safer"
            )

    return standard_result(
        "two_proportion_z_test",
        sample_size=n1 + n2,
        estimate={
            "value_column": value_column,
            "group_column": group_column,
            "groups": {
                first_group: {"n": n1, "successes": s1, "proportion": _round(p1)},
                second_group: {"n": n2, "successes": s2, "proportion": _round(p2)},
            },
            "difference_in_proportions": _round(difference),
            "pooled_proportion": _round(pooled),
        },
        test={
            "method": "Two-proportion z-test",
            "statistic": _round(z_score),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]),
            "upper": _round(interval[1]),
            "description": "CI ya difference in proportions (unpooled SE)",
        },
        effect_size={
            "name": "odds_ratio",
            "value": _round(odds_ratio) if odds_ratio is not None else None,
            "interpretation": "odds ratio",
            "cohens_h": _round(cohens_h),
        },
        diagnostics={
            "expected_successes": {
                first_group: _round(n1 * pooled, 2),
                second_group: _round(n2 * pooled, 2),
            }
        },
        warnings=warnings,
        tables={
            "contingency": [[s1, n1 - s1], [s2, n2 - s2]],
            "groups": [first_group, second_group],
        },
        meta={
            "parameters": {"value_column": value_column, "group_column": group_column}
        },
    )


def wilcoxon_signed_rank_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Wilcoxon signed-rank test for paired measurements."""
    first_column = require_column(frame, parameters.get("x"), "x")
    second_column = require_column(frame, parameters.get("y"), "y")
    if first_column == second_column:
        raise AnalysisError("Choose two different columns")
    first, second = paired_values(frame, first_column, second_column)
    pairs = int(first.size)
    differences = second - first
    differences = differences[differences != 0]
    n = int(differences.size)
    if n < 3:
        raise AnalysisError("Need at least 3 non-zero paired differences for this test")

    ranks = _rank_with_ties(np.abs(differences))
    w_plus = float(ranks[differences > 0].sum())
    w_minus = float(ranks[differences < 0].sum())
    statistic = min(w_plus, w_minus)
    mean_w = n * (n + 1) / 4.0
    _, counts = np.unique(np.abs(differences), return_counts=True)
    tie_sum = float(np.sum(counts**3 - counts))
    variance_w = n * (n + 1) * (2 * n + 1) / 24.0 - tie_sum / 48.0
    if variance_w <= 0:
        raise AnalysisError("All differences are tied, the test is undefined")
    z_score = (statistic - mean_w + 0.5) / np.sqrt(variance_w)
    p_value = 2.0 * normal_sf(abs(float(z_score)))
    effect = abs(float(z_score)) / np.sqrt(n)

    warnings: List[str] = []
    if pairs - n > 0:
        warnings.append(f"{pairs - n} pair(s) had a zero difference and were dropped")
    if n < 10:
        warnings.append(
            f"Only {n} non-zero differences: the normal approximation is rough"
        )

    return standard_result(
        "wilcoxon_signed_rank",
        sample_size=n,
        estimate={
            "first_column": first_column,
            "second_column": second_column,
            "median_difference": _round(float(np.median(differences))),
            "w_plus": _round(w_plus),
            "w_minus": _round(w_minus),
            "non_zero_differences": n,
        },
        test={
            "method": "Wilcoxon signed-rank (normal approximation)",
            "statistic": _round(statistic),
            "z": _round(z_score),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        effect_size={
            "name": "r",
            "value": _round(effect),
            "interpretation": _effect_label(effect, 0.1, 0.3, 0.5),
        },
        diagnostics={
            "zero_differences_dropped": pairs - n,
            "tie_correction": _round(tie_sum, 2),
        },
        warnings=warnings,
        meta={"parameters": {"x": first_column, "y": second_column}},
    )


def chi_square_gof_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Chi-square goodness-of-fit for one categorical column."""
    column = require_column(
        frame,
        parameters.get("column")
        or parameters.get("value_column")
        or parameters.get("x"),
        "column",
    )
    series = frame[column].astype("string").fillna("<missing>")
    counts = series.value_counts()
    levels = [str(value) for value in counts.index]
    observed = counts.to_numpy(dtype=float)
    k = int(observed.size)
    if k < 2:
        raise AnalysisError("The column needs at least two categories")

    expected_proportions = parameters.get("expected") or parameters.get(
        "expected_proportions"
    )
    if isinstance(expected_proportions, str):
        expected_proportions = [
            item.strip() for item in expected_proportions.split(",") if item.strip()
        ]
    if expected_proportions:
        try:
            weights = np.array(
                [float(item) for item in expected_proportions], dtype=float
            )
        except (TypeError, ValueError):
            raise AnalysisError("'expected' must be a list of numbers")
        if weights.size != k:
            raise AnalysisError(
                f"'expected' has {weights.size} value(s) but the column has {k} categories"
            )
        if float(weights.sum()) <= 0:
            raise AnalysisError("'expected' proportions must sum to a positive number")
        probabilities = weights / weights.sum()
        basis = "user_specified"
    else:
        probabilities = np.full(k, 1.0 / k)
        basis = "uniform"

    total = float(observed.sum())
    expected = total * probabilities
    with np.errstate(divide="ignore", invalid="ignore"):
        chi_square = float(
            np.nansum(np.where(expected > 0, (observed - expected) ** 2 / expected, 0.0))
        )
        residuals = np.where(
            expected > 0, (observed - expected) / np.sqrt(expected), 0.0
        )
    df = k - 1
    p_value = chi_square_sf(chi_square, df)
    cohens_w = float(np.sqrt(chi_square / total)) if total else 0.0

    warnings: List[str] = []
    if float(expected.min()) < 5:
        warnings.append(
            f"Smallest expected count is {float(expected.min()):.2f} (< 5): "
            "combine rare categories before trusting the p-value"
        )

    return standard_result(
        "chi_square_gof",
        sample_size=int(total),
        estimate={
            "column": column,
            "categories": levels,
            "observed": [int(value) for value in observed],
            "expected": [_round(value, 2) for value in expected],
            "expected_basis": basis,
            "probabilities": [_round(value) for value in probabilities],
            "standardized_residuals": {
                level: _round(residuals[index]) for index, level in enumerate(levels)
            },
        },
        test={
            "method": "Chi-square goodness-of-fit",
            "statistic": _round(chi_square),
            "df": int(df),
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        effect_size={
            "name": "cohens_w",
            "value": _round(cohens_w),
            "interpretation": _effect_label(cohens_w, 0.1, 0.3, 0.5),
        },
        diagnostics={
            "minimum_expected": _round(float(expected.min()), 2),
            "categories": k,
        },
        warnings=warnings,
        tables={
            "distribution": [
                {
                    "category": level,
                    "observed": int(observed[index]),
                    "expected": _round(expected[index], 2),
                    "percentage": _round(observed[index] / total * 100, 2)
                    if total
                    else None,
                    "standardized_residual": _round(residuals[index]),
                }
                for index, level in enumerate(levels)
            ]
        },
        meta={"parameters": {"column": column}},
    )


def _residualise(values: np.ndarray, controls: np.ndarray) -> np.ndarray:
    """Residuals of ``values`` regressed on ``controls`` (with intercept)."""
    design = np.column_stack([np.ones(values.size), controls])
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ coefficients


def partial_correlation_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Partial correlation of x and y after removing the control columns."""
    x_column = require_column(frame, parameters.get("x"), "x")
    y_column = require_column(frame, parameters.get("y"), "y")
    raw_controls = (
        parameters.get("control_columns")
        or parameters.get("controls")
        or parameters.get("z")
    )
    if isinstance(raw_controls, str):
        control_columns = [raw_controls] if raw_controls else []
    else:
        control_columns = [str(column) for column in (raw_controls or [])]
    control_columns = [
        column for column in control_columns if column not in {x_column, y_column}
    ]
    if not control_columns:
        raise AnalysisError(
            "At least one control column is needed; otherwise use a plain correlation"
        )
    for column in control_columns:
        if column not in frame.columns:
            raise AnalysisError(f"Control column '{column}' does not exist")

    working = pd.DataFrame(
        {
            "x": numeric_series(frame, x_column),
            "y": numeric_series(frame, y_column),
            **{column: numeric_series(frame, column) for column in control_columns},
        }
    ).dropna()
    n = int(working.shape[0])
    k = len(control_columns)
    if n < k + 4:
        raise AnalysisError(
            f"Need at least {k + 4} complete rows for {k} control variable(s), found {n}"
        )

    x_values = working["x"].to_numpy(dtype=float)
    y_values = working["y"].to_numpy(dtype=float)
    controls = working[control_columns].to_numpy(dtype=float)
    residual_x = _residualise(x_values, controls)
    residual_y = _residualise(y_values, controls)
    if np.std(residual_x) == 0 or np.std(residual_y) == 0:
        raise AnalysisError(
            "After removing the controls one variable has no variance left "
            "(the control explains it completely)"
        )
    partial_r = float(np.corrcoef(residual_x, residual_y)[0, 1])
    partial_r = min(max(partial_r, -1.0), 1.0)
    df = n - k - 2
    if abs(partial_r) >= 1.0 or df <= 0:
        p_value = 0.0
    else:
        t_statistic = partial_r * np.sqrt(df / (1 - partial_r**2))
        p_value = student_t_two_sided_p(float(t_statistic), df)

    zero_order = float(np.corrcoef(x_values, y_values)[0, 1])
    level = float(parameters.get("confidence_level") or 0.95)
    dof = n - k - 3
    interval = fisher_z_interval(partial_r, max(dof + 1, 4), level) if dof > 0 else None
    magnitude = abs(partial_r)
    strength = "strong" if magnitude >= 0.7 else "moderate" if magnitude >= 0.4 else "weak"
    if magnitude < 0.2:
        strength = "negligible"

    warnings: List[str] = []
    if n < 30:
        warnings.append(f"Only {n} complete rows: partial correlations are unstable")
    if abs(partial_r) > abs(zero_order) + 0.1:
        warnings.append(
            "Controlling changed the association a lot: check for suppression or "
            "multicollinearity among the controls"
        )

    return standard_result(
        "partial_correlation",
        sample_size=n,
        estimate={
            "x": x_column,
            "y": y_column,
            "control_columns": control_columns,
            "partial_correlation": _round(partial_r),
            "zero_order_correlation": _round(zero_order),
            "direction": "positive" if partial_r >= 0 else "negative",
            "strength": strength,
        },
        test={
            "method": "Partial correlation (t-test on df = n - k - 2)",
            "statistic": _round(partial_r),
            "df": df,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        confidence_interval={
            "level": level,
            "lower": _round(interval[0]) if interval else None,
            "upper": _round(interval[1]) if interval else None,
        },
        effect_size={
            "name": "partial_r",
            "value": _round(partial_r),
            "interpretation": strength,
        },
        diagnostics={
            "control_count": k,
            "residual_sd_x": _round(float(np.std(residual_x, ddof=1))),
            "residual_sd_y": _round(float(np.std(residual_y, ddof=1))),
        },
        warnings=warnings,
        tables={
            "scatter": {
                "x": [to_jsonable(value) for value in residual_x[:500]],
                "y": [to_jsonable(value) for value in residual_y[:500]],
                "x_label": f"{x_column} (residual)",
                "y_label": f"{y_column} (residual)",
            }
        },
        meta={"parameters": {"x": x_column, "y": y_column, "controls": control_columns}},
    )


def _glm_fit(
    design: np.ndarray,
    target: np.ndarray,
    family: str = "binomial",
    offset: Optional[np.ndarray] = None,
    max_iter: int = 60,
    tolerance: float = 1e-9,
) -> Dict[str, Any]:
    """Iteratively reweighted least squares for logit and log links.

    Only the two families the guide's regression section needs are here:
    ``binomial`` (logistic/probit-style log-odds) and ``poisson`` (log counts).
    Standard errors come from the inverse of X'WX, evaluated at the solution.
    """
    x = np.asarray(design, dtype=float)
    y = np.asarray(target, dtype=float)
    n, p = x.shape
    base = np.zeros(n) if offset is None else np.asarray(offset, dtype=float)

    beta = np.zeros(p)
    if family == "binomial":
        share = (float(y.sum()) + 0.5) / (n + 1.0)
        beta[0] = float(np.log(share / (1.0 - share)))
    else:
        beta[0] = float(np.log(max(float(y.mean()), 1e-6)))

    iterations = 0
    for iterations in range(1, max_iter + 1):
        eta = np.clip(x @ beta + base, -500.0, 500.0)
        if family == "binomial":
            mu = 1.0 / (1.0 + np.exp(-eta))
            variance = np.clip(mu * (1.0 - mu), 1e-12, None)
        else:
            mu = np.exp(eta)
            variance = np.clip(mu, 1e-12, None)
        working = eta - base + (y - mu) / variance
        root_weight = np.sqrt(variance)
        design_w = x * root_weight[:, None]
        working_w = working * root_weight
        updated, *_ = np.linalg.lstsq(design_w, working_w, rcond=None)
        delta = float(np.max(np.abs(updated - beta)))
        beta = updated
        if delta < tolerance:
            break

    eta = np.clip(x @ beta + base, -500.0, 500.0)
    if family == "binomial":
        mu = 1.0 / (1.0 + np.exp(-eta))
        variance = np.clip(mu * (1.0 - mu), 1e-12, None)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_likelihood = float(
                np.nansum(y * np.log(mu) + (1.0 - y) * np.log(1.0 - mu))
            )
    else:
        mu = np.exp(eta)
        variance = np.clip(mu, 1e-12, None)
        log_likelihood = float(
            np.sum(y * eta - mu - np.array([lgamma(v + 1.0) for v in y]))
        )

    information = x.T @ (x * variance[:, None])
    covariance = np.linalg.pinv(information)
    standard_errors = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
    return {
        "family": family,
        "coefficients": beta,
        "standard_errors": standard_errors,
        "covariance": covariance,
        "fitted": mu,
        "log_likelihood": log_likelihood,
        "iterations": iterations,
        "n": n,
        "p": p,
    }


def _design_matrix(
    frame: pd.DataFrame, features: Sequence[str]
) -> Tuple[np.ndarray, List[str]]:
    """Intercept + numeric features, raising a clear error for text columns."""
    columns: List[np.ndarray] = []
    for feature in features:
        series = numeric_series(frame, feature)
        if series.notna().sum() == 0:
            raise AnalysisError(
                f"'{feature}' has no numeric values; encode categorical predictors first"
            )
        columns.append(series.to_numpy(dtype=float))
    matrix = np.column_stack(columns) if columns else np.empty((frame.shape[0], 0))
    design = np.column_stack([np.ones(frame.shape[0]), matrix])
    return design, ["const", *[str(feature) for feature in features]]


def _binary_frame(
    frame: pd.DataFrame, target_column: str, positive_value: Any
) -> np.ndarray:
    """Encode a two-class column as 0/1 against an explicit positive class."""
    series = frame[target_column]
    if series.isna().any():
        raise AnalysisError(f"'{target_column}' contains missing values; impute them first")
    values = series.astype("object")
    positives = values == positive_value
    negatives = ~positives
    unexpected = ~(positives | negatives)
    if unexpected.any():
        raise AnalysisError(
            f"'{target_column}' has {int(unexpected.sum())} value(s) that are neither "
            f"'{positive_value}' nor the other class"
        )
    if not positives.any() or not negatives.any():
        raise AnalysisError(
            f"'{target_column}' must contain both classes; the positive class is '{positive_value}'"
        )
    return positives.to_numpy(dtype=float)


def _roc_curve(outcome: np.ndarray, fitted: np.ndarray) -> Dict[str, Any]:
    """Step-wise ROC curve plus the trapezoidal AUC."""
    events = float(outcome.sum())
    negatives = float(len(outcome) - events)
    order = np.argsort(-fitted)
    positives, negative_flags = outcome[order], 1.0 - outcome[order]
    cumulative_pos = np.cumsum(positives)
    cumulative_neg = np.cumsum(negative_flags)
    tpr = cumulative_pos / events if events else np.zeros_like(cumulative_pos)
    fpr = cumulative_neg / negatives if negatives else np.zeros_like(cumulative_neg)
    trapz = getattr(np, "trapezoid", None) or np.trapz
    auc = abs(float(trapz(tpr, fpr)))
    return {"fpr": fpr, "tpr": tpr, "auc": auc, "events": events, "non_events": negatives}


def _classification_scores(
    outcome: np.ndarray, predicted: np.ndarray, events: float, non_events: float
) -> Dict[str, Any]:
    """Confusion matrix, accuracy, sensitivity, specificity, precision and F1."""
    true_positive = int(((predicted == 1) & (outcome == 1)).sum())
    false_positive = int(((predicted == 1) & (outcome == 0)).sum())
    true_negative = int(((predicted == 0) & (outcome == 0)).sum())
    false_negative = int(((predicted == 0) & (outcome == 1)).sum())
    accuracy = (true_positive + true_negative) / len(outcome) if len(outcome) else None
    sensitivity = true_positive / events if events else None
    specificity = true_negative / non_events if non_events else None
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else None
    )
    f1 = (
        2 * precision * sensitivity / (precision + sensitivity)
        if precision and sensitivity and (precision + sensitivity)
        else None
    )
    return {
        "accuracy": _round(accuracy),
        "sensitivity": _round(sensitivity),
        "specificity": _round(specificity),
        "precision": _round(precision),
        "f1": _round(f1),
        "confusion_matrix": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
    }


def logistic_regression_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Binary logistic regression: odds ratios, AUC and a confusion matrix."""
    target_column = require_column(frame, parameters.get("target"), "target")
    raw_features = parameters.get("features") or []
    if isinstance(raw_features, str):
        raw_features = [raw_features]
    features = [str(name) for name in raw_features]
    if not features:
        raise AnalysisError("Logistic regression needs at least one feature column")

    # A binary target is a hard requirement: with more than two distinct values
    # the model is a multinomial problem, and silently thresholding a continuous
    # column would report an odds ratio for a split the reader never asked for.
    distinct = frame[target_column].dropna().unique()
    if len(distinct) > 2:
        raise AnalysisError(
            f"'{target_column}' has {len(distinct)} distinct values, so it is not a binary "
            "outcome. Use multinomial or ordinal logistic for a categorical target"
        )

    positive_value = parameters.get("positive_value")
    if positive_value is None:
        counts = frame[target_column].value_counts()
        if counts.empty:
            raise AnalysisError(f"'{target_column}' is empty")
        if len(counts) < 2:
            raise AnalysisError(
                f"'{target_column}' has a single value; logistic regression needs two classes"
            )
        # The rarer class is the event by default. Picking the majority would
        # silently flip the sign of every coefficient, which is the kind of
        # inversion that only shows up when someone reads the odds ratios.
        positive_value = counts.index[-1]
        if len(counts) == 2 and counts.iloc[0] == counts.iloc[1]:
            raise AnalysisError(
                f"'{target_column}' is evenly split, so there is no obvious event class; "
                "pass positive_value to say which value counts as 1"
            )
    outcome = _binary_frame(frame, target_column, positive_value)

    usable = np.ones(outcome.shape[0], dtype=bool)
    for feature in features:
        usable &= numeric_series(frame, feature).notna().to_numpy()
    complete = int(usable.sum())
    if complete < 3:
        raise AnalysisError("Fewer than 3 complete rows remain after dropping missing values")
    outcome = outcome[usable]
    if len(np.unique(outcome)) < 2:
        raise AnalysisError("After dropping missing rows only one class remains")

    design, names = _design_matrix(frame.loc[usable, :], features)
    fit = _glm_fit(design, outcome, family="binomial")
    beta = fit["coefficients"]
    standard_errors = fit["standard_errors"]
    z_scores = np.divide(
        beta, standard_errors, out=np.zeros_like(beta), where=standard_errors > 0
    )
    p_values = _two_sided_normal_p(z_scores)
    odds_ratios = np.exp(np.clip(beta, -50.0, 50.0))

    n_obs = float(len(outcome))
    events = float(outcome.sum())
    non_events = n_obs - events
    share = events / n_obs
    null_log_likelihood = float(
        np.sum(outcome * np.log(share) + (1.0 - outcome) * np.log(1.0 - share))
    )
    mcfadden = 1.0 - fit["log_likelihood"] / null_log_likelihood if null_log_likelihood else None
    cox_snell = 1 - np.exp(2.0 * (fit["log_likelihood"] - null_log_likelihood) / n_obs)
    denominator = 1 - np.exp(2.0 * null_log_likelihood / n_obs)
    nagelkerke = cox_snell / denominator if denominator else None

    roc = _roc_curve(outcome, fit["fitted"])
    threshold = float(parameters.get("threshold", 0.5))
    predicted = (fit["fitted"] >= threshold).astype(float)
    scores = _classification_scores(outcome, predicted, events, non_events)

    coefficients = [
        {
            "term": name,
            "beta": _round(coefficient),
            "standard_error": _round(error),
            "z": _round(z),
            "p_value": _round(p_value),
            "odds_ratio": _round(odds_ratio),
            "or_ci_lower": _round(_exp_clipped(coefficient - 1.96 * error)) if error > 0 else None,
            "or_ci_upper": _round(_exp_clipped(coefficient + 1.96 * error)) if error > 0 else None,
            "significant": bool(p_value < 0.05),
        }
        for name, coefficient, error, z, p_value, odds_ratio in zip(
            names, beta, standard_errors, z_scores, p_values, odds_ratios
        )
    ]

    warnings: List[str] = []
    required_events = 10 * (len(names) - 1)
    if events < required_events or non_events < required_events:
        warnings.append(
            f"Rule of thumb: about {required_events} observations in each class (10 per "
            f"parameter); you have {int(events)} and {int(non_events)}. Odds ratios are "
            "unstable, so widen the interval or simplify the model"
        )
    if roc["auc"] < 0.6:
        warnings.append(
            f"AUC of {roc['auc']:.2f} means weak discrimination; the features barely "
            "separate the two classes"
        )
    if float(np.max(np.abs(z_scores))) > 4:
        warnings.append(
            "Very large coefficients suggest separation; use Firth logistic regression"
        )
    if complete < n_obs:
        warnings.append(f"{int(n_obs - complete)} row(s) dropped for missing predictors")

    return standard_result(
        "logistic_regression",
        sample_size=int(n_obs),
        estimate={
            "target": target_column,
            "features": features,
            "positive_class": str(positive_value),
            "events": int(events),
            "non_events": int(non_events),
            "coefficients": coefficients,
        },
        test={
            "method": "Logistic regression (IRLS, logit link)",
            "statistic": None,
            "p_value": None,
            "alpha": 0.05,
            "significant": None,
        },
        confidence_interval={
            "level": 0.95,
            "basis": "Wald: odds ratio +/- 1.96 standard errors on the log-odds scale",
        },
        effect_size={
            "name": "pseudo_r_squared",
            "value": _round(mcfadden),
            "interpretation": (
                f"McFadden pseudo R2 {_round(mcfadden)}; Nagelkerke {_round(nagelkerke)}; "
                f"Cox-Snell {_round(cox_snell)}"
            ),
        },
        diagnostics={
            "auc": _round(roc["auc"]),
            "threshold": _round(threshold),
            "log_likelihood": _round(fit["log_likelihood"]),
            "null_log_likelihood": _round(null_log_likelihood),
            "iterations": int(fit["iterations"]),
            "events_per_parameter": _round(events / max(len(names) - 1, 1)),
            "rows_dropped": int(n_obs - complete),
            **scores,
        },
        warnings=warnings,
        tables={
            "roc": {
                "fpr": [to_jsonable(value) for value in np.round(roc["fpr"], 4)],
                "tpr": [to_jsonable(value) for value in np.round(roc["tpr"], 4)],
                "auc": _round(roc["auc"]),
            }
        },
        meta={"parameters": {"target": target_column, "features": features}},
    )


def poisson_regression_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Poisson regression for counts: incidence rate ratios and overdispersion."""
    target_column = require_column(frame, parameters.get("target"), "target")
    raw_features = parameters.get("features") or []
    if isinstance(raw_features, str):
        raw_features = [raw_features]
    features = [str(name) for name in raw_features]
    if not features:
        raise AnalysisError("Poisson regression needs at least one feature column")

    counts = numeric_series(frame, target_column)
    valid = counts.notna() & (counts >= 0) & (counts == np.floor(counts))
    usable = np.array(valid.to_numpy(), dtype=bool, copy=True)
    for feature in features:
        usable &= numeric_series(frame, feature).notna().to_numpy()
    if int(usable.sum()) < 3:
        raise AnalysisError("Fewer than 3 complete rows remain after dropping invalid counts")
    outcome = counts[usable].to_numpy(dtype=float)
    if outcome.max() < 1:
        raise AnalysisError("The count column is all zeros; there is nothing to model")

    design, names = _design_matrix(frame.loc[usable, :], features)
    offset = None
    exposure_column = parameters.get("exposure")
    if exposure_column:
        exposure_column = require_column(frame, exposure_column, "exposure")
        exposure = numeric_series(frame, exposure_column)[usable].to_numpy(dtype=float)
        if np.any(exposure <= 0):
            raise AnalysisError("The exposure column must be strictly positive (log link)")
        offset = np.log(exposure)

    fit = _glm_fit(design, outcome, family="poisson", offset=offset)
    beta = fit["coefficients"]
    standard_errors = fit["standard_errors"]
    z_scores = np.divide(
        beta, standard_errors, out=np.zeros_like(beta), where=standard_errors > 0
    )
    p_values = _two_sided_normal_p(z_scores)
    rate_ratios = np.exp(np.clip(beta, -50.0, 50.0))

    fitted = fit["fitted"]
    pearson_chi_square = float(np.sum((outcome - fitted) ** 2 / np.clip(fitted, 1e-12, None)))
    degrees = int(max(fit["n"] - fit["p"], 1))
    dispersion = pearson_chi_square / degrees
    observed_variance = float(np.var(outcome, ddof=1)) if len(outcome) > 1 else 0.0
    variance_ratio = observed_variance / float(np.mean(outcome)) if outcome.mean() else None
    zeros = int((outcome == 0).sum())
    zero_share = zeros / len(outcome)
    expected_zero_share = float(np.mean(np.exp(-fitted)))

    rows = [
        {
            "term": name,
            "beta": _round(coefficient),
            "standard_error": _round(error),
            "z": _round(z),
            "p_value": _round(p_value),
            "rate_ratio": _round(rate_ratio),
            "rr_ci_lower": _round(_exp_clipped(coefficient - 1.96 * error)) if error > 0 else None,
            "rr_ci_upper": _round(_exp_clipped(coefficient + 1.96 * error)) if error > 0 else None,
            "significant": bool(p_value < 0.05),
        }
        for name, coefficient, error, z, p_value, rate_ratio in zip(
            names, beta, standard_errors, z_scores, p_values, rate_ratios
        )
    ]

    warnings: List[str] = []
    if dispersion > 1.5:
        warnings.append(
            f"Dispersion ratio {dispersion:.2f} is above 1: the variance exceeds the mean "
            "(overdispersion), so standard errors are too small. Use Negative Binomial "
            "regression instead"
        )
    # The raw variance-to-mean ratio only means anything when every row has the
    # same expected count. With an exposure offset the means differ by design,
    # so the ratio is large even for perfectly Poisson data; in that case the
    # fitted-versus-observed check below is the one to read.
    if variance_ratio and variance_ratio > 1.5 and float(fitted.std()) < 0.1 * float(
        fitted.mean()
    ):
        warnings.append(
            f"Variance-to-mean ratio is {variance_ratio:.2f} with a near-constant "
            "expected count, which signals overdispersion"
        )
    if zero_share > expected_zero_share + 0.15:
        warnings.append(
            f"{zero_share:.0%} of counts are zero but only {expected_zero_share:.0%} are "
            "expected under Poisson; consider zero-inflated or hurdle models"
        )
    if outcome.max() > 10 and np.mean(outcome) > 0:
        warnings.append("The count column has large values; check that it is a count, not a currency")
    if not valid.all():
        warnings.append(
            f"{int((~valid).sum())} row(s) dropped: counts must be non-negative whole numbers"
        )

    return standard_result(
        "poisson_regression",
        sample_size=int(len(outcome)),
        estimate={
            "target": target_column,
            "features": features,
            "exposure": exposure_column,
            "mean_count": _round(float(np.mean(outcome))),
            "coefficients": rows,
        },
        test={
            "method": "Poisson regression (IRLS, log link)",
            "statistic": _round(pearson_chi_square),
            "df": degrees,
            "p_value": None,
            "alpha": 0.05,
            "significant": None,
        },
        confidence_interval={
            "level": 0.95,
            "basis": "Wald: rate ratio +/- 1.96 standard errors on the log scale",
        },
        effect_size={
            "name": "deviance_explained",
            "value": _round(max(0.0, 1 - pearson_chi_square / max(outcome.sum(), 1.0))),
            "interpretation": "Share of the raw count total not explained by the model",
        },
        diagnostics={
            "pearson_chi_square": _round(pearson_chi_square),
            "dispersion_ratio": _round(dispersion),
            "variance_to_mean_ratio": _round(variance_ratio),
            "log_likelihood": _round(fit["log_likelihood"]),
            "iterations": int(fit["iterations"]),
            "zero_share": _round(zero_share),
            "expected_zero_share": _round(expected_zero_share),
        },
        warnings=warnings,
        tables={
            "observed_vs_fitted": {
                "observed": [to_jsonable(value) for value in outcome[:500]],
                "fitted": [to_jsonable(value) for value in np.round(fitted[:500], 4)],
            }
        },
        meta={"parameters": {"target": target_column, "features": features}},
    )


def cronbach_alpha_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Internal consistency of a multi-item scale: alpha, omega proxy, item stats."""
    raw_items = parameters.get("items") or parameters.get("columns") or []
    if isinstance(raw_items, str):
        raw_items = [raw_items]
    items = [str(name) for name in raw_items]
    if len(items) < 2:
        raise AnalysisError("Cronbach's alpha needs at least two item columns")
    if len(set(items)) != len(items):
        raise AnalysisError("Each item column must be listed once")

    block = frame[items].apply(pd.to_numeric, errors="coerce")
    complete_rows = int(block.notna().all(axis=1).sum())
    if complete_rows < 3:
        raise AnalysisError("Fewer than 3 respondents answered every item")
    values = block.dropna()
    k = values.shape[1]
    n = values.shape[0]
    item_variances = values.var(axis=0, ddof=1).to_numpy(dtype=float)
    total_variance = values.sum(axis=1).var(ddof=1)
    if total_variance <= 0:
        raise AnalysisError("Every respondent has the same total score; alpha is undefined")

    alpha = float(k / (k - 1) * (1 - item_variances.sum() / total_variance))

    # Standardised alpha is the scale-free version, and omega (the mean of
    # item-total correlations divided by the total variance) is the modern
    # alternative that does not assume tau-equivalence.
    standardised = values / values.std(axis=0, ddof=1).replace(0, np.nan)
    standardised = standardised.dropna()
    standardised_total = standardised.sum(axis=1)
    item_total = [
        float(standardised[column].corr(standardised_total - standardised[column]))
        for column in standardised.columns
    ]
    omega = float(np.mean(item_total) / standardised_total.var(ddof=1)) if standardised_total.var(ddof=1) > 0 else None

    item_rows: List[Dict[str, Any]] = []
    for index, column in enumerate(items):
        series = values[column]
        alpha_if_deleted = None
        if k > 2 and item_variances[index] > 0:
            remaining = values.drop(columns=[column]).sum(axis=1).var(ddof=1)
            if remaining > 0:
                alpha_if_deleted = float(
                    (k - 1) / (k - 2) * (1 - (item_variances.sum() - item_variances[index]) / remaining)
                )
        item_rows.append(
            {
                "item": column,
                "mean": _round(float(series.mean())),
                "standard_deviation": _round(float(series.std(ddof=1))),
                "item_rest_correlation": _round(item_total[index]),
                "item_total_correlation": _round(float(series.corr(values.sum(axis=1) - series))),
                "alpha_if_deleted": _round(alpha_if_deleted),
            }
        )

    average_intercorrelation = float(np.mean(item_total))
    standard_error = None
    # The alpha standard-error formula can go negative for high average
    # inter-item correlation, which means the delta-method variance is not
    # usable; an interval is simply not reported in that case.
    if average_intercorrelation > 0 and n > 2:
        alpha_variance = (
            k / (k - 1)
            * (1 - 2 * k * average_intercorrelation + k * average_intercorrelation**2)
            / (n - 1)
        )
        if alpha_variance > 0:
            standard_error = float(np.sqrt(alpha_variance))

    if alpha >= 0.9:
        label = "excellent internal consistency, but check for redundant items"
    elif alpha >= 0.7:
        label = "acceptable internal consistency"
    elif alpha >= 0.6:
        label = "borderline; many journals require 0.7 or higher"
    else:
        label = "poor internal consistency; the items may not measure one construct"

    warnings: List[str] = []
    if alpha < 0.7:
        warnings.append(f"Alpha of {alpha:.2f} is below the usual 0.7 threshold. {label.capitalize()}")
    if alpha > 0.9:
        warnings.append("Alpha above 0.9 often means items are redundant rather than reliable")
    if n < 30:
        warnings.append(f"Only {n} complete respondents; alpha is unstable below about 30")
    dropped = int(frame.shape[0] - complete_rows)
    if dropped:
        warnings.append(f"{dropped} respondent(s) skipped because they missed at least one item")
    weakest = min(item_total)
    if weakest < 0.3:
        warnings.append(
            f"The weakest item correlates {weakest:.2f} with the rest of the scale; consider "
            "removing it and re-running alpha"
        )

    return standard_result(
        "cronbach_alpha",
        sample_size=n,
        estimate={
            "items": items,
            "item_count": k,
            "cronbach_alpha": _round(alpha),
            "standardised_alpha": _round(alpha),
            "omega": _round(omega),
            "average_inter_item_correlation": _round(average_intercorrelation),
            "total_score_mean": _round(float(values.sum(axis=1).mean())),
            "total_score_sd": _round(float(values.sum(axis=1).std(ddof=1))),
        },
        test={
            "method": "Cronbach's alpha",
            "statistic": _round(alpha),
            "p_value": None,
            "alpha": None,
            "significant": None,
        },
        confidence_interval={
            "level": 0.95,
            "lower": _round(alpha - 1.96 * standard_error) if standard_error else None,
            "upper": _round(alpha + 1.96 * standard_error) if standard_error else None,
            "basis": "alpha +/- 1.96 standard errors",
        },
        effect_size={
            "name": "average_inter_item_correlation",
            "value": _round(average_intercorrelation),
            "interpretation": label,
        },
        diagnostics={
            "alpha_standard_error": _round(standard_error),
            "item_variance_sum": _round(float(item_variances.sum())),
            "total_variance": _round(float(total_variance)),
            "complete_rows": complete_rows,
            "rows_dropped": dropped,
        },
        warnings=warnings,
        tables={"items": item_rows},
        meta={"parameters": {"items": items}},
    )


def _kaplan_meier_curve(times: np.ndarray, events: np.ndarray) -> Dict[str, Any]:
    """Product-limit survival estimates with Greenwood standard errors."""
    order = np.argsort(times, kind="mergesort")
    times, events = times[order], events[order]
    unique_times = np.unique(times[events == 1])
    survival = 1.0
    greenwood = 0.0
    at_risk = len(times)
    rows: List[Dict[str, Any]] = [
        {"time": 0.0, "survival": 1.0, "at_risk": at_risk, "events": 0, "censored": 0}
    ]
    for time in unique_times:
        deaths = int(((times == time) & (events == 1)).sum())
        censored = int(((times == time) & (events == 0)).sum())
        if at_risk <= 0:
            break
        survival *= 1.0 - deaths / at_risk
        if deaths:
            greenwood += deaths / (at_risk * (at_risk - deaths)) if at_risk > deaths else 1.0
        rows.append(
            {
                "time": float(time),
                "survival": float(survival),
                "at_risk": at_risk,
                "events": deaths,
                "censored": censored,
            }
        )
        at_risk -= deaths + censored
    for row in rows:
        variance = row["survival"] ** 2 * greenwood if row["time"] > 0 else 0.0
        standard_error = float(np.sqrt(variance)) if variance > 0 else 0.0
        row["standard_error"] = standard_error
        row["ci_lower"] = float(max(0.0, row["survival"] - 1.96 * standard_error))
        row["ci_upper"] = float(min(1.0, row["survival"] + 1.96 * standard_error))
    return {
        "rows": rows,
        "median": _median_survival(rows),
        "final_survival": rows[-1]["survival"] if len(rows) > 1 else 1.0,
    }


def _median_survival(rows: List[Dict[str, Any]]) -> Optional[float]:
    """First time at which survival drops to 0.5 or below."""
    for row in rows:
        if row["survival"] <= 0.5:
            return row["time"]
    return None


def _log_rank_test(
    times: np.ndarray, events: np.ndarray, groups: np.ndarray
) -> Dict[str, Any]:
    """Two-group log-rank test of equal survival curves."""
    group_a = groups == groups[0]
    group_b = ~group_a
    times_a, events_a = times[group_a], events[group_a]
    times_b, events_b = times[group_b], events[group_b]
    event_times = np.unique(times[events == 1])
    observed_a = 0.0
    expected_a = 0.0
    variance = 0.0
    for time in event_times:
        at_risk_a = int((times_a >= time).sum())
        at_risk_b = int((times_b >= time).sum())
        at_risk = at_risk_a + at_risk_b
        deaths = int(((times == time) & (events == 1)).sum())
        if at_risk < 2 or deaths < 1:
            continue
        observed_a += float(((times_a == time) & (events_a == 1)).sum())
        expected_a += deaths * at_risk_a / at_risk
        variance += (
            deaths * (at_risk_a / at_risk) * (1 - at_risk_a / at_risk) * (at_risk - deaths) / (at_risk - 1)
        )
    if variance <= 0:
        return {"chi_square": None, "p_value": None, "observed": None, "expected": None, "df": 1}
    chi_square = (observed_a - expected_a) ** 2 / variance
    return {
        "chi_square": chi_square,
        "p_value": float(chi_square_sf(chi_square, 1)),
        "observed": observed_a,
        "expected": expected_a,
        "variance": variance,
        "df": 1,
    }


def kaplan_meier_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Kaplan-Meier survival curve, median survival and optional log-rank test."""
    time_column = require_column(
        frame, parameters.get("time_column") or parameters.get("duration"), "time_column"
    )
    event_column = require_column(
        frame, parameters.get("event_column") or parameters.get("status"), "event_column"
    )
    if time_column == event_column:
        raise AnalysisError("The time column and the event column must be different")

    times_raw = numeric_series(frame, time_column)
    events_raw = frame[event_column]
    if events_raw.isna().any():
        raise AnalysisError(f"'{event_column}' contains missing values; censor them explicitly")

    unique_events = list(pd.unique(events_raw))
    if len(unique_events) > 2 and parameters.get("event_coding") is None:
        raise AnalysisError(
            f"'{event_column}' has {len(unique_events)} distinct values {unique_events[:5]}, "
            "so it is not an event indicator. Recode it to 1 = event, 0 = censored, "
            "or pass event_coding to say which value counts as the event"
        )
    # A lone distinct value means the other outcome never occurred, so every row
    # is censored. Treating the only value as the event would invent 100%
    # mortality out of a column that simply never recorded an event.
    all_censored = len(unique_events) == 1 and parameters.get("event_coding") is None
    coding = parameters.get("event_coding")
    if coding is not None:
        event_value = coding
        if coding not in set(unique_events):
            raise AnalysisError(
                f"event_coding={coding!r} does not appear in '{event_column}' "
                f"(it holds {unique_events[:5]})"
            )
    else:
        numeric_events = pd.to_numeric(events_raw, errors="coerce")
        if numeric_events.notna().all() and set(numeric_events.unique()) <= {0, 1}:
            event_value = 1
        else:
            # 'True'/'False', 'Yes'/'No', 'dead'/'alive' and 1/0 are all common.
            preferred = [
                value
                for value in (1, True, "Yes", "yes", "TRUE", "True", "event", "Event")
                if value in set(unique_events)
            ]
            event_value = preferred[0] if preferred else unique_events[0]

    events = (
        np.zeros(len(events_raw), dtype=float)
        if all_censored
        else (events_raw == event_value).to_numpy(dtype=float)
    )
    usable = times_raw.notna().to_numpy() & (times_raw >= 0).to_numpy()
    n = int(usable.sum())
    if n < 3:
        raise AnalysisError("Fewer than 3 valid rows with a time and an event flag")
    times = times_raw[usable].to_numpy(dtype=float)
    events = events[usable]
    if events.sum() == 0:
        return standard_result(
            "kaplan_meier",
            status=INSUFFICIENT,
            sample_size=n,
            estimate={
                "time_column": time_column,
                "event_column": event_column,
                "event_value": str(event_value),
            },
            warnings=[
                "No events were observed, so the survival curve stays at 1.0 throughout"
            ],
            meta={"parameters": {"time_column": time_column, "event_column": event_column}},
        )

    overall = _kaplan_meier_curve(times, events)
    warnings: List[str] = []
    censor_share = 1 - events.sum() / n
    if censor_share > 0.6:
        warnings.append(
            f"{censor_share:.0%} of observations are censored; the tail of the curve rests on "
            "few subjects, so read late survival probabilities with care"
        )
    if overall["median"] is None:
        warnings.append("Survival never falls to 0.5, so the median survival time is not reached")

    # Optional group comparison: one curve per level, plus a log-rank test when
    # the group column has exactly two levels.
    curves: Dict[str, Any] = {}
    log_rank: Optional[Dict[str, Any]] = None
    group_column = parameters.get("group_column")
    if group_column:
        group_column = require_column(frame, group_column, "group_column")
        groups_all = frame[group_column]
        group_mask = groups_all.notna().to_numpy() & usable
        groups = groups_all[group_mask].astype(str).to_numpy()
        times_g, events_g = times[group_mask], events[group_mask]
        levels = list(pd.unique(groups))
        for level in levels:
            mask = groups == level
            if events_g[mask].sum() > 0:
                curves[str(level)] = _kaplan_meier_curve(times_g[mask], events_g[mask])
        if len(levels) == 2:
            log_rank = _log_rank_test(times_g, events_g, groups)
        elif len(levels) > 2:
            warnings.append(
                f"The group column has {len(levels)} levels; a curve is drawn for each but the "
                "log-rank test compares only two groups at a time"
            )

    def curve_rows(curve: Dict[str, Any], with_counts: bool) -> List[Dict[str, Any]]:
        rows = []
        for row in curve["rows"]:
            entry = {
                "time": _round(row["time"]),
                "survival": _round(row["survival"]),
                "ci_lower": _round(row["ci_lower"]),
                "ci_upper": _round(row["ci_upper"]),
                "at_risk": row["at_risk"],
            }
            if with_counts:
                entry["events"] = row["events"]
                entry["censored"] = row["censored"]
            rows.append(entry)
        return rows

    tables: Dict[str, Any] = {"curve": curve_rows(overall, True)}
    for level, curve in curves.items():
        tables[f"curve_{level}"] = curve_rows(curve, False)

    p_value = log_rank.get("p_value") if log_rank else None
    return standard_result(
        "kaplan_meier",
        sample_size=n,
        estimate={
            "time_column": time_column,
            "event_column": event_column,
            "event_value": str(event_value),
            "group_column": group_column,
            "events": int(events.sum()),
            "censored": int(n - events.sum()),
            "median_survival": _round(overall["median"]),
            "final_survival": _round(overall["final_survival"]),
            "group_median_survival": {
                level: _round(curve["median"]) for level, curve in curves.items()
            },
        },
        test={
            "method": "Kaplan-Meier product-limit estimator"
            + (" with log-rank test" if log_rank else ""),
            "statistic": _round(log_rank.get("chi_square")) if log_rank else None,
            "df": log_rank.get("df") if log_rank else None,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05) if p_value is not None else None,
        },
        confidence_interval={
            "level": 0.95,
            "basis": "Greenwood standard error on the survival probability",
        },
        effect_size={
            "name": "survival_at_end_of_follow_up",
            "value": _round(overall["final_survival"]),
            "interpretation": (
                f"Estimated probability of surviving to the last observed time "
                f"({_round(overall['rows'][-1]['time'])})"
            ),
        },
        diagnostics={
            "censored_share": _round(censor_share),
            "events": int(events.sum()),
            "curve_points": len(overall["rows"]),
            "log_rank_observed": _round(log_rank.get("observed")) if log_rank else None,
            "log_rank_expected": _round(log_rank.get("expected")) if log_rank else None,
        },
        warnings=warnings,
        tables=tables,
        meta={"parameters": {"time_column": time_column, "event_column": event_column}},
    )


# __ENGINE_END__
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
    "correlation_matrix": correlation_matrix_analysis,
    "welch_t_test": welch_t_test_analysis,
    "mann_whitney": mann_whitney_analysis,
    "chi_square": chi_square_analysis,
    "fisher_exact": fisher_exact_analysis,
    "one_way_anova": anova_analysis,
    "kruskal_wallis": kruskal_wallis_analysis,
    "linear_regression": linear_regression_analysis,
    "crosstab": crosstab_analysis,
    "kendall": lambda frame, parameters: correlation_analysis_v2(
        frame, {**parameters, "method": "kendall"}
    ),
    "point_biserial": lambda frame, parameters: correlation_analysis_v2(
        frame, {**parameters, "method": "point_biserial"}
    ),
    "normality_tests": normality_test_analysis,
    "one_sample_t_test": one_sample_t_test_analysis,
    "paired_t_test": paired_t_test_analysis,
    "two_proportion_z_test": two_proportion_z_test_analysis,
    "wilcoxon_signed_rank": wilcoxon_signed_rank_analysis,
    "chi_square_gof": chi_square_gof_analysis,
    "partial_correlation": partial_correlation_analysis,
    "logistic_regression": logistic_regression_analysis,
    "poisson_regression": poisson_regression_analysis,
    "cronbach_alpha": cronbach_alpha_analysis,
    "kaplan_meier": kaplan_meier_analysis,
}

REQUIRED_PARAMETERS = {
    "descriptive": ["columns (optional)"],
    "frequency": ["columns or column (optional)"],
    "pearson": ["x", "y"],
    "spearman": ["x", "y"],
    "correlation_matrix": ["columns (optional, all numeric by default)"],
    "welch_t_test": ["value_column", "group_column"],
    "mann_whitney": ["value_column", "group_column"],
    "chi_square": ["row_column", "column_column"],
    "fisher_exact": ["row_column", "column_column"],
    "one_way_anova": ["value_column", "group_column"],
    "kruskal_wallis": ["value_column", "group_column"],
    "linear_regression": ["target", "features"],
    "crosstab": ["row_column", "column_column"],
    "kendall": ["x", "y"],
    "point_biserial": ["x", "y"],
    "normality_tests": ["column (optional, all numeric by default)"],
    "normality_test": ["column (optional, all numeric by default)"],  # legacy alias
    "one_sample_t_test": ["column", "mu (optional, default 0)"],
    "paired_t_test": ["x", "y"],
    "two_proportion_z_test": ["column", "group_column (optional; two columns otherwise)"],
    "wilcoxon_signed_rank": ["x", "y"],
    "chi_square_gof": ["column", "expected (optional, default uniform)"],
    "partial_correlation": ["x", "y", "controls (optional)"],
    "logistic_regression": [
        "target (binary)",
        "features",
        "positive_value (optional)",
        "threshold (optional, default 0.5)",
    ],
    "poisson_regression": ["target (count)", "features", "exposure (optional)"],
    "cronbach_alpha": ["items (two or more item columns)"],
    "kaplan_meier": [
        "time_column",
        "event_column",
        "group_column (optional)",
        "event_coding (optional)",
    ],
    "mcnemar": ["before_column", "after_column"],
    "one_sample_z_test": ["value_column", "mu (optional, default 0)", "sigma (optional)"],
    "two_way_anova": ["value_column", "group_column", "second_group_column"],
    "ordinal_logit": ["target (ordered, 3+ categories)", "features"],
    "probit": ["target (0/1)", "features", "positive_category (optional)"],
    "negative_binomial": ["target (counts)", "features", "exposure_column (optional offset)"],
    "zero_inflated": ["target (counts)", "features", "distribution (poisson/nb)"],
    "hurdle": ["target (counts)", "features", "distribution (poisson/nb)"],
    "tobit": ["target (censored)", "features", "threshold", "censor_type (right/left)"],
    "ridge_lasso": ["target", "features", "penalty (ridge/lasso/elastic_net)", "folds", "seed"],
    "quantile_regression": ["target", "features", "quantiles (e.g. 0.1, 0.5, 0.9)"],
    "mcdonalds_omega": ["columns (items, 2+)"],
    "cohens_kappa": ["row_column", "column_column"],
    "fleiss_kappa": ["columns (3+ raters)"],
    "icc": ["columns (2+ raters or occasions)"],
    "linear_probability_model": ["target (0/1)", "features", "positive_category (optional)"],
}


# The second wave lives in ``app.statflow.advanced``. That module imports the
# shared helpers from here and registers itself at the end of its own module
# body, so the dependency stays one-way and neither import order can fail: if
# ``stats_engine`` is imported first it simply has not met ``advanced`` yet.
ADVANCED_ANALYSES: Dict[str, str] = {
    "mcnemar": "mcnemar_test",
    "one_sample_z_test": "one_sample_z_test",
    "two_way_anova": "two_way_anova",
    "ordinal_logit": "ordinal_logit",
}


#: Analyses exposed by ``models_regression``. Kept as an explicit map, like
#: ``ADVANCED_ANALYSES``, so a missing or renamed handler shows up as a
#: catalogue/engine mismatch rather than as a silent 500 at run time.
REGRESSION_ANALYSES: Dict[str, str] = {
    "probit": "probit",
    "linear_probability_model": "linear_probability_model",
}

#: Analyses exposed by ``models_counts``: the count-outcome models.
COUNT_ANALYSES: Dict[str, str] = {
    "negative_binomial": "negative_binomial",
    "zero_inflated": "zero_inflated",
    "hurdle": "hurdle",
}

#: Analyses exposed by ``models_estimators``: censored, penalised and quantile
#: regression.
#: Analyses exposed by ``models_reliability``: agreement and internal
#: consistency over a response matrix.
RELIABILITY_ANALYSES: Dict[str, str] = {
    "mcdonalds_omega": "mcdonalds_omega",
    "cohens_kappa": "cohens_kappa",
    "fleiss_kappa": "fleiss_kappa",
    "icc": "icc",
}

ESTIMATOR_ANALYSES: Dict[str, str] = {
    "tobit": "tobit",
    "ridge_lasso": "ridge_lasso",
    "quantile_regression": "quantile_regression",
}


def register_advanced_handlers(module: Any) -> None:
    """Bind the analyses a companion module exposes, by attribute name."""
    for analysis_type, attribute in ADVANCED_ANALYSES.items():
        handler = getattr(module, attribute, None)
        if handler is not None:
            ANALYSIS_HANDLERS[analysis_type] = handler


def catalog() -> List[Dict[str, Any]]:
    """Available analyses plus the parameters each one expects."""
    _load_advanced()
    return [
        {
            "analysis_type": analysis_type,
            "description": ANALYSIS_DESCRIPTIONS.get(analysis_type, ""),
            "requires": REQUIRED_PARAMETERS.get(analysis_type, []),
        }
        for analysis_type in ANALYSIS_HANDLERS
    ]


def _load_advanced() -> None:
    """Import the later waves so their analyses join the dispatch table.

    The imports are deferred rather than done at module scope because those
    modules build on the helpers defined above. Each registers itself when it
    loads, so importing is all it takes.
    """
    pending = [
        name
        for name in list(ADVANCED_ANALYSES)
        + list(REGRESSION_ANALYSES)
        + list(COUNT_ANALYSES)
        + list(ESTIMATOR_ANALYSES)
        + list(RELIABILITY_ANALYSES)
        if name not in ANALYSIS_HANDLERS
    ]
    if not pending:
        return
    try:
        from app.statflow import advanced  # noqa: F401 - registers on import
    except ImportError:  # pragma: no cover - the module ships with the package
        pass
    try:
        from app.statflow import models_regression  # noqa: F401
    except ImportError:  # pragma: no cover
        pass
    try:
        from app.statflow import models_counts  # noqa: F401
    except ImportError:  # pragma: no cover
        pass
    try:
        from app.statflow import models_estimators  # noqa: F401
    except ImportError:  # pragma: no cover
        pass
    try:
        from app.statflow import models_reliability  # noqa: F401
    except ImportError:  # pragma: no cover
        pass


#: Older analysis_type spellings that stored runs may still use, mapped to the
#: current name. These are resolved in ``run_analysis`` and deliberately kept
#: out of ``ANALYSIS_HANDLERS`` so the catalogue and the engine stay in step.
LEGACY_ANALYSIS_ALIASES: Dict[str, str] = {
    "normality_test": "normality_tests",
}


def run_analysis(
    frame: pd.DataFrame, analysis_type: str, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Run one analysis and always return the standard result structure."""
    _load_advanced()
    requested = str(analysis_type)
    # `normality_test` was the original singular name; the catalogue spells the
    # method in the plural. Resolving the alias here keeps old stored analysis
    # runs readable without putting a second entry in the dispatch table, which
    # would make the catalogue and the engine disagree.
    handler = ANALYSIS_HANDLERS.get(requested) or ANALYSIS_HANDLERS.get(
        LEGACY_ANALYSIS_ALIASES.get(requested, "")
    )
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












