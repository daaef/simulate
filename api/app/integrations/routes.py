from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.policies import require_permission
from .models import (
    IntegrationMappingUpsertRequest,
    IntegrationWebhookProjectCreateRequest,
    IntegrationWebhookProjectRepositoriesRequest,
)
from . import service
from .github_workflow_run import (
    automation_enabled,
    process_github_workflow_run_webhook,
    record_automation_disabled_trigger,
)
from .webhook_config import resolve_project_from_signature

router = APIRouter(tags=["integrations"])


def _best_effort_repository(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unknown"
    repository = payload.get("repository") if isinstance(payload, dict) else None
    if isinstance(repository, dict):
        return str(repository.get("full_name") or "unknown")
    return "unknown"


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

    # Global master switch, checked before any event-specific dispatch or parsing so it
    # cannot be bypassed by a new event type or a future handler that forgets to check it.
    if not automation_enabled():
        signature = headers.get("x-hub-signature-256", "").strip()
        project = resolve_project_from_signature(body, signature) or "unknown"
        repository = _best_effort_repository(body)
        trigger_id = record_automation_disabled_trigger(
            project=project,
            event_name=github_event or "unknown",
            repository=repository,
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "automation_disabled",
            "project": project,
            "repository": repository,
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
def list_mappings(
    include_archived: bool = False,
    current_user: dict = Depends(require_permission("system", "read")),
) -> dict[str, Any]:
    return service.list_mappings(include_archived)


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


@router.post("/api/v1/integrations/github/mappings/{mapping_id}/restore")
def restore_mapping(
    mapping_id: int,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    return service.restore_mapping(mapping_id)


@router.get("/api/v1/integrations/github/triggers")
def list_triggers(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(require_permission("system", "read")),
) -> dict[str, Any]:
    return service.list_triggers(limit, offset)


@router.get("/api/v1/integrations/github/projects")
def list_webhook_projects(
    current_user: dict = Depends(require_permission("system", "read")),
) -> dict[str, Any]:
    return service.list_webhook_projects()


@router.post("/api/v1/integrations/github/projects")
def create_webhook_project(
    request: IntegrationWebhookProjectCreateRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    try:
        return service.create_webhook_project(request, current_user.get("id"))
    except ValueError as exc:
        if str(exc) == "project_already_exists":
            raise HTTPException(status_code=409, detail="A webhook project with this name already exists.") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/integrations/github/projects/{project}/rotate-secret")
def rotate_webhook_project_secret(
    project: str,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    try:
        return service.rotate_webhook_project_secret(project, current_user.get("id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Webhook project not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/api/v1/integrations/github/projects/{project}/repositories")
def update_webhook_project_repositories(
    project: str,
    request: IntegrationWebhookProjectRepositoriesRequest,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    try:
        return service.update_webhook_project_repositories(project, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Webhook project not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/v1/integrations/github/projects/{project}")
def delete_webhook_project(
    project: str,
    current_user: dict = Depends(require_permission("system", "configure")),
) -> dict[str, Any]:
    try:
        return service.delete_webhook_project(project)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Webhook project not found.") from exc
