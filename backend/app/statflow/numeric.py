"""Shared numerical primitives for the statflow analysis modules.

Every heavy model in this package -- GLMs, ARIMA, factor analysis, mixed
effects, causal designs -- needs the same low-level pieces: a likelihood
optimiser, robust standard errors, special functions, matrix helpers and
resamplers. They live here so each model file stays readable, and so the
package keeps working on a bare numpy + pandas install.

Nothing here knows about the ``standard_result`` shape; this is pure numerics
that the model modules wrap.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

# --------------------------------------------------------------------------
# Special functions
# --------------------------------------------------------------------------

# Lanczos g=7, n=9 coefficients. The series is evaluated with a fixed loop over
# nine terms, which is cheap; doing it per *element* in Python instead is what
# made a single likelihood evaluation take milliseconds.
_LANCZOS_G = 7.0
_LANCZOS_N = 9
_LANCZOS_P = (
    0.99999999999980993,
    676.5203681218851,
    -1259.1392167224028,
    771.32342877765313,
    -176.61502916214059,
    12.507343278686905,
    -0.13857109526572012,
    9.9843695780195716e-6,
    1.5056327351493116e-7,
)


def lgamma(x):
    """log|Gamma(x)| by the Lanczos series, vectorised over the input.

    A per-element Python loop here is invisible in a unit test and then
    dominates a whole fit: a Poisson/NB likelihood calls this once per
    observation per iteration, and the Newton Hessian calls it thousands of
    times.
    """
    values = np.asarray(x, dtype=float)
    scalar_input = values.ndim == 0
    flat = np.atleast_1d(values).astype(float)
    result = np.empty_like(flat)

    positive = flat > 0.5
    if np.any(positive):
        z = flat[positive] - 1.0
        series = np.full_like(z, _LANCZOS_P[0])
        for index in range(1, _LANCZOS_N):
            series = series + _LANCZOS_P[index] / (z + index)
        shifted = z + _LANCZOS_G + 0.5
        result[positive] = (
            0.5 * np.log(2 * np.pi)
            + (z + 0.5) * np.log(shifted)
            - shifted
            + np.log(series)
        )
    if np.any(~positive):
        # Reflection: Gamma(x)Gamma(1-x) = pi / sin(pi x). The reflected
        # argument is always above 0.5, so it is evaluated by the direct
        # series rather than by recursing into this function, which would
        # recurse forever.
        small = flat[~positive]
        sine = np.sin(np.pi * small)
        sine = np.where(np.abs(sine) < 1e-300, 1e-300, sine)
        complement = 1.0 - small
        z = complement - 1.0
        series = np.full_like(z, _LANCZOS_P[0])
        for index in range(1, _LANCZOS_N):
            series = series + _LANCZOS_P[index] / (z + index)
        shifted = z + _LANCZOS_G + 0.5
        positive_part = (
            0.5 * np.log(2 * np.pi)
            + (z + 0.5) * np.log(shifted)
            - shifted
            + np.log(series)
        )
        result[~positive] = np.log(np.pi / np.abs(sine)) - positive_part

    return float(result[0]) if scalar_input else result


def _lgamma_scalar(value: float) -> float:
    return lgamma(float(value))


#: Asymptotic-series terms for the digamma and trigamma, in Bernoulli-number
#: order. Signs alternate; getting them wrong shifts the answer by a few parts
#: in a million, which is enough to move a Newton step and not enough to look
#: obviously wrong in the output.
#:
#: psi(x) ~ log(x) - 1/(2x) - sum_k B_2k / (2k * x^(2k)). The -1/(2x) is the
#: first *term* of the series, not an additive constant: writing it as a
#: constant instead makes the error grow linearly with x, which reads as a
#: small constant offset near the threshold and grows without bound above it.
_DIGAMMA_TERMS = (
    (-0.5, 1),
    (-1.0 / 12.0, 2),
    (+1.0 / 120.0, 4),
    (-1.0 / 252.0, 6),
    (+1.0 / 240.0, 8),
    (-1.0 / 132.0, 10),
    (+691.0 / 32760.0, 12),
    (-1.0 / 12.0, 14),
    (+1385.0 / 5148.0, 16),
)
#: psi'(x) is obtained by differentiating the psi series above, rather than
#: being written out again: each psi term (c, x^-p) contributes (-c*p, x^-(p+1)),
#: and d/dx log(x) contributes the leading 1/x. Deriving one from the other
#: removes a whole class of bug -- the two series being written independently and
#: quietly disagreeing, which shows up only as a small constant offset.
_TRIGAMMA_TERMS = tuple(
    (-coefficient * power, power + 1) for coefficient, power in _DIGAMMA_TERMS
)
#: The recurrence is applied until every value reaches this threshold, above
#: which the asymptotic series has converged to full double precision. The
#: digamma series is divergent, so raising the threshold buys real accuracy
#: rather than just tidiness.
_POLISH_TARGET = 20.0


def digamma(x):
    """d/dx log Gamma(x): recurrence up to a threshold, then an asymptotic series.

    psi(x) = psi(x+1) - 1/x, so shifting a value up by one contributes -1/x at
    the value it came from. Getting that order backwards is an easy slip: the
    loop then divides by the shifted value instead of the original, which is
    wrong by a small constant and looks like nothing much at all.
    """
    values = np.atleast_1d(np.asarray(x, dtype=float)).astype(float)
    scalar_input = np.ndim(x) == 0
    step = np.zeros_like(values)
    for _ in range(int(_POLISH_TARGET) + 2):
        low = values < _POLISH_TARGET
        if not np.any(low):
            break
        safe = np.where(low, values, 1.0)
        step = step - np.where(low, 1.0 / safe, 0.0)
        values = values + low
    inverse = 1.0 / values
    series = np.zeros_like(values)
    for coefficient, power in _DIGAMMA_TERMS:
        series = series + coefficient * inverse ** power
    result = step + np.log(values) + series
    return float(result[0]) if scalar_input else result


def _digamma_scalar(value: float) -> float:
    return digamma(float(value))


def trigamma(x):
    """d^2/dx^2 log Gamma(x).

    psi'(x) = psi'(x+1) + 1/x^2, so the same shift adds 1/x^2.
    """
    values = np.atleast_1d(np.asarray(x, dtype=float)).astype(float)
    scalar_input = np.ndim(x) == 0
    step = np.zeros_like(values)
    for _ in range(int(_POLISH_TARGET) + 2):
        low = values < _POLISH_TARGET
        if not np.any(low):
            break
        safe = np.where(low, values, 1.0)
        step = step + np.where(low, 1.0 / safe ** 2, 0.0)
        values = values + low
    inverse = 1.0 / values
    series = np.zeros_like(values)
    for coefficient, power in _TRIGAMMA_TERMS:
        series = series + coefficient * inverse ** power
    # The leading 1/x of the asymptotic expansion is added here; the terms
    # above start at 1/x^2.
    result = step + inverse + series
    return float(result[0]) if scalar_input else result


def norm_pdf(x):
    value = np.asarray(x, dtype=float)
    return np.exp(-0.5 * value * value) / np.sqrt(2 * np.pi)


def norm_cdf(x):
    """Standard normal CDF, array-safe.

    ``distributions.normal_cdf`` goes through ``math.erf`` and therefore only
    accepts scalars, so the vectorised path is built here instead.
    """
    import math

    values = np.asarray(x, dtype=float)
    erf = np.vectorize(lambda v: math.erf(v / math.sqrt(2.0)), otypes=[float])
    return 0.5 * (1.0 + erf(values))


def norm_sf(x):
    return 1.0 - norm_cdf(x)


def norm_ppf(p):
    from app.statflow.distributions import normal_ppf

    return normal_ppf(p)


def chi2_sf(x: float, df: float) -> float:
    from app.statflow.distributions import gammaq

    # gammaq is the *upper* regularised incomplete gamma Q(a,x); gammap is the
    # lower one and returns the CDF, which silently inverts every p-value.
    return float(gammaq(0.5 * df, 0.5 * x))


def t_sf(x: float, df: float) -> float:
    from app.statflow.distributions import student_t_two_sided_p

    return float(student_t_two_sided_p(x, df))


def t_ppf(p: float, df: float) -> float:
    from app.statflow.distributions import student_t_ppf

    return float(student_t_ppf(p, df))


def inv_chisq(p: float, df: float) -> float:
    """Upper-tail inverse of chi-square, by bisection on the regularised gamma.

    ``distributions`` exposes the survival function but not its inverse, and
    information criteria and power calculations need the quantile.
    """
    if df <= 0:
        return 0.0
    if p >= 1.0:
        return 0.0
    if p <= 0.0:
        return float("inf")
    low, high = 1e-8, max(10.0, df * 4.0)
    while chi2_sf(high, df) > p and high < 1e8:
        high *= 2.0
    for _ in range(200):
        middle = 0.5 * (low + high)
        if chi2_sf(middle, df) > p:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


# --------------------------------------------------------------------------
# Matrix helpers
# --------------------------------------------------------------------------


def safe_inv(matrix: np.ndarray, ridge: float = 1e-10) -> np.ndarray:
    """Inverse that degrades gracefully on a singular matrix."""
    array = np.asarray(matrix, dtype=float)
    size = array.shape[0]
    scale = float(np.trace(array)) / size if size else 0.0
    if scale <= 0:
        scale = 1.0
    try:
        return np.linalg.inv(array + ridge * scale * np.eye(size))
    except np.linalg.LinAlgError:
        return np.linalg.pinv(array)


def sym(matrix: np.ndarray) -> np.ndarray:
    array = np.asarray(matrix, dtype=float)
    return (array + array.T) / 2.0


def is_spd(matrix: np.ndarray, tol: float = 1e-10) -> bool:
    array = np.asarray(matrix, dtype=float)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        return False
    try:
        eigenvalues = np.linalg.eigvalsh(sym(array))
    except np.linalg.LinAlgError:
        return False
    return bool(np.all(eigenvalues > tol * max(1.0, float(np.max(np.abs(eigenvalues))))))



# --------------------------------------------------------------------------
# Optimisation
# --------------------------------------------------------------------------


def numerical_gradient(
    function: Callable[[np.ndarray], float],
    point: np.ndarray,
    step: float = 1e-6,
) -> np.ndarray:
    """Central-difference gradient.

    Used wherever an analytic score is hard to get right: a wrong analytic
    derivative fails silently, because the optimiser still reports
    "converged" on something. The fallback is preferred over cleverness.
    """
    point = np.asarray(point, dtype=float)
    gradient = np.zeros_like(point)
    for index in range(point.size):
        forward = point.copy()
        backward = point.copy()
        forward[index] += step
        backward[index] -= step
        gradient[index] = (function(forward) - function(backward)) / (2 * step)
    return gradient


def numerical_hessian(
    function: Callable[[np.ndarray], float],
    point: np.ndarray,
    step: float = 1e-4,
) -> np.ndarray:
    """Central-difference Hessian, symmetrised."""
    point = np.asarray(point, dtype=float)
    size = point.size
    base = function(point)
    hessian = np.zeros((size, size))
    for row in range(size):
        for column in range(row, size):
            if row == column:
                up = point.copy()
                up[row] += step
                down = point.copy()
                down[row] -= step
                hessian[row, column] = (function(up) - 2 * base + function(down)) / step ** 2
                continue
            values = []
            for sign_row, sign_column in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                shifted = point.copy()
                shifted[row] += sign_row * step
                shifted[column] += sign_column * step
                values.append(function(shifted))
            entry = (values[0] - values[1] - values[2] + values[3]) / (4 * step * step)
            hessian[row, column] = entry
            hessian[column, row] = entry
    return sym(hessian)


def maximise(
    negative_loglik: Callable[[np.ndarray], float],
    start: np.ndarray,
    score: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    hessian: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    max_iter: int = 100,
    tol: float = 1e-7,
) -> Dict[str, Any]:
    """Maximise a likelihood with damped Newton steps.

    Returns the point, the log-likelihood, the parameter covariance and
    whether the fit settled.

    ``score`` is the gradient of the **log-likelihood** -- the quantity being
    maximised, not the negative log-likelihood the objective function returns.
    The sign matters: with the negative convention the ascent step silently
    becomes a descent step, every trial fails to improve, and the optimiser
    reports "converged" on its starting values.

    ``hessian`` should be the information matrix, i.e. the Hessian of the
    log-likelihood, which is negative definite. The *observed* Hessian of a GLM
    likelihood can be indefinite away from the optimum, and an indefinite matrix
    sends Newton off in a direction that increases the loss; the Fisher
    (expected) information is positive semidefinite by construction and keeps
    every step on an ascent path.

    Supplying both is optional. Without them the numerical versions are used,
    which are correct but slower.
    """
    point = np.asarray(start, dtype=float).copy()
    size = point.size
    best = float(-negative_loglik(point))
    converged = False
    steps = 0

    for _iteration in range(max_iter):
        if score is not None:
            grad = np.asarray(score(point), dtype=float)
        else:
            grad = -numerical_gradient(negative_loglik, point)
        grad = np.where(np.isfinite(grad), grad, 0.0)
        if float(np.max(np.abs(grad))) < tol:
            converged = True
            break

        if hessian is not None:
            information = sym(hessian(point))
        else:
            # The objective returns the *negative* log-likelihood, so its
            # Hessian is already the information matrix I = -Hess(loglik).
            # Negating it again yields a negative-definite matrix, the Newton
            # step reverses, and the optimiser reports "converged" on whatever
            # the line search can still improve.
            information = sym(numerical_hessian(negative_loglik, point))
        try:
            step = np.linalg.solve(information, grad)
        except np.linalg.LinAlgError:
            step = grad * 0.1
        if not np.all(np.isfinite(step)) or float(np.max(np.abs(step))) > 20.0:
            step = grad * 0.1

        improved = False
        scale = 1.0
        for _attempt in range(40):
            candidate = point + scale * step
            value = float(-negative_loglik(candidate))
            if np.isfinite(value) and value > best + 1e-12:
                point, best, steps = candidate, value, steps + 1
                improved = True
                break
            scale *= 0.5

        if not improved:
            # A bad Hessian must not stop a good optimiser: try a normalised
            # gradient-ascent step before declaring convergence.
            direction = grad / max(float(np.max(np.abs(grad))), 1e-12)
            scale = 0.05
            for _attempt in range(40):
                candidate = point + scale * direction
                value = float(-negative_loglik(candidate))
                if np.isfinite(value) and value > best + 1e-12:
                    point, best, steps = candidate, value, steps + 1
                    improved = True
                    break
                scale *= 0.5
        if not improved:
            converged = True
            break

    try:
        covariance = safe_inv(sym(numerical_hessian(negative_loglik, point)))
    except Exception:
        covariance = np.full((size, size), np.nan)
    variances = np.diag(covariance)
    standard_errors = np.where(
        np.isfinite(variances) & (variances > 1e-10),
        np.sqrt(np.clip(variances, 0.0, None)),
        np.nan,
    )
    return {
        "x": point,
        "log_likelihood": best,
        "cov": covariance,
        "se": standard_errors,
        "converged": bool(converged),
        "steps": steps,
    }


# --------------------------------------------------------------------------
# Inference helpers
# --------------------------------------------------------------------------


def coef_table(
    names: Sequence[str],
    beta: np.ndarray,
    se: np.ndarray,
    *,
    exponentiate: bool = False,
    t_df: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Coefficient rows with p-values and 95% intervals.

    ``t_df`` selects Student-t with that many residual degrees of freedom,
    which is what OLS needs; GLMs use the normal approximation.
    """
    from app.statflow.stats_engine import _exp_clipped, _round

    beta = np.asarray(beta, dtype=float)
    se = np.asarray(se, dtype=float)
    rows: List[Dict[str, Any]] = []
    for index, name in enumerate(names):
        estimate = float(beta[index])
        error = float(se[index]) if index < se.size else float("nan")
        usable = bool(np.isfinite(error) and error > 0)
        if usable:
            if t_df:
                p_value = t_sf(estimate / error, int(t_df))
                critical = t_ppf(0.975, int(t_df))
            else:
                critical = 1.96
                p_value = float(2.0 * (1.0 - float(norm_cdf(abs(estimate / error)))))
            low, high = estimate - critical * error, estimate + critical * error
        else:
            p_value = float("nan")
            low = high = float("nan")
        row: Dict[str, Any] = {
            "term": name,
            "beta": _round(estimate),
            "standard_error": _round(error) if np.isfinite(error) else None,
            "p_value": _round(p_value) if np.isfinite(p_value) else None,
            "significant": bool(p_value < 0.05) if np.isfinite(p_value) else None,
        }
        if exponentiate:
            row["exp"] = _round(_exp_clipped(estimate))
            row["exp_ci_lower"] = _round(_exp_clipped(low)) if usable else None
            row["exp_ci_upper"] = _round(_exp_clipped(high)) if usable else None
        else:
            row["ci_lower"] = _round(low) if usable else None
            row["ci_upper"] = _round(high) if usable else None
        rows.append(row)
    return rows


def cluster_covariance(
    residuals: np.ndarray,
    design: np.ndarray,
    groups: np.ndarray,
) -> np.ndarray:
    """Cluster-robust (CR1) covariance for arbitrary group labels.

    The right variance for clustered designs, surveys with PSUs and panel
    data, where errors correlate within a cluster but not across clusters.
    """
    residuals = np.asarray(residuals, dtype=float).reshape(-1, 1)
    design = np.asarray(design, dtype=float)
    n, k = design.shape
    bread = safe_inv(design.T @ design)
    labels = np.asarray(groups)
    unique = np.unique(labels)
    meat = np.zeros((k, k))
    for value in unique:
        mask = labels == value
        if not np.any(mask):
            continue
        block = design[mask].T @ residuals[mask]
        meat += block @ block.T
    correction = (len(unique) / max(len(unique) - 1, 1)) * ((n - 1) / max(n - k, 1))
    return sym(bread @ meat @ bread * correction)


def hc_covariance(residuals: np.ndarray, design: np.ndarray) -> np.ndarray:
    """White HC1 sandwich, for heteroscedastic but independent errors."""
    residuals = np.asarray(residuals, dtype=float).reshape(-1, 1)
    design = np.asarray(design, dtype=float)
    n, k = design.shape
    bread = safe_inv(design.T @ design)
    scores = design * residuals
    return sym(bread @ (scores.T @ scores) @ bread * (n / max(n - k, 1)))


def aic(log_likelihood: float, parameters: int) -> float:
    return float(-2.0 * log_likelihood + 2.0 * parameters)


def bic(log_likelihood: float, parameters: int, n: int) -> float:
    return float(-2.0 * log_likelihood + parameters * np.log(max(n, 1)))


def jackknife_se(values: np.ndarray) -> float:
    """Delete-one jackknife standard error from a vector of leave-one-out fits."""
    values = np.asarray(values, dtype=float)
    n = values.size
    if n < 2:
        return float("nan")
    replicates = (float(np.sum(values)) - values) / (n - 1)
    return float(np.sqrt((n - 1) / n * np.sum((replicates - replicates.mean()) ** 2)))


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average, shrinking the window at the edges."""
    values = np.asarray(values, dtype=float)
    n = values.size
    window = max(1, min(int(window), n))
    half = window // 2
    padded = np.pad(values, (half, window - 1 - half), mode="edge")
    smoothed = np.convolve(padded, np.ones(window) / window, mode="valid")
    return smoothed[:n]


def rng_from(parameters: Dict[str, Any]) -> np.random.Generator:
    """Reproducible generator; an explicit seed makes a run re-runnable."""
    seed = parameters.get("seed")
    if seed is None:
        seed = parameters.get("random_seed")
    try:
        return np.random.default_rng(int(seed) if seed is not None else 0)
    except (TypeError, ValueError):
        return np.random.default_rng(0)

        covariance = np.full((size, size), np.nan)
    variances = np.diag(covariance)
    standard_errors = np.where(
        np.isfinite(variances) & (variances > 1e-10),
        np.sqrt(np.clip(variances, 0.0, None)),
        np.nan,
    )
    return {
        "x": point,
        "log_likelihood": best,
        "cov": covariance,
        "se": standard_errors,
        "converged": bool(converged),
        "steps": steps,
    }


def nearest_spd(matrix: np.ndarray, floor: float = 1e-8) -> np.ndarray:
    """Project a symmetric matrix onto the nearest positive-definite one.

    Sample covariance matrices are singular whenever a column is constant or
    two columns are perfectly collinear, common in small survey data.
    Eigenvalue flooring keeps factor and cluster routines finite instead of
    letting one zero eigenvalue poison the whole decomposition.
    """
    array = sym(matrix)
    values, vectors = np.linalg.eigh(array)
    values = np.clip(values, floor, None)
    return (vectors * values) @ vectors.T


def standardize(values: np.ndarray) -> np.ndarray:
    """Zero-mean, unit-variance columns; constant columns are left at zero."""
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    centre = matrix.mean(axis=0)
    spread = matrix.std(axis=0, ddof=1) if matrix.shape[0] > 1 else np.ones(matrix.shape[1])
    spread = np.where(spread > 1e-12, spread, 1.0)
    return (matrix - centre) / spread


def corr_matrix(values: np.ndarray) -> np.ndarray:
    return np.clip(np.corrcoef(standardize(values), rowvar=False), -1.0, 1.0)


def remove_constant(matrix: np.ndarray, tol: float = 1e-12) -> Tuple[np.ndarray, List[int]]:
    """Drop columns with no variance; returns the trimmed matrix and kept indices."""
    array = np.asarray(matrix, dtype=float)
    keep = [i for i in range(array.shape[1]) if np.ptp(array[:, i]) > tol]
    if not keep:
        return array, []
    return array[:, keep], keep

    low, high = 1e-8, max(10.0, df * 4.0)
    while chi2_sf(high, df) > p and high < 1e8:
        high *= 2.0
    for _ in range(200):
        middle = 0.5 * (low + high)
        if chi2_sf(middle, df) > p:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)
