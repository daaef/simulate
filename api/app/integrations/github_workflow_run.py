from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ..runs import service as runs_service


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

DB_PATH = os.getenv("RUN_DB_PATH", "/workspace/simulate/runs/web-gui.sqlite")
DEFAULT_WORKFLOW_ENVIRONMENT = (
    os.getenv("SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT")
    or os.getenv("SIM_ENV")
    or "production"
).strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _github_project_secrets() -> dict[str, str]:
    payload = _json_env("SIMULATOR_WEBHOOK_PROJECT_SECRETS", {})
    if not isinstance(payload, dict):
        return {}

    return {
        str(project): str(secret)
        for project, secret in payload.items()
        if str(project).strip() and str(secret).strip()
    }


def _github_repo_allowlist() -> dict[str, list[str]]:
    payload = _json_env("SIMULATOR_WEBHOOK_REPO_ALLOWLIST", {})
    if isinstance(payload, list):
        return {"default": [str(item) for item in payload]}

    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for project, repos in payload.items():
        if isinstance(repos, list):
            normalized[str(project)] = [str(repo) for repo in repos if str(repo).strip()]
        elif isinstance(repos, str) and repos.strip():
            normalized[str(project)] = [repos.strip()]

    return normalized


@contextmanager
def _db_connection() -> Iterator[Any]:
    if USE_POSTGRES:
        import psycopg2
        from psycopg2.extras import DictCursor

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dict_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _verify_signature_project(body: bytes, headers: dict[str, str]) -> str | None:
    signature = headers.get("x-hub-signature-256", "").strip()
    if not signature.startswith("sha256="):
        return None

    secrets = _github_project_secrets()
    for project, secret in secrets.items():
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(signature, expected):
            return project

    return None


def _repo_allowed_for_project(project: str, repository: str) -> bool:
    allowlist = _github_repo_allowlist()
    allowed = allowlist.get(project) or allowlist.get("default") or []

    repository_lower = repository.lower()
    return any(repository_lower == item.lower() for item in allowed)


def _workflow_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_run = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}

    return {
        "action": payload.get("action"),
        "repository": repository.get("full_name"),
        "workflow": workflow_run.get("name"),
        "workflow_run_id": workflow_run.get("id"),
        "run_attempt": workflow_run.get("run_attempt"),
        "status": workflow_run.get("status"),
        "conclusion": workflow_run.get("conclusion"),
        "head_branch": workflow_run.get("head_branch"),
        "head_sha": workflow_run.get("head_sha"),
        "html_url": workflow_run.get("html_url"),
        "event": workflow_run.get("event"),
    }


def _insert_trigger(
    *,
    project: str,
    environment: str,
    repository: str,
    sha: str,
    deployment_id: str,
    deployment_status_id: str | None,
    dedupe_key: str,
    event_name: str,
    status: str,
    reason: str | None,
    payload: dict[str, Any],
) -> int:
    now = _utc_now()
    payload_json = json.dumps(payload, default=str)

    with _db_connection() as conn:
        cursor = conn.cursor()

        if USE_POSTGRES:
            cursor.execute(
                """
                INSERT INTO integration_triggers (
                    project,
                    environment,
                    repository,
                    sha,
                    deployment_id,
                    deployment_status_id,
                    dedupe_key,
                    event_name,
                    status,
                    reason,
                    payload,
                    run_id,
                    github_status_url,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, NULL, NULL, %s, %s
                )
                ON CONFLICT (dedupe_key)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    reason = EXCLUDED.reason,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                """,
                (
                    project,
                    environment,
                    repository,
                    sha,
                    deployment_id,
                    deployment_status_id,
                    dedupe_key,
                    event_name,
                    status,
                    reason,
                    payload_json,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            return int(row["id"] if isinstance(row, dict) else row[0])

        cursor.execute(
            """
            INSERT OR IGNORE INTO integration_triggers (
                project,
                environment,
                repository,
                sha,
                deployment_id,
                deployment_status_id,
                dedupe_key,
                event_name,
                status,
                reason,
                payload,
                run_id,
                github_status_url,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                project,
                environment,
                repository,
                sha,
                deployment_id,
                deployment_status_id,
                dedupe_key,
                event_name,
                status,
                reason,
                payload_json,
                now,
                now,
            ),
        )

        cursor.execute(
            "SELECT id FROM integration_triggers WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create or load integration trigger row.")
        return int(row["id"])


def _finish_trigger(
    trigger_id: int,
    *,
    status: str,
    reason: str | None,
    run_id: int | None = None,
    github_status_url: str | None = None,
) -> None:
    now = _utc_now()

    with _db_connection() as conn:
        cursor = conn.cursor()

        if USE_POSTGRES:
            cursor.execute(
                """
                UPDATE integration_triggers
                SET status = %s,
                    reason = %s,
                    run_id = %s,
                    github_status_url = %s,
                    updated_at = %s,
                    finished_at = %s
                WHERE id = %s
                """,
                (status, reason, run_id, github_status_url, now, now, trigger_id),
            )
            return

        cursor.execute(
            """
            UPDATE integration_triggers
            SET status = ?,
                reason = ?,
                run_id = ?,
                github_status_url = ?,
                updated_at = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (status, reason, run_id, github_status_url, now, now, trigger_id),
        )


def _lookup_mapping(project: str, environment: str) -> dict[str, Any] | None:
    with _db_connection() as conn:
        cursor = conn.cursor()

        if USE_POSTGRES:
            cursor.execute(
                """
                SELECT *
                FROM integration_profile_mappings
                WHERE project = %s AND environment = %s
                LIMIT 1
                """,
                (project, environment),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM integration_profile_mappings
                WHERE project = ? AND environment = ?
                LIMIT 1
                """,
                (project, environment),
            )

        return _dict_row(cursor.fetchone())


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _launch_profile(profile_id: int) -> int | None:
    payload = runs_service.launch_profile(profile_id, None)
    run = payload.get("run") if isinstance(payload, dict) else None

    if isinstance(run, dict) and run.get("id") is not None:
        return int(run["id"])

    if isinstance(payload, dict) and payload.get("id") is not None:
        return int(payload["id"])

    return None


def process_github_workflow_run_webhook(
    body: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    project = _verify_signature_project(body, headers)
    if not project:
        return {
            "accepted": False,
            "status": "rejected",
            "reason": "invalid_signature",
            "event": "workflow_run",
        }

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {
            "accepted": False,
            "status": "rejected",
            "reason": "invalid_json",
            "event": "workflow_run",
            "project": project,
        }

    repository_payload = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    workflow_run = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}

    repository = str(repository_payload.get("full_name") or "")
    action = str(payload.get("action") or "")
    conclusion = str(workflow_run.get("conclusion") or "")
    workflow_status = str(workflow_run.get("status") or "")

    workflow_run_id = str(workflow_run.get("id") or "")
    run_attempt = str(workflow_run.get("run_attempt") or "")
    sha = str(workflow_run.get("head_sha") or repository_payload.get("pushed_at") or "")
    environment = DEFAULT_WORKFLOW_ENVIRONMENT or "production"

    dedupe_key = f"workflow_run:{repository}:{workflow_run_id}:{run_attempt}:{conclusion or workflow_status}"
    summary = _workflow_payload_summary(payload)

    if not repository or not _repo_allowed_for_project(project, repository):
        trigger_id = _insert_trigger(
            project=project,
            environment=environment,
            repository=repository or "unknown",
            sha=sha or "unknown",
            deployment_id=workflow_run_id or "unknown",
            deployment_status_id=run_attempt or None,
            dedupe_key=dedupe_key,
            event_name="workflow_run",
            status="rejected",
            reason="repository_not_allowlisted",
            payload=summary,
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "repository_not_allowlisted",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    trigger_id = _insert_trigger(
        project=project,
        environment=environment,
        repository=repository,
        sha=sha or "unknown",
        deployment_id=workflow_run_id or "unknown",
        deployment_status_id=run_attempt or None,
        dedupe_key=dedupe_key,
        event_name="workflow_run",
        status="received",
        reason=None,
        payload=summary,
    )

    if action != "completed":
        _finish_trigger(
            trigger_id,
            status="ignored",
            reason="workflow_run_not_completed",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "ignored",
            "reason": "workflow_run_not_completed",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    if conclusion != "success":
        _finish_trigger(
            trigger_id,
            status="ignored",
            reason="workflow_run_not_successful",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "ignored",
            "reason": "workflow_run_not_successful",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    mapping = _lookup_mapping(project, environment)
    if not mapping:
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="mapping_not_found",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "mapping_not_found",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    if not _bool_value(mapping.get("enabled")):
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="mapping_disabled",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "mapping_disabled",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    profile_id = int(mapping["profile_id"])
    run_id = _launch_profile(profile_id)

    _finish_trigger(
        trigger_id,
        status="launched",
        reason="workflow_run_success",
        run_id=run_id,
    )

    return {
        "accepted": True,
        "trigger_id": trigger_id,
        "status": "launched",
        "reason": "workflow_run_success",
        "run_id": run_id,
        "project": project,
        "environment": environment,
        "repository": repository,
        "meta": summary,
    }