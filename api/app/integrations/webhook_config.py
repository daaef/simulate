from __future__ import annotations

import hashlib
import hmac
from typing import Any

from . import webhook_projects_store as store


def project_secrets() -> dict[str, str]:
    return store.project_secrets_map()


def repo_allowlist() -> dict[str, list[str]]:
    return store.repo_allowlist_map()


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
