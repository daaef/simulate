"""Shared event failure classification for metrics and findings."""

from __future__ import annotations

from typing import Any


def is_metric_failed_event(event: dict[str, Any]) -> bool:
    """Return True when an event counts toward the failed_events run metric."""
    status = str(event.get("status") or "").strip().lower()
    category = str(event.get("category") or "").strip().lower()
    http_status = event.get("http_status") or event.get("status_code")
    http_status_code: int | None = None
    try:
        if http_status is not None:
            http_status_code = int(http_status)
    except (TypeError, ValueError):
        http_status_code = None

    if category == "decision":
        return status in {"failed", "error", "blocked"}

    if http_status_code is not None:
        return http_status_code >= 500

    ok_flag = event.get("ok")
    if isinstance(ok_flag, bool):
        return not ok_flag
    return status in {"error", "failed", "failure"}
