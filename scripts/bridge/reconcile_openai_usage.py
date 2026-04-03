#!/usr/bin/env python3
"""Reconcile historical OpenAI/Hermes usage against Vizier evidence."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DB_PATH = Path.home() / ".hermes" / "state.db"


def _parse_time_arg(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        normalized = stripped.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()


def _format_timestamp(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        [name],
    ).fetchone()
    return row is not None


def _time_clause(column: str, start_ts: float | None, end_ts: float | None) -> tuple[str, list[float]]:
    clauses: list[str] = []
    params: list[float] = []
    if start_ts is not None:
        clauses.append(f"{column} >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append(f"{column} <= ?")
        params.append(end_ts)
    if not clauses:
        return ("", [])
    return ("WHERE " + " AND ".join(clauses), params)


def _cost_totals(
    conn: sqlite3.Connection,
    *,
    start_ts: float | None,
    end_ts: float | None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
) -> dict[str, int]:
    where_sql, params = _time_clause("timestamp", start_ts, end_ts)
    clauses = [where_sql[6:]] if where_sql else []
    if extra_where:
        clauses.append(extra_where)
    final_where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    row = conn.execute(
        f"""SELECT COUNT(*) AS call_count,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens
            FROM cost_ledger
            {final_where}""",
        [*params, *(extra_params or [])],
    ).fetchone()
    assert row is not None
    return {key: int(row[key] or 0) for key in ("call_count", "input_tokens", "output_tokens", "total_tokens")}


def _prompt_totals(
    conn: sqlite3.Connection,
    *,
    start_ts: float | None,
    end_ts: float | None,
) -> dict[str, int]:
    where_sql, params = _time_clause("timestamp", start_ts, end_ts)
    row = conn.execute(
        f"""SELECT COUNT(*) AS call_count,
                   COALESCE(SUM(tokens_in), 0) AS input_tokens,
                   COALESCE(SUM(tokens_out), 0) AS output_tokens,
                   COALESCE(SUM(tokens_in + tokens_out), 0) AS total_tokens
            FROM prompt_log
            {where_sql}""",
        params,
    ).fetchone()
    assert row is not None
    return {key: int(row[key] or 0) for key in ("call_count", "input_tokens", "output_tokens", "total_tokens")}


def _cost_breakdown(
    conn: sqlite3.Connection,
    *,
    group_expr: str,
    alias: str,
    start_ts: float | None,
    end_ts: float | None,
) -> dict[str, dict[str, int]]:
    where_sql, params = _time_clause("timestamp", start_ts, end_ts)
    rows = conn.execute(
        f"""SELECT {group_expr} AS {alias},
                   COUNT(*) AS call_count,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens
            FROM cost_ledger
            {where_sql}
            GROUP BY {group_expr}
            ORDER BY total_tokens DESC, {alias} ASC""",
        params,
    ).fetchall()
    return {
        str(row[alias]): {
            "call_count": int(row["call_count"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
        }
        for row in rows
    }


def _cost_risk_buckets(
    conn: sqlite3.Connection,
    *,
    start_ts: float | None,
    end_ts: float | None,
) -> dict[str, int]:
    where_sql, params = _time_clause("timestamp", start_ts, end_ts)
    clauses = [where_sql[6:]] if where_sql else []
    clauses.insert(0, "provider_name IS NOT NULL")
    final_where = f"WHERE {' AND '.join(clauses)}"
    row = conn.execute(
        f"""SELECT
                   SUM(CASE WHEN session_id IS NULL OR TRIM(session_id) = '' THEN 1 ELSE 0 END) AS missing_session_rows,
                   COALESCE(SUM(CASE WHEN session_id IS NULL OR TRIM(session_id) = '' THEN input_tokens + output_tokens ELSE 0 END), 0) AS missing_session_tokens,
                   SUM(CASE WHEN deliverable_id IS NULL OR TRIM(deliverable_id) = '' THEN 1 ELSE 0 END) AS missing_deliverable_rows,
                   COALESCE(SUM(CASE WHEN deliverable_id IS NULL OR TRIM(deliverable_id) = '' THEN input_tokens + output_tokens ELSE 0 END), 0) AS missing_deliverable_tokens,
                   SUM(CASE WHEN client_id IS NULL OR TRIM(client_id) = '' THEN 1 ELSE 0 END) AS missing_client_rows,
                   COALESCE(SUM(CASE WHEN client_id IS NULL OR TRIM(client_id) = '' THEN input_tokens + output_tokens ELSE 0 END), 0) AS missing_client_tokens
            FROM cost_ledger
            {final_where}""",
        params,
    ).fetchone()
    assert row is not None
    return {
        "metered_rows_missing_session_id": int(row["missing_session_rows"] or 0),
        "metered_tokens_missing_session_id": int(row["missing_session_tokens"] or 0),
        "metered_rows_missing_deliverable_id": int(row["missing_deliverable_rows"] or 0),
        "metered_tokens_missing_deliverable_id": int(row["missing_deliverable_tokens"] or 0),
        "metered_rows_missing_client_id": int(row["missing_client_rows"] or 0),
        "metered_tokens_missing_client_id": int(row["missing_client_tokens"] or 0),
    }


def _daily_totals(
    conn: sqlite3.Connection,
    *,
    table: str,
    token_expr: str,
    count_expr: str = "COUNT(*)",
    start_ts: float | None,
    end_ts: float | None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
) -> dict[str, dict[str, int]]:
    where_sql, params = _time_clause("timestamp", start_ts, end_ts)
    clauses = [where_sql[6:]] if where_sql else []
    if extra_where:
        clauses.append(extra_where)
    final_where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT date(timestamp, 'unixepoch') AS day,
                   {count_expr} AS call_count,
                   COALESCE(SUM({token_expr}), 0) AS total_tokens
            FROM {table}
            {final_where}
            GROUP BY day
            ORDER BY day ASC""",
        [*params, *(extra_params or [])],
    ).fetchall()
    return {
        str(row["day"]): {
            "call_count": int(row["call_count"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
        }
        for row in rows
    }


def reconcile_usage(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    start_ts: float | None = None,
    end_ts: float | None = None,
    openai_total_tokens: int | None = None,
    vizier_reported_tokens: int | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "db_path": str(db_path),
        "window": {
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "start_iso_utc": _format_timestamp(start_ts),
            "end_iso_utc": _format_timestamp(end_ts),
        },
        "notes": [
            "prompt_log is treated as Hermes-side activity evidence, not provider billing authority",
            "provider_name IS NOT NULL rows in cost_ledger are treated as provider-metered attempts",
            "estimated_unattributed_hermes_tokens is an inference: max(prompt_log_tokens - metered_hermes_tokens, 0)",
            "lifecycle_only_cost_rows are diagnostic rows without provider metadata and should not be double-counted as provider spend",
        ],
    }
    if not db_path.exists():
        report["error"] = f"Database not found: {db_path}"
        return report

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        if _table_exists(conn, "cost_ledger"):
            report["cost_ledger"] = {
                "all_rows": _cost_totals(conn, start_ts=start_ts, end_ts=end_ts),
                "provider_metered_rows": _cost_totals(
                    conn, start_ts=start_ts, end_ts=end_ts, extra_where="provider_name IS NOT NULL"
                ),
                "openai_metered_rows": _cost_totals(
                    conn, start_ts=start_ts, end_ts=end_ts, extra_where="provider_name = ?", extra_params=["openai"]
                ),
                "hermes_metered_rows": _cost_totals(
                    conn,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    extra_where="provider_name IS NOT NULL AND source = ?",
                    extra_params=["hermes"],
                ),
                "lifecycle_only_rows": _cost_totals(
                    conn, start_ts=start_ts, end_ts=end_ts, extra_where="provider_name IS NULL"
                ),
                "by_provider": _cost_breakdown(
                    conn,
                    group_expr="COALESCE(provider_name, 'lifecycle_only')",
                    alias="provider_name",
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                "by_source": _cost_breakdown(
                    conn,
                    group_expr="COALESCE(source, 'unknown')",
                    alias="source",
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                "by_modality": _cost_breakdown(
                    conn,
                    group_expr="COALESCE(modality, 'unknown')",
                    alias="modality",
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                "by_status": _cost_breakdown(
                    conn,
                    group_expr="COALESCE(status, 'unknown')",
                    alias="status",
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                "risk_buckets": _cost_risk_buckets(conn, start_ts=start_ts, end_ts=end_ts),
            }
        else:
            report["cost_ledger"] = {"missing": True}

        if _table_exists(conn, "prompt_log"):
            prompt_totals = _prompt_totals(conn, start_ts=start_ts, end_ts=end_ts)
            report["prompt_log"] = prompt_totals
        else:
            prompt_totals = {"call_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            report["prompt_log"] = {"missing": True, **prompt_totals}

        prompt_by_day = _daily_totals(
            conn,
            table="prompt_log",
            token_expr="tokens_in + tokens_out",
            start_ts=start_ts,
            end_ts=end_ts,
        ) if _table_exists(conn, "prompt_log") else {}
        metered_by_day = _daily_totals(
            conn,
            table="cost_ledger",
            token_expr="input_tokens + output_tokens",
            start_ts=start_ts,
            end_ts=end_ts,
            extra_where="provider_name IS NOT NULL",
        ) if _table_exists(conn, "cost_ledger") else {}
        openai_by_day = _daily_totals(
            conn,
            table="cost_ledger",
            token_expr="input_tokens + output_tokens",
            start_ts=start_ts,
            end_ts=end_ts,
            extra_where="provider_name = ?",
            extra_params=["openai"],
        ) if _table_exists(conn, "cost_ledger") else {}
        hermes_metered_by_day = _daily_totals(
            conn,
            table="cost_ledger",
            token_expr="input_tokens + output_tokens",
            start_ts=start_ts,
            end_ts=end_ts,
            extra_where="provider_name IS NOT NULL AND source = ?",
            extra_params=["hermes"],
        ) if _table_exists(conn, "cost_ledger") else {}
        lifecycle_by_day = _daily_totals(
            conn,
            table="cost_ledger",
            token_expr="input_tokens + output_tokens",
            start_ts=start_ts,
            end_ts=end_ts,
            extra_where="provider_name IS NULL",
        ) if _table_exists(conn, "cost_ledger") else {}

    all_days = sorted({*prompt_by_day.keys(), *metered_by_day.keys(), *openai_by_day.keys(), *hermes_metered_by_day.keys(), *lifecycle_by_day.keys()})
    daily_rows: list[dict[str, Any]] = []
    total_unattributed_tokens = 0
    total_unattributed_calls = 0
    for day in all_days:
        prompt = prompt_by_day.get(day, {"call_count": 0, "total_tokens": 0})
        metered = metered_by_day.get(day, {"call_count": 0, "total_tokens": 0})
        openai_metered = openai_by_day.get(day, {"call_count": 0, "total_tokens": 0})
        hermes_metered = hermes_metered_by_day.get(day, {"call_count": 0, "total_tokens": 0})
        lifecycle_only = lifecycle_by_day.get(day, {"call_count": 0, "total_tokens": 0})
        unattributed_tokens = max(prompt["total_tokens"] - hermes_metered["total_tokens"], 0)
        unattributed_calls = max(prompt["call_count"] - hermes_metered["call_count"], 0)
        total_unattributed_tokens += unattributed_tokens
        total_unattributed_calls += unattributed_calls
        daily_rows.append(
            {
                "day": day,
                "prompt_log_tokens": prompt["total_tokens"],
                "prompt_log_calls": prompt["call_count"],
                "metered_provider_tokens": metered["total_tokens"],
                "metered_provider_calls": metered["call_count"],
                "metered_openai_tokens": openai_metered["total_tokens"],
                "metered_openai_calls": openai_metered["call_count"],
                "metered_hermes_tokens": hermes_metered["total_tokens"],
                "metered_hermes_calls": hermes_metered["call_count"],
                "lifecycle_only_tokens": lifecycle_only["total_tokens"],
                "lifecycle_only_calls": lifecycle_only["call_count"],
                "estimated_unattributed_hermes_tokens": unattributed_tokens,
                "estimated_unattributed_hermes_calls": unattributed_calls,
            }
        )

    report["daily_reconciliation"] = daily_rows
    report["historical_gap_estimate"] = {
        "estimated_unattributed_hermes_tokens": total_unattributed_tokens,
        "estimated_unattributed_hermes_calls": total_unattributed_calls,
        "prompt_log_total_tokens": prompt_totals["total_tokens"],
        "provider_metered_total_tokens": (
            report["cost_ledger"].get("provider_metered_rows", {}).get("total_tokens", 0)
            if isinstance(report.get("cost_ledger"), dict)
            else 0
        ),
    }

    if openai_total_tokens is not None or vizier_reported_tokens is not None:
        openai_metered_total = (
            report["cost_ledger"].get("openai_metered_rows", {}).get("total_tokens", 0)
            if isinstance(report.get("cost_ledger"), dict)
            else 0
        )
        comparison: dict[str, Any] = {
            "openai_total_tokens": openai_total_tokens,
            "vizier_reported_tokens": vizier_reported_tokens,
            "metered_openai_tokens": openai_metered_total,
            "estimated_unattributed_hermes_tokens": total_unattributed_tokens,
        }
        if openai_total_tokens is not None:
            comparison["gap_openai_minus_metered_openai"] = openai_total_tokens - openai_metered_total
            comparison["remaining_gap_after_hermes_estimate"] = openai_total_tokens - openai_metered_total - total_unattributed_tokens
        if vizier_reported_tokens is not None:
            comparison["gap_openai_minus_vizier_reported"] = (
                openai_total_tokens - vizier_reported_tokens
                if openai_total_tokens is not None
                else None
            )
            comparison["gap_metered_openai_minus_vizier_reported"] = openai_metered_total - vizier_reported_tokens
        report["external_comparison"] = comparison

    return report


def render_text_report(report: dict[str, Any]) -> str:
    if report.get("error"):
        return str(report["error"])

    cost = report.get("cost_ledger", {})
    prompt = report.get("prompt_log", {})
    gap = report.get("historical_gap_estimate", {})
    lines = [
        f"DB: {report['db_path']}",
        f"Window: {report['window'].get('start_iso_utc') or 'beginning'} -> {report['window'].get('end_iso_utc') or 'latest'}",
        "",
        "Cost ledger",
        f"  Provider-metered tokens: {cost.get('provider_metered_rows', {}).get('total_tokens', 0)}",
        f"  OpenAI-metered tokens: {cost.get('openai_metered_rows', {}).get('total_tokens', 0)}",
        f"  Hermes-metered tokens: {cost.get('hermes_metered_rows', {}).get('total_tokens', 0)}",
        f"  Lifecycle-only tokens: {cost.get('lifecycle_only_rows', {}).get('total_tokens', 0)}",
        "",
        "Prompt log",
        f"  Hermes prompt-log tokens: {prompt.get('total_tokens', 0)}",
        "",
        "Historical gap estimate",
        f"  Estimated unattributed Hermes tokens: {gap.get('estimated_unattributed_hermes_tokens', 0)}",
        f"  Estimated unattributed Hermes calls: {gap.get('estimated_unattributed_hermes_calls', 0)}",
    ]

    external = report.get("external_comparison")
    if isinstance(external, dict):
        lines.extend(
            [
                "",
                "External comparison",
                f"  OpenAI total tokens: {external.get('openai_total_tokens')}",
                f"  Vizier reported tokens: {external.get('vizier_reported_tokens')}",
                f"  Gap (OpenAI - metered OpenAI): {external.get('gap_openai_minus_metered_openai')}",
                f"  Remaining gap after Hermes estimate: {external.get('remaining_gap_after_hermes_estimate')}",
            ]
        )

    top_days = sorted(
        report.get("daily_reconciliation", []),
        key=lambda row: row.get("estimated_unattributed_hermes_tokens", 0),
        reverse=True,
    )[:5]
    if top_days:
        lines.append("")
        lines.append("Top daily Hermes blind spots")
        for row in top_days:
            lines.append(
                f"  {row['day']}: +{row['estimated_unattributed_hermes_tokens']} tokens ({row['estimated_unattributed_hermes_calls']} calls)"
            )

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile historical OpenAI/Hermes usage against Vizier evidence."
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Path to Hermes/Vizier state.db.")
    parser.add_argument("--start", help="Optional window start as unix timestamp or ISO8601.")
    parser.add_argument("--end", help="Optional window end as unix timestamp or ISO8601.")
    parser.add_argument("--openai-total-tokens", type=int, help="Optional OpenAI billing total for the same window.")
    parser.add_argument("--vizier-reported-tokens", type=int, help="Optional Vizier/user-facing token total for the same window.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = reconcile_usage(
        db_path=Path(args.db_path),
        start_ts=_parse_time_arg(args.start),
        end_ts=_parse_time_arg(args.end),
        openai_total_tokens=args.openai_total_tokens,
        vizier_reported_tokens=args.vizier_reported_tokens,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print(render_text_report(report))
    return 0 if "error" not in report else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
