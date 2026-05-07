from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import ScheduleUpsertRequest

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Schedules runtime callback {name!r} has not been configured")
    return callback


def list_schedules(include_deleted: bool) -> dict[str, Any]:
    return _callback("list_schedules")(include_deleted)


def summary() -> dict[str, Any]:
    return _callback("summary")()


def create_schedule(request: ScheduleUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("create_schedule")(request, user_id)


def update_schedule(schedule_id: int, request: ScheduleUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("update_schedule")(schedule_id, request, user_id)


def set_status(schedule_id: int, status: str) -> dict[str, Any]:
    return _callback("set_status")(schedule_id, status)


def trigger_schedule(schedule_id: int, user_id: int | None) -> dict[str, Any]:
    return _callback("trigger_schedule")(schedule_id, user_id)
