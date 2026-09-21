"""Chart building: turns a dataset into Plotly-ready chart data.

The response shape is deliberately generic so ``react-plotly.js`` (frontend) can
consume it directly:

    {
      "chart_type": "bar",
      "x_label": "region",
      "y_label": "sum(sales)",
      "series": [{"name": "sales", "x": [...], "y": [...], "type": "bar"}],
      "meta": {...}
    }
"""

from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.data_service import (
    infer_column_type,
    to_jsonable,
)

MAX_CATEGORIES = 50  # keep charts readable (design system: max 5-6 for pie, 50 for bar)

AGGREGATIONS = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
    "min": "min",
    "max": "max",
    "median": "median",
}

CHART_TYPES = {"bar", "line", "scatter", "histogram"}


def _require_column(df: pd.DataFrame, column: Optional[str], label: str) -> str:
    if not column:
        raise ValueError(f"Parameter '{label}' is required for this chart type")
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist in this dataset")
    return column


def _limit_categories(frame: pd.DataFrame, x_column: str, value_column: str) -> pd.DataFrame:
    """Keep at most MAX_CATEGORIES categories (top by value) so bars stay readable."""
    if frame.shape[0] <= MAX_CATEGORIES:
        return frame
    ordered = frame.copy()
    if infer_column_type(frame[x_column]) == "numeric":
        ordered = ordered.sort_values(x_column)
    else:
        ordered = ordered.sort_values(value_column, ascending=False)
    return ordered.head(MAX_CATEGORIES)


def _aggregate(
    df: pd.DataFrame, x_column: str, y_column: Optional[str], aggregate: str
) -> pd.DataFrame:
    aggregator = AGGREGATIONS.get(aggregate)
    if aggregator is None:
        raise ValueError("aggregate must be one of: " + ", ".join(sorted(AGGREGATIONS)))

    if y_column is None:
        # No y column: count the rows per category.
        result = (
            df.groupby(x_column, dropna=False)
            .size()
            .reset_index(name="count")
        )
        return result

    numeric = pd.to_numeric(df[y_column], errors="coerce")
    if numeric.notna().sum() == 0:
        raise ValueError(
            f"Column '{y_column}' is not numeric, choose another column for the Y axis"
        )
    working = pd.DataFrame({"__x__": df[x_column], "__y__": numeric}).dropna(
        subset=["__y__"]
    )
    grouped = (
        working.groupby("__x__", dropna=False)["__y__"]
        .agg(aggregator)
        .reset_index()
    )
    grouped.columns = [x_column, y_column]
    return grouped


def _finalise_axis(frame: pd.DataFrame, x_column: str, value_column: str) -> pd.DataFrame:
    """Sort the aggregated frame for a readable chart."""
    if frame.empty:
        return frame
    if infer_column_type(frame[x_column]) in {"numeric", "date"}:
        return frame.sort_values(x_column)
    return frame.sort_values(value_column, ascending=False)


def _bar_or_line(
    df: pd.DataFrame, chart_type: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    x_column = _require_column(df, config.get("x"), "x")
    y_column = config.get("y")
    if y_column:
        _require_column(df, y_column, "y")
    aggregate = config.get("aggregate") or ("count" if not y_column else "sum")
    group_by = config.get("group_by")

    series: List[Dict[str, Any]] = []
    highlight = "highlights" if chart_type == "bar" else "lines+markers"

    if group_by:
        _require_column(df, group_by, "group_by")
        categories: List[Any] = []
        per_group: Dict[str, Dict[Any, float]] = {}
        for group_value, group_frame in df.groupby(group_by, dropna=False):
            aggregated = _aggregate(group_frame, x_column, y_column, aggregate)
            aggregated = _finalise_axis(
                aggregated, x_column, y_column or "count"
            )
            for category in aggregated[x_column].tolist():
                if category not in categories:
                    categories.append(category)
            per_group[str(to_jsonable(group_value))] = {
                to_jsonable(category): to_jsonable(value)
                for category, value in zip(
                    aggregated[x_column], aggregated[y_column or "count"]
                )
            }
        categories = categories[:MAX_CATEGORIES]
        for name, values in per_group.items():
            series.append(
                {
                    "name": name,
                    "x": categories,
                    "y": [values.get(category, 0) or 0 for category in categories],
                    "type": chart_type,
                    "mode": highlight,
                }
            )
    else:
        aggregated = _aggregate(df, x_column, y_column, aggregate)
        aggregated = _finalise_axis(aggregated, x_column, y_column or "count")
        aggregated = _limit_categories(
            aggregated, x_column, y_column or "count"
        )
        if aggregated.empty:
            raise ValueError("No data available to draw this chart")
        series.append(
            {
                "name": y_column or "count",
                "x": [to_jsonable(value) for value in aggregated[x_column].tolist()],
                "y": [to_jsonable(value) for value in aggregated[y_column or "count"].tolist()],
                "type": chart_type,
                "mode": highlight,
            }
        )

    return {
        "chart_type": chart_type,
        "x_label": x_column,
        "y_label": f"{aggregate}({y_column})" if y_column else "count",
        "series": series,
        "meta": {
            "aggregate": aggregate,
            "group_by": group_by,
            "rows_used": int(df.shape[0]),
            "categories": len(series[0]["x"]) if series else 0,
        },
    }


def _scatter(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    x_column = _require_column(df, config.get("x"), "x")
    y_column = _require_column(df, config.get("y"), "y")
    group_by = config.get("group_by")
    limit = int(config.get("limit") or 5000)

    x_values = pd.to_numeric(df[x_column], errors="coerce").to_numpy()
    y_values = pd.to_numeric(df[y_column], errors="coerce").to_numpy()
    working = pd.DataFrame({"__x__": x_values, "__y__": y_values})
    if group_by:
        _require_column(df, group_by, "group_by")
        working["__g__"] = df[group_by].to_numpy()
    working = working.dropna(subset=["__x__", "__y__"])
    if working.empty:
        raise ValueError("No complete numeric rows to draw this scatter plot")

    truncated = working.shape[0] > limit
    if truncated:
        working = working.sample(n=limit, random_state=42)

    series: List[Dict[str, Any]] = []
    if group_by:
        for group_value, group_frame in working.groupby("__g__", dropna=False):
            series.append(
                {
                    "name": str(to_jsonable(group_value)),
                    "x": [to_jsonable(value) for value in group_frame["__x__"].tolist()],
                    "y": [to_jsonable(value) for value in group_frame["__y__"].tolist()],
                    "type": "scatter",
                    "mode": "markers",
                }
            )
    else:
        series.append(
            {
                "name": y_column,
                "x": [to_jsonable(value) for value in working["__x__"].tolist()],
                "y": [to_jsonable(value) for value in working["__y__"].tolist()],
                "type": "scatter",
                "mode": "markers",
            }
        )

    return {
        "chart_type": "scatter",
        "x_label": x_column,
        "y_label": y_column,
        "series": series,
        "meta": {
            "group_by": group_by,
            "points_returned": sum(len(item["x"]) for item in series),
            "truncated": truncated,
            "rows_used": int(df.shape[0]),
        },
    }


def _histogram(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    x_column = _require_column(df, config.get("x"), "x")
    group_by = config.get("group_by")
    bins = int(config.get("bins") or 20)
    limit = int(config.get("limit") or 20000)

    values = pd.to_numeric(df[x_column], errors="coerce").to_numpy()
    working = pd.DataFrame({"__x__": values})
    if group_by:
        _require_column(df, group_by, "group_by")
        working["__g__"] = df[group_by].to_numpy()
    working = working.dropna(subset=["__x__"])
    if working.empty:
        raise ValueError(
            f"Column '{x_column}' is not numeric, choose another column for the histogram"
        )

    truncated = working.shape[0] > limit
    if truncated:
        working = working.sample(n=limit, random_state=42)

    series: List[Dict[str, Any]] = []
    groups = (
        [(str(to_jsonable(name)), frame) for name, frame in working.groupby("__g__", dropna=False)]
        if group_by
        else [(x_column, working)]
    )
    for name, frame in groups:
        series.append(
            {
                "name": name,
                "x": [to_jsonable(value) for value in frame["__x__"].tolist()],
                "type": "histogram",
                "nbinsx": bins,
            }
        )

    return {
        "chart_type": "histogram",
        "x_label": x_column,
        "y_label": "frequency",
        "series": series,
        "meta": {
            "bins": bins,
            "group_by": group_by,
            "points_returned": sum(len(item["x"]) for item in series),
            "truncated": truncated,
            "rows_used": int(df.shape[0]),
        },
    }


CHART_BUILDERS = {
    "bar": lambda df, config: _bar_or_line(df, "bar", config),
    "line": lambda df, config: _bar_or_line(df, "line", config),
    "scatter": _scatter,
    "histogram": _histogram,
}


def build_chart_data(
    df: pd.DataFrame, chart_type: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate a chart request and build Plotly-ready data."""
    if chart_type not in CHART_TYPES:
        raise ValueError("chart_type must be one of: " + ", ".join(sorted(CHART_TYPES)))
    if df.shape[0] == 0:
        raise ValueError("Hakuna data ya kutosha kuchora chati hii")
    return CHART_BUILDERS[chart_type](df, config or {})


def describe_chart(chart_type: str, config: Dict[str, Any]) -> str:
    """Human readable one-liner used in exports and chart lists."""
    target = config.get("y") or config.get("x")
    group = config.get("group_by")
    description = f"{chart_type.title()} chart of {target}"
    if chart_type in {"bar", "line"} and config.get("y"):
        description = (
            f"{chart_type.title()} chart: {config.get('aggregate', 'sum')}"
            f"({config['y']}) by {config.get('x')}"
        )
    if chart_type == "scatter":
        description = f"Scatter plot: {config.get('y')} vs {config.get('x')}"
    if chart_type == "histogram":
        description = f"Histogram of {config.get('x')}"
    if group:
        description += f" grouped by {group}"
    return description

