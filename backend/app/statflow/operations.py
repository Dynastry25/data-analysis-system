"""MVP-18: Cleaning & Transformation engine.

Every operation is a pure function ``(frame, configuration) -> (frame, summary,
warnings)`` so it can be applied to any dataset version and replayed from the
stored configuration (reproducibility). Nothing here writes files: the router
hands the result to ``version_store.create_version``.
"""

import ast
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.data_service import FALSY_STRINGS, TRUTHY_STRINGS, to_jsonable

CLEAN = "clean"
TRANSFORM = "transform"

FILTER_OPERATORS = {
    "eq": "equals (==)",
    "ne": "not equal (!=)",
    "gt": "greater than (>)",
    "gte": "greater or equal (>=)",
    "lt": "less than (<)",
    "lte": "less or equal (<=)",
    "between": "between two values (inclusive)",
    "in": "in list",
    "not_in": "not in list",
    "contains": "text contains",
    "startswith": "text starts with",
    "endswith": "text ends with",
    "is_null": "is missing",
    "not_null": "is not missing",
}

AGGREGATIONS = ("count", "sum", "mean", "median", "min", "max", "std", "nunique")
FILL_STRATEGIES = ("drop", "mean", "median", "mode", "zero", "constant")
CAST_TYPES = ("numeric", "integer", "text", "date", "boolean")

OperationResult = Tuple[pd.DataFrame, Dict[str, Any], List[str]]


class OperationError(ValueError):
    """Invalid operation request (mapped to HTTP 400)."""


# ------------------------------------------------------------------- helpers


def _require_column(frame: pd.DataFrame, column: Optional[str], label: str = "column") -> str:
    if not column:
        raise OperationError(f"Parameter '{label}' is required for this operation")
    if column not in frame.columns:
        raise OperationError(
            f"Column '{column}' does not exist. Available: {', '.join(map(str, frame.columns))}"
        )
    return str(column)


def _require_columns(
    frame: pd.DataFrame, columns: Optional[List[str]], label: str = "columns"
) -> List[str]:
    if not columns:
        raise OperationError(f"Parameter '{label}' is required for this operation")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise OperationError(f"Columns not found: {', '.join(missing)}")
    return [str(column) for column in columns]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _numeric_view(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _is_numeric(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return True
    converted = _numeric_view(series.dropna())
    return bool(len(converted) > 0 and converted.notna().all())


def _safe_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _column_profile(frame: pd.DataFrame) -> Dict[str, Any]:
    return {
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "columns": [str(column) for column in frame.columns],
        "missing_cells": int(frame.isna().sum().sum()),
    }


def _diff_profile(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rows_before": before["row_count"],
        "rows_after": after["row_count"],
        "rows_removed": before["row_count"] - after["row_count"],
        "columns_before": before["column_count"],
        "columns_after": after["column_count"],
        "missing_cells_before": before["missing_cells"],
        "missing_cells_after": after["missing_cells"],
    }


def op_drop_duplicates(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    subset = config.get("subset")
    subset = _require_columns(frame, subset) if subset else None
    keep = config.get("keep") or "first"
    if keep not in {"first", "last"}:
        raise OperationError("'keep' must be 'first' or 'last'")

    before = _column_profile(frame)
    cleaned = frame.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)
    after = _column_profile(cleaned)
    summary = {
        **_diff_profile(before, after),
        "duplicate_rows_removed": before["row_count"] - after["row_count"],
        "subset": subset or "all columns",
    }
    return cleaned, summary, []


def op_drop_missing(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    columns = config.get("columns") or config.get("column")
    columns = _require_columns(frame, _as_list(columns)) if columns else None
    threshold = config.get("threshold")
    if threshold is None and columns is None:
        threshold = 1

    before = _column_profile(frame)
    if threshold is not None:
        missing_counts = frame.isna().sum(axis=1)
        cleaned = frame.loc[missing_counts < int(threshold)].reset_index(drop=True)
        rule = f"rows with fewer than {int(threshold)} missing values kept"
    else:
        cleaned = frame.dropna(subset=columns).reset_index(drop=True)
        rule = f"rows complete on {', '.join(columns or [])}"

    after = _column_profile(cleaned)
    summary = {**_diff_profile(before, after), "rule": rule}
    return cleaned, summary, []


def op_fill_missing(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    strategy = str(config.get("strategy") or config.get("method") or "").lower()
    if strategy not in FILL_STRATEGIES:
        raise OperationError("strategy must be one of: " + ", ".join(FILL_STRATEGIES))

    targets = config.get("columns") or config.get("column")
    columns = (
        _require_columns(frame, _as_list(targets)) if targets else list(frame.columns)
    )
    if strategy == "drop":
        return op_drop_missing(frame, {"columns": columns})

    constant = config.get("value")
    if strategy == "constant" and constant is None:
        raise OperationError("'value' is required when strategy is 'constant'")

    before = _column_profile(frame)
    cleaned = frame.copy()
    filled: Dict[str, Any] = {}
    warnings: List[str] = []

    for column in columns:
        series = cleaned[column]
        missing_before = int(series.isna().sum())
        if missing_before == 0:
            continue

        if strategy in {"mean", "median"}:
            if not _is_numeric(series):
                warnings.append(
                    f"'{column}' is not numeric, skipped (use mode or constant instead)"
                )
                continue
            numeric = _numeric_view(series)
            replacement = _safe_number(
                numeric.mean() if strategy == "mean" else numeric.median()
            )
            cleaned[column] = numeric.fillna(replacement)
        elif strategy == "mode":
            modes = series.mode(dropna=True)
            if modes.empty:
                warnings.append(f"'{column}' has no observed value to use as mode")
                continue
            replacement = modes.iloc[0]
            cleaned[column] = series.fillna(replacement)
        elif strategy == "zero":
            if _is_numeric(series):
                replacement = 0
                cleaned[column] = _numeric_view(series).fillna(0)
            else:
                replacement = ""
                warnings.append(
                    f"'{column}' is not numeric, filled with an empty string instead of 0"
                )
                cleaned[column] = series.astype("string").fillna("")
        else:  # constant
            replacement = constant
            cleaned[column] = series.fillna(constant)

        filled[column] = {
            "missing_before": missing_before,
            "missing_after": int(cleaned[column].isna().sum()),
            "value": to_jsonable(replacement),
        }

    after = _column_profile(cleaned)
    summary = {
        **_diff_profile(before, after),
        "strategy": strategy,
        "columns_filled": filled,
        "missing_cells_filled": before["missing_cells"] - after["missing_cells"],
    }
    return cleaned, summary, warnings


def op_rename_columns(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    mapping = config.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        raise OperationError('"mapping" must be an object like {"old": "new"}')

    unknown = [old for old in mapping if old not in frame.columns]
    if unknown:
        raise OperationError(f"Columns not found: {', '.join(map(str, unknown))}")

    cleaned = frame.rename(
        columns={str(old): str(new) for old, new in mapping.items()}
    )
    duplicates = cleaned.columns[cleaned.columns.duplicated()].tolist()
    if duplicates:
        raise OperationError(
            f"Renaming would create duplicate columns: {', '.join(map(str, duplicates))}"
        )
    return cleaned, {"renamed": {str(k): str(v) for k, v in mapping.items()}}, []


def op_cast_types(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    column = _require_column(frame, config.get("column"))
    target = str(config.get("target_type") or config.get("data_type") or "").lower()
    if target not in CAST_TYPES:
        raise OperationError("target_type must be one of: " + ", ".join(CAST_TYPES))

    series = frame[column]
    if target == "numeric":
        converted = _numeric_view(series)
    elif target == "integer":
        converted = _numeric_view(series).round().astype("Int64")
    elif target == "text":
        converted = series.astype("string")
    elif target == "date":
        converted = pd.to_datetime(series, errors="coerce", format="mixed")
    else:  # boolean
        if pd.api.types.is_bool_dtype(series):
            converted = series.astype("boolean")
        else:
            mapping = {
                **{value: True for value in TRUTHY_STRINGS},
                **{value: False for value in FALSY_STRINGS},
            }
            converted = (
                series.astype("string")
                .str.strip()
                .str.lower()
                .map(mapping)
                .astype("boolean")
            )

    cleaned = frame.copy()
    cleaned[column] = converted
    became_missing = int(converted.isna().sum() - series.isna().sum())
    warnings: List[str] = []
    if became_missing > 0:
        warnings.append(
            f"{became_missing} value(s) in '{column}' could not be read as {target} "
            "and became missing"
        )
    return (
        cleaned,
        {
            "column": column,
            "target_type": target,
            "values_became_missing": max(became_missing, 0),
        },
        warnings,
    )


# --------------------------------------------------------------- transformation


def op_select_columns(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    columns = _require_columns(frame, config.get("columns"))
    cleaned = frame[columns].copy()
    dropped = [str(column) for column in frame.columns if column not in columns]
    return (
        cleaned,
        {"columns": columns, "dropped_columns": dropped, "dropped_count": len(dropped)},
        [],
    )


def _apply_condition(frame: pd.DataFrame, condition: Dict[str, Any]) -> np.ndarray:
    column = _require_column(frame, condition.get("column"))
    operator = str(condition.get("operator") or "eq").lower()
    if operator not in FILTER_OPERATORS:
        raise OperationError(
            "operator must be one of: " + ", ".join(sorted(FILTER_OPERATORS))
        )
    raw = condition.get("value")
    values = _as_list(condition.get("values") if raw is None else raw)
    series = frame[column]

    if operator == "is_null":
        return series.isna().to_numpy()
    if operator == "not_null":
        return series.notna().to_numpy()

    if operator in {"contains", "startswith", "endswith"}:
        if not values:
            raise OperationError(f"'value' is required for operator '{operator}'")
        text = series.astype("string").str.lower()
        needle = str(values[0]).lower()
        if operator == "contains":
            mask = text.str.contains(needle, na=False, regex=False)
        elif operator == "startswith":
            mask = text.str.startswith(needle, na=False)
        else:
            mask = text.str.endswith(needle, na=False)
        return mask.to_numpy()

    # Numeric comparison when both sides look numeric, text comparison otherwise.
    numeric_series = _numeric_view(series)
    numeric_values = [_safe_number(value) for value in values]
    use_numeric = (
        numeric_series.notna().sum() > 0
        and all(value is not None for value in numeric_values)
        and (_is_numeric(series) or len(numeric_values) > 0)
    )
    left = numeric_series if use_numeric else series.astype("string")
    right = numeric_values if use_numeric else [str(value) for value in values]

    if operator == "eq":
        return (left == right[0]).to_numpy()
    if operator == "ne":
        return (left != right[0]).to_numpy()
    if operator == "gt":
        return (left > right[0]).to_numpy()
    if operator == "gte":
        return (left >= right[0]).to_numpy()
    if operator == "lt":
        return (left < right[0]).to_numpy()
    if operator == "lte":
        return (left <= right[0]).to_numpy()
    if operator == "between":
        if len(right) < 2:
            raise OperationError("'value' must contain two limits for operator 'between'")
        low, high = min(right[:2]), max(right[:2])
        return ((left >= low) & (left <= high)).to_numpy()
    if operator == "in":
        return left.isin(right).to_numpy()
    if operator == "not_in":
        return (~left.isin(right)).to_numpy()
    raise OperationError(f"Unsupported operator '{operator}'")


def op_filter(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    conditions = config.get("conditions")
    if conditions:
        if not isinstance(conditions, list):
            raise OperationError("'conditions' must be a list of conditions")
        logic = str(config.get("logic") or "and").lower()
        if logic not in {"and", "or"}:
            raise OperationError("'logic' must be 'and' or 'or'")
        masks = [_apply_condition(frame, condition) for condition in conditions]
        mask = masks[0]
        for extra in masks[1:]:
            mask = (mask & extra) if logic == "and" else (mask | extra)
        description = {"logic": logic, "conditions": conditions}
    else:
        mask = _apply_condition(frame, config)
        description = {
            "column": config.get("column"),
            "operator": config.get("operator") or "eq",
            "value": config.get("value"),
        }

    before = _column_profile(frame)
    cleaned = frame.loc[mask].reset_index(drop=True)
    after = _column_profile(cleaned)
    summary = {
        **_diff_profile(before, after),
        "rows_kept": after["row_count"],
        "condition": description,
    }
    return cleaned, summary, []


def op_sort(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    by = config.get("by") or config.get("columns") or config.get("column")
    columns = _require_columns(frame, _as_list(by), "by")
    ascending = config.get("ascending", True)
    if isinstance(ascending, list):
        ascending_list = [bool(value) for value in ascending]
    else:
        ascending_list = bool(ascending)

    cleaned = frame.sort_values(
        by=columns, ascending=ascending_list, kind="stable"
    ).reset_index(drop=True)
    return cleaned, {"by": columns, "ascending": ascending_list}, []


# ------------------------------------------- calculated columns (safe evaluator)

_BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

_UNARY_OPERATORS = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
}

_COMPARISONS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
}

_FUNCTIONS: Dict[str, Callable] = {
    "abs": np.abs,
    "ceil": np.ceil,
    "clip": np.clip,
    "exp": np.exp,
    "floor": np.floor,
    "log": np.log,
    "log10": np.log10,
    "max": np.maximum,
    "min": np.minimum,
    "power": np.power,
    "round": np.round,
    "sign": np.sign,
    "sqrt": np.sqrt,
    "where": np.where,
}


def _evaluate_node(node: ast.AST, frame: pd.DataFrame) -> Any:
    """Evaluate a whitelisted arithmetic expression over the dataset columns.

    Only numbers, column names and the functions in ``_FUNCTIONS`` are allowed, so an
    expression can never execute arbitrary Python code.
    """
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body, frame)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or node.value is None:
            return node.value
        if not isinstance(node.value, (int, float)):
            raise OperationError("Only numeric constants are allowed in expressions")
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id not in frame.columns:
            raise OperationError(
                f"Unknown column '{node.id}' in the expression. "
                f"Available: {', '.join(map(str, frame.columns))}"
            )
        numeric = _numeric_view(frame[node.id])
        if numeric.notna().sum() == 0 and frame[node.id].notna().sum() > 0:
            raise OperationError(
                f"Column '{node.id}' is not numeric, cast it first or use another column"
            )
        return numeric.to_numpy(dtype=float)

    if isinstance(node, ast.BinOp):
        handler = _BINARY_OPERATORS.get(type(node.op))
        if handler is None:
            raise OperationError("This arithmetic operator is not allowed")
        with np.errstate(divide="ignore", invalid="ignore"):
            left = _evaluate_node(node.left, frame)
            right = _evaluate_node(node.right, frame)
            return handler(left, right)

    if isinstance(node, ast.UnaryOp):
        handler = _UNARY_OPERATORS.get(type(node.op))
        if handler is None:
            raise OperationError("This unary operator is not allowed")
        return handler(_evaluate_node(node.operand, frame))

    if isinstance(node, ast.Compare):
        left = _evaluate_node(node.left, frame)
        result = None
        for op, comparator in zip(node.ops, node.comparators):
            handler = _COMPARISONS.get(type(op))
            if handler is None:
                raise OperationError("This comparison is not allowed")
            piece = handler(left, _evaluate_node(comparator, frame))
            result = piece if result is None else (result & piece)
            left = comparator
        return result

    if isinstance(node, ast.BoolOp):
        values = [_evaluate_node(value, frame) for value in node.values]
        result = values[0]
        for value in values[1:]:
            result = (result & value) if isinstance(node.op, ast.And) else (result | value)
        return result

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise OperationError(
                "Only these functions are allowed: " + ", ".join(sorted(_FUNCTIONS))
            )
        args = [_evaluate_node(argument, frame) for argument in node.args]
        keywords = {
            keyword.arg: _evaluate_node(keyword.value, frame)
            for keyword in node.keywords
            if keyword.arg
        }
        with np.errstate(divide="ignore", invalid="ignore"):
            return _FUNCTIONS[node.func.id](*args, **keywords)

    raise OperationError("Unsupported expression, use plain arithmetic between columns")


def op_calculate_column(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    name = config.get("name") or config.get("column_name")
    expression = config.get("expression")
    if not name:
        raise OperationError("'name' is required for a calculated column")
    if not expression:
        raise OperationError("'expression' is required for a calculated column")
    name = str(name)

    replacing = name in frame.columns
    if replacing and not config.get("overwrite", False):
        raise OperationError(
            f"Column '{name}' already exists, pass overwrite=true to replace it"
        )

    try:
        tree = ast.parse(str(expression), mode="eval")
    except SyntaxError as exc:
        raise OperationError(f"Could not parse the expression: {exc.msg}")

    value = _evaluate_node(tree, frame)
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        array = np.full(int(frame.shape[0]), float(array))

    warnings: List[str] = []
    non_finite = int(np.count_nonzero(~np.isfinite(array)))
    if non_finite:
        warnings.append(
            f"{non_finite} value(s) were not finite (division by zero / invalid math) "
            "and became missing"
        )
        array = np.where(np.isfinite(array), array, np.nan)

    if str(config.get("dtype") or "float").lower() in {"integer", "int"}:
        array = np.round(array)

    cleaned = frame.copy()
    cleaned[name] = array
    summary = {
        "name": name,
        "expression": str(expression),
        "overwritten": replacing,
        "non_finite_values": non_finite,
        "columns_after": int(cleaned.shape[1]),
    }
    return cleaned, summary, warnings


def op_group_by(frame: pd.DataFrame, config: Dict[str, Any]) -> OperationResult:
    by = _require_columns(
        frame, _as_list(config.get("by") or config.get("columns")), "by"
    )

    aggregations = config.get("aggregations")
    if not aggregations:
        column = config.get("column")
        aggregation = str(config.get("aggregation") or "count").lower()
        aggregations = {column: [aggregation]} if column else {"__rows__": ["count"]}
    if not isinstance(aggregations, dict):
        raise OperationError(
            'aggregations must be an object like {"sales": ["sum", "mean"]}'
        )

    plan: List[Tuple[str, str, str]] = []  # (source column, aggregation, output name)
    warnings: List[str] = []
    for column, requested in aggregations.items():
        for aggregation in _as_list(requested):
            aggregation = str(aggregation).lower()
            if aggregation not in AGGREGATIONS:
                raise OperationError(
                    "aggregation must be one of: " + ", ".join(AGGREGATIONS)
                )
            if column == "__rows__":
                if aggregation != "count":
                    raise OperationError("Only 'count' can be applied to all rows")
                plan.append(("__rows__", "count", "row_count"))
                continue
            if column not in frame.columns:
                raise OperationError(f"Column '{column}' does not exist")
            if aggregation in {"sum", "mean", "median", "std"} and not _is_numeric(
                frame[column]
            ):
                warnings.append(
                    f"'{column}' is not numeric, skipped aggregation '{aggregation}'"
                )
                continue
            plan.append((str(column), aggregation, f"{column}_{aggregation}"))

    if not plan:
        raise OperationError("No valid aggregation was requested")

    working = frame.copy()
    working["__rows__"] = 1
    missing_keys = int(working[by].isna().any(axis=1).sum())
    if missing_keys:
        warnings.append(
            f"{missing_keys} row(s) have missing group keys and are grouped as "
            "an explicit missing group"
        )

    aggregated = working.groupby(by, dropna=False).agg(
        **{output: (source, aggregation) for source, aggregation, output in plan}
    )
    aggregated = (
        aggregated.reset_index().sort_values(by, kind="stable").reset_index(drop=True)
    )

    before = _column_profile(frame)
    after = _column_profile(aggregated)
    summary = {
        **_diff_profile(before, after),
        "by": by,
        "aggregations": {
            output: {"column": source, "aggregation": aggregation}
            for source, aggregation, output in plan
        },
        "groups": int(aggregated.shape[0]),
    }
    return aggregated, summary, warnings


# ------------------------------------------------------------------ registry

OPERATION_CATALOG: Dict[str, Dict[str, Any]] = {
    "drop_duplicates": {
        "group": CLEAN,
        "label": "Remove duplicate rows",
        "handler": op_drop_duplicates,
        "parameters": ["subset (optional)", "keep (first|last)"],
    },
    "drop_missing": {
        "group": CLEAN,
        "label": "Drop rows with missing values",
        "handler": op_drop_missing,
        "parameters": ["columns (optional)", "threshold (optional)"],
    },
    "fill_missing": {
        "group": CLEAN,
        "label": "Fill missing values",
        "handler": op_fill_missing,
        "parameters": [
            "strategy (drop|mean|median|mode|zero|constant)",
            "column or columns",
            "value (for constant)",
        ],
    },
    "rename_columns": {
        "group": CLEAN,
        "label": "Rename columns",
        "handler": op_rename_columns,
        "parameters": ["mapping {old: new}"],
    },
    "cast_types": {
        "group": CLEAN,
        "label": "Cast a column type",
        "handler": op_cast_types,
        "parameters": ["column", "target_type (numeric|integer|text|date|boolean)"],
    },
    "select_columns": {
        "group": TRANSFORM,
        "label": "Select columns",
        "handler": op_select_columns,
        "parameters": ["columns"],
    },
    "filter": {
        "group": TRANSFORM,
        "label": "Filter rows",
        "handler": op_filter,
        "parameters": ["column", "operator", "value", "conditions/logic (optional)"],
    },
    "sort": {
        "group": TRANSFORM,
        "label": "Sort rows",
        "handler": op_sort,
        "parameters": ["by", "ascending"],
    },
    "calculate_column": {
        "group": TRANSFORM,
        "label": "Calculate a new column",
        "handler": op_calculate_column,
        "parameters": ["name", "expression", "overwrite (optional)"],
    },
    "group_by": {
        "group": TRANSFORM,
        "label": "Group by and aggregate",
        "handler": op_group_by,
        "parameters": [
            "by",
            "aggregations {column: [count|sum|mean|median|min|max]}",
        ],
    },
}


def catalog() -> List[Dict[str, Any]]:
    """Operation metadata for the UI (groups, labels, expected parameters)."""
    return [
        {
            "type": operation_type,
            "group": metadata["group"],
            "label": metadata["label"],
            "parameters": metadata["parameters"],
        }
        for operation_type, metadata in OPERATION_CATALOG.items()
    ]


def get_operation(operation_type: str) -> Dict[str, Any]:
    metadata = OPERATION_CATALOG.get(str(operation_type))
    if metadata is None:
        raise OperationError(
            "Unknown operation_type. Allowed: " + ", ".join(sorted(OPERATION_CATALOG))
        )
    return metadata


def operation_group(operation_type: str) -> str:
    return str(get_operation(operation_type)["group"])


def apply_operation(
    frame: pd.DataFrame,
    operation_type: str,
    configuration: Optional[Dict[str, Any]] = None,
) -> OperationResult:
    """Run one operation and return ``(frame, summary, warnings)``."""
    metadata = get_operation(operation_type)
    if frame.shape[0] == 0:
        raise OperationError("The dataset has no rows to operate on")
    return metadata["handler"](frame, configuration or {})






