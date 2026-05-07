from __future__ import annotations

from collections.abc import Callable
from typing import Any

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Alerts runtime callback {name!r} has not been configured")
    return callback


def list_alerts() -> dict[str, Any]:
    return _callback("list_alerts")()
