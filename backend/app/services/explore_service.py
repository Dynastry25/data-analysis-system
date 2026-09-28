"""Exploratory summaries for the Explore stage of the journey.

This is the engine computing, not the assistant. Distributions, quantiles and
correlations all come out of pandas with a known formula, so a user can
recompute any number here from the same file.

Correlations are reported with both Pearson and Spearman and a plain-language
reading of the strength. Pearson answers "linear?", Spearman answers "monotonic?",
and the pair is only labelled a relationship when they agree; when they
disagree the data is curved or has outliers, and saying only "strong
correlation" would hide that. Nothing here implies causation.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MAX_HISTOGRAM_BINS = 20
MAX_TOP_VALUES = 8
QUANTILE_POINTS = (0.25, 0.5, 0.75)

# |r| at or above this counts as a strong relationship.
STRONG_AT = 0.7
MODERATE_AT = 0.4

# A column needs at least this many complete pairs before its correlation means
# anything. Below it we say nothing rather than print a number.
MIN_CORRELATION_PAIRS = 30


def classify_column(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "text"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        # A numeric column with only a handful of distinct values is a label
        # that arrived as a number, and means something different.
        if non_null.nunique() <= max(2, int(len(non_null) * 0.05)):
            return "categorical"
        return "numeric"
    if non_null.nunique() <= max(10, int(len(non_null) * 0.5)):
        return "categorical"
    return "text"


def _histogram(series: pd.Series) -> List[Dict[str, Any]]:
    clean = series.dropna()
    if clean.empty:
        return []
    try:
        counts, edges = np.histogram(clean.to_numpy(), bins=MAX_HISTOGRAM_BINS)
    except (ValueError, TypeError):
        return []
    return [
        {
            "start": float(edges[index]),
            "end": float(edges[index + 1]),
            "count": int(counts[index]),
        }
        for index in range(len(counts))
    ]


def _top_values(series: pd.Series) -> List[Dict[str, Any]]:
    clean = series.dropna()
    if clean.empty:
        return []
    counts = clean.value_counts().head(MAX_TOP_VALUES)
    return [
        {"value": _jsonable(value), "count": int(count)}
        for value, count in counts.items()
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value


def describe_column(series: pd.Series) -> Dict[str, Any]:
    kind = classify_column(series)
    row_count = int(len(series))
    missing = int(series.isna().sum())
    clean = series.dropna()

    entry: Dict[str, Any] = {
        "name": str(series.name),
        "data_type": str(series.dtype),
        "kind": kind,
        "missing_count": missing,
        "missing_ratio": round(missing / row_count, 4) if row_count else 0.0,
        "unique_count": int(clean.nunique()) if not clean.empty else None,
    }

    if kind == "numeric" and not clean.empty:
        numeric = pd.to_numeric(clean, errors="coerce").dropna()
        if not numeric.empty:
            entry["min"] = _jsonable(numeric.min())
            entry["max"] = _jsonable(numeric.max())
            entry["mean"] = _jsonable(round(float(numeric.mean()), 4))
            entry["median"] = _jsonable(round(float(numeric.median()), 4))
            entry["std"] = _jsonable(round(float(numeric.std()), 4))
            entry["quantiles"] = {
                f"p{int(point * 100)}": _jsonable(round(float(numeric.quantile(point)), 4))
                for point in QUANTILE_POINTS
            }
            entry["histogram"] = _histogram(numeric)
    elif kind == "categorical" and not clean.empty:
        entry["top_values"] = _top_values(clean)
    elif kind == "boolean" and not clean.empty:
        entry["top_values"] = _top_values(clean)

    return entry


def _strength(coefficient: float) -> str:
    magnitude = abs(coefficient)
    if magnitude >= STRONG_AT:
        return "strong"
    if magnitude >= MODERATE_AT:
        return "moderate"
    return "weak"


def _describe_pair(
    method: str, coefficient: float, column_kinds: Dict[str, str], x: str, y: str
) -> str:
    magnitude = abs(coefficient)
    direction = "kuongezeka" if coefficient > 0 else "kupungua"
    if method == "pearson":
        shape = "linear"
    else:
        shape = "monotonic"

    if magnitude < 0.1:
        return f"Hakuna uhusiano {shape} unaoonekana kati ya '{x}' na '{y}'."

    caveat = ""
    if column_kinds.get(x) == "numeric" and column_kinds.get(y) == "categorical":
        caveat = (
            f" '{x}' ni nambari na '{y}' ni kategoria, kwa hiyo husika na makundi "
            "bado, si mnyororo ulio moja kwa moja."
        )
    elif column_kinds.get(x) == "categorical" or column_kinds.get(y) == "categorical":
        caveat = " Moja kati ya hizi mbili ni kategoria, kwa hiyo maana ya r ni ya makundi."

    return (
        f"Uhusiano {shape} {direction}: kama '{x}' {direction}, '{y}' pia huwa "
        f"{direction} (r = {coefficient:.2f}). Huu ni uhusiano, si ushahidi wa kisababu.{caveat}"
    )


def _rank_correlation(left: pd.Series, right: pd.Series) -> float:
    """Spearman's rho: Pearson on the ranks, with ties given their average.

    Written out rather than calling `Series.corr(method="spearman")`, which
    routes through scipy. This keeps scipy out of the dependency list for one
    well-known formula, and the result is the same number scipy returns.
    """
    return float(left.rank().corr(right.rank(), method="pearson"))


def find_correlations(
    frame: pd.DataFrame, kinds: Dict[str, str], limit: int = 12
) -> List[Dict[str, Any]]:
    """Numeric pairs, strongest first, reported with Pearson and Spearman."""
    numeric_columns = [
        name for name in frame.columns if kinds.get(str(name)) == "numeric"
    ]
    if len(numeric_columns) < 2:
        return []

    pairs: List[Tuple[float, Dict[str, Any]]] = []
    for first in range(len(numeric_columns)):
        for second in range(first + 1, len(numeric_columns)):
            left, right = numeric_columns[first], numeric_columns[second]
            frame_pair = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(frame_pair) < MIN_CORRELATION_PAIRS:
                continue
            if frame_pair[left].nunique() < 2 or frame_pair[right].nunique() < 2:
                continue
            try:
                pearson = float(frame_pair[left].corr(frame_pair[right], method="pearson"))
                spearman = _rank_correlation(frame_pair[left], frame_pair[right])
            except (ValueError, FloatingPointError):
                continue
            if np.isnan(pearson) or np.isnan(spearman):
                continue

            pair_kind = kinds.get(str(left)) == "numeric" and kinds.get(str(right)) == "numeric"
            # The two agree when the relationship really is a straight line. When
            # they differ the shape is curved or the data has outliers, and
            # quoting only Pearson would hide it.
            agrees = abs(abs(pearson) - abs(spearman)) <= 0.1
            coefficient = pearson if agrees else spearman
            method = "pearson" if agrees else "spearman"

            pairs.append(
                (
                    abs(coefficient),
                    {
                        "x": str(left),
                        "y": str(right),
                        "method": method,
                        "coefficient": round(coefficient, 4),
                        "strength": _strength(coefficient),
                        "interpretation": _describe_pair(
                            method, coefficient, kinds, str(left), str(right)
                        )
                        + ("" if agrees else " Pearson na Spearman hawakubaliana, "
                           "kwa hiyo tumika Spearman."),
                    },
                )
            )

    pairs.sort(key=lambda item: item[0], reverse=True)
    return [payload for _score, payload in pairs[:limit]]


def _column_warnings(frame: pd.DataFrame, kinds: Dict[str, str]) -> List[str]:
    warnings: List[str] = []
    row_count = int(frame.shape[0])

    for name in frame.columns:
        missing = int(frame[name].isna().sum())
        if row_count and missing / row_count >= 0.5:
            warnings.append(
                f"'{name}' ina {missing / row_count:.0%} ya rows zikiwa hazina thamani. "
                "Kabla ya kuhesabu, zipige au uzishe na thamani nyingine."
            )

    if not any(kinds.get(str(name)) == "numeric" for name in frame.columns):
        warnings.append(
            "Hakuna column ya nambari iliyoonekana. Uchambuzi wa takwimu "
            "(mean, correlation, regression) hutaweza kufanya kazi mpaka "
            "column zibadilishwe kuwa numeric."
        )

    constant = [
        str(name)
        for name in frame.columns
        if frame[name].dropna().nunique() == 1 and row_count
    ]
    if constant:
        warnings.append(
            "Column zifuata zina thamani moja tu: "
            + ", ".join(constant)
            + ". Hazitatoa matokeo yoyote kwenye uchambuzi."
        )

    return warnings


def explore_frame(frame: pd.DataFrame) -> Dict[str, Any]:
    row_count, column_count = int(frame.shape[0]), int(frame.shape[1])
    kinds: Dict[str, str] = {}
    columns: List[Dict[str, Any]] = []
    for name in frame.columns:
        entry = describe_column(frame[name])
        kinds[str(name)] = entry["kind"]
        columns.append(entry)

    # Guard the correlation matrix itself. Pairwise complete observations can
    # drop it below the threshold even when the whole frame is large, and a
    # correlation from 12 rows is noise dressed as a finding.
    worst_missing = max(
        (column["missing_ratio"] for column in columns), default=0.0
    )
    usable_rows = int(len(frame) * (1.0 - min(worst_missing, 1.0)))

    return {
        "row_count": row_count,
        "column_count": column_count,
        "columns": columns,
        "correlations": (
            find_correlations(frame, kinds)
            if usable_rows >= MIN_CORRELATION_PAIRS
            else []
        ),
        "warnings": _column_warnings(frame, kinds),
    }
