from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import TimezonePolicyUpdateRequest

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

