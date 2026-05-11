from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import IntegrationMappingUpsertRequest

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Integrations runtime callback {name!r} has not been configured")
    return callback


def list_mappings() -> dict[str, Any]:
    return _callback("list_mappings")()


def upsert_mapping(request: IntegrationMappingUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("upsert_mapping")(request, user_id)


def delete_mapping(mapping_id: int) -> dict[str, Any]:
    return _callback("delete_mapping")(mapping_id)


def list_triggers(limit: int, offset: int) -> dict[str, Any]:
    return _callback("list_triggers")(limit, offset)


def process_github_deployment_webhook(
    body: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    return _callback("process_github_deployment_webhook")(body, headers)

