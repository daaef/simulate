from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)
DB_PATH = os.getenv("RUN_DB_PATH", "/workspace/simulate/runs/web-gui.sqlite")
DB_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _encryption_key() -> bytes:
    material = (
        os.getenv("SIMULATOR_SECRETS_ENCRYPTION_KEY", "").strip()
        or os.getenv("JWT_SECRET_KEY", "").strip()
        or "dev-insecure-change-me"
    ).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_secret(plaintext: str) -> str:
    from cryptography.fernet import Fernet

    token = Fernet(_encryption_key()).encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def _decrypt_secret(ciphertext: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(_encryption_key()).decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _secret_hint(plaintext: str) -> str:
    if len(plaintext) <= 4:
        return "****"
    return f"…{plaintext[-4:]}"


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


def ensure_schema_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_webhook_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL UNIQUE,
            secret_ciphertext TEXT NOT NULL,
            secret_hint TEXT NOT NULL,
            repositories TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            archived_at TEXT,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_schema_postgres(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_webhook_projects (
            id SERIAL PRIMARY KEY,
            project VARCHAR(120) NOT NULL UNIQUE,
            secret_ciphertext TEXT NOT NULL,
            secret_hint VARCHAR(16) NOT NULL,
            repositories JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            archived_at TIMESTAMP WITH TIME ZONE,
            created_by_user_id INTEGER,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )


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


def _row_to_public_dict(row: Any, *, include_repositories: bool = True) -> dict[str, Any]:
    payload = dict(row)
    repositories = payload.get("repositories") or []
    if isinstance(repositories, str):
        try:
            repositories = json.loads(repositories)
        except json.JSONDecodeError:
            repositories = []
    if not isinstance(repositories, list):
        repositories = []

    result = {
        "id": int(payload["id"]),
        "project": str(payload["project"]),
        "secret_hint": str(payload.get("secret_hint") or "****"),
        "status": str(payload.get("status") or "active"),
        "archived_at": payload.get("archived_at"),
        "created_by_user_id": payload.get("created_by_user_id"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "source": "database",
    }
    if include_repositories:
        result["repositories"] = [str(item) for item in repositories if str(item).strip()]
    return result


def _load_active_rows() -> list[dict[str, Any]]:
    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM integration_webhook_projects
                    WHERE status <> %s
                    ORDER BY project ASC, id ASC
                    """,
                    ("archived",),
                )
                rows = cursor.fetchall()
        return [_row_to_public_dict(row) for row in rows]

    with DB_LOCK, _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM integration_webhook_projects
            WHERE status <> ?
            ORDER BY project ASC, id ASC
            """,
            ("archived",),
        ).fetchall()
    return [_row_to_public_dict(row) for row in rows]


def active_secrets_by_project() -> dict[str, str]:
    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT project, secret_ciphertext FROM integration_webhook_projects
                    WHERE status <> %s
                    """,
                    ("archived",),
                )
                rows = cursor.fetchall()
        return {
            str(row["project"]).strip().lower(): _decrypt_secret(str(row["secret_ciphertext"]))
            for row in rows
        }

    with DB_LOCK, _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT project, secret_ciphertext FROM integration_webhook_projects
            WHERE status <> ?
            """,
            ("archived",),
        ).fetchall()
    return {
        str(row["project"]).strip().lower(): _decrypt_secret(str(row["secret_ciphertext"]))
        for row in rows
    }


def active_repositories_by_project() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in _load_active_rows():
        project = str(item["project"]).strip().lower()
        repos = item.get("repositories") or []
        if project and repos:
            result[project] = [str(repo) for repo in repos]
    return result


def list_projects(*, include_archived: bool = False) -> dict[str, Any]:
    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                if include_archived:
                    cursor.execute(
                        "SELECT * FROM integration_webhook_projects ORDER BY project ASC, id ASC"
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM integration_webhook_projects
                        WHERE status <> %s
                        ORDER BY project ASC, id ASC
                        """,
                        ("archived",),
                    )
                rows = cursor.fetchall()
        projects = [_row_to_public_dict(row) for row in rows]
    else:
        with DB_LOCK, _db_connection() as conn:
            if include_archived:
                rows = conn.execute(
                    "SELECT * FROM integration_webhook_projects ORDER BY project ASC, id ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_webhook_projects
                    WHERE status <> ?
                    ORDER BY project ASC, id ASC
                    """,
                    ("archived",),
                ).fetchall()
        projects = [_row_to_public_dict(row) for row in rows]

    return {"projects": projects}


def create_project(
    *,
    project: str,
    repositories: list[str] | None,
    user_id: int | None,
    secret: str | None = None,
) -> dict[str, Any]:
    project_key = _normalize_project(project)
    repos = _normalize_repositories(repositories)
    plaintext = str(secret or "").strip() or generate_webhook_secret()
    ciphertext = _encrypt_secret(plaintext)
    hint = _secret_hint(plaintext)
    now = _utc_now()
    repositories_json = json.dumps(repos)

    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO integration_webhook_projects (
                        project, secret_ciphertext, secret_hint, repositories,
                        status, created_by_user_id, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, 'active', %s, %s, %s)
                    RETURNING *
                    """,
                    (project_key, ciphertext, hint, repositories_json, user_id, now, now),
                )
                row = cursor.fetchone()
    else:
        with DB_LOCK, _db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO integration_webhook_projects (
                    project, secret_ciphertext, secret_hint, repositories,
                    status, created_by_user_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (project_key, ciphertext, hint, repositories_json, user_id, now, now),
            )
            row = conn.execute(
                "SELECT * FROM integration_webhook_projects WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()

    public = _row_to_public_dict(row)
    public["secret"] = plaintext
    public["secret_display_once"] = True
    return {"project": public}


def rotate_project_secret(project: str, *, user_id: int | None = None) -> dict[str, Any]:
    project_key = _normalize_project(project)
    plaintext = generate_webhook_secret()
    ciphertext = _encrypt_secret(plaintext)
    hint = _secret_hint(plaintext)
    now = _utc_now()

    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE integration_webhook_projects
                    SET secret_ciphertext = %s,
                        secret_hint = %s,
                        updated_at = %s
                    WHERE project = %s AND status <> %s
                    RETURNING *
                    """,
                    (ciphertext, hint, now, project_key, "archived"),
                )
                row = cursor.fetchone()
    else:
        with DB_LOCK, _db_connection() as conn:
            updated = conn.execute(
                """
                UPDATE integration_webhook_projects
                SET secret_ciphertext = ?,
                    secret_hint = ?,
                    updated_at = ?
                WHERE project = ? AND status <> ?
                """,
                (ciphertext, hint, now, project_key, "archived"),
            )
            if updated.rowcount == 0:
                row = None
            else:
                row = conn.execute(
                    "SELECT * FROM integration_webhook_projects WHERE project = ?",
                    (project_key,),
                ).fetchone()

    if row is None:
        raise KeyError(f"project {project_key!r} not found")

    public = _row_to_public_dict(row)
    public["secret"] = plaintext
    public["secret_display_once"] = True
    return {"project": public}


def update_project_repositories(project: str, repositories: list[str]) -> dict[str, Any]:
    project_key = _normalize_project(project)
    repos = _normalize_repositories(repositories)
    now = _utc_now()
    repositories_json = json.dumps(repos)

    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE integration_webhook_projects
                    SET repositories = %s::jsonb,
                        updated_at = %s
                    WHERE project = %s AND status <> %s
                    RETURNING *
                    """,
                    (repositories_json, now, project_key, "archived"),
                )
                row = cursor.fetchone()
    else:
        with DB_LOCK, _db_connection() as conn:
            updated = conn.execute(
                """
                UPDATE integration_webhook_projects
                SET repositories = ?,
                    updated_at = ?
                WHERE project = ? AND status <> ?
                """,
                (repositories_json, now, project_key, "archived"),
            )
            if updated.rowcount == 0:
                row = None
            else:
                row = conn.execute(
                    "SELECT * FROM integration_webhook_projects WHERE project = ?",
                    (project_key,),
                ).fetchone()

    if row is None:
        raise KeyError(f"project {project_key!r} not found")

    return {"project": _row_to_public_dict(row)}


def archive_project(project: str) -> dict[str, Any]:
    project_key = _normalize_project(project)
    now = _utc_now()

    if USE_POSTGRES:
        with _db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE integration_webhook_projects
                    SET status = %s,
                        archived_at = %s,
                        updated_at = %s
                    WHERE project = %s AND status <> %s
                    RETURNING *
                    """,
                    ("archived", now, now, project_key, "archived"),
                )
                row = cursor.fetchone()
    else:
        with DB_LOCK, _db_connection() as conn:
            updated = conn.execute(
                """
                UPDATE integration_webhook_projects
                SET status = ?,
                    archived_at = ?,
                    updated_at = ?
                WHERE project = ? AND status <> ?
                """,
                ("archived", now, now, project_key, "archived"),
            )
            if updated.rowcount == 0:
                row = None
            else:
                row = conn.execute(
                    "SELECT * FROM integration_webhook_projects WHERE project = ?",
                    (project_key,),
                ).fetchone()

    if row is None:
        raise KeyError(f"project {project_key!r} not found")

    return {"project": _row_to_public_dict(row), "archived": True}
