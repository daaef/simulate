from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from typing import Any

from .models import (
    IntegrationMappingUpsertRequest,
    IntegrationWebhookProjectCreateRequest,
    IntegrationWebhookProjectRepositoriesRequest,
)
from . import project_secrets as project_secrets_store

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Integrations runtime callback {name!r} has not been configured")
    return callback


def list_mappings(include_archived: bool = False) -> dict[str, Any]:
    return _callback("list_mappings")(include_archived)


def upsert_mapping(request: IntegrationMappingUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("upsert_mapping")(request, user_id)


def delete_mapping(mapping_id: int) -> dict[str, Any]:
    return _callback("delete_mapping")(mapping_id)


def restore_mapping(mapping_id: int) -> dict[str, Any]:
    return _callback("restore_mapping")(mapping_id)


def list_triggers(limit: int, offset: int) -> dict[str, Any]:
    return _callback("list_triggers")(limit, offset)


def process_github_deployment_webhook(
    body: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    return _callback("process_github_deployment_webhook")(body, headers)


def _webhook_endpoint_url() -> str:
    base = os.getenv("SIMULATOR_EXTERNAL_BASE_URL", "").strip().rstrip("/")
    if not base:
        return "/api/v1/integrations/github/deployment-complete"
    return f"{base}/api/v1/integrations/github/deployment-complete"


def _attach_webhook_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    payload["webhook_url"] = _webhook_endpoint_url()
    return payload


def list_webhook_projects(include_archived: bool = False) -> dict[str, Any]:
    return _attach_webhook_metadata(project_secrets_store.list_projects(include_archived=include_archived))


def create_webhook_project(
    request: IntegrationWebhookProjectCreateRequest,
    user_id: int | None,
) -> dict[str, Any]:
    try:
        created = project_secrets_store.create_project(
            project=request.project,
            repositories=request.repositories,
            user_id=user_id,
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("project_already_exists") from exc
    except Exception as exc:
        if exc.__class__.__name__ == "UniqueViolation":
            raise ValueError("project_already_exists") from exc
        raise
    return _attach_webhook_metadata(created)


def rotate_webhook_project_secret(project: str, user_id: int | None) -> dict[str, Any]:
    return _attach_webhook_metadata(
        project_secrets_store.rotate_project_secret(project, user_id=user_id)
    )


def update_webhook_project_repositories(
    project: str,
    request: IntegrationWebhookProjectRepositoriesRequest,
) -> dict[str, Any]:
    return _attach_webhook_metadata(
        project_secrets_store.update_project_repositories(project, request.repositories)
    )


def archive_webhook_project(project: str) -> dict[str, Any]:
    return project_secrets_store.archive_project(project)
