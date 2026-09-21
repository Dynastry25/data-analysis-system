"""Statistical analysis: descriptive stats, correlation, regression, t-test.

Regression and hypothesis testing use numpy + a self-contained implementation of the
regularized incomplete beta function (so we do not need scipy for this MVP).
"""

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from app.services.data_service import (
    coerce_numeric,
    infer_column_type,
    numeric_columns,
    to_jsonable,
)

FPMIN = 1e-300


# ------------------------------------------------------- t distribution helpers


def _betacf(a: float, b: float, x: float, max_iter: int = 200) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, dof: float) -> float:
    """P(T > t) for a Student t distribution (one-sided upper tail)."""
    if dof <= 0:
        return 1.0
    x = dof / (dof + t * t)
    two_sided = _betai(dof / 2.0, 0.5, x)
    return two_sided / 2.0 if t > 0 else 1.0 - two_sided / 2.0


# ------------------------------------------------------------------ descriptive


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _mode_value(series: pd.Series) -> Any:
    modes = series.mode(dropna=True)
    if modes.empty:
        return None
    return to_jsonable(modes.iloc[0])


def descriptive_stats(df: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Mean, median, mode, std dev, min/max (+ quartiles) and category summaries."""
    requested: Sequence[str] = parameters.get("columns") or []
    if requested:
        missing = [col for col in requested if col not in df.columns]
        if missing:
            raise ValueError(f"Columns not found: {', '.join(missing)}")
        frame = df[list(requested)]
    else:
        frame = df

    numeric_stats: List[Dict[str, Any]] = []
    categorical_stats: List[Dict[str, Any]] = []

    for column in frame.columns:
        series = frame[column]
        data_type = infer_column_type(series)
        if data_type == "numeric":
            values = pd.to_numeric(series, errors="coerce").dropna()
            if values.empty:
                continue
            numeric_stats.append(
                {
                    "column": column,
                    "count": int(values.shape[0]),
                    "missing": int(series.isna().sum()),
                    "mean": _safe_float(values.mean()),
                    "median": _safe_float(values.median()),
                    "mode": _mode_value(values),
                    "std_dev": _safe_float(values.std(ddof=1)) if values.shape[0] > 1 else 0.0,
                    "variance": _safe_float(values.var(ddof=1)) if values.shape[0] > 1 else 0.0,
                    "min": _safe_float(values.min()),
                    "q1": _safe_float(values.quantile(0.25)),
                    "q3": _safe_float(values.quantile(0.75)),
                    "max": _safe_float(values.max()),
                    "sum": _safe_float(values.sum()),
                }
            )
        else:
            clean = series.dropna()
            top = clean.value_counts()
            categorical_stats.append(
                {
                    "column": column,
                    "data_type": data_type,
                    "count": int(clean.shape[0]),
                    "missing": int(series.isna().sum()),
                    "unique": int(clean.nunique()),
                    "top": to_jsonable(top.index[0]) if not top.empty else None,
                    "top_frequency": int(top.iloc[0]) if not top.empty else 0,
                    "top_percentage": (
                        round(float(top.iloc[0]) / float(clean.shape[0]) * 100, 2)
                        if not top.empty and clean.shape[0]
                        else 0.0
                    ),
                }
            )

    return {
        "analysis_type": "descriptive_stats",
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "analyzed_columns": list(frame.columns),
        "numeric_stats": numeric_stats,
        "categorical_stats": categorical_stats,
    }


# ------------------------------------------------------------------ correlation


def _strength_label(r: float) -> str:
    magnitude = abs(r)
    if magnitude >= 0.8:
        return "very strong"
    if magnitude >= 0.6:
        return "strong"
    if magnitude >= 0.4:
        return "moderate"
    if magnitude >= 0.2:
        return "weak"
    return "very weak"


def correlation_analysis(
    df: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Pearson or Spearman correlation matrix + the strongest pairs."""
    method = (parameters.get("method") or "pearson").lower()
    if method not in {"pearson", "spearman"}:
        raise ValueError("method must be 'pearson' or 'spearman'")

    columns: Sequence[str] = parameters.get("columns") or numeric_columns(df)
    columns = [col for col in columns if col in df.columns]
    if len(columns) < 2:
        raise ValueError(
            "Correlation needs at least two numeric columns. "
            "Convert some columns to numeric first."
        )

    frame = pd.DataFrame({col: coerce_numeric(df, col) for col in columns})
    matrix = frame.corr(method=method, min_periods=2)
    matrix_values = [
        [_safe_float(value) for value in row] for row in matrix.to_numpy().tolist()
    ]

    pairs: List[Dict[str, Any]] = []
    for i, col_a in enumerate(columns):
        for col_b in columns[i + 1 :]:
            r = _safe_float(matrix.loc[col_a, col_b])
            if r is None:
                continue
            pairs.append(
                {
                    "column_a": col_a,
                    "column_b": col_b,
                    "coefficient": round(r, 4),
                    "strength": _strength_label(r),
                    "direction": "positive" if r >= 0 else "negative",
                }
            )
    pairs.sort(key=lambda item: abs(item["coefficient"]), reverse=True)

    return {
        "analysis_type": "correlation",
        "method": method,
        "columns": list(columns),
        "matrix": matrix_values,
        "pairs": pairs,
        "row_count": int(df.shape[0]),
    }


# ------------------------------------------------------------------- regression


def regression_analysis(df: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Ordinary least squares linear regression (one target, one or more features)."""
    target = parameters.get("target")
    if not target:
        raise ValueError("Parameter 'target' is required for regression")
    if target not in df.columns:
        raise ValueError(f"Column '{target}' does not exist in this dataset")

    features: Sequence[str] = parameters.get("features") or [
        col for col in numeric_columns(df) if col != target
    ]
    features = [col for col in features if col in df.columns and col != target]
    if not features:
        raise ValueError("Regression needs at least one numeric feature column")

    y = coerce_numeric(df, target)
    x_frame = pd.DataFrame({col: coerce_numeric(df, col) for col in features})
    x_frame["__target__"] = y
    usable = x_frame.dropna()
    if usable.shape[0] < len(features) + 2:
        raise ValueError(
            "Not enough complete rows to fit this regression. "
            "Clean missing values first."
        )

    y_values = usable["__target__"].to_numpy(dtype=float)
    x_values = usable[list(features)].to_numpy(dtype=float)
    design = np.column_stack([np.ones(x_values.shape[0]), x_values])

    coefficients, *_ = np.linalg.lstsq(design, y_values, rcond=None)
    predictions = design @ coefficients
    residuals = y_values - predictions

    ss_total = float(np.sum((y_values - y_values.mean()) ** 2))
    ss_residual = float(np.sum(residuals**2))
    r_squared = 1.0 - (ss_residual / ss_total) if ss_total > 0 else 0.0
    n = int(y_values.shape[0])
    p = len(features)
    adjusted_r_squared = (
        1.0 - (1.0 - r_squared) * (n - 1) / (n - p - 1) if n - p - 1 > 0 else None
    )
    std_error = math.sqrt(ss_residual / (n - p - 1)) if n - p - 1 > 0 else None

    coefficient_map = {
        feature: round(float(coef), 6)
        for feature, coef in zip(features, coefficients[1:])
    }
    intercept = float(coefficients[0])
    terms = " + ".join(
        f"{coef:+.4f}*{feature}" for feature, coef in coefficient_map.items()
    )
    equation = f"{target} = {intercept:.4f} {terms}"

    preview = [
        {
            "actual": round(float(actual), 6),
            "predicted": round(float(predicted), 6),
            "residual": round(float(residual), 6),
        }
        for actual, predicted, residual in list(
            zip(y_values, predictions, residuals)
        )[:20]
    ]

    return {
        "analysis_type": "regression",
        "target": target,
        "features": list(features),
        "n_observations": n,
        "intercept": round(intercept, 6),
        "coefficients": coefficient_map,
        "r_squared": round(r_squared, 6),
        "adjusted_r_squared": (
            round(adjusted_r_squared, 6) if adjusted_r_squared is not None else None
        ),
        "std_error": round(std_error, 6) if std_error is not None else None,
        "equation": equation,
        "predictions_preview": preview,
    }


# --------------------------------------------------------------- hypothesis test


def hypothesis_test(df: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """One-sample or two-sample (Welch) t-test on a numeric column."""
    value_column = parameters.get("value_column") or parameters.get("target")
    if not value_column:
        raise ValueError("Parameter 'value_column' is required")
    values = coerce_numeric(df, value_column)

    group_column: Optional[str] = parameters.get("group_column")
    alpha = float(parameters.get("alpha") or 0.05)
    alternative = (parameters.get("alternative") or "two-sided").lower()
    if alternative not in {"two-sided", "greater", "less"}:
        raise ValueError("alternative must be 'two-sided', 'greater' or 'less'")

    if group_column:
        if group_column not in df.columns:
            raise ValueError(f"Column '{group_column}' does not exist in this dataset")
        grouped = pd.DataFrame({"value": values, "group": df[group_column]}).dropna()
        counts = grouped["group"].value_counts()
        if counts.shape[0] != 2:
            raise ValueError(
                "Two-sample t-test needs a group column with exactly two categories. "
                f"Found {counts.shape[0]}."
            )
        labels = list(counts.index[:2])
        sample_a = grouped.loc[grouped["group"] == labels[0], "value"].to_numpy(float)
        sample_b = grouped.loc[grouped["group"] == labels[1], "value"].to_numpy(float)
        if sample_a.size < 2 or sample_b.size < 2:
            raise ValueError("Each group needs at least 2 observations")

        n_a, n_b = sample_a.size, sample_b.size
        mean_a, mean_b = float(sample_a.mean()), float(sample_b.mean())
        var_a, var_b = float(sample_a.var(ddof=1)), float(sample_b.var(ddof=1))
        denominator = math.sqrt(var_a / n_a + var_b / n_b)
        if denominator == 0:
            raise ValueError("Both groups have zero variance, the t-test is undefined")
        t_stat = (mean_a - mean_b) / denominator
        dof = (var_a / n_a + var_b / n_b) ** 2 / (
            (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        )
        test_name = "welch_two_sample_t_test"
        groups: Dict[str, Any] = {
            str(labels[0]): {
                "n": int(n_a),
                "mean": round(mean_a, 6),
                "std_dev": round(math.sqrt(var_a), 6),
            },
            str(labels[1]): {
                "n": int(n_b),
                "mean": round(mean_b, 6),
                "std_dev": round(math.sqrt(var_b), 6),
            },
        }
        hypothesis = (
            f"mean({labels[0]}) equals mean({labels[1]}) for column '{value_column}'"
        )
    else:
        expected = float(parameters.get("population_mean") or 0.0)
        sample = values.dropna().to_numpy(float)
        n_a = sample.size
        if n_a < 2:
            raise ValueError("Need at least 2 observations for a one-sample t-test")
        mean_a = float(sample.mean())
        var_a = float(sample.var(ddof=1))
        if var_a == 0:
            raise ValueError("The column has zero variance, the t-test is undefined")
        t_stat = (mean_a - expected) / math.sqrt(var_a / n_a)
        dof = n_a - 1
        test_name = "one_sample_t_test"
        groups = {
            "sample": {
                "n": int(n_a),
                "mean": round(mean_a, 6),
                "std_dev": round(math.sqrt(var_a), 6),
            },
            "population_mean": expected,
        }
        hypothesis = f"mean('{value_column}') equals {expected}"

    if alternative == "two-sided":
        p_value = 2.0 * student_t_sf(abs(t_stat), dof)
    elif alternative == "greater":
        p_value = student_t_sf(t_stat, dof)
    else:
        p_value = 1.0 - student_t_sf(t_stat, dof)
    p_value = min(max(p_value, 0.0), 1.0)

    significant = p_value < alpha
    return {
        "analysis_type": "hypothesis_test",
        "test": test_name,
        "value_column": value_column,
        "group_column": group_column,
        "hypothesis": hypothesis,
        "alternative": alternative,
        "alpha": alpha,
        "t_statistic": round(t_stat, 6),
        "degrees_of_freedom": round(dof, 4),
        "p_value": round(p_value, 8),
        "significant": significant,
        "groups": groups,
        "interpretation": (
            f"p = {p_value:.4f} is {'below' if significant else 'not below'} "
            f"alpha = {alpha}: "
            + (
                "there is a statistically significant difference."
                if significant
                else "there is no statistically significant difference."
            )
        ),
    }


ANALYSIS_HANDLERS = {
    "descriptive_stats": descriptive_stats,
    "correlation": correlation_analysis,
    "regression": regression_analysis,
    "hypothesis_test": hypothesis_test,
}


def run_analysis(
    df: pd.DataFrame, analysis_type: str, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch an analysis request to its handler."""
    handler = ANALYSIS_HANDLERS.get(analysis_type)
    if handler is None:
        raise ValueError(
            "Unsupported analysis_type. Allowed: "
            + ", ".join(sorted(ANALYSIS_HANDLERS))
        )
    return handler(df, parameters or {})


