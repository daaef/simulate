"""Run-health aggregation for simulator reports."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any


def ascii_bar(value: float, *, maximum: float, width: int = 24) -> str:
    if maximum <= 0 or value <= 0:
        return "-" * width
    filled = int(round((value / maximum) * width))
    filled = max(0, min(width, filled))
    return "#" * filled + "-" * (width - filled)


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    weighted = ordered[lower] * (upper - rank) + ordered[upper] * (rank - lower)
    return int(round(weighted))


def _latency_summary(values: list[int]) -> dict[str, int]:
    if not values:
        return {"count": 0, "avg": 0, "p50": 0, "p95": 0, "max": 0}
    return {
        "count": len(values),
        "avg": int(round(sum(values) / len(values))),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _status_group(status: int | None) -> str:
    if status is None:
        return "unknown"
    if 200 <= status <= 299:
        return "2xx"
    if 300 <= status <= 399:
        return "3xx"
    if 400 <= status <= 499:
        return "4xx"
    if 500 <= status <= 599:
        return "5xx"
    return "other"


def _verdict(
    *,
    issue_counts: Counter,
    scenarios: list[dict[str, Any]],
    websocket_expected: int,
    websocket_matched: int,
) -> str:
    scenario_verdicts = [
        str(item.get("effective_verdict") or item.get("base_verdict") or "")
        for item in scenarios
    ]
    if issue_counts.get("error", 0) or any(
        verdict in {"blocked", "failed", "error"} for verdict in scenario_verdicts
    ):
        return "failed"
    if issue_counts.get("warning", 0) or any(
        verdict in {"degraded", "unsupported"} for verdict in scenario_verdicts
    ):
        return "degraded"
    if websocket_expected and websocket_matched < websocket_expected:
        return "degraded"
    return "passed"


def build_health_summary(
    *,
    duration_ms: int,
    scenarios: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    events: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    http_events = [
        event
        for event in events
        if event.get("method") or event.get("http_status") is not None
    ]
    latencies = [
        int(event["latency_ms"])
        for event in http_events
        if event.get("latency_ms") is not None
    ]
    endpoint_buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in http_events:
        method = str(event.get("method") or "")
        endpoint = str(event.get("endpoint") or event.get("full_url") or "")
        endpoint_buckets[(method, endpoint)].append(event)

    endpoint_stats = []
    for (method, endpoint), bucket in endpoint_buckets.items():
        bucket_latencies = [
            int(event["latency_ms"])
            for event in bucket
            if event.get("latency_ms") is not None
        ]
        errors = sum(1 for event in bucket if int(event.get("http_status") or 0) >= 400)
        endpoint_stats.append(
            {
                "method": method,
                "endpoint": endpoint,
                "count": len(bucket),
                "errors": errors,
                "latency_ms": _latency_summary(bucket_latencies),
            }
        )
    endpoint_stats.sort(
        key=lambda item: (item["latency_ms"]["p95"], item["latency_ms"]["max"]),
        reverse=True,
    )

    slowest = sorted(
        [
            {
                "id": event.get("id"),
                "actor": event.get("actor"),
                "action": event.get("action"),
                "method": event.get("method", ""),
                "endpoint": event.get("endpoint") or event.get("full_url") or "",
                "latency_ms": int(event.get("latency_ms") or 0),
                "http_status": event.get("http_status"),
            }
            for event in http_events
            if event.get("latency_ms") is not None
        ],
        key=lambda item: item["latency_ms"],
        reverse=True,
    )[:10]

    expected_ws = [event for event in events if event.get("expect_websocket")]
    matched_ws = [
        event
        for event in expected_ws
        if (event.get("websocket_match") or {}).get("matched")
    ]
    issue_counts = Counter(str(issue.get("severity") or "unknown") for issue in issues)
    status_groups = Counter(_status_group(event.get("http_status")) for event in http_events)
    order_statuses = Counter(str(order.get("final_status") or "unknown") for order in orders)

    summary = {
        "duration_ms": duration_ms,
        "duration_seconds": round(duration_ms / 1000, 1),
        "scenario_count": len(scenarios),
        "order_count": len(orders),
        "event_count": len(events),
        "issue_counts": dict(issue_counts),
        "order_final_statuses": dict(order_statuses),
        "http": {
            "count": len(http_events),
            "status_groups": dict(status_groups),
            "latency_ms": _latency_summary(latencies),
            "endpoints": endpoint_stats,
            "slowest": slowest,
        },
        "websockets": {
            "expected": len(expected_ws),
            "matched": len(matched_ws),
            "missing": len(expected_ws) - len(matched_ws),
            "match_rate": round(len(matched_ws) / len(expected_ws), 3)
            if expected_ws
            else 1.0,
        },
        "scenarios": scenarios,
    }
    summary["verdict"] = _verdict(
        issue_counts=issue_counts,
        scenarios=scenarios,
        websocket_expected=summary["websockets"]["expected"],
        websocket_matched=summary["websockets"]["matched"],
    )
    return summary
