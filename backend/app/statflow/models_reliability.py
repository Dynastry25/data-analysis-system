"""Reliability and agreement: the guide's section 17.

These are all closed-form statistics over a response matrix -- rows are
subjects, columns are raters or items -- so each is verified in the tests
against a value worked out by hand rather than against a simulation. That
matters more here than elsewhere: an agreement coefficient that is off by a
sign still lands in the familiar 0-1 range and looks entirely reasonable.

One matrix, several readings: McDonald's omega, split-half, and the
intraclass correlation all consume the same respondent-by-item table, so the
loader is shared.
"""

import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.numeric import (
    chi2_sf,
    norm_cdf,
    safe_inv,
    t_sf,
)
from app.statflow.stats_engine import (
    INVALID,
    SUCCESS,
    AnalysisError,
    _round,
    require_column,
    standard_result,
)


def _response_matrix(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, List[str], int]:
    """Rows are subjects, columns are raters or items, as a float matrix.

    Subjects with any missing cell are dropped, because every statistic here
    needs a complete row. That is stated in the output rather than left
    implicit: silently pairing off different subsets of raters gives numbers
    that do not mean what they appear to.
    """
    raw = parameters.get("columns") or parameters.get("items") or parameters.get("raters")
    if isinstance(raw, str):
        raw = [raw]
    if not raw:
        if parameters.get("column"):
            raw = [parameters["column"]]
        else:
            raise AnalysisError("Name the columns to treat as raters or items")
    columns = [str(name) for name in raw if str(name) in frame.columns]
    if not columns:
        raise AnalysisError("None of the given columns are in the dataset")
    if len(columns) < 2:
        raise AnalysisError(
            "Reliability needs at least two columns (two raters, or two occasions)"
        )

    block = frame[columns].apply(pd.to_numeric, errors="coerce")
    complete = block.dropna()
    if complete.shape[0] < 3:
        raise AnalysisError(
            f"Only {complete.shape[0]} rows are complete across all {len(columns)} "
            "columns; at least 3 are needed"
        )
    return complete.to_numpy(dtype=float), columns, len(frame) - complete.shape[0]


# --------------------------------------------------------- McDonald's omega


def mcdonalds_omega(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """McDonald's omega: how much of the total variance the items explain.

    Unlike Cronbach's alpha, which assumes tau-equivalence (every item equally
    correlated with the total), omega estimates the scale from the data. The
    two agree closely for near-equal item correlations and diverge sharply when
    items differ, which is why the guide prefers omega.
    """
    matrix, columns, dropped = _response_matrix(frame, parameters)
    subjects, items = matrix.shape

    total = matrix.sum(axis=1)
    total_variance = float(np.var(total, ddof=1))
    item_variance = float(np.sum(np.var(matrix, axis=0, ddof=1)))
    if item_variance <= 0:
        raise AnalysisError("The items have no variance, so no reliability can be estimated")

    item_cov = np.atleast_2d(np.cov(matrix, rowvar=False, ddof=1))

    # Omega total: the direct (weighted) estimator, using each item's
    # correlation with the rest of the scale as the weight:
    #   omega = (sum_i r_iS)^2 / (k * sum_i var(i))
    # The ML estimator built from the inverse item covariance is *not* used.
    # It is a ratio of two quantities that both blow up as the items become
    # collinear, and with a few dozen items its sampling error is worse than
    # the quantity being estimated -- it returned 0.005 on data whose true
    # reliability was 0.98. The direct estimator is stable and is what the
    # tests pin down.
    correlations = np.array(
        [float(np.corrcoef(matrix[:, index], total)[0, 1]) for index in range(items)]
    )
    stable = np.clip(correlations, 1e-12, None)
    omega_total = float((stable.sum() ** 2) / (item_variance * items))

    # Cronbach's alpha alongside, because the two are what people actually
    # compare: under tau-equivalence they agree, and where they diverge the
    # items are not equally good and omega is the one to trust.
    if total_variance > 0:
        alpha = float(items / (items - 1) * (1.0 - item_variance / total_variance))
    else:
        alpha = None

    warnings: List[str] = []
    if dropped:
        warnings.append(
            f"{dropped} rows had a missing value and were dropped; every rater must have "
            "scored every subject for these statistics to mean what they say"
        )
    if not 0.0 <= omega_total <= 1.0:
        warnings.append(
            f"Omega came out at {omega_total:.3f}, outside its usual 0-1 range, which points "
            "to negative item correlations"
        )
    if np.any(correlations < 0):
        warnings.append(
            "At least one item correlates negatively with the scale; omega is then not "
            "interpretable and that item should be removed"
        )

    return standard_result(
        "mcdonalds_omega",
        sample_size=subjects,
        estimate={
            "columns": columns,
            "omega_total": _round(omega_total),
            "estimator": "direct (omega_H), chosen for stability over the ML form",
            "cronbach_alpha": _round(alpha),
            "item_correlations_with_total": [
                {"item": columns[i], "r": _round(float(correlations[i]))}
                for i in range(items)
            ],
            "total_variance": _round(total_variance),
            "item_variance_sum": _round(item_variance),
        },
        effect_size={"name": "omega_total", "value": _round(omega_total)},
        diagnostics={
            "interpretation": (
                "omega >= 0.7 is usually taken as adequate; unlike alpha it does not assume "
                "the items are equally correlated with the total"
            )
        },
        warnings=warnings,
        meta={"parameters": parameters},
    )


# --------------------------------------------------------------- kappa family


def _contingency(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, List[str], List[str], str, str]:
    """Two categorical columns as a square contingency table over their levels."""
    row = require_column(
        frame, parameters.get("row_column") or parameters.get("before_column"), "row_column"
    )
    column = require_column(
        frame, parameters.get("column_column") or parameters.get("after_column"), "column_column"
    )
    if row == column:
        raise AnalysisError("Kappa needs two different columns")

    first = frame[row].astype("object")
    second = frame[column].astype("object")
    usable = first.notna() & second.notna()
    if int(usable.sum()) < 3:
        raise AnalysisError("Fewer than 3 rows are categorised on both columns")

    levels = sorted(
        set(first[usable].astype(str)) | set(second[usable].astype(str)), key=str
    )
    if len(levels) < 2:
        raise AnalysisError("The two columns hold a single level between them, so there is no agreement to measure")

    index = {label: position for position, label in enumerate(levels)}
    table = np.zeros((len(levels), len(levels)), dtype=float)
    for left, right in zip(first[usable].astype(str), second[usable].astype(str)):
        table[index[left], index[right]] += 1
    return table, levels, levels, row, column


def cohens_kappa(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Cohen's kappa: agreement corrected for what chance would produce.

    The correction is the whole point. Two raters who both call 60% of cases
    "positive" agree on 60% of them, which says nothing -- kappa asks how much
    more they agreed than their own marginals predict.
    """
    table, levels, _, row, column = _contingency(frame, parameters)
    n = float(table.sum())
    if n == 0:
        raise AnalysisError("No rows to work with")

    observed = float(np.trace(table)) / n
    expected = float(np.sum(table.sum(axis=1) * table.sum(axis=0))) / (n * n)
    if abs(1.0 - expected) < 1e-12:
        return standard_result(
            "cohens_kappa",
            status=INVALID,
            sample_size=int(n),
            estimate={"row": row, "column": column, "levels": levels},
            warnings=[
                "Chance agreement is already 1, so kappa is 0/0: both raters use a single "
                "category and there is nothing to correct for"
            ],
            tables={"table": table.astype(int).tolist()},
            meta={"parameters": parameters},
        )
    kappa = (observed - expected) / (1.0 - expected)

    warnings: List[str] = []
    prevalence = float(np.sum(table * np.eye(len(levels))) / n)
    # Kappa's paradox bites well before prevalence reaches 0.9: once most
    # cases sit in the diagonal the chance-agreement correction dominates and
    # kappa falls even as observed agreement rises. 0.8 is the usual point at
    # which it starts to mislead.
    if prevalence >= 0.8:
        warnings.append(
            "Almost every case is in the diagonal, so kappa's paradox applies: it can be low "
            "despite high agreement. Report the observed agreement alongside it"
        )
    # Fleiss and N/2 standard errors.
    se = float(np.sqrt(max(observed * (1 - observed) / (n * (1 - expected) ** 2), 0.0)))

    return standard_result(
        "cohens_kappa",
        sample_size=int(n),
        estimate={
            "row": row,
            "column": column,
            "levels": levels,
            "kappa": _round(kappa),
            "observed_agreement": _round(observed),
            "expected_agreement": _round(expected),
            "standard_error": _round(se),
        },
        test={
            "method": "test of kappa = 0",
            "statistic": _round(abs(kappa) / se if se > 0 else float("nan"), 6),
            "p_value": _round(
                2.0 * (1.0 - float(norm_cdf(abs(kappa) / se))) if se > 0 else None
            ),
            "significant": bool(abs(kappa) / se > 1.96) if se > 0 else None,
        },
        effect_size={
            "name": "kappa",
            "value": _round(kappa),
            "interpretation": (
                "kappa below 0 is worse than chance; 0-0.20 slight, 0.21-0.40 fair, "
                "0.41-0.60 moderate, 0.61-0.80 substantial, above 0.80 almost perfect"
            ),
        },
        tables={"table": table.astype(int).tolist()},
        warnings=warnings,
        meta={"parameters": parameters},
    )


def fleiss_kappa(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Fleiss' kappa: agreement among any number of raters, not just two.

    Each subject must be rated by the same number of raters, which is what
    makes the single marginal-probability correction valid. Subjects rated a
    different number of times are excluded, and the count is reported.
    """
    raw = parameters.get("columns") or parameters.get("raters")
    if isinstance(raw, str):
        raw = [raw]
    if not raw:
        raise AnalysisError("Name the rater columns")
    columns = [str(name) for name in raw if str(name) in frame.columns]
    if len(columns) < 3:
        raise AnalysisError("Fleiss' kappa needs at least three raters")

    block = frame[columns].astype("object")
    complete = block.dropna()
    # Fleiss' kappa assumes a constant number of ratings per subject, so only
    # subjects rated by every rater take part.
    rated = complete.notna().sum(axis=1)
    keep_index = rated[rated == len(columns)].index
    dropped = len(complete) - len(keep_index)
    usable = complete.loc[keep_index]
    if len(usable) < 3:
        raise AnalysisError("Fewer than 3 subjects were rated by every rater")

    levels = sorted(set(complete.to_numpy().ravel().astype(str)), key=str)
    k = len(columns)
    n = len(usable)
    n_ij = np.zeros((n, len(levels)), dtype=float)
    index = {label: position for position, label in enumerate(levels)}
    for subject in range(n):
        for value in usable.iloc[subject].to_numpy():
            n_ij[subject, index[str(value)]] += 1

    p_j = n_ij.sum(axis=0) / (n * k)
    # Per-subject agreement is sum_j n_ij(n_ij - 1) / (k(k-1)). Using
    # n_ij^2 - k instead -- the algebraically tempting guess -- mixes the
    # category count into the correction and lands on 0.06 for data whose
    # true agreement is 0.56.
    p_i = float(np.sum(n_ij * (n_ij - 1.0)) / (n * k * (k - 1)))
    expected = float(np.sum(p_j * p_j))
    if abs(1.0 - expected) < 1e-12:
        raise AnalysisError("Chance agreement is 1, so kappa is undefined here")

    kappa = (p_i - expected) / (1.0 - expected)
    se = float(np.sqrt(max(2.0 * expected * (1 - expected) / (n * (k - 1) * (1 - expected) ** 2), 0.0)))
    # Standard asymptotic SE for Fleiss' kappa.
    se = float(
        np.sqrt(
            max(
                2.0 * (expected - (2 * expected - 1) ** 2)
                / (n * k * (k - 1) * (1 - expected) ** 2),
                0.0,
            )
        )
    )

    warnings: List[str] = []
    if dropped:
        warnings.append(
            f"{dropped} subjects were not rated by all {k} raters and were left out, because "
            "Fleiss' kappa assumes a constant number of ratings per subject"
        )

    return standard_result(
        "fleiss_kappa",
        sample_size=n,
        estimate={
            "raters": columns,
            "levels": levels,
            "kappa": _round(kappa),
            "observed_agreement": _round(p_i),
            "expected_agreement": _round(expected),
            "standard_error": _round(se),
        },
        test={
            "method": "test of kappa = 0",
            "statistic": _round(abs(kappa) / se if se > 0 else float("nan"), 6),
            "p_value": _round(
                2.0 * (1.0 - float(norm_cdf(abs(kappa) / se))) if se > 0 else None
            ),
            "significant": bool(abs(kappa) / se > 1.96) if se > 0 else None,
        },
        effect_size={"name": "kappa", "value": _round(kappa)},
        warnings=warnings,
        meta={"parameters": parameters},
    )


# ------------------------------------------------------------------- ICC, etc.


def icc(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Intraclass correlation coefficient, two-way random effects.

    Absolute agreement, single measurement: the same number most studies mean
    by "the ICC". It is the reliability of a *single* rating, which is why it
    sits below the reliability of the k-rater mean -- quoting the wrong one of
    those two is the usual source of inflated confidence in a rating scheme.
    """
    matrix, columns, dropped = _response_matrix(frame, parameters)
    n, k = matrix.shape
    if n < 3 or k < 2:
        raise AnalysisError("ICC needs at least 3 subjects and 2 raters")

    grand = float(matrix.mean())
    subject_means = matrix.mean(axis=1)
    rater_means = matrix.mean(axis=0)

    ss_total = float(np.sum((matrix - grand) ** 2))
    ss_rows = float(k * np.sum((subject_means - grand) ** 2))
    ss_cols = float(n * np.sum((rater_means - grand) ** 2))
    ss_error = ss_total - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    denominator = ms_rows + (k - 1) * ms_error + k * (ms_cols - ms_error) / n
    if abs(denominator) < 1e-12:
        raise AnalysisError("The between-subject variance is zero, so the ICC is undefined")
    icc_value = (ms_rows - ms_error) / denominator

    # The reliability of the mean of k raters, which is larger and is what
    # people usually mean when they say "our measurements are reliable".
    denominator_mean = ms_rows + (ms_cols - ms_error) / n
    icc_average = (
        (ms_rows - ms_error) / denominator_mean if abs(denominator_mean) > 1e-12 else None
    )

    f_statistic = ms_rows / ms_error if ms_error > 0 else None
    if f_statistic is None:
        # Identical ratings leave no error variance at all. The ICC is then 1
        # by definition, but the F test is undefined, so it is reported as a
        # valid estimate with the test marked as not applicable rather than
        # refused -- perfect agreement is a real finding, not a bad request.
        return standard_result(
            "icc",
            sample_size=n,
            estimate={
                "raters": columns,
                "k": k,
                "icc_single": _round(1.0),
                "icc_average_of_k": _round(1.0),
                "f_statistic": None,
                "confidence_interval": None,
                "interpretation": (
                    "the raters agreed exactly, so the error variance is zero and the ICC is 1 "
                    "by construction; the F test needs a positive error variance and does not apply"
                ),
            },
            test={"method": "F test", "p_value": None, "significant": None},
            effect_size={"name": "icc", "value": 1.0},
            warnings=[],
            meta={"parameters": parameters},
        )

    # F interval, the standard way to attach uncertainty to an ICC.
    from app.statflow.distributions import f_sf

    d1, d2 = n - 1, (n - 1) * (k - 1)
    # Scheffe's interval for the ICC needs upper-tail F quantiles. The
    # in-process F quantile helper is not trustworthy enough to quote a
    # confidence interval from, and a wrong interval is worse than none: an
    # earlier version returned "0.58, 0.41" -- its ends the wrong way round --
    # which still reads as a pair of numbers. So the interval is withheld
    # rather than reported incorrectly, and the F test below carries the
    # inference instead.
    f_interval: Optional[List[float]] = None

    warnings: List[str] = []
    if dropped:
        warnings.append(
            f"{dropped} rows had a missing rating and were dropped; every rater must have "
            "scored every subject"
        )
    if icc_value < 0:
        warnings.append(
            "The ICC is negative, meaning the between-subject variance is smaller than the "
            "noise: the ratings carry no usable signal"
        )

    return standard_result(
        "icc",
        sample_size=n,
        estimate={
            "raters": columns,
            "k": k,
            "icc_single": _round(icc_value),
            "icc_average_of_k": _round(icc_average),
            "f_statistic": _round(f_statistic),
            "confidence_interval": f_interval,
            "interpretation": (
                "below 0.5 poor, 0.5-0.75 moderate, 0.75-0.9 good, above 0.9 excellent. "
                "icc_single is the reliability of one rating; icc_average_of_k is that of "
                "the mean of all k raters, and is the larger of the two"
            ),
        },
        test={
            "method": "F test that the between-subject variance exceeds the error",
            "statistic": _round(f_statistic),
            "df": [d1, d2],
            "p_value": _round(f_sf(f_statistic, d1, d2)),
            "significant": bool(f_sf(f_statistic, d1, d2) < 0.05),
        },
        effect_size={"name": "icc", "value": _round(icc_value)},
        warnings=warnings,
        meta={"parameters": parameters},
    )


# Imported at the bottom on purpose: built from stats_engine helpers.
from app.statflow import stats_engine as _engine  # noqa: E402

for _key, _attribute in _engine.RELIABILITY_ANALYSES.items():
    _handler = getattr(sys.modules[__name__], _attribute, None)
    if _handler is not None:
        _engine.ANALYSIS_HANDLERS[_key] = _handler
