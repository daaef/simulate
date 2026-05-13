from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from .models import EmailSettingsUpdateRequest, TimezonePolicyUpdateRequest
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


@router.get("/api/v1/system/email")
def get_email_settings(current_user: dict = Depends(require_permission("system", "read"))) -> dict[str, Any]:
    return service.get_email_settings()


@router.put("/api/v1/system/email")
def set_email_settings(
    request: EmailSettingsUpdateRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.set_email_settings(request)


@router.post("/api/v1/system/email/test")
def send_test_email(current_user: dict = Depends(require_permission("system", "configure"))) -> dict[str, Any]:
    return service.send_test_email()
