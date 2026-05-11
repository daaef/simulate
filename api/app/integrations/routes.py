from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ..auth.policies import require_permission
from .models import IntegrationMappingUpsertRequest
from . import service
from .github_workflow_run import process_github_workflow_run_webhook

router = APIRouter(tags=["integrations"])


@router.post("/api/v1/integrations/github/deployment-complete")
async def github_deployment_complete(request: Request) -> dict[str, Any]:
    body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    github_event = headers.get("x-github-event", "")

    if github_event == "ping":
        return {
            "ok": True,
            "event": "ping",
            "message": "GitHub webhook ping received.",
        }

    if github_event == "workflow_run":
        return process_github_workflow_run_webhook(body, headers)

    if github_event in {"deployment_status", "deployment"}:
        return service.process_github_deployment_webhook(body, headers)

    return {
        "ok": True,
        "event": github_event,
        "ignored": True,
        "reason": "unsupported_github_event",
    }


@router.get("/api/v1/integrations/github/mappings")
def list_mappings(current_user: dict = Depends(require_permission("system", "read"))) -> dict[str, Any]:
    return service.list_mappings()


@router.post("/api/v1/integrations/github/mappings")
def upsert_mapping(
    request: IntegrationMappingUpsertRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.upsert_mapping(request, current_user.get("id"))


@router.delete("/api/v1/integrations/github/mappings/{mapping_id}")
def delete_mapping(
    mapping_id: int,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.delete_mapping(mapping_id)


@router.get("/api/v1/integrations/github/triggers")
def list_triggers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_permission("system", "read")),
) -> dict[str, Any]:
    return service.list_triggers(limit, offset)