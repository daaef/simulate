from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth.policies import require_permission
from .models import SimulationPlanUpsertRequest
from . import service

router = APIRouter(prefix="/api/v1/simulation-plans", tags=["simulation-plans"])


@router.get("")
def list_plans(current_user: dict = Depends(require_permission("runs", "create"))) -> dict[str, Any]:
    return service.list_plans()


@router.get("/{plan_id}")
def get_plan(
    plan_id: str,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.get_plan(plan_id)


@router.post("")
def create_plan(
    request: SimulationPlanUpsertRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.create_plan(request)


@router.put("/{plan_id}")
def update_plan(
    plan_id: str,
    request: SimulationPlanUpsertRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.update_plan(plan_id, request)


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: str,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.delete_plan(plan_id)
