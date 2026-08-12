from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ..runs import service as runs_service
from .routing import route_key_from_workflow_run


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

DB_PATH = os.getenv("RUN_DB_PATH", "/workspace/simulate/runs/web-gui.sqlite")


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
    from .webhook_config import project_secrets

    return project_secrets()


def _github_repo_allowlist() -> dict[str, list[str]]:
    from .webhook_config import repo_allowlist

    return repo_allowlist()


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
    from .webhook_config import resolve_project_from_signature

    signature = headers.get("x-hub-signature-256", "").strip()
    return resolve_project_from_signature(body, signature)


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
) -> tuple[int, bool]:
    """Insert an audit row, check-then-insert on dedupe_key (mirrors
    main._create_integration_trigger's pattern for the deployment_status path).

    Returns (trigger_id, created). created=False means dedupe_key already existed and this
    call did not write anything — callers must treat that as a duplicate delivery and must
    not launch a profile for it.
    """
    now = _utc_now()
    payload_json = json.dumps(payload, default=str)

    with _db_connection() as conn:
        cursor = conn.cursor()

        if USE_POSTGRES:
            cursor.execute(
                "SELECT id FROM integration_triggers WHERE dedupe_key = %s",
                (dedupe_key,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return int(existing["id"] if isinstance(existing, dict) else existing[0]), False

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
            return int(row["id"] if isinstance(row, dict) else row[0]), True

        existing = cursor.execute(
            "SELECT id FROM integration_triggers WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), False

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
        return int(row["id"]), True


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
                WHERE project = %s AND environment = %s AND status <> %s
                LIMIT 1
                """,
                (project, environment, "archived"),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM integration_profile_mappings
                WHERE project = ? AND environment = ? AND status <> ?
                LIMIT 1
                """,
                (project, environment, "archived"),
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


# Must match api.app.main.INTEGRATION_AUTOMATION_SETTINGS_KEY — same system_settings row, read
# independently here (mirroring how _lookup_mapping below duplicates main.py's mapping lookup)
# so the webhook path never depends on main.py's callback wiring to enforce the gate.
_INTEGRATION_AUTOMATION_SETTINGS_KEY = "integration_automation"


def automation_enabled() -> bool:
    """Master switch for GitHub-triggered simulation runs, checked before any event-specific parsing.

    Absent row => automation on (the per-mapping trigger spec below is the fail-closed gate).
    Any read error => automation off, since this is a safety switch and must fail closed.
    """
    try:
        with _db_connection() as conn:
            cursor = conn.cursor()
            if USE_POSTGRES:
                cursor.execute(
                    "SELECT value FROM system_settings WHERE key = %s",
                    (_INTEGRATION_AUTOMATION_SETTINGS_KEY,),
                )
            else:
                cursor.execute(
                    "SELECT value FROM system_settings WHERE key = ?",
                    (_INTEGRATION_AUTOMATION_SETTINGS_KEY,),
                )
            row = cursor.fetchone()
    except Exception:
        return False

    if row is None:
        return True

    raw = row["value"]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False
    if not isinstance(raw, dict):
        return False
    return _bool_value(raw.get("automation_enabled", True))


def record_automation_disabled_trigger(*, project: str, event_name: str, repository: str) -> int:
    """Audit row for a delivery rejected by the global automation switch, before any
    event-specific parsing (route key, workflow name, conclusion) has happened."""
    now = _utc_now()
    dedupe_key = f"automation_disabled:{project}:{repository}:{event_name}:{now}"
    trigger_id, _created = _insert_trigger(
        project=project,
        environment="unknown",
        repository=repository or "unknown",
        sha="unknown",
        deployment_id="unknown",
        deployment_status_id=None,
        dedupe_key=dedupe_key,
        event_name=event_name,
        status="rejected",
        reason="automation_disabled",
        payload={},
    )
    return trigger_id


def _launch_profile(profile_id: int, *, trigger_overlay: dict[str, Any] | None = None) -> int | None:
    payload = runs_service.launch_profile(profile_id, None, trigger_overlay)
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
    environment = route_key_from_workflow_run(workflow_run)

    workflow_name = str(workflow_run.get("name") or "")
    dedupe_key = f"workflow_run:{repository}:{workflow_run_id}:{run_attempt}:{conclusion or workflow_status}"
    summary = _workflow_payload_summary(payload)

    if not repository or not _repo_allowed_for_project(project, repository):
        trigger_id, _created = _insert_trigger(
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

    # GitHub also delivers "requested" and "in_progress" workflow_run events for the same
    # run. Neither can ever lead to a launch decision, so no audit row is written for them
    # -- only a delivery whose action is "completed" is worth recording.
    if action != "completed":
        return {
            "accepted": False,
            "status": "ignored",
            "reason": "workflow_run_not_completed",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    trigger_id, created = _insert_trigger(
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

    if not created:
        # Same (repository, workflow_run_id, run_attempt, conclusion) delivered again --
        # GitHub redelivers on timeout/retry. Must not launch a second time for it.
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "duplicate",
            "reason": "duplicate_delivery",
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

    # Positive trigger spec (allowlist, not denylist): a mapping must declare exactly what
    # launches it. No spec, wrong event type, wrong workflow name, or wrong conclusion all
    # mean "do not launch" -- there is no default-permit path left below this point.
    trigger_event = str(mapping.get("trigger_event") or "").strip()
    if not trigger_event:
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="trigger_not_configured",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "trigger_not_configured",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    if trigger_event != "workflow_run":
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="event_not_allowed",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "event_not_allowed",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    expected_workflow = str(mapping.get("trigger_workflow") or "").strip()
    if not expected_workflow or expected_workflow != workflow_name:
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="workflow_not_allowed",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "workflow_not_allowed",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    expected_conclusion = str(mapping.get("trigger_conclusion") or "success").strip().lower()
    if conclusion.strip().lower() != expected_conclusion:
        _finish_trigger(
            trigger_id,
            status="rejected",
            reason="conclusion_not_allowed",
        )
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "rejected",
            "reason": "conclusion_not_allowed",
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

    profile_id = int(mapping["profile_id"])
    trigger_overlay: dict[str, Any] = {
        "trigger_source": "github",
        "trigger_label": f"GitHub integration: {project}/{environment}",
        "integration_trigger_id": trigger_id,
        "trigger_context": {
            "project": project,
            "environment": environment,
            "repository": repository,
            "integration_trigger_id": trigger_id,
            "profile_id": profile_id,
            "github_event": "workflow_run",
            "workflow_summary": summary,
        },
    }

    try:
        run_id = _launch_profile(profile_id, trigger_overlay=trigger_overlay)
    except Exception as exc:  # noqa: BLE001 - a launch failure (e.g. archived profile) must
        # not crash the webhook endpoint; record it and return a normal rejected response.
        reason = f"launch_failed:{exc}"
        _finish_trigger(trigger_id, status="failed", reason=reason)
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "status": "failed",
            "reason": reason,
            "project": project,
            "environment": environment,
            "repository": repository,
            "meta": summary,
        }

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
