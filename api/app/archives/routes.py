from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["archives"])


@router.get("/api/v1/archives/summary")
def archives_summary(current_user: dict = Depends(require_permission("archives", "read"))) -> dict[str, Any]:
    return service.summary()


@router.get("/api/v1/archives/runs")
def list_archive_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_permission("archives", "read")),
) -> dict[str, Any]:
    return service.list_runs(limit, offset)
