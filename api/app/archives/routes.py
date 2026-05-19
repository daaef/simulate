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


@router.get("/api/v1/archives/profiles")
def list_archived_profiles(current_user: dict = Depends(require_permission("archives", "read"))) -> dict[str, Any]:
    return service.list_profiles()


@router.get("/api/v1/archives/schedules")
def list_archived_schedules(current_user: dict = Depends(require_permission("archives", "read"))) -> dict[str, Any]:
    return service.list_schedules()


@router.get("/api/v1/archives/integration-mappings")
def list_archived_integration_mappings(current_user: dict = Depends(require_permission("archives", "read"))) -> dict[str, Any]:
    return service.list_integration_mappings()


@router.post("/api/v1/archives/runs/{run_id}/purge")
def purge_run(
    run_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.purge_run(run_id)


@router.post("/api/v1/archives/profiles/{profile_id}/purge")
def purge_profile(
    profile_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.purge_profile(profile_id)


@router.post("/api/v1/archives/schedules/{schedule_id}/purge")
def purge_schedule(
    schedule_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.purge_schedule(schedule_id)


@router.post("/api/v1/archives/integration-mappings/{mapping_id}/purge")
def purge_integration_mapping(
    mapping_id: int,
    current_user: dict = Depends(require_permission("runs", "delete")),
) -> dict[str, Any]:
    return service.purge_integration_mapping(mapping_id)
