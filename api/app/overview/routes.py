from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["overview"])


@router.get("/api/v1/overview/latest-run")
def latest_run_overview(
    current_user: dict = Depends(require_permission("dashboard", "read")),
) -> dict[str, Any]:
    return service.latest_run_overview()


@router.get("/api/v1/overview/runs/{run_id}")
def run_overview(
    run_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_permission("dashboard", "read")),
) -> dict[str, Any]:
    return service.run_overview(run_id)
