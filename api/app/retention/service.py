from __future__ import annotations

from collections.abc import Callable
from typing import Any

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Retention runtime callback {name!r} has not been configured")
    return callback


def summary() -> dict[str, Any]:
    return _callback("summary")()
