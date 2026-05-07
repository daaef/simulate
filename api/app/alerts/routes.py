from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["alerts"])


@router.get("/api/v1/alerts")
def list_alerts(current_user: dict = Depends(require_permission("alerts", "read"))) -> dict[str, Any]:
    return service.list_alerts()
