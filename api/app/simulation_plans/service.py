from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import SimulationPlanUpsertRequest

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Simulation plans runtime callback {name!r} has not been configured")
    return callback


def list_plans() -> dict[str, Any]:
    return _callback("list_plans")()


def get_plan(plan_id: str) -> dict[str, Any]:
    return _callback("get_plan")(plan_id)


def create_plan(request: SimulationPlanUpsertRequest) -> dict[str, Any]:
    return _callback("create_plan")(request)


def update_plan(plan_id: str, request: SimulationPlanUpsertRequest) -> dict[str, Any]:
    return _callback("update_plan")(plan_id, request)


def delete_plan(plan_id: str) -> dict[str, Any]:
    return _callback("delete_plan")(plan_id)
