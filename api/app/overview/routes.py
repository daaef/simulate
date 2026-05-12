from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["overview"])


@router.get("/api/v1/overview/latest-run")
def latest_run_overview(
    current_user: dict = Depends(require_permission("dashboard", "read")),
) -> dict[str, Any]:
    return service.latest_run_overview()