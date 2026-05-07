from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from ..auth.policies import require_permission
from .models import RunCreateRequest, RunProfileUpsertRequest
from . import service

router = APIRouter(tags=["runs"])


@router.get("/api/v1/flows")
def list_flows(current_user: dict = Depends(require_permission("dashboard", "read"))) -> dict[str, Any]:
    return service.list_flows()


@router.get("/api/v1/runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_permission("runs", "read")),
) -> dict[str, Any]:
    return service.list_runs(limit, offset)


@router.get("/api/v1/runs/count")
def count_runs(current_user: dict = Depends(require_permission("runs", "read"))) -> dict[str, Any]:
    return service.count_runs()


@router.get("/api/v1/dashboard/summary")
def dashboard_summary(current_user: dict = Depends(require_permission("dashboard", "read"))) -> dict[str, Any]:
    return service.dashboard_summary()


@router.post("/api/v1/runs")
def create_run(
    request: RunCreateRequest,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.create_run(request, current_user.get("id"))


@router.get("/api/v1/runs/{run_id}")
def get_run(run_id: int, current_user: dict = Depends(require_permission("runs", "read"))) -> dict[str, Any]:
    return service.get_run(run_id)


@router.get("/api/v1/runs/{run_id}/log")
def get_run_log(
    run_id: int,
    tail: int = Query(default=200, ge=1, le=5000),
    current_user: dict = Depends(require_permission("runs", "read")),
) -> dict[str, Any]:
    return service.get_run_log(run_id, tail)


@router.get("/api/v1/runs/{run_id}/artifacts/{kind}")
def get_run_artifact(
    run_id: int,
    kind: Literal["report", "story", "events"],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
    compact: bool = Query(default=True),
    current_user: dict = Depends(require_permission("runs", "read")),
) -> dict[str, Any]:
    return service.get_run_artifact(run_id, kind, offset, limit, compact)


@router.get("/api/v1/runs/{run_id}/metrics")
def get_run_metrics(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "read")),
) -> dict[str, Any]:
    return service.get_run_metrics(run_id)


@router.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "cancel")),
) -> dict[str, Any]:
    return service.cancel_run(run_id)


@router.delete("/api/v1/runs/{run_id}")
def delete_run(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.delete_run(run_id)


@router.get("/api/v1/run-profiles")
def list_profiles(current_user: dict = Depends(require_permission("runs", "read"))) -> dict[str, Any]:
    return service.list_profiles()


@router.post("/api/v1/run-profiles")
def create_profile(
    request: RunProfileUpsertRequest,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.create_profile(request, current_user.get("id"))


@router.put("/api/v1/run-profiles/{profile_id}")
def update_profile(
    profile_id: int,
    request: RunProfileUpsertRequest,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.update_profile(profile_id, request, current_user.get("id"))


@router.delete("/api/v1/run-profiles/{profile_id}")
def delete_profile(
    profile_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.delete_profile(profile_id)


@router.post("/api/v1/run-profiles/{profile_id}/launch")
def launch_profile(
    profile_id: int,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.launch_profile(profile_id, current_user.get("id"))


@router.get("/api/v1/runs/{run_id}/execution-snapshot")
def get_execution_snapshot(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "read")),
) -> dict[str, Any]:
    return service.get_execution_snapshot(run_id)


@router.post("/api/v1/runs/{run_id}/replay")
def replay_run(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "create")),
) -> dict[str, Any]:
    return service.replay_run(run_id, current_user.get("id"))
