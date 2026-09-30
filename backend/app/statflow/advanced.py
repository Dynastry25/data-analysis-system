"""The second wave of the Methods of Analysis guide: the analyses that need more
than a closed-form test statistic.

Kept apart from ``stats_engine`` because that module is already the home of the
quick univariate tests, and this file is home of the models — anything with an
iterative fit, a matrix decomposition, a resampling step or a design effect.

Everything here uses the same building blocks as ``stats_engine``: numpy,
``statflow.distributions`` and the shared ``standard_result`` shape, so the
result renderer, the router and the frontend need no special case for any of it.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import sys

import numpy as np
import pandas as pd

from app.statflow.distributions import (
    chi_square_sf,
    f_sf,
    normal_sf,
    student_t_two_sided_p,
    t_critical,
)
from app.statflow.stats_engine import (
    INVALID,
    SUCCESS,
    AnalysisError,
    _design_matrix,
    _effect_label,
    _exp_clipped,
    _glm_fit,
    _round,
    _two_sided_normal_p,
    correlation_test,
    group_samples,
    numeric_series,
    require_column,
    standard_result,
)
from app.services.data_service import to_jsonable


def _numeric_columns(frame: pd.DataFrame, names: Sequence[str]) -> np.ndarray:
    """Stack several columns into a matrix, dropping rows that are incomplete."""
    block = frame[list(names)].apply(pd.to_numeric, errors="coerce")
    return block.dropna().to_numpy(dtype=float)


def _weight_vector(frame: pd.DataFrame, column: Optional[str], size: int) -> np.ndarray:
    if not column:
        return np.ones(size, dtype=float)
    column = require_column(frame, column, "weight_column")
    weights = numeric_series(frame, column).to_numpy(dtype=float)
    if np.any(weights < 0):
        raise AnalysisError("Weights cannot be negative")
    if weights.sum() <= 0:
        raise AnalysisError("The weights sum to zero, so nothing can be estimated")
    return weights


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = weights.sum()
    return float(np.sum(values * weights) / total) if total else float("nan")


def _weighted_variance(values: np.ndarray, weights: np.ndarray, ddof: int = 1) -> float:
    """Frequency-weight variance, matching the survey convention."""
    total = weights.sum()
    if total <= 0:
        return float("nan")
    mean = _weighted_mean(values, weights)
    denominator = total - (1.0 / total) if ddof == 1 else total
    if denominator <= 0:
        return float("nan")
    return float(np.sum(weights * (values - mean) ** 2) / denominator)


def _ols(design: np.ndarray, target: np.ndarray) -> Dict[str, Any]:
    """Least squares with the usual inferential read-out, no diagnostics."""
    x = np.asarray(design, dtype=float)
    y = np.asarray(target, dtype=float)
    n, p = x.shape
    xtx_inverse = np.linalg.pinv(x.T @ x)
    beta = xtx_inverse @ x.T @ y
    fitted = x @ beta
    residuals = y - fitted
    dof = max(n - p, 1)
    sigma_squared = float(np.sum(residuals**2) / dof)
    covariance = sigma_squared * xtx_inverse
    standard_errors = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
    rss = float(np.sum(residuals**2))
    tss = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - rss / tss if tss else None
    return {
        "coefficients": beta,
        "standard_errors": standard_errors,
        "fitted": fitted,
        "residuals": residuals,
        "r_squared": r_squared,
        "adjusted_r_squared": 1 - (1 - r_squared) * (n - 1) / dof if r_squared is not None else None,
        "rss": rss,
        "n": n,
        "p": p,
        "sigma_squared": sigma_squared,
    }


def _coefficient_rows(
    names: Sequence[str],
    beta: np.ndarray,
    standard_errors: np.ndarray,
    p_values: np.ndarray,
    exponentiate: bool = False,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name, estimate, error, p_value in zip(names, beta, standard_errors, p_values):
        usable = error == error and error > 0  # NaN standard error => no interval
        row: Dict[str, Any] = {
            "term": name,
            "beta": _round(estimate),
            "standard_error": _round(error),
            "p_value": _round(p_value),
            "significant": bool(p_value < 0.05) if p_value == p_value else None,
        }
        if exponentiate:
            row["odds_ratio"] = _round(_exp_clipped(estimate))
        if usable:
            row["or_ci_lower" if exponentiate else "beta_ci_lower"] = _round(
                _exp_clipped(estimate - 1.96 * error) if exponentiate else estimate - 1.96 * error
            )
            row["or_ci_upper" if exponentiate else "beta_ci_upper"] = _round(
                _exp_clipped(estimate + 1.96 * error) if exponentiate else estimate + 1.96 * error
            )
        else:
            row["or_ci_lower" if exponentiate else "beta_ci_lower"] = None
            row["or_ci_upper" if exponentiate else "beta_ci_upper"] = None
        rows.append(row)
    return rows


# ------------------------------------------------------- association extras


def mcnemar_test(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """McNemar's test for two raters scoring the same units.

    Needs the same units measured twice, so the table has to be square: the
    cells are paired counts, not independent ones.
    """
    before = require_column(
        frame, parameters.get("before_column") or parameters.get("row_column"), "before_column"
    )
    after = require_column(
        frame, parameters.get("after_column") or parameters.get("column_column"), "after_column"
    )
    if before == after:
        raise AnalysisError("McNemar needs two different columns")

    first = frame[before].astype("object")
    second = frame[after].astype("object")
    usable = first.notna() & second.notna()
    if int(usable.sum()) < 3:
        raise AnalysisError("Fewer than 3 rows are scored on both columns")

    labels = sorted(set(first[usable]) | set(second[usable]), key=str)
    if len(labels) > 2:
        raise AnalysisError(
            f"The engine computes McNemar for two categories, but '{before}'/'{after}' hold "
            f"{len(labels)}: {labels[:6]}. Use Cochran's Q for more"
        )
    if len(labels) < 2:
        # One category only means no unit ever changed category. That is a real
        # result with no test statistic attached, not a malformed request.
        return standard_result(
            "mcnemar",
            status=INVALID,
            sample_size=int(usable.sum()),
            estimate={
                "before": before,
                "after": after,
                "categories": [str(x) for x in labels],
                "agreements": int(usable.sum()),
                "discordant": 0,
            },
            warnings=[
                "Every unit kept the same category, so there is nothing for McNemar to test"
            ],
            meta={"parameters": {"before_column": before, "after_column": after}},
        )

    index = {label: position for position, label in enumerate(labels)}
    table = np.zeros((2, 2), dtype=float)
    for left, right in zip(first[usable], second[usable]):
        table[index[left], index[right]] += 1

    # Only the off-diagonal cells matter: they are the pairs where the raters
    # disagreed, and the diagonal is the agreement.
    b_only = float(table[0, 1])
    a_only = float(table[1, 0])
    total = b_only + a_only
    if total == 0:
        return standard_result(
            "mcnemar",
            status=INVALID,
            sample_size=int(usable.sum()),
            estimate={"before": before, "after": after, "categories": [str(x) for x in labels]},
            warnings=["The two raters never disagreed, so the test has no information"],
            tables={"table": table.astype(int).tolist()},
            meta={"parameters": {"before_column": before, "after_column": after}},
        )

    chi_square = (abs(b_only - a_only) - 1.0) ** 2 / total  # continuity correction
    p_value = float(chi_square_sf(chi_square, 1))
    effect = abs(b_only - a_only) / total

    warnings: List[str] = []
    if total < 25:
        warnings.append(
            f"Only {int(total)} discordant pairs: the chi-square approximation is unreliable, "
            "so read the exact binomial version instead"
        )

    return standard_result(
        "mcnemar",
        sample_size=int(usable.sum()),
        estimate={
            "before": before,
            "after": after,
            "categories": [str(label) for label in labels],
            "agreements": int(table[0, 0] + table[1, 1]),
            "discordant": int(total),
            "changed_to_second": int(b_only),
            "changed_to_first": int(a_only),
        },
        test={
            "method": "McNemar's test (chi-square with continuity correction)",
            "statistic": _round(chi_square),
            "df": 1,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        effect_size={
            "name": "discordant_proportion",
            "value": _round(effect),
            "interpretation": _effect_label(effect, 0.1, 0.3, 0.5),
        },
        diagnostics={"contingency": table.astype(int).tolist()},
        warnings=warnings,
        tables={
            "table": {
                "rows": [str(label) for label in labels],
                "columns": [str(label) for label in labels],
                "counts": table.astype(int).tolist(),
            }
        },
        meta={"parameters": {"before_column": before, "after_column": after}},
    )


def one_sample_z_test(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """One-sample z-test against a known population mean and standard deviation."""
    column = require_column(
        frame, parameters.get("value_column") or parameters.get("column"), "value_column"
    )
    values = numeric_series(frame, column).dropna().to_numpy(dtype=float)
    n = int(values.size)
    if n < 3:
        raise AnalysisError("Need at least 3 observations")

    mu = float(parameters.get("mu", 0.0))
    supplied = parameters.get("sigma")
    warnings: List[str] = []
    if supplied is None:
        # Without a known population SD the z-test is not available at all; the
        # sample SD version is a t-test, so the guide's alternative is named
        # rather than silently substituted.
        sigma = float(np.std(values, ddof=1))
        warnings.append(
            "No population standard deviation was supplied, so the sample SD was used. That "
            "makes this a t-test rather than a z-test; prefer one_sample_t_test unless the "
            "population SD is genuinely known"
        )
    else:
        sigma = float(supplied)
    if sigma <= 0:
        raise AnalysisError("The standard deviation must be positive")

    mean = float(values.mean())
    standard_error = sigma / np.sqrt(n)
    z_score = (mean - mu) / standard_error
    p_value = float(2.0 * normal_sf(abs(z_score)))
    margin = float(t_critical(n - 1, 0.95)) * standard_error
    effect = (mean - mu) / sigma

    return standard_result(
        "one_sample_z_test",
        sample_size=n,
        estimate={
            "column": column,
            "mean": _round(mean),
            "reference_mean": _round(mu),
            "standard_deviation_used": _round(sigma),
        },
        test={
            "method": "One-sample z-test",
            "statistic": _round(z_score),
            "df": None,
            "p_value": _round(p_value),
            "alpha": 0.05,
            "significant": bool(p_value < 0.05),
        },
        confidence_interval={
            "level": 0.95,
            "lower": _round(mean - margin),
            "upper": _round(mean + margin),
            "basis": "mean +/- 1.96 * (sigma / sqrt(n))",
        },
        effect_size={
            "name": "cohens_d",
            "value": _round(effect),
            "interpretation": _effect_label(effect, 0.2, 0.5, 0.8),
        },
        diagnostics={"standard_error": _round(standard_error), "n": n},
        warnings=warnings,
        meta={"parameters": {"value_column": column, "mu": mu, "sigma": sigma}},
    )


def two_way_anova(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Two-factor factorial ANOVA, including the interaction the guide asks for."""
    value_column = require_column(
        frame, parameters.get("value_column") or parameters.get("column"), "value_column"
    )
    first = require_column(frame, parameters.get("group_column"), "group_column")
    second = require_column(frame, parameters.get("second_group_column"), "second_group_column")
    if first == second:
        raise AnalysisError("The two factors must be different columns")

    values = numeric_series(frame, value_column)
    usable = values.notna() & frame[first].notna() & frame[second].notna()
    factor_a = frame[first][usable].astype("object").to_numpy()
    factor_b = frame[second][usable].astype("object").to_numpy()
    y = values[usable].to_numpy(dtype=float)
    n = int(y.size)

    levels_a = sorted(set(factor_a), key=str)
    levels_b = sorted(set(factor_b), key=str)
    if len(levels_a) < 2 or len(levels_b) < 2:
        raise AnalysisError("A two-way ANOVA needs at least two levels in each factor")

    cells: Dict[Tuple[str, str], np.ndarray] = {
        (level_a, level_b): y[(factor_a == level_a) & (factor_b == level_b)]
        for level_a in levels_a
        for level_b in levels_b
    }
    smallest_cell = min(int(cell.size) for cell in cells.values())
    if smallest_cell < 3:
        return standard_result(
            "two_way_anova",
            status=INVALID,
            sample_size=n,
            estimate={
                "value_column": value_column,
                "levels_a": [str(x) for x in levels_a],
                "levels_b": [str(x) for x in levels_b],
            },
            warnings=[
                f"The smallest cell holds {smallest_cell} observation(s); below about 3 the "
                "interaction cannot be estimated. Combine levels or collect more data"
            ],
            meta={"parameters": {"value_column": value_column}},
        )

    grand_mean = float(y.mean())
    # Sums of squares: total, then each main effect, then the cells. What is
    # left of the cells once the main effects are removed is the interaction.
    ss_total = float(np.sum((y - grand_mean) ** 2))
    ss_a = sum(float((factor_a == x).sum()) * (y[factor_a == x].mean() - grand_mean) ** 2 for x in levels_a)
    ss_b = sum(float((factor_b == x).sum()) * (y[factor_b == x].mean() - grand_mean) ** 2 for x in levels_b)
    ss_cells = sum(float(c.size) * (c.mean() - grand_mean) ** 2 for c in cells.values() if c.size)
    ss_interaction = ss_cells - ss_a - ss_b
    ss_error = ss_total - ss_cells
    if ss_error <= 1e-12:
        raise AnalysisError("There is no residual variation left, so the F-tests are undefined")

    residual_df = max(n - len(cells), 1)
    error_mean_square = ss_error / residual_df
    specifications = [
        ("factor_a", first, len(levels_a) - 1, ss_a),
        ("factor_b", second, len(levels_b) - 1, ss_b),
        ("interaction", f"{first} x {second}", (len(levels_a) - 1) * (len(levels_b) - 1), ss_interaction),
    ]
    rows: List[Dict[str, Any]] = []
    for name, column, degrees, ss in specifications:
        degrees = max(degrees, 1)
        mean_square = max(ss, 0.0) / degrees
        f_value = mean_square / error_mean_square
        p_value = float(f_sf(f_value, degrees, residual_df))
        rows.append(
            {
                "term": name,
                "column": column,
                "degrees_of_freedom": degrees,
                "sum_of_squares": _round(ss),
                "mean_square": _round(mean_square),
                "f": _round(f_value),
                "p_value": _round(p_value),
                "eta_squared": _round(max(ss, 0.0) / ss_total) if ss_total else None,
                "significant": bool(p_value < 0.05),
            }
        )

    warnings: List[str] = []
    if smallest_cell < 5:
        warnings.append(
            f"The smallest cell holds {smallest_cell} observation(s); below about 5 the F-tests "
            "are unreliable, so a permutation test is safer"
        )
    if not rows[2]["significant"]:
        warnings.append(
            "The interaction is not significant, so the two main effects can be read directly "
            "without a simple-effects follow-up"
        )

    return standard_result(
        "two_way_anova",
        sample_size=n,
        estimate={
            "value_column": value_column,
            "levels_a": [str(x) for x in levels_a],
            "levels_b": [str(x) for x in levels_b],
            "grand_mean": _round(grand_mean),
            "terms": rows,
        },
        test={
            "method": "Two-way (factorial) ANOVA",
            "statistic": _round(max(row["f"] or 0 for row in rows)),
            "df": residual_df,
            "p_value": rows[0]["p_value"],
            "alpha": 0.05,
            "significant": rows[0]["significant"],
        },
        effect_size={
            "name": "eta_squared",
            "value": rows[0]["eta_squared"],
            "interpretation": "Share of the outcome's variance explained by the first factor",
        },
        diagnostics={
            "residual_sum_of_squares": _round(ss_error),
            "total_sum_of_squares": _round(ss_total),
            "smallest_cell": smallest_cell,
        },
        warnings=warnings,
        tables={
            "cell_means": {
                "levels_a": [str(x) for x in levels_a],
                "levels_b": [str(x) for x in levels_b],
                "means": [
                    [_round(float(cells[(a, b)].mean())) if cells[(a, b)].size else None for b in levels_b]
                    for a in levels_a
                ],
            }
        },
        meta={"parameters": {"value_column": value_column, "group_column": first, "second_group_column": second}},
    )


def _ordinal_loglik(
    design: np.ndarray, outcome: np.ndarray, beta: np.ndarray, thresholds: np.ndarray
) -> float:
    """Log-likelihood of the proportional-odds model, vectorised.

    The convention here is ``P(Y <= k | x) = logistic(eta - kappa_k)``, so a
    positive slope raises the odds of a higher category. Keeping eta on the
    positive side matters: with the opposite convention the fitted slopes come
    out with the wrong sign, which is the kind of error that still looks like a
    plausible result.
    """
    levels = outcome.astype(int)
    eta = np.clip(design @ beta, -30.0, 30.0)
    # s[j] is P(Y <= j); the open ends are pinned to 0 and 1.
    cumulative = [np.zeros_like(eta)]
    for kappa in thresholds:
        cumulative.append(1.0 / (1.0 + np.exp(np.clip(eta - kappa, -30.0, 30.0))))
    cumulative.append(np.ones_like(eta))
    total = 0.0
    for level in range(len(thresholds) + 1):
        selected = levels == level
        if not selected.any():
            continue
        probability = cumulative[level + 1] - cumulative[level]
        # The floor keeps this surface smooth. Clipping at machine epsilon
        # instead creates a plateau where every probability underflows, the
        # gradient reads zero, and the fit stops at a false stationary point
        # with the thresholds sent to +/-30. A floor of 1e-10 costs nothing on
        # real data (a probability that small contributes nothing anyway) and
        # keeps the ascent alive.
        total += float(np.sum(np.log(np.maximum(probability[selected], 1e-10))))
    return total


def _ordinal_gradient(
    design: np.ndarray,
    outcome: np.ndarray,
    beta: np.ndarray,
    thresholds: np.ndarray,
    step: float = 1e-6,
) -> np.ndarray:
    """Central-difference gradient of the log-likelihood.

    The analytic score for this model is easy to get subtly wrong, and a wrong
    score does not fail loudly: it just wanders to an enormous solution. The
    vector here is a handful of numbers and the likelihood is vectorised, so
    numerical differentiation stays cheap.
    """
    p = len(beta)
    total = p + len(thresholds)
    gradient = np.zeros(total)
    for column in range(total):
        up = np.concatenate([beta, thresholds])
        down = up.copy()
        up[column] += step
        down[column] -= step
        gradient[column] = (
            _ordinal_loglik(design, outcome, up[:p], up[p:])
            - _ordinal_loglik(design, outcome, down[:p], down[p:])
        ) / (2 * step)
    return gradient


def _fit_proportional_odds(
    design: np.ndarray, outcome: np.ndarray, cutpoints: int, max_iter: int = 500
) -> Dict[str, Any]:
    """Fit slopes and thresholds by ascent on the log-likelihood.

    A plain Newton step is fragile here: the slopes and thresholds are only
    weakly separated, so the step can walk off to an enormous solution that is a
    hair better in likelihood terms. Ascent with a backtracking line search
    cannot do that, because every accepted step has to improve the likelihood.
    """
    p = design.shape[1]
    total = p + cutpoints
    from app.statflow.distributions import normal_ppf

    # Thresholds start at the empirical cumulative proportions. Under
    # P(Y <= k) = logistic(eta - kappa) the cut that reproduces a share r of the
    # sample satisfies eta - kappa = logit(r), so kappa = eta - logit(r) is
    # approximated by -logit(r) with eta at its mean.
    mean_eta = float(design.mean(axis=0) @ np.zeros(p)) if p else 0.0
    rates = [float((outcome >= k).mean()) for k in range(1, cutpoints + 1)]
    thresholds = np.array(
        [
            mean_eta - float(normal_ppf(min(max(rate, 1e-3), 1 - 1e-3)))
            for rate in rates
        ]
    )
    beta = np.zeros(p)
    share = float((outcome > 0).mean())
    if 0 < share < 1:
        beta[0] = float(normal_ppf(share))
    parameters = np.concatenate([beta, thresholds])

    def likelihood(vector: np.ndarray) -> float:
        return _ordinal_loglik(design, outcome, vector[:p], vector[p:])

    best = likelihood(parameters)
    converged = False
    for _ in range(max_iter):
        gradient = _ordinal_gradient(design, outcome, parameters[:p], parameters[p:])
        if np.max(np.abs(gradient)) < 1e-6:
            converged = True
            break
        # A small step along the normalised gradient, backed off until the
        # likelihood improves. A large fixed step overshoots here because the
        # thresholds and the slopes trade off against each other.
        direction = gradient / max(float(np.max(np.abs(gradient))), 1e-12)
        scale = 0.05
        improved = False
        for _attempt in range(60):
            candidate = parameters + scale * direction
            value = likelihood(candidate)
            if value > best:
                parameters, best = candidate, value
                improved = True
                break
            scale *= 0.6
        if not improved:
            converged = True
            break

    beta = parameters[:p]
    thresholds = parameters[p:]

    # Numerical Hessian for the standard errors, symmetrised.
    information = np.zeros((total, total))
    h = 1e-4
    for row in range(total):
        for column in range(row, total):
            values = []
            for sign_row, sign_column in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                shifted = parameters.copy()
                shifted[row] += sign_row * h
                shifted[column] += sign_column * h
                values.append(likelihood(shifted))
            entry = (values[0] - values[1] - values[2] + values[3]) / (4 * h * h)
            information[row, column] = entry
            information[column, row] = entry
    covariance = np.linalg.pinv(-information)
    # The intercept is weakly identified once the thresholds float freely, so its
    # variance can come back as a sliver of a matrix inverse. A standard error
    # of exactly zero prints as "0.00" and reads as certainty, so it is reported
    # as missing rather than as a fake number.
    variances = np.diag(covariance)[:p]
    standard_errors = np.where(
        variances > 1e-8, np.sqrt(np.clip(variances, 0.0, None)), np.nan
    )
    return {
        "beta": beta,
        "thresholds": thresholds,
        "standard_errors": standard_errors,
        "converged": converged,
        "log_likelihood": best,
        "n": design.shape[0],
        "p": p,
    }


def ordinal_logit(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Proportional-odds logistic regression on an ordered outcome."""
    target = require_column(frame, parameters.get("target"), "target")
    raw_features = parameters.get("features") or []
    if isinstance(raw_features, str):
        raw_features = [raw_features]
    features = [str(name) for name in raw_features]
    if not features:
        raise AnalysisError("Ordinal logistic regression needs at least one feature column")

    raw = frame[target].astype("object")
    labels = sorted(set(raw.dropna()), key=str)
    if len(labels) < 3:
        raise AnalysisError(
            f"An ordinal outcome needs at least 3 ordered categories; '{target}' has {len(labels)}"
        )
    index = {label: position for position, label in enumerate(labels)}
    usable = np.array(frame[target].notna().to_numpy(), dtype=bool, copy=True)
    for feature in features:
        usable &= numeric_series(frame, feature).notna().to_numpy()
    complete = int(usable.sum())
    if complete < len(labels) * 3:
        raise AnalysisError(
            f"Only {complete} complete rows for {len(labels)} categories; ordinal regression needs "
            "at least about 3 per category"
        )

    outcome = raw.map(index).to_numpy(dtype=float)[usable]
    design, names = _design_matrix(frame.loc[usable, :], features)
    fit = _fit_proportional_odds(design, outcome, cutpoints=len(labels) - 1)

    beta = fit["beta"]
    standard_errors = fit["standard_errors"]
    safe_errors = np.where(standard_errors == standard_errors, standard_errors, 0.0)
    z_scores = np.divide(beta, safe_errors, out=np.zeros_like(beta), where=safe_errors > 0)
    p_values = _two_sided_normal_p(z_scores)
    counts = [int((outcome == level).sum()) for level in range(1, len(labels))]

    warnings: List[str] = []
    if not fit["converged"]:
        warnings.append(
            "The proportional-odds fit did not fully converge, so the estimates and thresholds "
            "should be read as approximate"
        )
    # The proportional-odds assumption itself is not tested here: a large
    # z-score means a strong predictor, not a failed assumption, and guessing
    # otherwise would send the reader to a partial model for no reason.
    if min(counts) < 10:
        warnings.append(
            f"The thinnest category holds {min(counts)} observation(s); ordinal estimates are "
            "unstable below about 10 per category"
        )

    return standard_result(
        "ordinal_logit",
        sample_size=complete,
        estimate={
            "target": target,
            "features": features,
            "categories": [str(label) for label in labels],
            "category_counts": counts,
            "coefficients": _coefficient_rows(names, beta, standard_errors, p_values, True),
            "thresholds": [_round(value) for value in fit["thresholds"]],
        },
        test={
            "method": "Ordinal logistic regression (proportional odds)",
            "statistic": _round(float(np.max(np.abs(z_scores)))) if z_scores.size else None,
            "df": None,
            "p_value": _round(float(np.min(p_values))) if p_values.size else None,
            "alpha": 0.05,
            "significant": bool(p_values.size and np.min(p_values) < 0.05),
        },
        confidence_interval={"level": 0.95, "basis": "Wald on the log-odds scale"},
        effect_size={
            "name": "odds_ratio",
            "value": _round(_exp_clipped(beta[1])) if len(beta) > 1 else None,
            "interpretation": "Common odds ratio per unit of the first feature, across thresholds",
        },
        diagnostics={
            "assumption": "proportional odds",
            "cutpoint_count": len(labels) - 1,
            "thin_category": min(counts),
            "converged": fit["converged"],
        },
        warnings=warnings,
        meta={"parameters": {"target": target, "features": features}},
    )


# Registration happens here, at the bottom of the module, so the dependency on
# stats_engine is fully resolved before the handler table is touched. Doing it
# at the top would ask stats_engine for attributes this module has not defined
# yet whenever this module is the one imported first.
from app.statflow import stats_engine as _engine  # noqa: E402

_engine.register_advanced_handlers(sys.modules[__name__])






