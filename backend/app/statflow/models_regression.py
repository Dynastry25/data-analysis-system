"""The regression family: every GLM and estimator the guide lists under
section 4 that is not already in ``advanced``.

Grouped by what they share rather than by what the guide numbers them, because
the shared part is the bulk of the work: a design matrix with dummy coding, a
likelihood, and the standard coefficient table.

Covers probit, LPM, multinomial and ordinal logit, negative binomial,
zero-inflated and hurdle count models, ridge/lasso/elastic net, Tobit,
quantile regression, mixed effects, fractional logit and multiple regression.
"""

import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.numeric import (
    aic,
    bic,
    coef_table,
    hc_covariance,
    maximise,
    safe_inv,
    t_sf,
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


def _feature_columns(
    parameters: Dict[str, Any], frame: pd.DataFrame, *, required: bool = True
) -> List[str]:
    raw = parameters.get("features") or parameters.get("predictors") or []
    if isinstance(raw, str):
        raw = [raw]
    columns = [str(name) for name in raw if str(name) in frame.columns]
    if not columns and required:
        raise AnalysisError(
            "Name at least one feature column: none of the given predictors is in the dataset"
        )
    return columns


def _complete_mask(frame: pd.DataFrame, columns: Sequence[str]) -> np.ndarray:
    mask = np.ones(len(frame), dtype=bool)
    for column in columns:
        mask &= frame[column].notna().to_numpy()
    return mask


def _norm_ppf(p: float) -> float:
    from app.statflow.distributions import normal_ppf

    return float(normal_ppf(min(max(p, 1e-9), 1 - 1e-9)))


def _mcfadden(y: np.ndarray, log_likelihood: float, null_log_likelihood: float) -> Optional[float]:
    """1 - ll_model/ll_null, the intercept-only fit of the *same* family.

    Both likelihoods must come from the same model. Comparing a probit fit
    against a Bernoulli log-likelihood mixes scales and produces a meaningless
    ratio, so the null model here is always refitted with the same link.
    """
    if not np.isfinite(null_log_likelihood) or null_log_likelihood == 0:
        return None
    return float(1.0 - log_likelihood / null_log_likelihood)


def _dw(residuals: np.ndarray) -> Optional[float]:
    if residuals.size < 2:
        return None
    denominator = float(residuals @ residuals)
    if denominator <= 0:
        return None
    return float(np.sum(np.diff(residuals) ** 2) / denominator)


def _binary_split(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, str]:
    """Shared 0/1 target handling for the binary-outcome models.

    Rejects a numeric outcome that is not already 0/1: silently splitting a
    continuous column at some arbitrary point produces plausible-looking
    odds ratios for a contrast nobody asked for.
    """
    from app.statflow.distributions import normal_cdf

    column = require_column(frame, parameters.get("target"), "target")
    raw = frame[column]
    values = pd.to_numeric(raw, errors="coerce")
    if int(values.notna().sum()) >= 3:
        unique = set(np.unique(values.dropna().tolist()))
        if unique <= {0.0, 1.0}:
            return values.to_numpy(dtype=float), column
        raise AnalysisError(
            f"'{column}' holds {sorted(unique)[:4]}: this model needs a 0/1 outcome, not a "
            "numeric scale. Recode it first"
        )
    categories = sorted(set(raw.dropna().astype(str)), key=str)
    if len(categories) != 2:
        raise AnalysisError(
            f"'{column}' has {len(categories)} categories; this model needs exactly 2"
        )
    positive = str(parameters.get("positive_category") or categories[-1])
    if positive not in categories:
        raise AnalysisError(f"positive_category '{positive}' is not one of {categories}")
    return (raw.astype(str) == positive).to_numpy(dtype=float), column


# ------------------------------------------------------------- probit / LPM


def probit(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Probit regression: a latent Gaussian index drives the 0/1 outcome."""
    from app.statflow.numeric import norm_cdf as _ncdf, norm_pdf as _npdf

    features = _feature_columns(parameters, frame, required=False)
    outcome, target = _binary_split(frame, parameters)
    mask = _complete_mask(frame, [target] + features)
    if int(mask.sum()) < 10:
        raise AnalysisError("Probit needs at least 10 complete rows")
    if not features:
        # An intercept-only probit is the null model, useful on its own for a
        # baseline rate; there is nothing to report beyond that.
        return standard_result(
            "probit",
            sample_size=int(mask.sum()),
            estimate={"target": target, "coefficients": [], "note": "No predictors supplied: null model only"},
            warnings=["No feature columns were given, so this is the intercept-only (null) model"],
            meta={"parameters": parameters},
        )

    design, names = _design_matrix(frame.loc[mask, :], features)
    y = outcome[mask]
    if len(set(y.tolist())) < 2:
        raise AnalysisError("The outcome is constant, so no coefficient can be estimated")

    # log P(Y=1|eta) = log Phi(eta), log P(Y=0|eta) = log(1 - Phi(eta)).
    # The linear form Phi(eta) is the likelihood itself, not its log: it exceeds
    # 1 and silently inverts every ratio built on it (McFadden R2, AIC).
    def nll(beta: np.ndarray) -> float:
        eta = np.clip(design @ beta, -35.0, 35.0)
        upper = _ncdf(eta)
        lower = 1.0 - upper
        return float(
            -np.sum(
                y * np.log(np.clip(upper, 1e-300, None))
                + (1 - y) * np.log(np.clip(lower, 1e-300, None))
            )
        )

    def score(beta: np.ndarray) -> np.ndarray:
        eta = np.clip(design @ beta, -35.0, 35.0)
        phi = _npdf(eta)
        # d/deta of the probit log-likelihood is phi(eta) * (y - Phi(eta))
        return design.T @ (phi * (y - _ncdf(eta)))



    def fisher(beta: np.ndarray) -> np.ndarray:
        phi = _npdf(np.clip(design @ beta, -35.0, 35.0))
        weighted = design * phi[:, None]
        # Fisher information sum(phi^2 x x') is positive semidefinite, unlike
        # the observed Hessian which is indefinite away from the optimum.
        return weighted.T @ weighted

    start = np.zeros(design.shape[1])
    start[0] = _norm_ppf(float(y.mean()))
    fit = maximise(nll, start, score=score, hessian=fisher)
    beta, se = fit["x"], fit["se"]

    # Null model: the same probit link with an intercept only, so the
    # pseudo-R2 compares like with like. Its MLE has the closed form
    # Phi^-1(mean(y)), but the shared optimiser is still used so both fits go
    # through one code path; the score is supplied because a bare numerical
    # Hessian on a single parameter is exactly zero at the origin for this
    # link, which would stall the search.
    ones = np.ones((design.shape[0], 1))

    def nll_null(b: np.ndarray) -> float:
        eta = np.clip(b[0] * ones[:, 0], -35.0, 35.0)
        upper = _ncdf(eta)
        lower = 1.0 - upper
        return float(
            -np.sum(
                y * np.log(np.clip(upper, 1e-300, None))
                + (1 - y) * np.log(np.clip(lower, 1e-300, None))
            )
        )

    def score_null(b: np.ndarray) -> np.ndarray:
        eta = np.clip(b[0] * ones[:, 0], -35.0, 35.0)
        return np.array([float(np.sum(_npdf(eta) * (y - _ncdf(eta))))])

    def fisher_null(b: np.ndarray) -> np.ndarray:
        phi = _npdf(np.clip(b[0] * ones[:, 0], -35.0, 35.0))
        return np.array([[float(np.sum(phi * phi))]])

    null = maximise(nll_null, np.array([start[0]]), score=score_null, hessian=fisher_null)
    pseudo_r2 = _mcfadden(y, fit["log_likelihood"], null["log_likelihood"])

    warnings: List[str] = []
    if not fit["converged"]:
        warnings.append("The optimiser stopped before converging; treat the fit as provisional")
    if float(np.max(np.abs(design @ beta))) > 6:
        warnings.append(
            "Some fitted probabilities are near 0 or 1, where the latent normal index "
            "is weakly identified"
        )
    return standard_result(
        "probit",
        sample_size=int(mask.sum()),
        estimate={
            "target": target,
            "link": "probit (latent normal)",
            "coefficients": coef_table(names, beta, se),
            "converged": fit["converged"],
        },
        effect_size={"name": "pseudo_r2_mcfadden", "value": _round(pseudo_r2)},
        diagnostics={"log_likelihood": _round(fit["log_likelihood"])},
        warnings=warnings,
        meta={"parameters": parameters, "note": "Coefficients are z-scores, not odds ratios"},
    )


def linear_probability_model(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """OLS on a 0/1 outcome: gives marginal effects directly.

    Weaker than logit where probabilities are bounded, but it is the right
    choice for marginal effects, many fixed effects, and IV/2SLS.
    """
    features = _feature_columns(parameters, frame)
    outcome, target = _binary_split(frame, parameters)
    mask = _complete_mask(frame, [target] + features)
    y = outcome[mask]
    design, names = _design_matrix(frame.loc[mask, :], features)
    n, k = design.shape
    if n <= k:
        raise AnalysisError("The LPM needs more rows than parameters")

    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ beta
    df = n - k
    sigma2 = float(residuals @ residuals) / max(df, 1)
    covariance = sigma2 * safe_inv(design.T @ design)
    se = np.sqrt(np.clip(np.diag(covariance), 0.0, None))

    fitted = design @ beta
    warnings: List[str] = []
    if float(np.max(fitted)) > 1.0 or float(np.min(fitted)) < 0.0:
        warnings.append(
            "The model predicts probabilities outside 0-1, the known weakness of the LPM. "
            "Read it as a linear index, or use logit/probit"
        )

    return standard_result(
        "linear_probability_model",
        sample_size=n,
        estimate={
            "target": target,
            "coefficients": coef_table(names, beta, se, t_df=df),
            "residual_df": df,
        },
        effect_size={
            "name": "r_squared",
            "value": _round(
                1.0
                - float(residuals @ residuals)
                / max(float(((y - y.mean()) ** 2).sum()), 1e-12)
            ),
        },
        diagnostics={
            "sigma_squared": _round(sigma2),
            "durbin_watson": _round(_dw(residuals)),
            "note": "Heteroscedastic by construction, so robust SEs are reported too",
        },
        tables={"coefficients_hc3": coef_table(names, beta, np.sqrt(np.clip(np.diag(hc_covariance(residuals, design)), 0.0, None)), t_df=df)},
        warnings=warnings,
        meta={"parameters": parameters},
    )


# Imported at the bottom on purpose: this module is built from the helpers in
# stats_engine, so touching the dispatch table before that import resolves
# would fail whenever this module happens to be the one imported first.
from app.statflow import stats_engine as _engine  # noqa: E402

_engine.REGRESSION_ANALYSES.setdefault("probit", "probit")
for _key, _attribute in _engine.REGRESSION_ANALYSES.items():
    _handler = getattr(sys.modules[__name__], _attribute, None)
    if _handler is not None:
        _engine.ANALYSIS_HANDLERS[_key] = _handler

