from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["retention"])


@router.get("/api/v1/retention/summary")
def retention_summary(current_user: dict = Depends(require_permission("retention", "read"))) -> dict[str, Any]:
    return service.summary()
