from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import EmailSettingsUpdateRequest, RetentionPolicyUpdateRequest, TimezonePolicyUpdateRequest

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"System runtime callback {name!r} has not been configured")
    return callback


def get_timezones_policy() -> dict[str, Any]:
    return _callback("get_timezones_policy")()


def set_timezones_policy(request: TimezonePolicyUpdateRequest) -> dict[str, Any]:
    return _callback("set_timezones_policy")(request)


def get_email_settings() -> dict[str, Any]:
    return _callback("get_email_settings")()


def set_email_settings(request: EmailSettingsUpdateRequest) -> dict[str, Any]:
    return _callback("set_email_settings")(request)


def send_test_email() -> dict[str, Any]:
    return _callback("send_test_email")()


def get_retention_policy() -> dict[str, Any]:
    return _callback("get_retention_policy")()


def set_retention_policy(request: RetentionPolicyUpdateRequest) -> dict[str, Any]:
    return _callback("set_retention_policy")(request.active_days, request.archive_days)
