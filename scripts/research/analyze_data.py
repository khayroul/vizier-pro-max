"""Pandas data analysis wrapper."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_OPERATIONS = {"describe", "groupby", "filter"}


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
        filtered = df.query(filter_expr)  # type: ignore[arg-type]
        raw = filtered.to_json(orient="records")

    summary: str = raw or "{}"

    if output_path:
        df.to_csv(output_path, index=False)

    logger.info("Analysis complete: %s on %s", operation, input_path)
    return {"summary": summary}
