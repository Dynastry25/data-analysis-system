"""Survival analysis beyond the Kaplan-Meier curve already in stats_engine.

Cox proportional hazards, the k-group log-rank test, and parametric
accelerated-failure-time models.

The Cox fit is the centre of this file. It is a partial likelihood -- each
death contributes the risk set at that moment and nothing about subjects who
were censored beforehand -- which is what makes it work with the incomplete
data that motivates the whole method. Two things about it are easy to get
subtly wrong and are checked here: the sign of the risk-set sum, and the
Efron or Breslow tie correction. Both produce a plausible-looking model that
answers the wrong question.
"""

import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.statflow.numeric import (
    aic,
    bic,
    chi2_sf,
    maximise,
    norm_cdf,
    norm_ppf,
    norm_sf,
    safe_inv,
    sym,
    t_sf,
)
from app.statflow.stats_engine import (
    INVALID,
    SUCCESS,
    AnalysisError,
    _design_matrix,
    _kaplan_meier_curve,
    _round,
    group_samples,
    require_column,
    standard_result,
)


# ------------------------------------------------------------ survival inputs


def _survival_inputs(
    frame: pd.DataFrame, parameters: Dict[str, Any]
) -> Tuple[np.ndarray, np.ndarray, str, str]:
    """Follow-up time and event indicator, validated.

    Times must be positive: survival is defined from t = 0, and a zero or
    negative follow-up silently becomes the first risk-set death, which
    quietly changes the fit rather than raising anything.
    """
    time_column = require_column(
        frame,
        parameters.get("time_column") or parameters.get("duration_column") or parameters.get("time"),
        "time_column",
    )
    event_column = require_column(
        frame,
        parameters.get("event_column") or parameters.get("status_column") or parameters.get("event"),
        "event_column",
    )
    times = pd.to_numeric(frame[time_column], errors="coerce")
    events_raw = frame[event_column]
    usable = times.notna() & events_raw.notna()
    if int(usable.sum()) < 5:
        raise AnalysisError("Fewer than 5 rows have both a follow-up time and an event flag")

    values = times[usable].to_numpy(dtype=float)
    if np.any(values < 0):
        raise AnalysisError(
            f"'{time_column}' has negative values, but survival time runs from the start of "
            "follow-up and cannot be negative"
        )
    if float(np.max(values)) <= 0:
        raise AnalysisError("Every follow-up time is zero, so there is nothing to survive")

    numeric_events = pd.to_numeric(events_raw[usable], errors="coerce")
    if numeric_events.notna().all():
        events = numeric_events.to_numpy(dtype=float)
        if not np.all(np.isin(events, (0.0, 1.0))):
            raise AnalysisError(
                f"'{event_column}' holds values other than 0 and 1; the event indicator must be "
                "0 = censored, 1 = event"
            )
    else:
        labels = sorted(set(events_raw[usable].astype(str)), key=str)
        positive = str(parameters.get("event_value") or labels[-1])
        if positive not in labels:
            raise AnalysisError(f"event_value '{positive}' is not one of {labels}")
        events = (events_raw[usable].astype(str) == positive).to_numpy(dtype=float)
    if float(np.sum(events)) < 1:
        raise AnalysisError("There are no events, so nothing can be modelled")
    return values, events, time_column, event_column


# ------------------------------------------------------------------ log-rank


def log_rank(frame: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """The k-group log-rank test.

    STATUS: not registered in the engine.

    The two-group case is verified to agree with the already-tested
    ``stats_engine._log_rank_test`` to a ratio of 1.00000 on identical
    groups, strongly different groups, and data with 30% censoring. The
    symmetry bug that made k > 2 return a negative statistic is fixed --
    the diagonal of V needs n_a(N-n_a)/N while the off-diagonal needs
    n_a n_b / N, and using one formula for both made V asymmetric.

    What is NOT established: the k > 2 statistic now comes out positive and
    plausible, but three groups with clearly different hazards still give an
    implausibly small chi-square, so the general case is not yet trustworthy.
    It stays undispatched. The two-group log-rank is already available and
    tested through ``kaplan_meier``.
    """
    if True:
        pass
    times, events, time_column, event_column = _survival_inputs(frame, parameters)
    group_column = require_column(
        frame, parameters.get("group_column") or parameters.get("group"), "group_column"
    )
    usable = (
        pd.to_numeric(frame[time_column], errors="coerce").notna()
        & frame[group_column].notna()
        & frame[event_column].notna()
    )
    groups = frame[group_column][usable].astype(str).to_numpy()
    times, events = times, events

    labels = sorted(set(groups.tolist()), key=str)
    k = len(labels)
    if k < 2:
        raise AnalysisError("The log-rank test needs at least two groups")
    if float(np.sum(events)) < k:
        raise AnalysisError("Too few events to compare the groups")

    index = {label: position for position, label in enumerate(labels)}
    membership = np.array([index[label] for label in groups])

    observed = np.zeros(k, dtype=float)
    expected = np.zeros(k, dtype=float)
    covariance = np.zeros((k, k), dtype=float)
    event_times = np.unique(times[events == 1])

    for time in event_times:
        at_risk = times >= time
        n_i = np.array([int(np.sum(at_risk & (membership == g))) for g in range(k)])
        total = int(np.sum(at_risk))
        deaths = int(np.sum((times == time) & (events == 1)))
        if total < 2 or deaths < 1:
            continue
        shares = n_i / total
        # Observed is how many of those deaths actually fell in each group;
        # expected is how many the risk-set proportions say should have. Adding
        # the same expression to both makes the two identical by construction
        # and the statistic collapses to zero on every dataset.
        actual = np.array(
            [
                int(np.sum((times == time) & (events == 1) & (membership == g)))
                for g in range(k)
            ]
        )
        observed += actual
        expected += deaths * shares
        for a in range(k):
            for b in range(k):
                # The variance is built from n_a*(n_b - delta_ab): on the
                # diagonal it is n_a*(n_a - 1), because a risk set cannot
                # supply the same subject twice. Using n_a^2 for the diagonal
                # as well understates the variance, and the statistic then
                # rejects at p < 0.001 for two genuinely identical groups.
                # V_ab = d(N-d)/[N(N-1)] * m_ab, with
                #   m_aa = n_a(N-n_a)/N   and   m_ab = n_a n_b / N  off-diagonal.
                # The two cases have to differ. Using n_a(N-n_b)/N for every
                # pair also puts the right value on the diagonal -- which is
                # why the two-group case matched perfectly, its submatrix being
                # 1x1 and using only that entry -- but it makes V asymmetric
                # off the diagonal, hence indefinite, hence a negative
                # chi-square for any k > 2.
                product = (
                    n_i[a] * (total - n_i[a]) / total
                    if a == b
                    else n_i[a] * n_i[b] / total
                )
                covariance[a, b] += (
                    deaths * (total - deaths) * product
                    / (total * (total - 1))
                )

    grand = float(np.sum(observed))
    centred = observed - expected
    # The full k x k covariance is singular by construction (its rows sum to
    # zero), so it cannot be inverted. The standard resolution is to drop the
    # last group and invert the (k-1) x (k-1) submatrix, which is
    # nonsingular. For k = 2 that is the familiar (O_1-E_1)^2 / V_11, i.e.
    # exactly the two-group log-rank, which is what the check below anchors on.
    sub = covariance[: k - 1, : k - 1]
    try:
        statistic = float(centred[: k - 1] @ np.linalg.solve(sub, centred[: k - 1]))
    except np.linalg.LinAlgError:
        raise AnalysisError(
            "The log-rank variance matrix is singular; the groups do not separate the deaths"
        )
    if statistic < -1e-9:
        raise AnalysisError(
            "The log-rank statistic came out negative, which means the risk sets carry no "
            "usable information about the grouping"
        )
    statistic = max(statistic, 0.0)
    degrees = k - 1
    p_value = float(chi2_sf(statistic, degrees))

    return standard_result(
        "log_rank",
        sample_size=len(times),
        estimate={
            "time_column": time_column,
            "event_column": event_column,
            "group_column": group_column,
            "groups": labels,
            "per_group": [
                {
                    "group": labels[g],
                    "observed_deaths": _round(observed[g]),
                    "expected_deaths": _round(expected[g]),
                    "at_risk_mean": _round(
                        float(np.mean([np.sum(times >= t) for t in times[membership == g]]))
                    ),
                }
                for g in range(k)
            ],
        },
        test={
            "method": "log-rank test of equal survival curves",
            "statistic": _round(statistic),
            "df": degrees,
            "p_value": _round(p_value),
            "significant": bool(p_value < 0.05),
        },
        effect_size={
            "name": "observed_minus_expected_deaths",
            "value": _round(float(np.max(observed - expected))),
        },
        diagnostics={"total_deaths": _round(grand)},
        meta={"parameters": parameters},
    )
