from __future__ import annotations

import hashlib
import hmac
import sys
from typing import Any

from . import webhook_projects_store as store


def _main_global_dict(name: str) -> dict[str, Any]:
    module = sys.modules.get("api.app.main")
    value = getattr(module, name, {}) if module is not None else {}
    return value if isinstance(value, dict) else {}


def _normalize_secret_map(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(project).strip().lower(): str(secret).strip()
        for project, secret in payload.items()
        if str(project).strip() and str(secret).strip()
    }


def _normalize_allowlist_map(payload: dict[str, Any]) -> dict[str, list[str]]:
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


def project_secrets() -> dict[str, str]:
    merged = dict(store.project_secrets_map())
    merged.update(_normalize_secret_map(_main_global_dict("SIMULATOR_WEBHOOK_PROJECT_SECRETS")))
    return merged


def repo_allowlist() -> dict[str, list[str]]:
    merged = dict(store.repo_allowlist_map())
    merged.update(_normalize_allowlist_map(_main_global_dict("SIMULATOR_WEBHOOK_REPO_ALLOWLIST")))
    return merged


def match_project_for_repository(repository: str) -> str | None:
    repo = repository.strip().lower()
    allowlist = repo_allowlist()
    for project, repos in allowlist.items():
        normalized_repos = {str(item).strip().lower() for item in repos if str(item).strip()}
        if repo in normalized_repos:
            return str(project).strip().lower()
    return None


def verify_github_signature(project: str, body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    project_key = str(project).strip().lower()
    secret = str(project_secrets().get(project_key, "")).strip()
    if not secret:
        return False

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(digest, provided)


def resolve_project_from_signature(body: bytes, signature_header: str) -> str | None:
    signature = str(signature_header or "").strip()
    if not signature.startswith("sha256="):
        return None

    for project, secret in project_secrets().items():
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(signature, expected):
            return project
    return None
