"""Pandas data analysis wrapper."""
from __future__ import annotations

import operator
import re
from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

_OPERATIONS = {"describe", "groupby", "filter"}

_SAFE_OPERATORS: dict[str, operator.gt[object, object]] = {  # type: ignore[type-arg]
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

_FILTER_PATTERN = re.compile(
    r"^\s*(\w+)\s*(==|!=|<=|>=|<|>)\s*(.+?)\s*$"
)


def _safe_filter(df: pd.DataFrame, filter_expr: str | None) -> pd.DataFrame:
    """Apply a simple comparison filter without eval().

    Only allows expressions like ``column_name operator value``.

    Args:
        df: DataFrame to filter.
        filter_expr: Expression such as ``"age > 30"`` or ``"name == 'Alice'"``.

    Returns:
        Filtered DataFrame.

    Raises:
        ValueError: If expression is None, unparseable, uses an unknown
            operator, or references a column not in the DataFrame.
    """
    if filter_expr is None:
        msg = "filter_expr is required for the filter operation"
        raise ValueError(msg)

    match = _FILTER_PATTERN.match(filter_expr)
    if not match:
        msg = (
            f"Cannot parse filter expression: {filter_expr!r}. "
            "Expected format: column operator value (e.g. 'age > 30')"
        )
        raise ValueError(msg)

    col, op_str, raw_value = match.group(1), match.group(2), match.group(3)

    if col not in df.columns:
        msg = (
            f"Column {col!r} not in DataFrame."
            f" Available: {sorted(df.columns.tolist())}"
        )
        raise ValueError(msg)

    op_func = _SAFE_OPERATORS[op_str]

    # Coerce value to the column's dtype
    stripped = raw_value.strip("'\"")
    try:
        typed_value = df[col].dtype.type(stripped)
    except (ValueError, TypeError):
        typed_value = stripped  # type: ignore[assignment]

    mask = op_func(df[col], typed_value)
    result = df[mask]
    if not isinstance(result, pd.DataFrame):
        msg = "Filter did not produce a DataFrame"
        raise ValueError(msg)
    return result


def run(
    *,
    input_path: str,
    operation: str,
    group_column: str | None = None,
    agg_column: str | None = None,
    agg_function: str = "sum",
    filter_expr: str | None = None,
    output_path: str | None = None,
) -> dict[str, str]:
    """Analyze tabular data with pandas.

    Args:
        input_path: Path to CSV, JSON, or Excel file.
        operation: One of "describe", "groupby", "filter".
        group_column: Column name to group by (groupby operation).
        agg_column: Column name to aggregate (groupby operation).
        agg_function: Aggregation function: sum, mean, count, min, max.
        filter_expr: Pandas query expression (filter operation).
        output_path: Optional path to write result as CSV.

    Returns:
        Dict with "summary" key containing JSON string of result.

    Raises:
        ValueError: If operation is not one of the supported operations.
    """
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    path = Path(input_path)
    if path.suffix == ".json":
        df = pd.read_json(path)
    elif path.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    raw: str | None
    if operation == "describe":
        result_df = df.describe(include="all")
        raw = result_df.to_json()
    elif operation == "groupby":
        grouped = df.groupby(group_column)[agg_column].agg(agg_function)  # type: ignore[index]
        raw = grouped.to_json()
    else:  # filter
        filtered = _safe_filter(df, filter_expr)
        raw = filtered.to_json(orient="records")

    summary: str = raw or "{}"

    if output_path:
        df.to_csv(output_path, index=False)

    logger.info("Analysis complete: %s on %s", operation, input_path)
    return {"summary": summary}
