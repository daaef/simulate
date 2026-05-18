from __future__ import annotations

import os
from typing import Any


def _webhook_route_by() -> str:
    return os.getenv("SIMULATOR_WEBHOOK_ROUTE_BY", "environment").strip().lower()


def _workflow_fallback() -> str:
    return (
        os.getenv("SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT")
        or os.getenv("SIM_ENV")
        or "production"
    ).strip()


def route_by_branch() -> bool:
    return _webhook_route_by() in {"branch", "branches", "ref", "refs"}


def webhook_routing_mode() -> str:
    return "branch" if route_by_branch() else "environment"


def normalize_route_key(value: str) -> str:
    raw = value.strip()
    if raw.startswith("refs/heads/"):
        raw = raw[len("refs/heads/") :]
    elif raw.startswith("refs/tags/"):
        raw = raw[len("refs/tags/") :]
    return raw.lower()


def route_key_from_workflow_run(workflow_run: dict[str, Any]) -> str:
    if route_by_branch():
        branch = normalize_route_key(str(workflow_run.get("head_branch") or ""))
        if branch:
            return branch
    fallback = normalize_route_key(_workflow_fallback())
    return fallback or "production"


def route_key_from_deployment(deployment: dict[str, Any]) -> str:
    if route_by_branch():
        ref = normalize_route_key(str(deployment.get("ref") or ""))
        if ref:
            return ref
    return normalize_route_key(str(deployment.get("environment") or ""))
