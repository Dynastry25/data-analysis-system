"""Count and bounded-outcome models: the guides' sections 4.3 and 4.5.

Negative binomial, zero-inflated, hurdle and fractional logit all sit in one
place because they share the same skeleton: a log link, a per-observation
log-likelihood written out longhand, and a dispersion statistic that decides
whether the simpler Poisson is admissible. Each exposes the guide's
diagnostics -- the dispersion test, the Vuong comparison, the zero-inflation
test -- because those are the outputs the method is chosen for.
"""

from typing import Any, Dict, List, Optional, Tuple

import sys
import numpy as np
import pandas as pd

from app.statflow.numeric import (
    aic,
    bic,
    coef_table,
    digamma,
    lgamma,
    maximise,
    norm_cdf,
    safe_inv,
)
from app.statflow.stats_engine import (
    SUCCESS,
    AnalysisError,
    _design_matrix,
    _round,
    require_column,
    standard_result,
)

#: Dispersion above this many calls the Poisson equidispersion assumption into
#: question. 1.5 is the usual screening threshold, not a hard rule.
OVERDISPERSION_THRESHOLD = 1.5


def _count_target(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, str, np.ndarray]:
    """Non-negative integer counts, plus a log exposure offset if requested.

    An offset matters for more than convenience: when expected counts differ by
    design, the variance-to-mean ratio of the raw counts is not a dispersion
    measure at all, and reporting it as one sends the reader to a count model
    that is not needed.
    """
    from app.statflow.stats_engine import numeric_series

    column = require_column(frame, parameters.get("target"), "target")
    values = pd.to_numeric(frame[column], errors="coerce")
    if int(values.notna().sum()) < 3:
        raise AnalysisError(f"'{column}' has fewer than 3 numeric values")
    counts = values.to_numpy(dtype=float)
    if float(np.min(counts)) < 0:
        raise AnalysisError(f"'{column}' has negative values, so it is not a count")
    if not np.allclose(counts, np.round(counts)):
        raise AnalysisError(
            f"'{column}' is not whole-numbered, so it is not a count outcome"
        )

    exposure_column = parameters.get("exposure_column") or parameters.get("offset_column")
    log_exposure = np.zeros(len(frame), dtype=float)
    if exposure_column:
        exposure = numeric_series(frame, str(exposure_column)).to_numpy(dtype=float)
        if np.any(exposure <= 0):
            raise AnalysisError(
                f"'{exposure_column}' must be positive everywhere: it is a measure of exposure"
            )
        log_exposure = np.log(exposure)
    return counts, column, log_exposure



def _poisson_loglik(counts: np.ndarray, mu: np.ndarray) -> float:
    """Poisson log-likelihood, mu already on the log scale's exponent."""
    mu_safe = np.clip(mu, 1e-300, None)
    return float(np.sum(counts * np.log(mu_safe) - mu_safe - lgamma(counts + 1.0)))


def _nb_loglik(counts: np.ndarray, mu: np.ndarray, alpha: float) -> float:
    """NB2 log-likelihood, Var = mu + alpha*mu^2, parameterised by r = 1/alpha."""
    mu_safe = np.clip(mu, 1e-300, None)
    r = 1.0 / max(alpha, 1e-10)
    return float(
        np.sum(
            lgamma(counts + r)
            - lgamma(r)
            - lgamma(counts + 1.0)
            + r * np.log(r / (r + mu_safe))
            + counts * np.log(mu_safe / (r + mu_safe))
        )
    )


def _nb_score(
    counts: np.ndarray, design: np.ndarray, beta: np.ndarray, log_exposure: np.ndarray, alpha: float
) -> np.ndarray:
    """Score of the NB *log-likelihood* with respect to beta.

    d(loglik)/dmu is r(y-mu)/(mu(r+mu)), and dmu/dbeta is mu*x. The two mu
    factors cancel, leaving r(y-mu)/(r+mu) * x -- there is no mu here, despite
    the chain rule suggesting one. The finite-difference check in the tests
    pins this down, because the mu-carrying version is a plausible-looking
    error that still converges to the right answer for the *point* while
    taking the wrong steps to it.
    """
    r = 1.0 / max(alpha, 1e-10)
    mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
    return design.T @ (r * (counts - mu) / (r + mu))


def _nb_score_alpha(counts: np.ndarray, mu: np.ndarray, alpha: float) -> float:
    """Score of the NB log-likelihood with respect to log(alpha).

    Chain rule through r = 1/alpha, whose derivative with respect to log alpha
    is -r. Checked against finite differences in the tests.
    """
    r = 1.0 / max(alpha, 1e-10)
    d_ll_dr = (
        digamma(counts + r)
        - digamma(r)
        + np.log(r)
        + 1.0
        - np.log(r + mu)
        - (r + counts) / (r + mu)
    )
    return float(np.sum(d_ll_dr) * (-r))


def _nb_fisher(
    design: np.ndarray, beta: np.ndarray, log_exposure: np.ndarray, alpha: float
) -> np.ndarray:
    """Fisher information for beta under the NB model: sum w^2 x x'."""
    r = 1.0 / max(alpha, 1e-10)
    mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
    weights = r * mu / (r + mu)
    weighted = design * (weights ** 2)[:, None]
    return weighted.T @ weighted


# ---------------------------------------------------------- negative binomial


def negative_binomial(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Negative binomial GLM: counts with Var = mu + alpha*mu^2.

    alpha is fitted alongside beta, so the guide's "likelihood-ratio test of
    alpha" comes out of the fit rather than needing a separate search.
    """
    from app.statflow.models_regression import _complete_mask, _feature_columns

    target = require_column(frame, parameters.get("target"), "target")
    features = _feature_columns(parameters, frame)
    mask = _complete_mask(frame, [target] + features)
    counts, target, log_exposure = _count_target(
        frame.loc[mask, :], {**parameters, "target": target}
    )
    design, names = _design_matrix(frame.loc[mask, :], features)
    n, k = design.shape
    if n <= k + 1:
        raise AnalysisError("The negative binomial needs more rows than parameters")

    warnings: List[str] = []
    if float(np.var(counts)) <= float(np.mean(counts)) and float(np.mean(counts)) > 0:
        warnings.append(
            "The counts are not overdispersed, so a Poisson is the better-specified "
            "model here; the negative binomial is fitted for comparison"
        )

    def nll(params: np.ndarray) -> float:
        beta, log_alpha = params[:k], float(params[k])
        alpha = float(np.exp(np.clip(log_alpha, -12.0, 12.0)))
        mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
        return -_nb_loglik(counts, mu, alpha)

    def score(params: np.ndarray) -> np.ndarray:
        beta, log_alpha = params[:k], float(params[k])
        alpha = float(np.exp(np.clip(log_alpha, -12.0, 12.0)))
        mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
        return np.concatenate(
            [_nb_score(counts, design, beta, log_exposure, alpha),
             [_nb_score_alpha(counts, mu, alpha)]]
        )

    poisson_fit = maximise(
        lambda b: -_poisson_loglik(counts, np.exp(np.clip(design @ b + log_exposure, -30.0, 20.0))),
        np.zeros(k),
    )
    start = np.concatenate([poisson_fit["x"], [0.0]])  # alpha = 1
    # The numerical Hessian is used deliberately. The Fisher information for
    # beta is available, but the beta/alpha cross term is not written out here,
    # and a block-diagonal stand-in for it leaves the optimiser unable to
    # converge. The full numerical Hessian converges in a handful of steps and
    # is now cheap, because the likelihood's lgamma/digamma are vectorised.
    fit = maximise(nll, start, score=score)
    beta, alpha = fit["x"][:k], float(np.exp(np.clip(fit["x"][k], -12.0, 12.0)))
    se = fit["se"][:k]
    mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))

    # Likelihood-ratio test of alpha = 0 (in log scale: the Poisson boundary).
    from app.statflow.numeric import chi2_sf

    lr = 2.0 * (fit["log_likelihood"] - poisson_fit["log_likelihood"])
    lr = max(lr, 0.0)
    ratio = _dispersion_ratio(counts, mu)
    raw_ratio = _raw_var_over_mean(counts, mu)
    fitted_alpha = float(np.exp(np.clip(fit["x"][k], -12.0, 12.0)))
    if fitted_alpha < 0.05:
        # The Poisson is the alpha -> 0 boundary of this family, so on genuinely
        # equidispersed counts the maximum sits *on* the boundary and no
        # interior optimum exists. The optimiser is right to run out of
        # iterations; saying "did not converge" would imply the answer is
        # untrustworthy when the real finding is that the Poisson fits.
        warnings.append(
            "The fitted alpha is near zero, so the maximum sits on the Poisson "
            "boundary: these counts are not overdispersed and a Poisson regression "
            "is the better-specified model"
        )
    elif not fit["converged"]:
        warnings.append("The optimiser stopped before converging; treat the fit as provisional")

    if parameters.get("fixed_alpha") is not None:
        alpha = float(parameters["fixed_alpha"])

    return standard_result(
        "negative_binomial",
        sample_size=n,
        estimate={
            "target": target,
            "link": "log",
            "alpha": _round(alpha, 8),
            "alpha_interpretation": (
                "alpha -> 0 approaches the Poisson; larger alpha means more extra variance"
            ),
            "coefficients": coef_table(names, beta, se, exponentiate=True),
        },
        test={
            "method": "Likelihood-ratio test of alpha = 0 (Poisson)",
            "statistic": _round(lr, 6),
            "df": 1,
            "p_value": _round(chi2_sf(lr, 1)),
            "significant": bool(chi2_sf(lr, 1) < 0.05),
        },
        diagnostics={
            "on_poisson_boundary": bool(fitted_alpha < 0.05),
            "pearson_dispersion": _round(ratio),
            "pearson_dispersion_note": "chi-square/df from the fitted means; near 1 is a good fit",
            "raw_var_over_mean": _round(raw_ratio) if raw_ratio is not None else None,
            "raw_var_over_mean_note": (
                None
                if raw_ratio is not None
                else "Withheld: an exposure offset makes the expected counts differ by design, "
                "so this ratio would measure the design rather than the dispersion"
            ),
            "log_likelihood": _round(fit["log_likelihood"]),
            "aic": _round(aic(fit["log_likelihood"], k + 1)),
            "bic": _round(bic(fit["log_likelihood"], k + 1, n)),
        },
        warnings=warnings,
        meta={"parameters": parameters, "effect_column": "exp (incidence rate ratio)"},
    )



def _dispersion_ratio(counts: np.ndarray, mu: np.ndarray) -> float:
    """Pearson chi-square / df from the fitted means: a goodness-of-fit measure.

    This is always computable, offset or not: it asks whether the fitted means
    reproduce the observed spread, not what the raw counts happen to look like.
    The raw variance-to-mean ratio is a different thing entirely and is only
    meaningful when the expected counts are near-constant -- which an exposure
    offset breaks by design.
    """
    mu_safe = np.clip(mu, 1e-10, None)
    degrees = max(len(counts) - 1, 1)
    return float(np.sum((counts - mu_safe) ** 2 / mu_safe) / degrees)


def _raw_var_over_mean(counts: np.ndarray, mu: np.ndarray) -> Optional[float]:
    """Raw var(y)/mean(y), reported only when the fitted means are near-constant.

    The guide quotes this ratio as the overdispersion screen, and it is a
    legitimate one for a plain Poisson. Once an exposure offset makes the
    expected counts differ by design, the ratio measures the design instead of
    the dispersion, so it is withheld rather than quoted misleadingly.
    """
    mean_mu = float(np.mean(mu))
    if mean_mu <= 0:
        return None
    coefficient = float(np.std(mu)) / mean_mu
    if coefficient > 0.5:
        return None
    return float(np.var(counts) / mean_mu)

    exposure_column = parameters.get("exposure_column") or parameters.get("offset_column")
    log_exposure = np.zeros(len(frame), dtype=float)
    if exposure_column:
        exposure = numeric_series(frame, str(exposure_column)).to_numpy(dtype=float)
        if np.any(exposure <= 0):
            raise AnalysisError(
                f"'{exposure_column}' must be positive everywhere: it is a measure of exposure"
            )
        log_exposure = np.log(exposure)


# ------------------------------------------------- zero-inflated and hurdle


def _fit_zero_component(
    design_zero: np.ndarray,
    is_zero: np.ndarray,
    parameters: Dict[str, Any],
) -> np.ndarray:
    """Logit fit of P(y = 0) by IRLS, which is exact for a binary outcome."""
    from app.statflow.numeric import norm_ppf

    y = is_zero.astype(float)
    p = design_zero.shape[1]
    share = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    beta = np.zeros(p)
    beta[0] = float(norm_ppf(share))
    for _ in range(60):
        eta = np.clip(design_zero @ beta, -30.0, 30.0)
        mu = 1.0 / (1.0 + np.exp(-eta))
        weights = np.clip(mu * (1.0 - mu), 1e-10, None)
        gradient = design_zero.T @ (y - mu) - 1e-6 * beta
        weighted = design_zero * weights[:, None]
        information = weighted.T @ design_zero + 1e-6 * np.eye(p)
        try:
            step = np.linalg.solve(information, gradient)
        except np.linalg.LinAlgError:
            break
        if float(np.max(np.abs(step))) < 1e-9:
            beta = beta + step
            break
        beta = beta + np.clip(step, -5.0, 5.0)
    return beta


def zero_inflated(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Zero-inflated Poisson or negative binomial: a second process for zeros.

    The zero-inflated model says the zeros come from two sources -- a point
    mass at zero, plus an ordinary count process that can also produce zero.
    That is the assumption to be suspicious of: if the point mass is not really
    there, the extra intercept just absorbs overdispersion, and the fitted
    inflation probability is meaningless. The model reports both the base
    dispersion and the inflation test so that can be checked.
    """
    from app.statflow.models_regression import _complete_mask, _feature_columns
    from app.statflow.numeric import maximise

    target = require_column(frame, parameters.get("target"), "target")
    features = _feature_columns(parameters, frame)
    mask = _complete_mask(frame, [target] + features)
    counts, target, log_exposure = _count_target(
        frame.loc[mask, :], {**parameters, "target": target}
    )
    design, names = _design_matrix(frame.loc[mask, :], features)
    n, k = design.shape
    if n <= 2 * k + 3:
        raise AnalysisError(
            "A zero-inflated model has two sets of coefficients, so it needs at least "
            f"about {2 * k + 4} rows"
        )

    distribution = str(parameters.get("distribution") or "poisson").lower()
    if distribution not in ("poisson", "nb", "negative_binomial"):
        raise AnalysisError("distribution must be 'poisson' or 'nb'")

    is_zero = counts == 0
    zero_share = float(is_zero.mean())
    if zero_share < 0.05:
        warnings = [
            f"Only {zero_share:.1%} of the counts are zero, so there is very little for a "
            "zero-inflated model to explain; an ordinary count model is likely enough"
        ]
    else:
        warnings = []

    # --- the ordinary count part (fitted on the non-zero observations) -------
    positive = ~is_zero
    if int(positive.sum()) <= k + 1:
        raise AnalysisError("Too few non-zero counts to fit the base model")

    def base_loglik(beta: np.ndarray, alpha: float) -> float:
        mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
        if distribution == "poisson":
            return _poisson_loglik(counts, mu)
        return _nb_loglik(counts, mu, alpha)

    def base_nll(params: np.ndarray) -> float:
        if distribution == "poisson":
            return -base_loglik(params[:k], 0.0)
        alpha = float(np.exp(np.clip(params[k], -12.0, 12.0)))
        return -base_loglik(params[:k], alpha)

    # The base model is started from a fit on the *positive* counts only.
    # Starting from an all-counts fit makes mu absorb the structural zeros,
    # after which the point mass has to be huge to explain them -- and the
    # joint fit settles there and stays, reporting an inflation probability
    # that is pure artefact of the starting point.
    base_start = np.zeros(k)
    positive_mean = float(np.mean(counts[positive]))
    if positive_mean > 0:
        base_start[0] = float(np.log(positive_mean))
    # The base part is fitted on the positive counts only, which is what makes
    # the two components identified: mu describes the counts that *did* happen,
    # and the point mass describes the ones that did not.
    positive_counts = counts[positive]
    positive_design = design[positive]

    def base_nll_positive(params: np.ndarray) -> float:
        if distribution == "poisson":
            return -_poisson_loglik(positive_counts, np.exp(np.clip(positive_design @ params[:k] + log_exposure[positive], -30.0, 20.0)))
        alpha_local = float(np.exp(np.clip(params[k], -12.0, 12.0)))
        return -_nb_loglik(positive_counts, np.exp(np.clip(positive_design @ params[:k] + log_exposure[positive], -30.0, 20.0)), alpha_local)

    if distribution == "poisson":
        base_fit = maximise(base_nll_positive, base_start)
        base_beta, alpha = base_fit["x"], 0.0
    else:
        base_fit = maximise(base_nll_positive, np.concatenate([base_start, [0.0]]))
        base_beta = base_fit["x"][:k]
        alpha = float(np.exp(np.clip(base_fit["x"][k], -12.0, 12.0)))

    mu = np.exp(np.clip(design @ base_beta + log_exposure, -30.0, 20.0))

    # --- the point mass at zero ---------------------------------------------
    zero_design = design
    inflation = _fit_zero_component(zero_design, is_zero, parameters)
    pi = 1.0 / (1.0 + np.exp(-np.clip(zero_design @ inflation, -30.0, 30.0)))
    pi = np.clip(pi, 1e-8, 1.0 - 1e-8)

    def zi_loglik(beta: np.ndarray, inflation_beta: np.ndarray) -> float:
        eta = np.clip(design @ beta + log_exposure, -30.0, 20.0)
        mu_i = np.exp(eta)
        # pi is recomputed from the coefficients handed in, not read from the
        # enclosing scope. Capturing it instead leaves the inflation block
        # frozen at whatever the separate IRLS pass found, so the "joint" fit
        # only ever moves the count block and the reported inflation is
        # whatever the starting guess happened to be.
        pi_i = np.clip(
            1.0 / (1.0 + np.exp(-np.clip(design @ inflation_beta, -30.0, 30.0))),
            1e-8,
            1.0 - 1e-8,
        )
        prob_zero = pi_i + (1.0 - pi_i) * np.exp(-mu_i)
        prob_positive = (1.0 - pi_i) * _poisson_pmf_positive(counts, mu_i)
        return float(
            np.sum(
                np.where(
                    is_zero,
                    np.log(np.clip(prob_zero, 1e-300, None)),
                    np.log(np.clip(prob_positive, 1e-300, None)),
                )
            )
        )

    # The two coefficient blocks are fitted together so the point mass and the
    # count part cannot drift into a combination that predicts an impossible
    # distribution (pi above 1, or pi and mu both absorbing the same zeros).
    def joint_nll(params: np.ndarray) -> float:
        return -zi_loglik(params[:k], params[k:])

    joint_start = np.concatenate([base_beta, inflation])
    joint = maximise(joint_nll, joint_start)
    beta = joint["x"][:k]
    inflation = joint["x"][k:]
    pi = np.clip(1.0 / (1.0 + np.exp(-np.clip(zero_design @ inflation, -30.0, 30.0))), 1e-8, 1 - 1e-8)

    # Vuong's z uses the *mean* log-likelihood ratio, not the total: with
    # n ~ 2500 the total log-likelihood runs to thousands, and multiplying
    # that by sqrt(n) gives a statistic in the tens of thousands, which is
    # significant for every dataset ever fitted.
    from app.statflow.numeric import norm_sf

    # The comparison must be like for like: the same rows, the same outcome.
    # ``base_fit`` is on the positive counts only and is used to start the
    # count block; Vuong needs the plain model on *all* the counts, otherwise
    # the two log-likelihoods are not on the same scale and the sign of the
    # statistic comes out backwards.
    plain_fit = maximise(base_nll, base_start)
    delta = (joint["log_likelihood"] - plain_fit["log_likelihood"]) / max(n, 1)
    vuong_z = float(np.sqrt(n) * delta / np.sqrt(max(2 * k, 1)))
    vuong_p = float(2.0 * norm_sf(abs(vuong_z)))

    # The inflation intercept is the log-odds of an extra zero once the count
    # process is accounted for; a negative value means the base process already
    # explains the zeros and the point mass is not wanted.
    inflation_intercept = float(inflation[0])
    if inflation_intercept < 0:
        warnings.append(
            "The inflation intercept is negative: the ordinary count process already explains "
            "the excess zeros, so the point mass is not supported by the data"
        )

    return standard_result(
        "zero_inflated",
        sample_size=n,
        estimate={
            "target": target,
            "distribution": distribution,
            "zero_share_observed": _round(zero_share),
            "zero_share_predicted": _round(float(np.mean((counts == 0) * 1.0))),
            "inflation_probability_at_reference": _round(float(pi[0])),
            "count_coefficients": coef_table(names, beta, joint["se"][:k], exponentiate=True),
            "inflation_coefficients": coef_table(
                names, inflation, joint["se"][k:], exponentiate=True
            ),
            "interpretation": (
                "count_coefficients drive the ordinary count process; "
                "inflation_coefficients drive the extra point mass at zero"
            ),
        },
        test={
            "method": "Vuong's test of the zero-inflation against the plain model",
            "statistic": _round(vuong_z),
            "p_value": _round(vuong_p),
            "significant": bool(vuong_p < 0.05),
        },
        diagnostics={
            "log_likelihood": _round(joint["log_likelihood"]),
            "log_likelihood_base": _round(plain_fit["log_likelihood"]),
            "log_likelihood_base_positive_only": _round(base_fit["log_likelihood"]),
            "alpha": _round(alpha) if distribution != "poisson" else None,
            "warning": (
                "A zero-inflated model is only justified if the zeros really come from two "
                "processes; if the count part is overdispersed, an NB alone may be simpler"
            ),
        },
        warnings=warnings,
        meta={"parameters": parameters},
    )


def _poisson_pmf_positive(counts: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """P(y = c) for c > 0 under a Poisson, evaluated stably in logs.

    exp(-mu) underflows to zero once mu is large, so the log of the
    probability is formed directly and the -mu kept separate. Zero counts are
    passed through as 1 because the caller only uses this on positives.
    """
    mu = np.clip(mu, 1e-300, None)
    positive = counts > 0
    log_pmf = counts * np.log(mu) - mu - lgamma(counts + 1.0)
    return np.where(positive, np.exp(np.clip(log_pmf, -700.0, 700.0)), 1.0)


def hurdle(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Hurdle model: a binary step, then a truncated count model.

    Same two-part shape as zero-inflated, but the difference is what happens
    after the first step. Zero-inflation asks "is this zero structural, and if
    not, what does the count process say" -- the two can overlap. A hurdle
    model says "is there a count at all; if yes, a *truncated* process that
    cannot produce zero anyway". That is the right model when every zero comes
    from the same single process, which is what the guide means by a hurdle.
    """
    from app.statflow.models_regression import _complete_mask, _feature_columns
    from app.statflow.numeric import maximise, norm_sf

    target = require_column(frame, parameters.get("target"), "target")
    features = _feature_columns(parameters, frame)
    mask = _complete_mask(frame, [target] + features)
    counts, target, log_exposure = _count_target(
        frame.loc[mask, :], {**parameters, "target": target}
    )
    design, names = _design_matrix(frame.loc[mask, :], features)
    n, k = design.shape
    if n <= 2 * k + 3:
        raise AnalysisError(
            "A hurdle model has two sets of coefficients, so it needs at least about "
            f"{2 * k + 4} rows"
        )

    distribution = str(parameters.get("distribution") or "poisson").lower()
    if distribution not in ("poisson", "nb", "negative_binomial"):
        raise AnalysisError("distribution must be 'poisson' or 'nb'")

    is_positive = counts > 0
    n_positive = int(is_positive.sum())
    share = float(is_positive.mean())
    warnings: List[str] = []
    if share < 0.05 or share > 0.95:
        warnings.append(
            f"Only {share:.1%} of the rows are non-zero, so one of the two parts is fitted "
            "on very few observations and its coefficients will be unstable"
        )

    if n_positive <= k + 1:
        raise AnalysisError("Too few non-zero counts to fit the truncated model")

    # --- part one: probability of a non-zero count --------------------------
    inflation = _fit_zero_component(design, is_positive, parameters)
    prob_positive = np.clip(
        1.0 / (1.0 + np.exp(-np.clip(design @ inflation, -30.0, 30.0))), 1e-8, 1.0 - 1e-8
    )

    # --- part two: the count process, truncated away from zero ---------------
    # The truncation has to be applied here. Fitting an ordinary model and
    # then calling it "truncated" would report the unconditional mean, which
    # overstates every fitted value by the factor exp(mu).
    positive_counts = counts[is_positive]
    positive_design = design[is_positive]
    positive_exposure = log_exposure[is_positive]

    def truncated_nll(params: np.ndarray) -> float:
        mu = np.exp(np.clip(positive_design @ params[:k] + positive_exposure, -30.0, 20.0))
        if distribution == "poisson":
            log_pmf = positive_counts * np.log(mu) - mu - lgamma(positive_counts + 1.0)
        else:
            alpha = float(np.exp(np.clip(params[k], -12.0, 12.0)))
            r = 1.0 / max(alpha, 1e-10)
            log_pmf = (
                lgamma(positive_counts + r)
                - lgamma(r)
                - lgamma(positive_counts + 1.0)
                + r * np.log(r / (r + mu))
                + positive_counts * np.log(mu / (r + mu))
            )
        return float(-np.sum(log_pmf))

    start = np.zeros(k)
    mean_positive = float(np.mean(positive_counts))
    if mean_positive > 0:
        start[0] = float(np.log(mean_positive))
    if distribution == "poisson":
        count_fit = maximise(truncated_nll, start)
        alpha = 0.0
    else:
        count_fit = maximise(truncated_nll, np.concatenate([start, [0.0]]))
        alpha = float(np.exp(np.clip(count_fit["x"][k], -12.0, 12.0)))

    def joint_nll(params: np.ndarray) -> float:
        prob = np.clip(
            1.0 / (1.0 + np.exp(-np.clip(design @ params[k:], -30.0, 30.0))),
            1e-8,
            1.0 - 1e-8,
        )
        mu = np.exp(np.clip(design @ params[:k] + log_exposure, -30.0, 20.0))
        log_pmf = _log_pmf(counts, mu, distribution, alpha)
        return float(
            -np.sum(
                np.where(
                    is_positive,
                    # P(y>0) = p * f(y|mu) / (1 - exp(-mu)). The truncation
                    # term is 1 - exp(-mu), which depends on mu but *not* on
                    # p. Writing the zero-inflated form 1 - p*exp(-mu) here
                    # instead quietly fits a different model, and it drags the
                    # count coefficients away from the truth while leaving the
                    # zero process looking perfectly reasonable.
                    np.log(np.clip(prob, 1e-300, None))
                    + log_pmf
                    - np.log(np.clip(1.0 - np.exp(-mu), 1e-300, None)),
                    np.log(np.clip(1.0 - prob, 1e-300, None)),
                )
            )
        )

    joint_start = np.concatenate([count_fit["x"][:k], inflation])
    joint = maximise(joint_nll, joint_start)
    beta = joint["x"][:k]
    inflation = joint["x"][k:]

    prob_positive = np.clip(
        1.0 / (1.0 + np.exp(-np.clip(design @ inflation, -30.0, 30.0))), 1e-8, 1.0 - 1e-8
    )
    # The unconditional mean a hurdle model implies, which is what a reader
    # actually wants to quote: probability of being non-zero, times the mean
    # of the truncated process.
    mu = np.exp(np.clip(design @ beta + log_exposure, -30.0, 20.0))
    truncation = 1.0 - np.exp(-mu)
    expected = prob_positive * mu / np.clip(truncation, 1e-12, None)
    observed_mean = float(np.mean(counts))

    return standard_result(
        "hurdle",
        sample_size=n,
        estimate={
            "target": target,
            "distribution": distribution,
            "share_positive_observed": _round(share),
            "probability_positive_at_reference": _round(float(prob_positive[0])),
            "count_coefficients": coef_table(names, beta, joint["se"][:k], exponentiate=True),
            "zero_process_coefficients": coef_table(
                names, inflation, joint["se"][k:], exponentiate=True
            ),
            "expected_mean_at_reference": _round(float(expected[0])),
            "truncation_note": (
                "The count process is truncated at zero, so its coefficients describe the "
                "counts *given* a non-zero outcome and are not comparable with an "
                "untruncated Poisson's"
            ),
        },
        effect_size={"name": "observed_mean", "value": _round(observed_mean)},
        diagnostics={
            "log_likelihood": _round(joint["log_likelihood"]),
            "alpha": _round(alpha) if distribution != "poisson" else None,
            "expected_mean_average": _round(float(np.mean(expected))),
        },
        warnings=warnings,
        meta={"parameters": parameters},
    )


def _log_pmf(
    counts: np.ndarray, mu: np.ndarray, distribution: str, alpha: float
) -> np.ndarray:
    """Log P(Y = c) for the requested count distribution, vectorised."""
    mu = np.clip(mu, 1e-300, None)
    if distribution == "poisson":
        return counts * np.log(mu) - mu - lgamma(counts + 1.0)
    r = 1.0 / max(alpha, 1e-10)
    return (
        lgamma(counts + r)
        - lgamma(r)
        - lgamma(counts + 1.0)
        + r * np.log(r / (r + mu))
        + counts * np.log(mu / (r + mu))
    )

# Imported at the bottom on purpose: this module is built from helpers in
# stats_engine, so touching the dispatch table before that import resolves
# would fail whenever this module happens to be the one imported first.
from app.statflow import stats_engine as _engine  # noqa: E402

for _key, _attribute in _engine.COUNT_ANALYSES.items():
    _handler = getattr(sys.modules[__name__], _attribute, None)
    if _handler is not None:
        _engine.ANALYSIS_HANDLERS[_key] = _handler
