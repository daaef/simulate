from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from .models import TimezonePolicyUpdateRequest
from . import service

router = APIRouter(tags=["system"])


@router.get("/api/v1/system/timezones")
def get_timezones_policy(current_user: dict = Depends(require_permission("system", "read"))) -> dict[str, Any]:
    return service.get_timezones_policy()


@router.put("/api/v1/system/timezones")
def set_timezones_policy(
    request: TimezonePolicyUpdateRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.set_timezones_policy(request)

