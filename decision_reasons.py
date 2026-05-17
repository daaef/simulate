"""Shared decision reason classification helpers."""

from __future__ import annotations

from typing import Any


INFORMATIONAL_DECISION_REASON_CODES = frozenset(
    {
        "unsupported_profile_fetch_contract",
        "no_customer_id",
        "missing_auth_token",
    }
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def is_informational_decision_reason(*, status: Any, reason_code: Any) -> bool:
    """Return True for expected non-failure decision outcomes."""
    decision_status = _as_text(status)
    reason = _as_text(reason_code)

    if decision_status not in {"skipped", "recovered"}:
        return False
    if reason.startswith("missing_"):
        return True
    return reason in INFORMATIONAL_DECISION_REASON_CODES

