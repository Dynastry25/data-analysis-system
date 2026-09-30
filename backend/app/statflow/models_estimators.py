"""Estimators that are not plain OLS or a single GLM.

This wave: censored regression (Tobit), penalised regression (ridge / lasso /
elastic net) and quantile regression. Each answers a "OLS is the wrong tool"
question from the guide, and each is fitted by an iterative scheme checked in
the tests against a closed form or a directly recomputed objective -- a
penalised fit that silently returns the OLS answer, or a quantile fit that
quietly returns the mean, is exactly what those tests exist to catch.
"""

import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.numeric import (
    coef_table,
    norm_cdf,
    norm_pdf,
    rng_from,
    safe_inv,
    sym,
)
from app.statflow.stats_engine import (
    INVALID,
    SUCCESS,
    AnalysisError,
    _design_matrix,
    _effect_label,
    _round,
    require_column,
    standard_result,
)


def _prepare(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, np.ndarray, List[str], str]:
    """Shared target/feature/complete-case handling for these estimators."""
    from app.statflow.models_regression import _complete_mask, _feature_columns

    target = require_column(frame, parameters.get("target"), "target")
    features = _feature_columns(parameters, frame)
    mask = _complete_mask(frame, [target] + features)
    if int(mask.sum()) < 5:
        raise AnalysisError("Too few complete rows to fit this model")
    values = pd.to_numeric(frame.loc[mask, target], errors="coerce").to_numpy(dtype=float)
    if not np.all(np.isfinite(values)):
        raise AnalysisError(f"'{target}' is not numeric, so it cannot be modelled directly")
    design, names = _design_matrix(frame.loc[mask, :], features)
    return values, design, names, target


def tobit(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Tobit: a censored outcome, observed only once it crosses a threshold.

    The likelihood has to know *where* the censoring happens. Treating a
    censored value as if it were the threshold itself, or ignoring the
    censoring as OLS does, both bias the estimate, so the bound is required
    rather than guessed.
    """
    from app.statflow.numeric import maximise

    y, design, names, target = _prepare(frame, parameters)
    n, k = design.shape
    if n <= k + 1:
        raise AnalysisError("Tobit needs more rows than parameters")

    mode = str(parameters.get("censor_type") or parameters.get("side") or "right").lower()
    if mode not in ("right", "left"):
        raise AnalysisError("censor_type must be 'right' (a ceiling) or 'left' (a floor)")

    threshold = parameters.get("threshold", parameters.get("censoring_value"))
    if threshold is None:
        raise AnalysisError(
            "Tobit needs the censoring threshold: name it with 'threshold'. It cannot be "
            "guessed, because a column that merely contains a large value is not censored"
        )
    limit = float(threshold)

    censored = (y >= limit - 1e-9) if mode == "right" else (y <= limit + 1e-9)
    n_censored = int(censored.sum())
    if n_censored == 0:
        raise AnalysisError(
            "No row is censored at that threshold, so there is no censored data and a "
            "Tobit model is not the right tool -- use OLS"
        )
    if n_censored == n:
        raise AnalysisError("Every row is censored, so the coefficients are not identified")

    warnings: List[str] = []
    if n_censored / n > 0.5:
        warnings.append(
            f"{n_censored} of {n} rows are censored, which is most of the sample; the "
            "latent-mean estimates will be sensitive to the normal assumption"
        )

    def nll(params: np.ndarray) -> float:
        beta, log_sigma = params[:k], float(params[k])
        sigma = float(np.exp(np.clip(log_sigma, -8.0, 8.0)))
        mu = design @ beta
        z = (y - mu) / sigma
        density = norm_pdf(z) / sigma
        # A ceiling censors values *above* the limit, so the event is
        # y* > limit, which is P(Z > z) = Phi(-z). A floor censors values
        # below it, giving P(y* < limit) = Phi(z). Swapping these two tails
        # still produces a clean-looking fit, biased toward the limit.
        probability = norm_cdf(-z if mode == "right" else z)
        contribution = np.where(censored, probability, density)
        return float(-np.sum(np.log(np.clip(contribution, 1e-300, None))))

    start = np.concatenate([np.linalg.lstsq(design, y, rcond=None)[0], [0.0]])
    fit = maximise(nll, start)
    beta, sigma = fit["x"][:k], float(np.exp(np.clip(fit["x"][k], -8.0, 8.0)))

    share = n_censored / n
    # The expected *observed* value differs from the latent mean for censored
    # rows, so both are reported. Quoting only beta invites the reader to
    # predict a value the data can never show.
    expected_observed: List[Dict[str, Any]] = []
    for name, row in zip(names, design):
        mu_row = float(row @ beta)
        if mode == "right":
            lam = (limit - mu_row) / sigma
            ratio = float(norm_pdf(lam)) / max(float(norm_cdf(lam)), 1e-12)
            value = mu_row + sigma * ratio - limit * (1.0 - float(norm_cdf(lam)))
        else:
            lam = (mu_row - limit) / sigma
            ratio = float(norm_pdf(lam)) / max(float(norm_cdf(lam)), 1e-12)
            value = mu_row - sigma * ratio + limit * (1.0 - float(norm_cdf(lam)))
        expected_observed.append({"term": name, "expected_value": _round(value)})

    return standard_result(
        "tobit",
        sample_size=n,
        estimate={
            "target": target,
            "censor_type": mode,
            "threshold": _round(limit),
            "censored_observations": n_censored,
            "censored_share": _round(share),
            "sigma": _round(sigma),
            "latent_mean_note": (
                "beta is the conditional mean of the latent variable y*, not of the "
                "observed value; for censored rows the expected observation differs"
            ),
            "expected_observed": expected_observed,
            "coefficients": coef_table(names, beta, fit["se"][:k], t_df=max(n - k, 1)),
        },
        test={"method": "Normal censored regression (Tobit)"},
        effect_size={
            "name": "censored_share",
            "value": _round(share),
            "interpretation": _effect_label(share, 0.05, 0.2, 0.4),
        },
        diagnostics={"log_likelihood": _round(fit["log_likelihood"])},
        warnings=warnings,
        meta={"parameters": parameters},
    )


# ------------------------------------------------- ridge / lasso / elastic net


def _standardised_design(
    design: np.ndarray, names: List[str]
) -> Tuple[np.ndarray, List[int], np.ndarray, np.ndarray]:
    """Centre and scale every column, keeping the intercept out of the penalty.

    Penalising an intercept would drag the fitted surface towards zero, which is
    a modelling choice nobody is asking for. The penalty also has to be
    scale-free: a column measured in thousands would otherwise dominate a
    column measured in ones, purely because of its units.
    """
    keep = [i for i in range(design.shape[1]) if i != 0 and np.ptp(design[:, i]) > 1e-12]
    if not keep:
        return design, keep, np.zeros(design.shape[0]), np.ones(design.shape[1])
    block = design[:, keep]
    centre = block.mean(axis=0)
    spread = block.std(axis=0, ddof=0)
    spread = np.where(spread > 1e-12, spread, 1.0)
    return (block - centre) / spread, keep, centre, spread


def _ridge_closed_form(
    design: np.ndarray, y: np.ndarray, alpha: float, l1_ratio: float
) -> np.ndarray:
    """Elastic-net solution in closed form, for the pure-ridge case.

    Ridge (and only ridge) has a linear solution. For the objective
    ||r||^2/(2n) + (alpha/2)||b||^2, multiplying through by n gives the normal
    equations (X'X + n*alpha*I) b = X'y, which is what this returns. The
    coordinate-descent path used for lasso is checked against this exact answer,
    which is what pins the 1/n scaling down: getting it wrong still converges,
    just to a different -- and wrong -- optimum.
    """
    n, k = design.shape
    gram = design.T @ design + alpha * n * np.eye(k)
    return safe_inv(gram) @ (design.T @ y)


def _elastic_net_coordinate(
    design: np.ndarray,
    y: np.ndarray,
    alpha: float,
    l1_ratio: float,
    max_iter: int = 300,
    tol: float = 1e-7,
) -> Tuple[np.ndarray, int]:
    """Cyclic coordinate descent for the elastic-net penalty.

    The objective is (1/(2n))||y - Xb||^2 + alpha*(l1_ratio*|b|_1 +
    (1-l1_ratio)/2*||b||^2). Each coefficient has a scalar solution given the
    others, so the sweep is exact and converges quickly; the lasso kink is
    handled by the usual soft-threshold, not by subgradient descent.
    """
    n, k = design.shape
    beta = np.zeros(k, dtype=float)
    l1 = alpha * l1_ratio
    l2 = alpha * (1.0 - l1_ratio)
    columns = [design[:, j] for j in range(k)]
    norms = np.array([float(c @ c) for c in columns])
    passes = 0
    for passes in range(1, max_iter + 1):
        largest = 0.0
        for j in range(k):
            if norms[j] <= 1e-14:
                continue
            column = columns[j]
            # Partial residual: y - Xb + x_j b_j, i.e. the part of the fit
            # that does not involve coefficient j. Recomputing the whole
            # matrix product here would be correct but needlessly slow.
            residual = y - design @ beta + column * beta[j]
            rho = float(column @ residual) / n
            previous = beta[j]
            if l1 > 0.0:
                # Soft-threshold the partial correlation, then divide by the
                # ridge term. Both penalties scale by 1/n because the loss is
                # written as ||r||^2/(2n).
                shrunk = np.sign(rho) * max(abs(rho) - l1, 0.0)
                beta[j] = shrunk / (norms[j] / n + l2)
            else:
                # Pure ridge has a linear solution for each coefficient, with no
                # term in the previous value: the L2 piece is already inside
                # the denominator. Carrying a stale l2*b_j across the update
                # looks harmless but converges to the wrong optimum, and the
                # error grows with alpha.
                beta[j] = rho / (norms[j] / n + l2)
            largest = max(largest, abs(beta[j] - previous))
        if largest < tol:
            break
    return beta, passes


def _elastic_net_objective(
    design: np.ndarray, y: np.ndarray, beta: np.ndarray, alpha: float, l1_ratio: float
) -> float:
    n = design.shape[0]
    residual = y - design @ beta
    l1 = alpha * l1_ratio * float(np.sum(np.abs(beta)))
    l2 = alpha * (1.0 - l1_ratio) / 2.0 * float(beta @ beta)
    return float(residual @ residual) / (2.0 * n) + l1 + l2


def ridge_lasso(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Ridge, lasso or elastic net, with the penalty chosen by k-fold CV.

    Standardised internally so the penalty is scale-free, then coefficients are
    mapped back to the original units so the output stays interpretable.
    """
    y, design, names, target = _prepare(frame, parameters)
    n, k = design.shape
    if n <= k + 1:
        raise AnalysisError("A penalised fit needs more rows than parameters")

    penalty = str(parameters.get("penalty") or parameters.get("model") or "ridge").lower()
    if penalty in ("elastic_net", "elasticnet", "elastic net"):
        penalty = "elastic_net"
    if penalty not in ("ridge", "lasso", "elastic_net"):
        raise AnalysisError("penalty must be 'ridge', 'lasso' or 'elastic_net'")

    l1_ratio = parameters.get("l1_ratio")
    if l1_ratio is None:
        l1_ratio = 0.5 if penalty == "elastic_net" else (1.0 if penalty == "lasso" else 0.0)
    l1_ratio = float(l1_ratio)
    if not 0.0 <= l1_ratio <= 1.0:
        raise AnalysisError("l1_ratio must lie between 0 and 1")

    block, keep, centre, spread = _standardised_design(design, names)
    intercept = float(np.mean(y - block @ np.zeros(block.shape[1])))
    centred_y = y - intercept

    def fit_at(alpha: float, X: np.ndarray, target_values: np.ndarray) -> np.ndarray:
        if alpha <= 0.0:
            gram = X.T @ X
            if not np.all(np.isfinite(gram)) or np.linalg.cond(gram) > 1e12:
                return np.zeros(X.shape[1])
            return safe_inv(gram) @ (X.T @ target_values)
        return _elastic_net_coordinate(X, target_values, alpha, l1_ratio)[0]

    # A path of candidate penalties, spanning "no penalty" to "everything gone".
    grid = parameters.get("alphas")
    if grid:
        candidates = sorted({float(a) for a in grid})
    else:
        candidates = list(np.logspace(-4, 2, 25))

    rng = rng_from(parameters)
    # k-fold CV on the held-out error. The fold assignment is fixed once from
    # the seeded generator, so the same request gives the same answer.
    order = rng.permutation(n)
    fold_count = max(2, min(int(parameters.get("folds") or 5), 10))
    order = rng.permutation(n)
    folds = [order[index::fold_count] for index in range(fold_count)]

    errors: List[float] = []
    for alpha in candidates:
        total = 0.0
        for index in range(fold_count):
            test = folds[index]
            train = np.concatenate(
                [folds[j] for j in range(fold_count) if j != index]
            )
            if train.size <= block.shape[1] or test.size == 0:
                continue
            beta = fit_at(alpha, block[train], centred_y[train])
            total += float(np.sum((centred_y[test] - block[test] @ beta) ** 2))
        errors.append(total / max(n, 1))

    best = int(np.argmin(errors))
    best_alpha = float(candidates[best])
    beta_scaled = fit_at(best_alpha, block, centred_y)
    passes = _elastic_net_coordinate(block, centred_y, best_alpha, l1_ratio)[1] if best_alpha > 0 else 0

    # Map back to the original units. Internally the model is
    #   y - intercept ~ sum_j (x_j - centre_j)/spread_j * b_j
    # so the coefficient on the *raw* column is b_j / spread_j, and the raw
    # intercept must absorb the centring:
    #   intercept_raw = intercept - sum_j b_j * centre_j / spread_j
    raw = np.zeros(k)
    for position, column in enumerate(keep):
        raw[column] = beta_scaled[position] / spread[position]
    if keep:
        raw[0] = intercept - float(
            np.sum(beta_scaled * centre / spread)
        )
    else:
        raw[0] = intercept

    predictions = design @ raw
    residuals = y - predictions
    total_variance = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - float(residuals @ residuals) / max(total_variance, 1e-12)

    warnings: List[str] = []
    if penalty in ("lasso", "elastic_net"):
        # Standardised coefficients are the ones compared against zero, since
        # a raw coefficient of 0.001 can be large on a tightly scaled column
        # and negligible on a widely spread one.
        surviving = [
            names[column]
            for position, column in enumerate(keep)
            if abs(beta_scaled[position]) > 1e-10
        ]
        dropped = [names[column] for column in keep if names[column] not in surviving]
        if dropped:
            warnings.append(
                "The penalty set these to exactly zero: " + ", ".join(dropped)
            )
    if best_alpha == max(candidates):
        warnings.append(
            "The best cross-validation score is at the top of the search range; a larger "
            "penalty may fit better still"
        )
    if n <= 10 * block.shape[1]:
        warnings.append(
            "There are fewer than 10 rows per predictor, so a penalised fit is likely to be "
            "unstable in-sample even if it predicts well"
        )
    warnings.append(
        "A penalised fit is for prediction. Its coefficients are biased by construction, so "
        "their p-values are not interpretable"
    )

    return standard_result(
        "ridge_lasso",
        sample_size=n,
        estimate={
            "target": target,
            "penalty": penalty,
            "l1_ratio": _round(l1_ratio),
            "alpha": best_alpha,
            "alpha_note": "chosen by %d-fold cross-validation on the held-out error" % fold_count,
            "standardised": True,
            "coefficients": coef_table(names, raw, np.full(k, np.nan)),
            "standardised_coefficients": [
                {"term": names[column], "value": _round(beta_scaled[position])}
                for position, column in enumerate(keep)
            ],
        },
        diagnostics={
            "cv_rmse_by_alpha": [
                {"alpha": _round(a), "rmse": _round(float(np.sqrt(e)))}
                for a, e in zip(candidates, errors)
            ],
            "r_squared": _round(r_squared),
            "coordinate_passes": passes,
        },
        warnings=warnings,
        meta={"parameters": parameters},
    )


# ------------------------------------------------------ quantile regression


def _quantile_loss(residual: np.ndarray, tau: float) -> np.ndarray:
    """The check (pinball) loss: tau-weighted absolute error.

    tau = 0.5 gives the absolute loss whose minimiser is the median, and the
    family is minimised by the tau-quantile. Using the mean instead -- or
    least squares -- quietly returns an OLS fit under a quantile label.
    """
    return np.where(residual >= 0.0, tau * residual, (tau - 1.0) * residual)


def _check_quantile_score(residual: np.ndarray, tau: float) -> np.ndarray:
    """d/dtau, ignoring the points where the loss is not differentiable."""
    return np.where(residual > 0.0, float(tau), np.where(residual < 0.0, float(tau) - 1.0, 0.0))


def quantile_regression(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Quantile regression at one or more taus, by smoothed quantile scores.

    Fitted with IRLS on the smoothed score, so it behaves like a GLM and
    inherits the same machinery. Several taus at once are the point of the
    method: comparing them shows whether an effect is concentrated in the poor
    or the rich, which a single OLS line cannot.
    """
    from app.statflow.numeric import maximise

    y, design, names, target = _prepare(frame, parameters)
    n, k = design.shape
    if n <= k + 1:
        raise AnalysisError("Quantile regression needs more rows than parameters")

    raw_taus = parameters.get("quantiles") or parameters.get("tau")
    if raw_taus is None:
        raw_taus = [0.1, 0.25, 0.5, 0.75, 0.9]
    if isinstance(raw_taus, (int, float)):
        raw_taus = [raw_taus]
    taus = [float(t) for t in raw_taus]
    for tau in taus:
        if not 0.0 < tau < 1.0:
            raise AnalysisError("every quantile must lie strictly between 0 and 1")

    def fit_one(tau: float) -> Dict[str, Any]:
        # A small ridge term keeps the design invertible when a column is
        # constant or nearly collinear; at 1e-6 it is far below the precision
        # anyone reports, and it makes the fit a well-posed problem.
        ridge = 1e-6

        def nll(beta: np.ndarray) -> float:
            # This is a *loss*, not a negative log-likelihood, and the sign has
            # to stay positive. `maximise` raises the objective to the negative
            # power, so passing -loss here would make it maximise the pinball
            # sum -- the coefficients then run off to large values, and the
            # optimiser reports success because the line search is happy with
            # the rising loss it is being asked to climb.
            residual = y - design @ beta
            return float(np.sum(_quantile_loss(residual, tau)) + ridge * float(beta @ beta))

        def score(beta: np.ndarray) -> np.ndarray:
            # Gradient of the negated objective, i.e. of what is being
            # maximised: X'w - 2*ridge*beta with w the check score.
            residual = y - design @ beta
            return design.T @ _check_quantile_score(residual, tau) - 2.0 * ridge * beta

        def information(beta: np.ndarray) -> np.ndarray:
            # The pinball loss is piecewise *linear*, so its second derivative
            # is zero almost everywhere and a numerical Hessian is a matrix of
            # zeros -- Newton has no curvature to work with and the fit runs
            # away. The Fisher information is the substitute that has it:
            # n * (X'X)^-1 X'diag(w^2)X (X'X)^-1, positive semidefinite by
            # construction, and the same matrix that gives the standard errors.
            residual = y - design @ beta
            weights = np.abs(_check_quantile_score(residual, tau))
            gram = design.T @ design + ridge * n * np.eye(k)
            bread = safe_inv(gram)
            scaled = design * (weights ** 2)[:, None]
            return sym(bread @ (scaled.T @ design) @ bread) * n

        start = np.linalg.lstsq(
            design, np.full(n, float(np.quantile(y, tau))), rcond=None
        )[0]
        return maximise(nll, start, score=score, hessian=information)

    fits: Dict[float, Dict[str, Any]] = {}
    for tau in taus:
        fits[tau] = fit_one(tau)

    # The asymptotic covariance of the quantile fit: bread * meat * bread with
    # the check scores as the meat. This is the quantity that makes the
    # per-quantile standard errors meaningful.
    def covariance_for(beta: np.ndarray, tau: float) -> np.ndarray:
        residual = y - design @ beta
        weights = np.abs(_check_quantile_score(residual, tau))
        bread = safe_inv(design.T @ design)
        # meat = X' diag(w^2) X, with the check scores as w. The magnitude of
        # the check score is tau or 1-tau and must not be clipped: the scale of
        # w is what sets the standard errors.
        scaled = design * (weights ** 2)[:, None]
        return sym(bread @ (scaled.T @ design) @ bread) * n

    rows: List[Dict[str, Any]] = []
    fits_needed: List[Dict[str, Any]] = []
    for tau in taus:
        fit = fits[tau]
        covariance = covariance_for(fit["x"], tau)
        se = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
        table = coef_table(names, fit["x"], se)
        for row in table:
            row["quantile"] = _round(tau)
        rows.extend(table)
        fits_needed.append(
            {
                "quantile": _round(tau),
                "intercept": _round(float(fit["x"][0])),
                "coefficients": [dict(row) for row in table],
            }
        )

    warnings: List[str] = []
    if 0.25 <= min(taus) and max(taus) <= 0.75:
        warnings.append(
            "The requested quantiles all sit in the middle of the distribution, where the "
            "estimates are similar; use 0.1/0.9 to compare tails"
        )
    if n < 10 * k:
        warnings.append(
            "Fewer than 10 rows per predictor: quantile estimates at the tails will be noisy"
        )
    warnings.append(
        "A coefficient that changes across quantiles means the effect is not a single "
        "constant slope; that is the finding the method exists to detect"
    )

    return standard_result(
        "quantile_regression",
        sample_size=n,
        estimate={
            "target": target,
            "quantiles": [_round(t) for t in taus],
            "method": "smoothed quantile scores (IRLS)",
            "fits": fits_needed,
        },
        effect_size={"name": "quantile_coefficients", "value": len(taus)},
        tables={"coefficients_by_quantile": rows},
        warnings=warnings,
        meta={"parameters": parameters},
    )


# Imported at the bottom on purpose: this module is built from helpers in
# stats_engine, so touching the dispatch table before that import resolves
# would fail whenever this module happens to be the one imported first.
from app.statflow import stats_engine as _engine  # noqa: E402

for _key, _attribute in _engine.ESTIMATOR_ANALYSES.items():
    _handler = getattr(sys.modules[__name__], _attribute, None)
    if _handler is not None:
        _engine.ANALYSIS_HANDLERS[_key] = _handler
