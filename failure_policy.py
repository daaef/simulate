"""Failure policy and preflight classification helpers."""

from __future__ import annotations

from typing import Any, Literal


FailurePolicy = Literal["api_only", "strict"]
PreflightStrategy = Literal["auto_recover", "skip_warn", "hard_stop"]
FailureClass = Literal["api_fault", "precondition"]

VALID_FAILURE_POLICIES = {"api_only", "strict"}
VALID_PREFLIGHT_STRATEGIES = {"auto_recover", "skip_warn", "hard_stop"}


def normalise_failure_policy(value: str | None) -> FailurePolicy:
    candidate = str(value or "").strip().lower()
    if candidate in VALID_FAILURE_POLICIES:
        return candidate  # type: ignore[return-value]
    return "api_only"


def normalise_preflight_strategy(value: str | None) -> PreflightStrategy:
    candidate = str(value or "").strip().lower()
    if candidate in VALID_PREFLIGHT_STRATEGIES:
        return candidate  # type: ignore[return-value]
    return "auto_recover"


def is_api_only(policy: str | None) -> bool:
    return normalise_failure_policy(policy) == "api_only"


def is_hard_stop(strategy: str | None) -> bool:
    return normalise_preflight_strategy(strategy) == "hard_stop"


def classify_http_status(status_code: int | None) -> FailureClass:
    if status_code is None:
        return "precondition"
    if status_code >= 500:
        return "api_fault"
    if status_code >= 400:
        return "precondition"
    return "precondition"


def classify_transport_error(message: str) -> FailureClass:
    text = (message or "").strip().lower()
    api_fault_markers = (
        "timed out",
        "timeout",
        "connection",
        "name or service not known",
        "temporary failure in name resolution",
        "network is unreachable",
        "service unavailable",
        "bad gateway",
        "gateway",
        "websocket",
    )
    if any(marker in text for marker in api_fault_markers):
        return "api_fault"
    return "precondition"


def classify_issue(
    *,
    code: str | None,
    message: str | None,
    details: dict[str, Any] | None = None,
    default: FailureClass = "precondition",
) -> FailureClass:
    if isinstance(details, dict):
        try:
            http_status = details.get("http_status") or details.get("status_code")
            if http_status is not None:
                return classify_http_status(int(http_status))
        except (TypeError, ValueError):
            pass
    combined = f"{str(code or '').lower()} {str(message or '').lower()}"
    if any(
        marker in combined
        for marker in (
            "timeout",
            "timed out",
            "connection",
            "gateway",
            "server_error",
            "service unavailable",
            "websocket_connection",
            "http_error",
            "probe_http_server_error",
        )
    ):
        return "api_fault"
    return default
