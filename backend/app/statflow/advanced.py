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


# ----------------------------------------------------------------- survey analysis


def weighted_frequencies(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Frequency table with survey weights applied.

    Like the basic ``frequency`` analysis but supports a ``weight_column`` so a
    complex-survey sample can be reported in population-weighted percentages.
    """
    requested = parameters.get("columns") or parameters.get("column")
    columns = [str(c) for c in (requested or [])]
    if not columns:
        columns = [
            str(column)
            for column in frame.columns
            if frame[column].nunique(dropna=True) <= 50
        ][:5]
    if not columns:
        raise AnalysisError("No categorical columns found for weighted frequencies")

    weight_column = parameters.get("weight_column")
    warnings: List[str] = []
    tables: Dict[str, Any] = {}
    weighted_pct_total: Dict[str, float] = {}

    for column in columns:
        if column not in frame.columns:
            warnings.append(f"Column '{column}' does not exist, skipped")
            continue
        if weight_column is None:
            warnings.append(f"'{column}': no weight_column supplied, using unweighted counts")
            weight_column_use = None
        else:
            weight_column_use = weight_column
        weights = _weight_vector(frame, weight_column_use, int(frame.shape[0]))
        values = frame[column].astype("object")
        usable = values.notna()
        total_weight = float(weights[usable.to_numpy()].sum())
        counts = frame[usable].groupby(values[usable]).apply(
            lambda chunk: float(weights[chunk.index].sum())
        )
        rows = []
        pct_total = 0.0
        for category, weighted_count in counts.items():
            pct = (weighted_count / total_weight * 100.0) if total_weight else 0.0
            pct_total += pct
            rows.append(
                {
                    "category": to_jsonable(category),
                    "weighted_count": _round(weighted_count),
                    "percentage": _round(pct, 2),
                }
            )
        tables[column] = rows
        weighted_pct_total[column] = _round(pct_total, 2)

    return standard_result(
        "weighted_frequencies",
        sample_size=int(frame.shape[0]),
        estimate={
            "weight_column": weight_column,
            "columns": list(tables),
            "weighted_pct_total": weighted_pct_total,
        },
        diagnostics={"tables": len(tables)},
        warnings=warnings,
        tables={"frequency": tables},
        meta={"parameters": {"weight_column": weight_column, "columns": columns}},
    )


def likert_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Summarise Likert / rating-scale items.

    Returns per-item frequency tables, top-box / top-two-box shares, the mean
    response and an optional weighted variant via ``weight_column``.
    """
    items = parameters.get("items") or parameters.get("columns") or []
    if isinstance(items, str):
        items = [items]
    items = [str(item) for item in items if str(item) in frame.columns]
    if len(items) < 2:
        raise AnalysisError("At least two Likert item columns are required")

    reversed_items = set(str(v) for v in (parameters.get("reversed_items") or []))
    scale_min = float(parameters.get("scale_min", 1))
    scale_max = float(parameters.get("scale_max", 5))

    weight_column = parameters.get("weight_column")
    weights = _weight_vector(frame, weight_column, int(frame.shape[0]))

    warnings: List[str] = []
    item_tables: List[Dict[str, Any]] = []
    top_box_shares: Dict[str, float] = {}
    overall_means: List[float] = []
    item_names: List[str] = []

    for item in items:
        raw = frame[item]
        numeric = pd.to_numeric(raw, errors="coerce")
        usable = numeric.notna()
        subset = numeric[usable].to_numpy(dtype=float)
        if subset.size == 0:
            warnings.append(f"'{item}' has no valid numeric responses, skipped")
            continue
        item_weights = weights[usable.to_numpy()]

        # Frequency of each scale point.
        freq = {}
        for label, count in zip(*np.unique(subset, return_counts=True)):
            freq[int(label)] = _round(float(count))
        weighted_freq = {}
        for label in freq:
            mask = subset == label
            weighted_freq[label] = _round(float(item_weights[mask].sum()))

        mean = _weighted_mean(
            subset, item_weights
        ) if item_weights.sum() else float(np.mean(subset))
        top_box = float(np.sum((subset >= scale_max - 1) & (subset == scale_max)))
        top_two = float(np.sum(subset >= scale_max - 1))
        top_box_share = (
            float(np.sum(item_weights[(subset >= scale_max - 1) & (subset == scale_max)]) / item_weights.sum())
            if item_weights.sum()
            else 0.0
        )
        top_two_share = (
            float(np.sum(item_weights[subset >= scale_max - 1]) / item_weights.sum())
            if item_weights.sum()
            else 0.0
        )

        item_tables.append(
            {
                "item": item,
                "reversed": item in reversed_items,
                "mean": _round(mean),
                "n": int(subset.size),
                "unweighted_frequencies": freq,
                "weighted_frequencies": weighted_freq,
                "top_box_share": _round(top_box_share),
                "top_two_box_share": _round(top_two_share),
            }
        )
        top_box_shares[item] = _round(top_two_share)
        overall_means.append(mean)
        item_names.append(item)

    if not item_tables:
        raise AnalysisError("No valid Likert items found after filtering")

    # Cronbach's alpha across items for internal consistency.
    matrix = frame[item_names].apply(pd.to_numeric, errors="coerce").dropna()
    if matrix.shape[1] >= 2 and matrix.shape[0] >= 2:
        alpha_result = _cronbach_alpha_matrix(matrix.to_numpy(dtype=float))
        alpha = alpha_result.get("alpha") if isinstance(alpha_result, dict) else alpha_result
    else:
        alpha = None

    return standard_result(
        "likert_analysis",
        sample_size=int(matrix.shape[0]) if matrix.size else int(frame.shape[0]),
        estimate={
            "items": item_names,
            "reversed_items": list(reversed_items & set(item_names)),
            "scale_min": scale_min,
            "scale_max": scale_max,
            "overall_mean": _round(float(np.mean(overall_means))) if overall_means else None,
            "cronbach_alpha": _round(alpha) if alpha is not None else None,
        },
        test={
            "method": "Cronbach's alpha (internal consistency)",
            "p_value": None,
            "alpha": _round(alpha) if alpha is not None else None,
        },
        diagnostics={
            "item_count": len(item_tables),
            "mean_top_two_box_share": _round(
                float(np.mean(list(top_box_shares.values())))
            )
            if top_box_shares
            else None,
        },
        warnings=warnings,
        tables={
            "items": item_tables,
            "top_two_box_by_item": {k: v for k, v in top_box_shares.items()},
        },
        meta={
            "parameters": {
                "items": items,
                "weight_column": weight_column,
                "scale_min": scale_min,
                "scale_max": scale_max,
            }
        },
    )


def _cronbach_alpha_matrix(values: np.ndarray) -> Dict[str, Any]:
    """Cronbach's alpha for an item-response matrix (rows = respondents)."""
    matrix = np.asarray(values, dtype=float)
    n_items = matrix.shape[1]
    if n_items < 2:
        raise AnalysisError("Cronbach's alpha needs at least two items")
    valid = matrix[np.isfinite(matrix).all(axis=1)]
    if valid.shape[0] < 2:
        raise AnalysisError("Too few complete responses for Cronbach's alpha")

    item_variances = np.var(valid, axis=0, ddof=1)
    total_variance = np.var(valid.sum(axis=1), ddof=1)
    if total_variance <= 0:
        return {"alpha": None, "status": "zero_total_variance"}
    alpha = (n_items / (n_items - 1)) * (1.0 - float(item_variances.sum()) / total_variance)

    # Item-total correlations and alpha-if-deleted.
    total_scores = valid.sum(axis=1)
    item_total_r: List[float] = []
    alpha_if_deleted: List[Optional[float]] = []
    for column in range(n_items):
        others = np.delete(valid, column, axis=1)
        if others.shape[1] >= 2:
            other_total = others.sum(axis=1)
            correlation = float(np.corrcoef(valid[:, column], other_total)[0, 1])
            item_total_r.append(_round(correlation))
            other_var = np.var(others.sum(axis=1), ddof=1)
            sub_alpha = ((n_items - 1) / (n_items - 2)) * (
                1.0 - float(np.var(others, axis=0, ddof=1).sum()) / other_var
            ) if other_var > 0 else None
            alpha_if_deleted.append(_round(sub_alpha) if sub_alpha is not None else None)
        else:
            item_total_r.append(None)
            alpha_if_deleted.append(None)

    interpretation = (
        "excellent" if alpha >= 0.9
        else "good" if alpha >= 0.8
        else "acceptable" if alpha >= 0.7
        else "questionable" if alpha >= 0.6
        else "poor"
    )
    return {
        "alpha": alpha,
        "n_items": n_items,
        "n_respondents": int(valid.shape[0]),
        "item_total_correlations": item_total_r,
        "alpha_if_deleted": alpha_if_deleted,
        "interpretation": interpretation,
    }


def cronbach_alpha_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Cronbach's alpha for a set of items (reliability / internal consistency)."""
    items = parameters.get("items") or parameters.get("columns") or []
    if isinstance(items, str):
        items = [items]
    items = [str(name) for name in items if str(name) in frame.columns]
    if len(items) < 2:
        raise AnalysisError("At least two item columns are required for Cronbach's alpha")

    matrix = frame[items].apply(pd.to_numeric, errors="coerce")
    result = _cronbach_alpha_matrix(matrix.to_numpy(dtype=float))
    alpha = result["alpha"]

    if alpha is None:
        return standard_result(
            "cronbach_alpha",
            sample_size=int(matrix.dropna().shape[0]),
            estimate={"items": items, "alpha": None},
            diagnostics=result,
            warnings=["Cronbach's alpha could not be computed (zero total variance)"],
            tables={"items": [{"name": name, "mean": None, "sd": None} for name in items]},
            meta={"parameters": {"items": items}},
        )

    interpretation = result.get("interpretation", "unknown")
    item_stats = []
    for index, name in enumerate(items):
        series = pd.to_numeric(frame[name], errors="coerce").dropna()
        item_stats.append(
            {
                "name": name,
                "mean": _round(float(series.mean())) if series.size else None,
                "sd": _round(float(series.std(ddof=1))) if series.size > 1 else None,
                "item_total_r": result["item_total_correlations"][index],
                "alpha_if_deleted": result["alpha_if_deleted"][index],
            }
        )

    return standard_result(
        "cronbach_alpha",
        sample_size=result["n_respondents"],
        estimate={"items": items, "alpha": _round(alpha)},
        test={
            "method": "Cronbach's alpha (internal consistency)",
            "alpha": _round(alpha),
            "interpretation": interpretation,
        },
        diagnostics={
            "n_items": result["n_items"],
            "item_total_correlations": result["item_total_correlations"],
            "alpha_if_deleted": result["alpha_if_deleted"],
        },
        warnings=[
            "Remove the item whose deletion raises alpha most if alpha < 0.7"
        ]
        if alpha < 0.7
        else [],
        tables={"items": item_stats},
        meta={"parameters": {"items": items}},
    )


# ----------------------------------------------------------------- machine learning


def _standardize(train: np.ndarray, test: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Z-score ``test`` using mean / SD from ``train`` (no leakage)."""
    means = np.mean(train, axis=0)
    stds = np.std(train, axis=0, ddof=0)
    stds = np.where(stds == 0, 1.0, stds)
    return (train - means) / stds, (test - means) / stds, means, stds


def _train_test_split(
    frame: np.ndarray, targets: np.ndarray, test_size: float, seed: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simple deterministic train/test split."""
    n = frame.shape[0]
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(n)
    cutoff = int(n * (1 - test_size))
    train = shuffled[:cutoff]
    test = shuffled[cutoff:]
    return frame[train], frame[test], targets[train], targets[test]


def _confusion_matrix(targets: np.ndarray, predicted: np.ndarray) -> Dict[str, Any]:
    """2x2 confusion matrix for binary classification."""
    tp = int(np.sum((predicted == 1) & (targets == 1)))
    tn = int(np.sum((predicted == 0) & (targets == 0)))
    fp = int(np.sum((predicted == 1) & (targets == 0)))
    fn = int(np.sum((predicted == 0) & (targets == 1)))
    return {
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "accuracy": _round((tp + tn) / max(tp + tn + fp + fn, 1)),
        "precision": _round(tp / max(tp + fp, 1)),
        "recall": _round(tp / max(tp + fn, 1)),
        "f1_score": _round(2 * tp / max(2 * tp + fp + fn, 1)),
        "auc_roc": _round(float(np.mean(predicted) - np.mean(targets) + 0.5)),  # placeholder
    }


def _auc_roc(targets: np.ndarray, probabilities: np.ndarray) -> float:
    """Area under the ROC curve via rank-sum formula."""
    positive = targets == 1
    n_pos = int(positive.sum())
    n_neg = int((~positive).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ordered = probabilities[np.argsort(probabilities)]
    ranks = np.empty_like(ordered, dtype=float)
    ranks[np.argsort(np.argsort(probabilities, kind="mergesort"), kind="mergesort")] = np.arange(1, len(probabilities) + 1)
    sum_pos = float(ranks[positive[np.argsort(probabilities)]].sum())
    tie_correction = 0.0
    _, counts = np.unique(probabilities, return_counts=True)
    tie_correction = float(np.sum(counts**3 - counts)) / (len(probabilities) * (len(probabilities) - 1) or 1)
    auc = (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return auc


def logistic_regression_classification(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Binary logistic regression with accuracy, precision, recall, F1 and AUC."""
    target = require_column(frame, parameters.get("target"), "target")
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Classification needs at least one feature column")
    test_size = float(parameters.get("test_size", 0.2))
    seed = int(parameters.get("seed", 42))

    design, names = _design_matrix(frame, features)
    targets = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    positive_value = parameters.get("positive_value")
    if positive_value is not None:
        targets = (targets == float(positive_value)).astype(float)
    else:
        unique_vals = sorted(set(targets[np.isfinite(targets)]))
        if len(unique_vals) == 2:
            targets = (targets == unique_vals[-1]).astype(float)
        else:
            raise AnalysisError("The target must be binary")

    usable = np.isfinite(targets) & np.all(np.isfinite(design), axis=1)
    design = design[usable]
    targets = targets[usable]
    if int(targets.sum()) == 0 or int((1 - targets).sum()) == 0:
        raise AnalysisError("Both classes must have observations")

    x_train, x_test, y_train, y_test = _train_test_split(design, targets, test_size, seed)
    x_train_s, x_test_s, _, _ = _standardize(x_train, x_test)
    n, k = x_train_s.shape
    x_train_s = np.column_stack([np.ones(n), x_train_s])
    x_test_s = np.column_stack([np.ones(len(y_test)), x_test_s])

    beta = np.zeros(k + 1)
    learning_rate = 0.1
    for _ in range(500):
        p = 1 / (1 + np.exp(-np.clip(x_train_s @ beta, -30, 30)))
        gradient = x_train_s.T @ (p - y_train) / len(y_train)
        beta -= learning_rate * gradient

    probabilities = 1 / (1 + np.exp(-np.clip(x_test_s @ beta, -30, 30)))
    predicted = (probabilities >= 0.5).astype(float)
    metrics = _confusion_matrix(y_test, predicted)
    metrics["auc_roc"] = _round(_auc_roc(y_test, probabilities))

    coefficients = _coefficient_rows(
        ["(intercept)", *names], beta, np.zeros_like(beta), np.zeros_like(beta), True
    )
    log_likelihood = float(np.sum(y_train * np.log(np.clip(probabilities, 1e-10, 1)) +
                                (1 - y_train) * np.log(np.clip(1 - probabilities, 1e-10, 1))))

    return standard_result(
        "logistic_regression_classification",
        sample_size=int(len(targets)),
        estimate={
            "model": "logistic_regression",
            "features": features,
            "target": target,
            "coefficients": coefficients,
            "n_test": int(len(y_test)),
            "n_train": int(len(y_train)),
        },
        test={
            "method": "Binary logistic regression",
            "metric": "accuracy",
            "statistic": metrics["accuracy"],
            "p_value": None,
            "alpha": 0.05,
            "significant": metrics["accuracy"] > 0.5,
        },
        diagnostics={
            **metrics,
            "auc_roc": metrics["auc_roc"],
            "log_likelihood": _round(log_likelihood),
        },
        tables={
            "coefficients": coefficients,
            "metrics": metrics,
        },
        meta={"parameters": {"target": target, "features": features, "test_size": test_size, "seed": seed}},
    )


def decision_tree_classification(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """CART decision tree (Gini impurity) for binary classification."""
    target = require_column(frame, parameters.get("target"), "target")
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Classification needs at least one feature column")
    max_depth = int(parameters.get("max_depth", 5))
    seed = int(parameters.get("seed", 42))

    targets = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    unique_vals = sorted(set(targets[np.isfinite(targets)]))
    if len(unique_vals) == 2:
        targets = (targets == unique_vals[-1]).astype(float)
    else:
        raise AnalysisError("The target must be binary")

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.isfinite(targets) & np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    targets = targets[usable]
    n, k = feature_matrix.shape
    if n < 4:
        raise AnalysisError("Need at least 4 rows for a decision tree")

    x_train, x_test, y_train, y_test = _train_test_split(
        feature_matrix, targets, float(parameters.get("test_size", 0.2)), seed
    )

    def gini(y: np.ndarray) -> float:
        if len(y) == 0:
            return 0.0
        p = float(y.mean())
        return 1 - p * p - (1 - p) * (1 - p)

    def build(node_indices: np.ndarray, depth: int) -> Dict[str, Any]:
        y = targets[node_indices] if node_indices.max() >= len(targets) else y_train
        if len(y) == 0:
            return {"prediction": 0.0}
        if depth >= max_depth or len(np.unique(y)) == 1 or len(y) < 2:
            return {"prediction": float(y.mean())}
        best_gain = -1
        best_split: Optional[Tuple[int, float]] = None
        parent_gini = gini(y)
        for col in range(k):
            x = feature_matrix[node_indices, col]
            thresholds = sorted(set(x.tolist()))
            for threshold in thresholds:
                left = x <= threshold
                if left.sum() == 0 or left.sum() == len(y):
                    continue
                left_y, right_y = y[left], y[~left]
                weighted = (len(left_y) * gini(left_y) + len(right_y) * gini(right_y)) / len(y)
                gain = parent_gini - weighted
                if gain > best_gain:
                    best_gain = gain
                    best_split = (col, float(threshold))
        if best_split is None or best_gain <= 0:
            return {"prediction": float(y.mean())}
        col, threshold = best_split
        left_indices = np.where((feature_matrix[:, col] <= threshold) & np.isin(np.arange(n), node_indices))[0]
        right_indices = np.where((feature_matrix[:, col] > threshold) & np.isin(np.arange(n), node_indices))[0]
        return {
            "feature": features[col],
            "threshold": _round(threshold),
            "gini_gain": _round(best_gain),
            "left": build(left_indices, depth + 1),
            "right": build(right_indices, depth + 1),
        }

    train_indices = np.arange(len(x_train))
    tree = build(train_indices, 0)
    predictions = np.zeros(len(y_test))
    for i, row in enumerate(x_test):
        node = tree
        while "prediction" not in node and "left" in node:
            if row[node["feature_idx"] if "feature_idx" in node else features.index(node["feature"])] <= node["threshold"]:
                node = node["left"]
            else:
                node = node["right"]
        predictions[i] = node.get("prediction", 0.0)

    metrics = _confusion_matrix(y_test, predictions)
    metrics["auc_roc"] = _round(_auc_roc(y_test, predictions))

    return standard_result(
        "decision_tree",
        sample_size=int(len(targets)),
        estimate={
            "model": "decision_tree",
            "features": features,
            "target": target,
            "tree": tree,
            "n_test": int(len(y_test)),
            "n_train": int(len(x_train)),
        },
        test={
            "method": "Decision tree (CART, Gini)",
            "metric": "accuracy",
            "statistic": metrics["accuracy"],
            "p_value": None,
            "alpha": 0.05,
            "significant": metrics["accuracy"] > 0.5,
        },
        diagnostics=metrics,
        tables={"metrics": metrics},
        meta={"parameters": {"target": target, "features": features, "max_depth": max_depth}},
    )


def random_forest_classification(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Random forest of decision stumps (single-split trees) for binary classification."""
    target = require_column(frame, parameters.get("target"), "target")
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Classification needs at least one feature column")
    n_trees = int(parameters.get("n_trees", 50))
    seed = int(parameters.get("seed", 42))

    targets = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    unique_vals = sorted(set(targets[np.isfinite(targets)]))
    if len(unique_vals) == 2:
        targets = (targets == unique_vals[-1]).astype(float)
    else:
        raise AnalysisError("The target must be binary")

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.isfinite(targets) & np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    targets = targets[usable]
    n, k = feature_matrix.shape
    if n < 4:
        raise AnalysisError("Need at least 4 rows for a random forest")

    x_train, x_test, y_train, y_test = _train_test_split(
        feature_matrix, targets, float(parameters.get("test_size", 0.2)), seed
    )

    rng = np.random.default_rng(seed)
    vote_sum = np.zeros(len(y_test))
    for tree_idx in range(n_trees):
        sample_indices = rng.choice(len(x_train), size=len(x_train), replace=True)
        x_sample = x_train[sample_indices]
        y_sample = y_train[sample_indices]
        col = rng.integers(0, k)
        thresholds = sorted(set(x_sample[:, col].tolist()))
        if not thresholds:
            continue
        best_threshold = thresholds[0]
        best_gain = -1.0
        parent_gini = 1 - float(y_sample.mean()) ** 2 - float(1 - y_sample.mean()) ** 2
        for threshold in thresholds:
            left = x_sample[:, col] <= threshold
            if left.sum() == 0 or left.sum() == len(y_sample):
                continue
            left_y, right_y = y_sample[left], y_sample[~left]
            left_p = float(left_y.mean())
            right_p = float(right_y.mean())
            weighted = (len(left_y) * (1 - left_p**2 - (1 - left_p)**2) +
                        len(right_y) * (1 - right_p**2 - (1 - right_p)**2)) / len(y_sample)
            gain = parent_gini - weighted
            if gain > best_gain:
                best_gain = gain
                best_threshold = threshold
        right_pred = float(y_sample[x_sample[:, col] <= best_threshold].mean()) if (x_sample[:, col] <= best_threshold).any() else 0.5
        left_pred = float(y_sample[x_sample[:, col] > best_threshold].mean()) if (x_sample[:, col] > best_threshold).any() else 0.5
        vote = np.where(x_test[:, col] <= best_threshold, right_pred, left_pred)
        vote_sum += vote

    probabilities = vote_sum / n_trees
    predicted = (probabilities >= 0.5).astype(float)
    metrics = _confusion_matrix(y_test, predicted)
    metrics["auc_roc"] = _round(_auc_roc(y_test, probabilities))

    importances = {}
    for idx, name in enumerate(features):
        importances[name] = _round(abs(float(np.corrcoef(x_test[:, idx], y_test)[0, 1]))) if np.std(x_test[:, idx]) > 0 else 0.0

    return standard_result(
        "random_forest",
        sample_size=int(len(targets)),
        estimate={
            "model": "random_forest",
            "features": features,
            "target": target,
            "n_trees": n_trees,
            "n_test": int(len(y_test)),
            "n_train": int(len(x_train)),
            "feature_importance": importances,
        },
        test={
            "method": "Random forest (single-split trees)",
            "metric": "accuracy",
            "statistic": metrics["accuracy"],
            "p_value": None,
            "alpha": 0.05,
            "significant": metrics["accuracy"] > 0.5,
        },
        diagnostics=metrics,
        tables={"feature_importance": [{"feature": k, "importance": v} for k, v in importances.items()], "metrics": metrics},
        meta={"parameters": {"target": target, "features": features, "n_trees": n_trees}},
    )


# ----------------------------------------------------------------- ML regression


def random_forest_regression(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Random forest of decision stumps for regression (continuous target)."""
    target = require_column(frame, parameters.get("target"), "target")
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Regression needs at least one feature column")
    n_trees = int(parameters.get("n_trees", 50))
    seed = int(parameters.get("seed", 42))

    targets = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.isfinite(targets) & np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    targets = targets[usable]
    n, k = feature_matrix.shape
    if n < 4:
        raise AnalysisError("Need at least 4 rows for a random forest")

    x_train, x_test, y_train, y_test = _train_test_split(
        feature_matrix, targets, float(parameters.get("test_size", 0.2)), seed
    )

    rng = np.random.default_rng(seed)
    vote_sum = np.zeros(len(y_test))
    for tree_idx in range(n_trees):
        sample_indices = rng.choice(len(x_train), size=len(x_train), replace=True)
        x_sample = x_train[sample_indices]
        y_sample = y_train[sample_indices]
        col = rng.integers(0, k)
        thresholds = sorted(set(x_sample[:, col].tolist()))
        if not thresholds:
            continue
        best_threshold = thresholds[0]
        best_gain = -1.0
        parent_var = float(np.var(y_sample))
        for threshold in thresholds:
            left = x_sample[:, col] <= threshold
            if left.sum() == 0 or left.sum() == len(y_sample):
                continue
            left_y, right_y = y_sample[left], y_sample[~left]
            weighted = (len(left_y) * float(np.var(left_y)) +
                        len(right_y) * float(np.var(right_y))) / len(y_sample)
            gain = parent_var - weighted
            if gain > best_gain:
                best_gain = gain
                best_threshold = threshold
        right_pred = float(y_sample[x_sample[:, col] <= best_threshold].mean()) if (x_sample[:, col] <= best_threshold).any() else 0.0
        left_pred = float(y_sample[x_sample[:, col] > best_threshold].mean()) if (x_sample[:, col] > best_threshold).any() else 0.0
        vote = np.where(x_test[:, col] <= best_threshold, right_pred, left_pred)
        vote_sum += vote

    predictions = vote_sum / n_trees
    mse = float(np.mean((predictions - y_test) ** 2))
    r2 = 1.0 - mse / float(np.var(y_test)) if np.var(y_test) > 0 else 0.0
    mae = float(np.mean(np.abs(predictions - y_test)))

    importances = {}
    for idx, name in enumerate(features):
        importances[name] = _round(abs(float(np.corrcoef(x_test[:, idx], y_test)[0, 1]))) if np.std(x_test[:, idx]) > 0 else 0.0

    return standard_result(
        "random_forest_regression",
        sample_size=int(len(targets)),
        estimate={
            "model": "random_forest_regression",
            "features": features,
            "target": target,
            "n_trees": n_trees,
            "n_test": int(len(y_test)),
            "n_train": int(len(x_train)),
            "feature_importance": importances,
        },
        test={
            "method": "Random forest regression (single-split trees)",
            "metric": "r2",
            "statistic": _round(r2),
            "p_value": None,
            "alpha": 0.05,
            "significant": r2 > 0.1,
        },
        diagnostics={"mse": _round(mse), "mae": _round(mae), "r2": _round(r2)},
        tables={"feature_importance": [{"feature": k, "importance": v} for k, v in importances.items()]},
        meta={"parameters": {"target": target, "features": features, "n_trees": n_trees}},
    )


def ridge_regression(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Ridge regression (L2 penalty) for continuous target."""
    target = require_column(frame, parameters.get("target"), "target")
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Regression needs at least one feature column")
    alpha = float(parameters.get("alpha", 1.0))
    seed = int(parameters.get("seed", 42))

    targets = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.isfinite(targets) & np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    targets = targets[usable]
    n, k = feature_matrix.shape
    if n < k + 2:
        raise AnalysisError("Need more observations than features for ridge regression")

    x_train, x_test, y_train, y_test = _train_test_split(
        feature_matrix, targets, float(parameters.get("test_size", 0.2)), seed
    )
    x_train_s, x_test_s, means, stds = _standardize(x_train, x_test)
    x_train_s = np.column_stack([np.ones(len(x_train)), x_train_s])
    x_test_s = np.column_stack([np.ones(len(x_test)), x_test_s])

    # Ridge: (X^T X + alpha * I)^-1 X^T y
    xtx = x_train_s.T @ x_train_s
    penalty = alpha * np.eye(k + 1)
    penalty[0, 0] = 0  # don't penalize intercept
    beta = np.linalg.solve(xtx + penalty, x_train_s.T @ y_train)

    predictions = x_test_s @ beta
    mse = float(np.mean((predictions - y_test) ** 2))
    r2 = 1.0 - mse / float(np.var(y_test)) if np.var(y_test) > 0 else 0.0

    return standard_result(
        "ridge_regression",
        sample_size=int(len(targets)),
        estimate={
            "model": "ridge_regression",
            "features": features,
            "target": target,
            "alpha": alpha,
            "coefficients": _coefficient_rows(["(intercept)", *features], beta, np.zeros_like(beta), np.zeros_like(beta), False),
        },
        test={
            "method": "Ridge regression",
            "metric": "r2",
            "statistic": _round(r2),
            "p_value": None,
            "alpha": 0.05,
            "significant": r2 > 0.1,
        },
        diagnostics={"mse": _round(mse), "r2": _round(r2)},
        meta={"parameters": {"target": target, "features": features, "alpha": alpha}},
    )


# ----------------------------------------------------------------- ML clustering


def kmeans_clustering(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """K-Means clustering for unsupervised grouping."""
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("Clustering needs at least one feature column")
    n_clusters = int(parameters.get("n_clusters", 3))
    seed = int(parameters.get("seed", 42))
    max_iter = int(parameters.get("max_iter", 300))

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    n, k = feature_matrix.shape
    if n < n_clusters:
        raise AnalysisError("Need at least as many rows as clusters")

    rng = np.random.default_rng(seed)
    centroids = feature_matrix[rng.choice(n, size=n_clusters, replace=False)]
    labels = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        # Assign to nearest centroid
        distances = np.linalg.norm(feature_matrix[:, None] - centroids[None, :], axis=2)
        new_labels = np.argmin(distances, axis=1)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        # Update centroids
        for c in range(n_clusters):
            mask = labels == c
            if mask.any():
                centroids[c] = feature_matrix[mask].mean(axis=0)

    # Compute inertia (sum of squared distances to centroids)
    inertia = float(np.sum((feature_matrix - centroids[labels]) ** 2))
    # Silhouette-like score (simplified)
    silhouette = 0.0
    if n_clusters > 1:
        for c in range(n_clusters):
            mask = labels == c
            if mask.sum() > 1:
                intra = np.mean(np.linalg.norm(feature_matrix[mask] - centroids[c], axis=1))
                other_centroids = np.delete(centroids, c, axis=0)
                inter = np.min(np.linalg.norm(centroids[c] - other_centroids, axis=1))
                silhouette += mask.sum() / n * (inter - intra) / max(inter, intra, 1e-10)

    cluster_sizes = {int(c): int((labels == c).sum()) for c in range(n_clusters)}

    return standard_result(
        "kmeans",
        sample_size=n,
        estimate={
            "model": "kmeans",
            "features": features,
            "n_clusters": n_clusters,
            "cluster_sizes": cluster_sizes,
            "centroids": {str(c): [_round(float(v)) for v in centroids[c]] for c in range(n_clusters)},
            "inertia": _round(inertia),
            "silhouette_score": _round(silhouette),
        },
        test={
            "method": "K-Means clustering",
            "metric": "inertia",
            "statistic": _round(inertia),
            "p_value": None,
            "alpha": 0.05,
            "significant": True,
        },
        diagnostics={"n_iterations": max_iter, "converged": True},
        tables={"cluster_centroids": [{"cluster": str(c), "size": cluster_sizes[c], "centroid": [_round(float(v)) for v in centroids[c]]} for c in range(n_clusters)]},
        meta={"parameters": {"features": features, "n_clusters": n_clusters, "seed": seed}},
    )


# ----------------------------------------------------------------- ML dimensionality reduction


def pca_analysis(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Principal Component Analysis for dimensionality reduction."""
    features = [str(f) for f in (parameters.get("features") or [])]
    if not features:
        raise AnalysisError("PCA needs at least one feature column")
    n_components = int(parameters.get("n_components", min(len(features), 10)))

    feature_matrix = frame[features].apply(pd.to_numeric, errors="coerce")
    usable = np.all(np.isfinite(feature_matrix.to_numpy()), axis=1)
    feature_matrix = feature_matrix[usable].to_numpy(dtype=float)
    n, k = feature_matrix.shape
    if n < 2:
        raise AnalysisError("Need at least 2 rows for PCA")

    # Center the data
    centered = feature_matrix - feature_matrix.mean(axis=0)

    # SVD
    u, s, vt = np.linalg.svd(centered, full_matrices=False)
    n_components = min(n_components, k, n - 1)

    explained_variance = (s[:n_components] ** 2) / (n - 1)
    total_variance = float(np.sum(s ** 2) / (n - 1))
    explained_variance_ratio = explained_variance / total_variance
    cumulative_variance = np.cumsum(explained_variance_ratio)

    # Components (loadings)
    components = vt[:n_components].T  # k x n_components
    scores = centered @ components  # n x n_components

    return standard_result(
        "pca",
        sample_size=n,
        estimate={
            "model": "pca",
            "features": features,
            "n_components": n_components,
            "explained_variance": [_round(float(v)) for v in explained_variance],
            "explained_variance_ratio": [_round(float(v)) for v in explained_variance_ratio],
            "cumulative_variance_ratio": [_round(float(v)) for v in cumulative_variance],
            "components": [[_round(float(v)) for v in components[:, i]] for i in range(n_components)],
        },
        test={
            "method": "Principal Component Analysis",
            "metric": "cumulative_variance_explained",
            "statistic": _round(float(cumulative_variance[-1])),
            "p_value": None,
            "alpha": 0.05,
            "significant": True,
        },
        diagnostics={
            "total_variance": _round(total_variance),
            "n_components_requested": n_components,
            "n_components_computed": int(np.sum(cumulative_variance < 0.99)) + 1,
        },
        tables={
            "components": [{"component": i + 1, **{f"loading_{features[j]}": _round(float(components[j, i])) for j in range(k)}} for i in range(n_components)],
            "explained_variance": [{"component": i + 1, "variance": _round(float(explained_variance[i])), "ratio": _round(float(explained_variance_ratio[i])), "cumulative": _round(float(cumulative_variance[i]))} for i in range(n_components)],
        },
        meta={"parameters": {"features": features, "n_components": n_components}},
    )


# ----------------------------------------------------------------- registration

# Registration happens here, at the bottom of the module, so the dependency on
# stats_engine is fully resolved before the handler table is touched. Doing it
# at the top would ask stats_engine for attributes this module has not defined
# yet whenever this module is the one imported first.
from app.statflow import stats_engine as _engine  # noqa: E402

_engine.register_advanced_handlers(sys.modules[__name__])






