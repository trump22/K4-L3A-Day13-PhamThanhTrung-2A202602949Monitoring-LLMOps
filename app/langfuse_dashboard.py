from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from langfuse import get_client


def _query_metrics(
    *,
    from_timestamp: str,
    to_timestamp: str,
    metrics: list[dict[str, str]],
    filters: list[dict[str, Any]] | None = None,
    view: str = "observations",
) -> list[dict[str, Any]]:
    query = {
        "view": view,
        "metrics": metrics,
        "dimensions": [],
        "filters": filters or [],
        "fromTimestamp": from_timestamp,
        "toTimestamp": to_timestamp,
    }
    response = get_client().api.metrics.metrics(query=json.dumps(query))
    return response.data


def _number(row: dict[str, Any], key: str) -> float | None:
    try:
        value = row.get(key)
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first(data: list[dict[str, Any]]) -> dict[str, Any]:
    return data[0] if data else {}


def fetch_langfuse_dashboard_metrics() -> dict[str, Any]:
    """Fetch privacy-safe aggregates; never request observation input/output."""
    load_dotenv(".env", override=False)
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return {"available": False, "reason": "Langfuse credentials are not configured."}

    now = datetime.now(timezone.utc)
    from_timestamp, to_timestamp = "1970-01-01T00:00:00Z", now.isoformat()
    try:
        roots = _first(
            _query_metrics(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                filters=[
                    {"column": "isRootObservation", "operator": "=", "value": True, "type": "boolean"}
                ],
                metrics=[
                    {"measure": "count", "aggregation": "count"},
                    {"measure": "latency", "aggregation": "p50"},
                    {"measure": "latency", "aggregation": "p95"},
                    {"measure": "latency", "aggregation": "p99"},
                ],
            )
        )
        generations = _first(
            _query_metrics(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                filters=[
                    {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}
                ],
                metrics=[
                    {"measure": "totalCost", "aggregation": "sum"},
                    {"measure": "inputTokens", "aggregation": "sum"},
                    {"measure": "outputTokens", "aggregation": "sum"},
                    {"measure": "timeToFirstToken", "aggregation": "p95"},
                ],
            )
        )
        failed_roots = _number(
            _first(
                _query_metrics(
                    from_timestamp=from_timestamp,
                    to_timestamp=to_timestamp,
                    filters=[
                        {"column": "isRootObservation", "operator": "=", "value": True, "type": "boolean"},
                        {"column": "level", "operator": "any of", "value": ["ERROR"], "type": "stringOptions"},
                    ],
                    metrics=[{"measure": "count", "aggregation": "count"}],
                )
            ),
            "count_count",
        )
        retrieval_total = _number(
            _first(
                _query_metrics(
                    from_timestamp=from_timestamp,
                    to_timestamp=to_timestamp,
                    filters=[{"column": "name", "operator": "=", "value": "retrieval", "type": "string"}],
                    metrics=[{"measure": "count", "aggregation": "count"}],
                )
            ),
            "count_count",
        )
        retrieval_failed = _number(
            _first(
                _query_metrics(
                    from_timestamp=from_timestamp,
                    to_timestamp=to_timestamp,
                    filters=[
                        {"column": "name", "operator": "=", "value": "retrieval", "type": "string"},
                        {"column": "level", "operator": "any of", "value": ["ERROR"], "type": "stringOptions"},
                    ],
                    metrics=[{"measure": "count", "aggregation": "count"}],
                )
            ),
            "count_count",
        )
        scores = _first(
            _query_metrics(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                metrics=[
                    {"measure": "value", "aggregation": "avg"},
                    {"measure": "count", "aggregation": "count"},
                ],
                view="scores-numeric",
            )
        )
        return {
            "available": True,
            "window": "all_time",
            "trace_count": _number(roots, "count_count"),
            "failed_trace_count": failed_roots,
            "error_rate_pct": (
                failed_roots / _number(roots, "count_count") * 100
                if failed_roots is not None and (_number(roots, "count_count") or 0) > 0
                else None
            ),
            "retrieval_count": retrieval_total,
            "retrieval_success_pct": (
                (retrieval_total - retrieval_failed) / retrieval_total * 100
                if retrieval_total is not None and retrieval_failed is not None and retrieval_total > 0
                else None
            ),
            "latency_p50": _number(roots, "p50_latency"),
            "latency_p95": _number(roots, "p95_latency"),
            "latency_p99": _number(roots, "p99_latency"),
            "ttft_p95": _number(generations, "p95_timeToFirstToken"),
            "cost_usd": _number(generations, "sum_totalCost"),
            "tokens_in": _number(generations, "sum_inputTokens"),
            "tokens_out": _number(generations, "sum_outputTokens"),
            "quality_avg": _number(scores, "avg_value"),
            "quality_score_count": _number(scores, "count_count"),
        }
    except Exception as exc:  # API outages must not take down the local dashboard.
        return {"available": False, "reason": f"Langfuse metrics unavailable ({type(exc).__name__})."}
