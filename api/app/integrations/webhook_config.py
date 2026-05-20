from __future__ import annotations

import json
import os
from typing import Any

from . import project_secrets as project_secrets_store


def _json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _normalize_secret_map(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(project).strip().lower(): str(secret).strip()
        for project, secret in payload.items()
        if str(project).strip() and str(secret).strip()
    }


def _normalize_allowlist(payload: Any) -> dict[str, list[str]]:
    if isinstance(payload, list):
        return {"default": [str(item).strip() for item in payload if str(item).strip()]}

    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for project, repos in payload.items():
        project_key = str(project).strip().lower()
        if not project_key:
            continue
        if isinstance(repos, list):
            values = [str(repo).strip() for repo in repos if str(repo).strip()]
        elif isinstance(repos, str) and repos.strip():
            values = [repos.strip()]
        else:
            values = []
        if values:
            normalized[project_key] = values
    return normalized


def env_project_secrets() -> dict[str, str]:
    payload = _json_env("SIMULATOR_WEBHOOK_PROJECT_SECRETS", {})
    return _normalize_secret_map(payload)


def env_repo_allowlist() -> dict[str, list[str]]:
    payload = _json_env("SIMULATOR_WEBHOOK_REPO_ALLOWLIST", {})
    return _normalize_allowlist(payload)


def merged_project_secrets() -> dict[str, str]:
    merged = dict(env_project_secrets())
    merged.update(project_secrets_store.active_secrets_by_project())
    return merged


def merged_repo_allowlist() -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in env_repo_allowlist().items()}
    for project, repos in project_secrets_store.active_repositories_by_project().items():
        existing = merged.get(project, [])
        combined = list(dict.fromkeys([*existing, *repos]))
        merged[project] = combined
    return merged


def match_project_for_repository(repository: str) -> str | None:
    repo = repository.strip().lower()
    allowlist = merged_repo_allowlist()
    for project, repos in allowlist.items():
        normalized_repos = {str(item).strip().lower() for item in repos if str(item).strip()}
        if repo in normalized_repos:
            return str(project).strip().lower()
    return None


def verify_github_signature(project: str, body: bytes, signature_header: str | None) -> bool:
    import hashlib
    import hmac

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    project_key = str(project).strip().lower()
    secret = str(merged_project_secrets().get(project_key, "")).strip()
    if not secret:
        return False

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(digest, provided)


def resolve_project_from_signature(body: bytes, signature_header: str) -> str | None:
    import hashlib
    import hmac

    signature = str(signature_header or "").strip()
    if not signature.startswith("sha256="):
        return None

    for project, secret in merged_project_secrets().items():
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(signature, expected):
            return project
    return None
