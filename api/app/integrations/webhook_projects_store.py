from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FILE_LOCK = threading.Lock()
DEFAULT_FILE = "/workspace/simulate/data/webhook-projects.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _projects_file() -> Path:
    raw = os.getenv("SIMULATOR_WEBHOOK_PROJECTS_FILE", "").strip()
    if not raw:
        project_dir = os.getenv("SIMULATOR_PROJECT_DIR", "").strip()
        raw = str(Path(project_dir) / "data" / "webhook-projects.json") if project_dir else DEFAULT_FILE
    return Path(raw)


def _normalize_project(project: str) -> str:
    normalized = str(project or "").strip().lower()
    if not normalized:
        raise ValueError("project is required")
    if len(normalized) > 120:
        raise ValueError("project must be 120 characters or fewer")
    return normalized


def _normalize_repositories(repositories: list[str] | None) -> list[str]:
    if not repositories:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for repo in repositories:
        value = str(repo or "").strip()
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        normalized.append(value)
    return normalized


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


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_raw_unlocked() -> dict[str, Any]:
    path = _projects_file()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _bootstrap_from_env_if_empty(data: dict[str, Any]) -> dict[str, Any]:
    if data:
        return data
    secrets_map = _normalize_secret_map(_json_env("SIMULATOR_WEBHOOK_PROJECT_SECRETS", {}))
    allowlist = _normalize_allowlist(_json_env("SIMULATOR_WEBHOOK_REPO_ALLOWLIST", {}))
    if not secrets_map and not allowlist:
        return {}
    now = _utc_now()
    bootstrapped: dict[str, Any] = {}
    projects = set(secrets_map.keys()) | set(allowlist.keys())
    for project in projects:
        bootstrapped[project] = {
            "secret": secrets_map.get(project, ""),
            "repositories": allowlist.get(project, []),
            "created_at": now,
            "updated_at": now,
        }
    if os.getenv("SIMULATOR_WEBHOOK_PROJECTS_FILE", "").strip():
        path = _projects_file()
        _ensure_parent_dir(path)
        path.write_text(json.dumps(bootstrapped, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return bootstrapped


def _read_all() -> dict[str, Any]:
    with FILE_LOCK:
        data = _read_raw_unlocked()
        if not data:
            data = _bootstrap_from_env_if_empty(data)
        return data


def _write_all(data: dict[str, Any]) -> None:
    path = _projects_file()
    _ensure_parent_dir(path)
    with FILE_LOCK:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


def _secret_hint(plaintext: str) -> str:
    if len(plaintext) <= 4:
        return "****"
    return f"…{plaintext[-4:]}"


def _entry_to_public(project: str, entry: dict[str, Any], *, include_secret: bool = False) -> dict[str, Any]:
    repositories = entry.get("repositories") or []
    if not isinstance(repositories, list):
        repositories = []
    payload = {
        "project": project,
        "secret_hint": _secret_hint(str(entry.get("secret") or "")),
        "repositories": [str(item) for item in repositories if str(item).strip()],
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "source": "file",
    }
    if include_secret:
        payload["secret"] = str(entry.get("secret") or "")
        payload["secret_display_once"] = True
    return payload


def list_projects() -> list[dict[str, Any]]:
    data = _read_all()
    return [_entry_to_public(project, entry) for project, entry in sorted(data.items())]


def export_github_payloads() -> tuple[dict[str, str], dict[str, list[str]]]:
    data = _read_all()
    secrets_map: dict[str, str] = {}
    allowlist_map: dict[str, list[str]] = {}
    for project, entry in data.items():
        if not isinstance(entry, dict):
            continue
        secret = str(entry.get("secret") or "").strip()
        repos = entry.get("repositories") or []
        if secret:
            secrets_map[project] = secret
        if isinstance(repos, list) and repos:
            allowlist_map[project] = [str(item) for item in repos if str(item).strip()]
    return secrets_map, allowlist_map


def project_secrets_map() -> dict[str, str]:
    secrets_map, _ = export_github_payloads()
    return secrets_map


def repo_allowlist_map() -> dict[str, list[str]]:
    _, allowlist_map = export_github_payloads()
    return allowlist_map


def get_project(project: str) -> dict[str, Any] | None:
    project_key = _normalize_project(project)
    data = _read_all()
    entry = data.get(project_key)
    if not isinstance(entry, dict):
        return None
    return _entry_to_public(project_key, entry)


def create_project(
    *,
    project: str,
    repositories: list[str] | None,
    secret: str | None = None,
) -> dict[str, Any]:
    project_key = _normalize_project(project)
    data = _read_all()
    if project_key in data:
        raise ValueError("project_already_exists")

    now = _utc_now()
    plaintext = str(secret or "").strip() or generate_webhook_secret()
    data[project_key] = {
        "secret": plaintext,
        "repositories": _normalize_repositories(repositories),
        "created_at": now,
        "updated_at": now,
    }
    _write_all(data)
    return {"project": _entry_to_public(project_key, data[project_key], include_secret=True)}


def rotate_project_secret(project: str) -> dict[str, Any]:
    project_key = _normalize_project(project)
    data = _read_all()
    entry = data.get(project_key)
    if not isinstance(entry, dict):
        raise KeyError(f"project {project_key!r} not found")

    plaintext = generate_webhook_secret()
    entry["secret"] = plaintext
    entry["updated_at"] = _utc_now()
    data[project_key] = entry
    _write_all(data)
    return {"project": _entry_to_public(project_key, entry, include_secret=True)}


def update_project_repositories(project: str, repositories: list[str]) -> dict[str, Any]:
    project_key = _normalize_project(project)
    data = _read_all()
    entry = data.get(project_key)
    if not isinstance(entry, dict):
        raise KeyError(f"project {project_key!r} not found")

    entry["repositories"] = _normalize_repositories(repositories)
    entry["updated_at"] = _utc_now()
    data[project_key] = entry
    _write_all(data)
    return {"project": _entry_to_public(project_key, entry)}


def delete_project(project: str) -> dict[str, Any]:
    project_key = _normalize_project(project)
    data = _read_all()
    entry = data.pop(project_key, None)
    if not isinstance(entry, dict):
        raise KeyError(f"project {project_key!r} not found")
    _write_all(data)
    return {"project": _entry_to_public(project_key, entry), "deleted": True}
