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

# Visualization Studio: per-box sample cap mirrors the scatter cap below — a
# box of 100k points is the same pixels as a box of 2k, just 50x the JSON.
MAX_BOX_POINTS = 2000
# Facet panels: one subplot per value, so an unbounded category becomes an
# unbounded figure. The frontend renders up to this many panels; the service
# refuses past it rather than returning a chart nobody can read.
MAX_FACETS = 12

AGGREGATIONS = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
    "min": "min",
    "max": "max",
    "median": "median",
}

CHART_TYPES = {"bar", "line", "scatter", "histogram", "box", "pie", "heatmap"}


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
    color_by = config.get("color_by")
    size_by = config.get("size_by")
    limit = int(config.get("limit") or 5000)

    if group_by and color_by:
        raise ValueError("Use either 'group_by' or 'color_by', not both")
    if group_by:
        _require_column(df, group_by, "group_by")
    if color_by and color_by not in df.columns:
        raise ValueError(f"Column '{color_by}' does not exist in this dataset")

    x_values = pd.to_numeric(df[x_column], errors="coerce").to_numpy()
    y_values = pd.to_numeric(df[y_column], errors="coerce").to_numpy()
    working = pd.DataFrame({"__x__": x_values, "__y__": y_values})
    splitter = group_by or color_by
    if splitter:
        working["__g__"] = df[splitter].to_numpy()
    sizes: Optional[pd.Series] = None
    if size_by:
        _require_column(df, size_by, "size_by")
        sizes = pd.to_numeric(df[size_by], errors="coerce")
        if sizes.notna().sum() == 0:
            raise ValueError(
                f"Column '{size_by}' is not numeric, choose another column for the size channel"
            )
        working["__s__"] = sizes.reset_index(drop=True)
    working = working.dropna(subset=["__x__", "__y__"])
    if working.empty:
        raise ValueError("No complete numeric rows to draw this scatter plot")

    truncated = working.shape[0] > limit
    if truncated:
        working = working.sample(n=limit, random_state=42)

    series: List[Dict[str, Any]] = []
    if splitter:
        groups = list(working.groupby("__g__", dropna=False))
        if len(groups) > MAX_CATEGORIES:
            raise ValueError(
                f"Column '{splitter}' has too many distinct values to split by "
                f"(max {MAX_CATEGORIES})"
            )
        for group_value, group_frame in groups:
            entry: Dict[str, Any] = {
                "name": str(to_jsonable(group_value)),
                "x": [to_jsonable(value) for value in group_frame["__x__"].tolist()],
                "y": [to_jsonable(value) for value in group_frame["__y__"].tolist()],
                "type": "scatter",
                "mode": "markers",
            }
            if "__s__" in group_frame.columns:
                entry["sizes"] = [
                    to_jsonable(value) for value in group_frame["__s__"].tolist()
                ]
            series.append(entry)
    else:
        entry = {
            "name": y_column,
            "x": [to_jsonable(value) for value in working["__x__"].tolist()],
            "y": [to_jsonable(value) for value in working["__y__"].tolist()],
            "type": "scatter",
            "mode": "markers",
        }
        if "__s__" in working.columns:
            entry["sizes"] = [
                to_jsonable(value) for value in working["__s__"].tolist()
            ]
        series.append(entry)

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


def _box(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """Distribution (box) plot: one box per category of ``x`` over numeric ``y``.

    Without ``y`` this is a single box of the numeric ``x`` column itself.
    """
    x_column = _require_column(df, config.get("x"), "x")
    y_column = config.get("y")
    if y_column:
        _require_column(df, y_column, "y")
        values = pd.to_numeric(df[y_column], errors="coerce")
        if values.notna().sum() == 0:
            raise ValueError(
                f"Column '{y_column}' is not numeric, choose another column for the Y axis"
            )
        labels = df[x_column].astype("object")
        frame = pd.DataFrame({"__label__": labels, "__value__": values}).dropna(
            subset=["__value__"]
        )
        groups = list(frame.groupby("__label__", dropna=False))
        if len(groups) > MAX_CATEGORIES:
            raise ValueError(
                f"Column '{x_column}' has too many distinct values to split by "
                f"(max {MAX_CATEGORIES})"
            )
        boxes = [(str(to_jsonable(name)), group) for name, group in groups]
    else:
        values = pd.to_numeric(df[x_column], errors="coerce").dropna()
        if values.empty:
            raise ValueError(
                f"Column '{x_column}' is not numeric, choose a numeric column"
            )
        boxes = [(x_column, pd.DataFrame({"__value__": values}))]

    series = []
    for name, group in boxes:
        points = group["__value__"].tolist()
        truncated = len(points) > MAX_BOX_POINTS
        if truncated:
            points = (
                pd.Series(points).sample(n=MAX_BOX_POINTS, random_state=42).tolist()
            )
        series.append(
            {
                "name": name,
                "y": [to_jsonable(value) for value in points],
                "type": "box",
                "truncated": truncated,
            }
        )

    return {
        "chart_type": "box",
        "x_label": x_column,
        "y_label": y_column or x_column,
        "series": series,
        "meta": {
            "boxes": len(series),
            "rows_used": int(df.shape[0]),
        },
    }


def _pie(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """Part-to-whole: share of ``aggregate(y)`` (or row counts) per ``x`` value."""
    x_column = _require_column(df, config.get("x"), "x")
    y_column = config.get("y")
    aggregate = config.get("aggregate") or ("count" if not y_column else "sum")
    if aggregate not in AGGREGATIONS:
        raise ValueError(
            "aggregate must be one of: " + ", ".join(sorted(AGGREGATIONS))
        )
    aggregated = _aggregate(df, x_column, y_column, aggregate)
    aggregated = _limit_categories(aggregated, x_column, y_column or "count")
    if aggregated.empty:
        raise ValueError("No data available to draw this chart")
    value_column = y_column or "count"
    total = float(pd.to_numeric(aggregated[value_column], errors="coerce").fillna(0).sum())
    shares = (
        pd.to_numeric(aggregated[value_column], errors="coerce").fillna(0) / total
        if total
        else pd.Series([0.0] * len(aggregated))
    )
    return {
        "chart_type": "pie",
        "x_label": x_column,
        "y_label": f"{aggregate}({y_column})" if y_column else "count",
        "series": [
            {
                "name": "share",
                "labels": [to_jsonable(value) for value in aggregated[x_column].tolist()],
                "values": [to_jsonable(value) for value in aggregated[value_column].tolist()],
                "shares": [to_jsonable(value) for value in shares.tolist()],
                "type": "pie",
            }
        ],
        "meta": {
            "aggregate": aggregate,
            "slices": int(aggregated.shape[0]),
            "rows_used": int(df.shape[0]),
        },
    }


def _heatmap(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """Two-variable matrix: ``aggregate(y)`` for each (x, group) cell.

    ``x`` runs along the horizontal axis, ``group_by`` (or ``color_by``) down
    the vertical axis. Without ``y`` cells hold row counts.
    """
    x_column = _require_column(df, config.get("x"), "x")
    row_column = config.get("group_by") or config.get("color_by")
    if not row_column:
        raise ValueError("A heatmap needs a second categorical column ('group_by')")
    _require_column(df, row_column, "group_by")
    if row_column == x_column:
        raise ValueError("The two heatmap axes must be different columns")
    y_column = config.get("y")
    aggregate = config.get("aggregate") or ("count" if not y_column else "sum")
    if aggregate not in AGGREGATIONS:
        raise ValueError(
            "aggregate must be one of: " + ", ".join(sorted(AGGREGATIONS))
        )
    columns = list(dict.fromkeys([str(to_jsonable(value)) for value in df[x_column].tolist()]))
    rows = list(dict.fromkeys([str(to_jsonable(value)) for value in df[row_column].tolist()]))
    if len(columns) > MAX_CATEGORIES or len(rows) > MAX_CATEGORIES:
        raise ValueError(
            f"A heatmap axis holds at most {MAX_CATEGORIES} values — "
            "aggregate the data first"
        )
    columns.sort()
    rows.sort()
    matrix: List[List[Any]] = []
    for row in rows:
        cells: List[Any] = []
        for column in columns:
            cell = df[
                (df[x_column].astype(str) == column)
                & (df[row_column].astype(str) == row)
            ]
            if y_column:
                numeric = pd.to_numeric(cell[y_column], errors="coerce").dropna()
                if aggregate == "count":
                    value: Any = int(cell.shape[0])
                elif numeric.empty:
                    value = None
                else:
                    value = float(getattr(numeric, AGGREGATIONS[aggregate])())
            else:
                value = int(cell.shape[0])
            cells.append(to_jsonable(value))
        matrix.append(cells)
    return {
        "chart_type": "heatmap",
        "x_label": x_column,
        "y_label": row_column,
        "series": [
            {
                "name": f"{aggregate}({y_column})" if y_column else "count",
                "x": columns,
                "y": rows,
                "z": matrix,
                "type": "heatmap",
            }
        ],
        "meta": {
            "aggregate": aggregate,
            "rows_used": int(df.shape[0]),
        },
    }


def _apply_chart_filter(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    """Narrow a frame for drawing only — no version is written.

    The filter shape mirrors ``op_filter`` (same operators, ``and``/``or``
    logic) and reuses its mask builder so a chart filter behaves exactly like
    the same filter saved as a step; only where it lives is different.
    """
    filters = config.get("filters")
    if not filters:
        return df
    conditions = filters.get("conditions") if isinstance(filters, dict) else None
    if not conditions:
        raise ValueError("A chart filter needs at least one condition")
    from app.statflow.operations import filter_mask

    mask = filter_mask(df, conditions, filters.get("logic", "and"))
    return df.loc[mask].reset_index(drop=True)


def _resolve_annotations(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate the text notes pinned to data positions.

    Coordinates are data values, so annotations survive re-renders and exports;
    the renderer only has to place them.
    """
    annotations = config.get("annotations") or []
    if not isinstance(annotations, list):
        raise ValueError("'annotations' must be a list")
    resolved: List[Dict[str, Any]] = []
    for index, item in enumerate(annotations):
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            raise ValueError(f"Annotation {index + 1} needs a text")
        if item.get("x") is None:
            raise ValueError(f"Annotation {index + 1} needs an x position")
        resolved.append(
            {
                "text": str(item["text"]).strip()[:280],
                "x": to_jsonable(item.get("x")),
                "y": to_jsonable(item.get("y")),
                "series": item.get("series"),
            }
        )
    return resolved


def _split_facets(
    df: pd.DataFrame, config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Partition the frame into one panel per ``facet_by`` value.

    Each panel carries the facet label the frontend lays out in a grid. Values
    are capped at ``MAX_FACETS``: a facet per distinct id column is a figure
    nobody can read, and the service should refuse before shipping megabytes
    of panels.
    """
    facet_by = config.get("facet_by")
    if not facet_by:
        return [{"facet": None, "frame": df}]
    _require_column(df, facet_by, "facet_by")
    values = list(dict.fromkeys(str(to_jsonable(value)) for value in df[facet_by].tolist()))
    if len(values) > MAX_FACETS:
        raise ValueError(
            f"Column '{facet_by}' has too many distinct values to facet by "
            f"(max {MAX_FACETS})"
        )
    return [
        {
            "facet": value,
            "frame": df[df[facet_by].astype(str) == value].reset_index(drop=True),
        }
        for value in values
    ]


CHART_BUILDERS = {
    "bar": lambda df, config: _bar_or_line(df, "bar", config),
    "line": lambda df, config: _bar_or_line(df, "line", config),
    "scatter": _scatter,
    "histogram": _histogram,
    "box": _box,
    "pie": _pie,
    "heatmap": _heatmap,
}


def build_chart_data(
    df: pd.DataFrame, chart_type: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate a chart request and build Plotly-ready data.

    Configs without the studio extensions take exactly the same path as before:
    no filter, no facets, no annotations, one panel. Old saved charts therefore
    re-render byte-identically through this function.
    """
    if chart_type not in CHART_TYPES:
        raise ValueError("chart_type must be one of: " + ", ".join(sorted(CHART_TYPES)))
    if df.shape[0] == 0:
        raise ValueError("Hakuna data ya kutosha kuchora chati hii")
    config = dict(config or {})
    filtered = _apply_chart_filter(df, config)
    if filtered.empty:
        raise ValueError("The chart filter removed every row — loosen the filter")
    panels = _split_facets(filtered, config)
    facets = [
        {
            "facet": panel["facet"],
            "chart": CHART_BUILDERS[chart_type](panel["frame"], config),
        }
        for panel in panels
    ]
    annotations = _resolve_annotations(config)
    first = facets[0]["chart"]
    first = dict(first)
    if len(facets) > 1:
        first["facets"] = facets
    meta = dict(first.get("meta") or {})
    meta["rows_used"] = int(df.shape[0])
    meta["rows_after_filter"] = int(filtered.shape[0])
    meta["facets"] = len(facets)
    if annotations:
        first["annotations"] = annotations
    first["meta"] = meta
    return first


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
    if chart_type == "box":
        description = f"Box plot of {config.get('y') or config.get('x')} by {config.get('x')}"
    if chart_type == "pie":
        description = f"Pie chart of {config.get('x')}"
    if chart_type == "heatmap":
        description = (
            f"Heatmap of {config.get('x')} by "
            f"{config.get('group_by') or config.get('color_by')}"
        )
    if group:
        description += f" grouped by {group}"
    if config.get("facet_by"):
        description += f" faceted by {config.get('facet_by')}"
    if config.get("filters", {}).get("conditions"):
        description += " (filtered)"
    return description

