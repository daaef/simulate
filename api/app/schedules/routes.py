from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..auth.policies import require_permission
from .models import ScheduleUpsertRequest
from . import service

router = APIRouter(tags=["schedules"])


@router.get("/api/v1/schedules")
def list_schedules(
    include_deleted: bool = Query(default=False),
    current_user: dict = Depends(require_permission("schedules", "read")),
) -> dict[str, Any]:
    return service.list_schedules(include_deleted)


@router.get("/api/v1/schedules/summary")
def schedule_summary(current_user: dict = Depends(require_permission("schedules", "read"))) -> dict[str, Any]:
    return service.summary()


@router.post("/api/v1/schedules")
def create_schedule(
    request: ScheduleUpsertRequest,
    current_user: dict = Depends(require_permission("schedules", "create")),
) -> dict[str, Any]:
    return service.create_schedule(request, current_user.get("id"))


@router.put("/api/v1/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    request: ScheduleUpsertRequest,
    current_user: dict = Depends(require_permission("schedules", "update")),
) -> dict[str, Any]:
    return service.update_schedule(schedule_id, request, current_user.get("id"))


@router.post("/api/v1/schedules/{schedule_id}/trigger")
def trigger_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "trigger")),
) -> dict[str, Any]:
    return service.trigger_schedule(schedule_id, current_user.get("id"))


@router.post("/api/v1/schedules/{schedule_id}/pause")
def pause_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "update")),
) -> dict[str, Any]:
    return service.set_status(schedule_id, "paused")


@router.post("/api/v1/schedules/{schedule_id}/resume")
def resume_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "update")),
) -> dict[str, Any]:
    return service.set_status(schedule_id, "active")


@router.post("/api/v1/schedules/{schedule_id}/disable")
def disable_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "update")),
) -> dict[str, Any]:
    return service.set_status(schedule_id, "disabled")


@router.post("/api/v1/schedules/{schedule_id}/delete")
def soft_delete_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "delete")),
) -> dict[str, Any]:
    return service.set_status(schedule_id, "deleted")


@router.post("/api/v1/schedules/{schedule_id}/restore")
def restore_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("schedules", "update")),
) -> dict[str, Any]:
    return service.set_status(schedule_id, "active")
