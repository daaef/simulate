from __future__ import annotations

import logging
import json
import os
import sqlite3
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from flow_presets import FLOW_PRESETS

# Database configuration
USE_POSTGRES = os.getenv('DATABASE_URL') is not None
POSTGRES_URL = os.getenv('DATABASE_URL', '')

# Import PostgreSQL extras
if USE_POSTGRES:
    try:
        from psycopg2.extras import DictCursor
    except ImportError:
        DictCursor = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

SIM_ENV = os.getenv("SIM_ENV", "development").strip().lower()
AUTH_DISABLED = _as_bool(os.getenv("SIM_AUTH_DISABLED"), default=False)

try:
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from auth import (
        init_auth,
        get_auth_manager,
        UserCreate,
        UserLogin,
        TokenResponse,
        UserProfile as AuthUserProfile,
    )

    AUTH_IMPORT_ERROR: Exception | None = None
except ImportError as e:
    init_auth = None  # type: ignore[assignment]
    get_auth_manager = None  # type: ignore[assignment]
    UserCreate = None  # type: ignore[assignment]
    UserLogin = None  # type: ignore[assignment]
    TokenResponse = None  # type: ignore[assignment]
    AuthUserProfile = None  # type: ignore[assignment]
    AUTH_IMPORT_ERROR = e

AUTH_ENABLED = not AUTH_DISABLED and AUTH_IMPORT_ERROR is None

if AUTH_DISABLED and SIM_ENV in {"production", "prod"}:
    raise RuntimeError("SIM_AUTH_DISABLED=true is not allowed when SIM_ENV=production.")

if AUTH_IMPORT_ERROR is not None and not AUTH_DISABLED:
    raise RuntimeError(
        "Authentication module could not be imported. "
        "Set SIM_AUTH_DISABLED=true only for local development."
    ) from AUTH_IMPORT_ERROR

ALLOWED_ROLES = {"admin", "operator", "runner", "viewer"}
RUN_CREATE_ROLES = {"admin", "operator", "runner"}
RUN_DELETE_ROLES = {"admin", "operator"}
ADMIN_ROLES = {"admin"}

SIMULATOR_WORKDIR = os.getenv("SIMULATOR_WORKDIR", "/workspace")
PROJECT_DIR = os.getenv("SIMULATOR_PROJECT_DIR", "/workspace/simulate")
DB_PATH = os.getenv("RUN_DB_PATH", "/workspace/simulate/runs/web-gui.sqlite")
LOG_DIR = Path(os.getenv("RUN_LOG_DIR", "/workspace/simulate/runs/web-gui"))
AUTO_REFRESH_SECONDS = max(5, int(os.getenv("RUN_AUTO_REFRESH_SECONDS", "30")))
ALLOW_ORIGINS = os.getenv("WEB_CORS_ORIGINS", "*")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_LOCK = threading.Lock()
RUN_PROCESSES: dict[int, subprocess.Popen[str]] = {}
RUN_CANCELLED: set[int] = set()
RUN_LOCK = threading.Lock()
ARTIFACT_FIELDS = ("report_path", "story_path", "events_path")
EVENT_CACHE_LOCK = threading.Lock()
EVENT_CACHE_MAX_ITEMS = max(4, int(os.getenv("SIM_GUI_EVENT_CACHE_MAX_ITEMS", "24")))
SLOW_REQUEST_THRESHOLD_MS = float(os.getenv("SIM_GUI_SLOW_REQUEST_THRESHOLD_MS", "800"))
MONITORED_ENDPOINT_PREFIXES = (
    "/api/v1/runs",
    "/api/v1/dashboard/summary",
)
LOGGER = logging.getLogger("simulate.web_api")


@dataclass
class EventCacheEntry:
    path: str
    mtime_ns: int
    size: int
    events: list[dict[str, Any]]
    metrics: dict[str, Any]
    loaded_at_monotonic: float


EVENT_CACHE: "OrderedDict[str, EventCacheEntry]" = OrderedDict()


# Database abstraction layer
def _get_db_connection():
    """Get database connection (SQLite or PostgreSQL)"""
    if USE_POSTGRES:
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(POSTGRES_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

def _db() -> sqlite3.Connection:
    """Legacy SQLite connection for backward compatibility"""
    if USE_POSTGRES:
        raise RuntimeError("PostgreSQL is enabled, use _get_db_connection() instead")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db() -> None:
    """Initialize database schema"""
    if USE_POSTGRES:
        # PostgreSQL schema is created by migrations
        return
    
    # SQLite schema
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flow TEXT NOT NULL,
                plan TEXT NOT NULL,
                timing TEXT NOT NULL,
                mode TEXT,
                store_id TEXT,
                phone TEXT,
                store_phone TEXT,
                user_name TEXT,
                store_name TEXT,
                all_users INTEGER NOT NULL DEFAULT 0,
                no_auto_provision INTEGER NOT NULL DEFAULT 0,
                post_order_actions INTEGER,
                extra_args TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                command TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                exit_code INTEGER,
                log_path TEXT,
                report_path TEXT,
                story_path TEXT,
                events_path TEXT,
                error TEXT
            )
            """
        )
        _migrate_db(conn)


def _migrate_db(conn: sqlite3.Connection) -> None:
    """Apply schema migrations for SQLite."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()]
    if "store_phone" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN store_phone TEXT")
    if "user_name" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN user_name TEXT")
    if "store_name" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN store_name TEXT")

# Authentication dependencies
security = HTTPBearer(auto_error=False)

class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    new_password: str


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    """Get current authenticated user."""
    if not AUTH_ENABLED:
        if AUTH_DISABLED and SIM_ENV not in {"production", "prod"}:
            return {
                "id": None,
                "username": "local-dev",
                "role": "admin",
                "is_active": True,
            }

        raise HTTPException(
            status_code=503,
            detail="Authentication is not available.",
        )

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_manager = get_auth_manager()
    payload = auth_manager.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = str(user.get("role") or "").strip().lower()
    if role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Unsupported user role: {role or 'unknown'}",
        )

    return user

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    """Get current user if authenticated, otherwise return None."""
    if not AUTH_ENABLED:
        if AUTH_DISABLED and SIM_ENV not in {"production", "prod"}:
            return {
                "id": None,
                "username": "local-dev",
                "role": "admin",
                "is_active": True,
            }
        return None

    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

def _user_role(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return str(user.get("role") or "").strip().lower()


def _user_id(user: dict[str, Any] | None) -> int | None:
    if not user:
        return None
    value = user.get("id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_admin(user: dict[str, Any] | None) -> bool:
    return _user_role(user) in ADMIN_ROLES


def _require_role(user: dict[str, Any], allowed_roles: set[str], action: str) -> None:
    role = _user_role(user)

    if role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to {action}.",
        )

def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["all_users"] = bool(payload["all_users"])
    payload["no_auto_provision"] = bool(payload["no_auto_provision"])
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
    return payload


def _row_to_dict_any(row) -> dict[str, Any]:
    """Convert database row to dict, supporting both SQLite and PostgreSQL"""
    if USE_POSTGRES:
        # PostgreSQL returns dict-like objects
        return dict(row)
    else:
        # SQLite returns Row objects
        payload = dict(row)
        payload["all_users"] = bool(payload["all_users"])
        payload["no_auto_provision"] = bool(payload["no_auto_provision"])
        if payload["post_order_actions"] is not None:
            payload["post_order_actions"] = bool(payload["post_order_actions"])
        payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
        return payload

def _list_runs(limit: int = 100, offset: int = 0, user_id: Optional[int] = None) -> list[dict[str, Any]]:
    _cleanup_stale_processes()
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                if user_id:
                    cursor.execute(
                        "SELECT * FROM runs WHERE user_id = %s ORDER BY id DESC LIMIT %s OFFSET %s",
                        (user_id, limit, offset)
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM runs ORDER BY id DESC LIMIT %s OFFSET %s",
                        (limit, offset)
                    )
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
    
    runs = [_row_to_dict_any(row) for row in rows]
    return [_hydrate_run_artifacts(run) for run in runs]

def _count_runs(user_id: Optional[int] = None) -> int:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                if user_id:
                    cursor.execute("SELECT COUNT(*) FROM runs WHERE user_id = %s", (user_id,))
                else:
                    cursor.execute("SELECT COUNT(*) FROM runs")
                result = cursor.fetchone()
                return result[0] if result else 0
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            result = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
            return result[0] if result else 0

def _cleanup_stale_processes() -> None:
    """Remove finished processes from RUN_PROCESSES and update their status if needed."""
    with RUN_LOCK:
        stale_processes = []
        for run_id, process in list(RUN_PROCESSES.items()):
            if process.poll() is not None:
                # Process has finished but wasn't cleaned up
                stale_processes.append((run_id, process))
                RUN_PROCESSES.pop(run_id, None)
    
    # Update status for stale runs that are still marked as running/cancelling
    # (done outside RUN_LOCK to avoid holding lock during DB operations)
    for run_id, process in stale_processes:
        try:
            # Direct DB query to avoid recursion with _get_run
            if USE_POSTGRES:
                conn = _get_db_connection()
                try:
                    with conn.cursor(cursor_factory=DictCursor) as cursor:
                        cursor.execute("SELECT status FROM runs WHERE id = %s", (run_id,))
                        row = cursor.fetchone()
                        status = row["status"] if row else None
                finally:
                    conn.close()
            else:
                with DB_LOCK, _db() as conn:
                    row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
                    status = row["status"] if row else None
            
            if status and status.lower() in ("running", "cancelling"):
                # Process finished but status wasn't updated
                return_code = process.poll()
                if run_id in RUN_CANCELLED:
                    RUN_CANCELLED.discard(run_id)
                    new_status = "cancelled"
                else:
                    new_status = "succeeded" if return_code == 0 else "failed"
                _update_run(
                    run_id,
                    status=new_status,
                    finished_at=_utc_now(),
                    exit_code=return_code,
                )
                LOGGER.info(f"Updated stale run {run_id} status to {new_status}")
        except Exception as e:
            LOGGER.error(f"Failed to update stale run {run_id}: {e}")


def _get_run(run_id: int) -> dict[str, Any]:
    _cleanup_stale_processes()
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT * FROM runs WHERE id = %s", (run_id,))
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
                return _hydrate_run_artifacts(_row_to_dict_any(row))
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
            return _hydrate_run_artifacts(_row_to_dict(row))

def _update_run(run_id: int, **fields: Any) -> None:
    if not fields:
        return
    
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                keys = list(fields.keys())
                values = [fields[key] for key in keys]
                assignment = ", ".join(f"{key} = %s" for key in keys)
                cursor.execute(
                    f"UPDATE runs SET {assignment} WHERE id = %s",
                    (*values, run_id)
                )
                conn.commit()
        finally:
            conn.close()
    else:
        keys = list(fields.keys())
        values = [fields[key] for key in keys]
        assignment = ", ".join(f"{key} = ?" for key in keys)
        with DB_LOCK, _db() as conn:
            conn.execute(
                f"UPDATE runs SET {assignment} WHERE id = ?",
                (*values, run_id),
            )


@dataclass
class ScheduledRun:
    flow: str
    plan: str
    timing: str
    store_id: Optional[str] = None


class RunCreateRequest(BaseModel):
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Optional[Literal["trace", "load"]] = None
    store_id: Optional[str] = None
    phone: Optional[str] = None
    all_users: bool = False
    no_auto_provision: bool = False
    post_order_actions: Optional[bool] = None
    extra_args: List[str] = Field(default_factory=list)


def _build_command(request: RunCreateRequest) -> list[str]:
    if request.flow not in FLOW_PRESETS:
        expected = ", ".join(sorted(FLOW_PRESETS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported flow {request.flow!r}. Expected one of {expected}.",
        )
    command = [
        "python3",
        "-u",
        "-m",
        "simulate",
        request.flow,
        "--plan",
        request.plan,
        "--timing",
        request.timing,
    ]
    if request.mode:
        command.extend(["--mode", request.mode])
    if request.store_id:
        command.extend(["--store", request.store_id])
    if request.phone:
        command.extend(["--phone", request.phone])
    if request.all_users:
        command.append("--all-users")
    if request.no_auto_provision:
        command.append("--no-auto-provision")
    if request.post_order_actions:
        command.append("--post-order-actions")
    if request.extra_args:
        command.extend(request.extra_args)
    return command


def _parse_artifact_paths(line: str) -> tuple[str, str] | None:
    markers = (
        ("main: report:", "report_path"),
        ("main: story:", "story_path"),
        ("main: events:", "events_path"),
    )
    lowered = line.lower()
    for marker, target in markers:
        if marker in lowered:
            return target, line.split(marker, 1)[1].strip()
    return None


def _looks_like_artifact_path(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False
    if not (candidate.startswith("/") or candidate.startswith("./") or candidate.startswith("../")):
        return False
    if candidate.endswith(".md") or candidate.endswith(".json"):
        return True
    return any(token in candidate for token in ("report.md", "story.md", "events.json"))


def _capture_artifacts_from_lines(lines: list[str]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    pending_key: str | None = None
    for line in lines:
        parsed = _parse_artifact_paths(line)
        if parsed:
            key, value = parsed
            if value:
                artifacts[key] = value
                pending_key = None
            else:
                pending_key = key
            continue
        if pending_key:
            candidate = line.strip()
            if _looks_like_artifact_path(candidate):
                artifacts[pending_key] = candidate
                pending_key = None
    return artifacts


def _extract_metadata_from_log(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    artifacts = _capture_artifacts_from_lines(lines)
    identity = _parse_identity_from_lines(lines)
    store_id = _parse_store_id_from_lines(lines)
    phone = identity.get("user_phone") or _parse_phone_from_lines(lines)
    
    return {
        "artifacts": artifacts,
        "identity": identity,
        "store_id": store_id,
        "phone": phone
    }


def _extract_artifacts_from_log(log_path: Path) -> dict[str, str]:
    """Legacy helper for backward compatibility."""
    return _extract_metadata_from_log(log_path).get("artifacts", {})


def _parse_store_id_from_lines(lines: list[str]) -> str | None:
    """Extract selected store_id from log lines."""
    # Look for: "trace: Selected store FZY_926025 (subentity_id=7)."
    # or: "store: Store profile acquired for FZY_926025 (subentity_id=7, ..."
    for line in lines:
        if "Selected store" in line:
            try:
                start = line.find("Selected store ") + len("Selected store ")
                end = line.find(" (", start)
                if end > start:
                    return line[start:end].strip()
            except Exception:
                pass
        elif "Store profile acquired for" in line:
            try:
                start = line.find("Store profile acquired for ") + len("Store profile acquired for ")
                end = line.find(" (", start)
                if end > start:
                    return line[start:end].strip()
            except Exception:
                pass
    return None


def _parse_phone_from_lines(lines: list[str]) -> str | None:
    """Extract phone number from log lines."""
    # Priority 1: identity_context marker
    identity = _parse_identity_from_lines(lines)
    if identity.get("user_phone"):
        return identity["user_phone"]
        
    # Priority 2: Starting panel
    # Look for: "Users       : 1 (+2348166675609)"
    for line in lines:
        if "Users" in line and "(" in line and ")" in line:
            try:
                start = line.find("(") + 1
                end = line.find(")", start)
                if end > start:
                    phone = line[start:end].strip()
                    if phone and phone not in ("--all-users", "auto"):
                        return phone
            except Exception:
                pass
    return None


def _parse_identity_from_lines(lines: list[str]) -> dict[str, str]:
    """Parse complete identity from specialized JSON marker."""
    for line in lines:
        if "identity_context:" in line:
            try:
                # [dim]main:[/] identity_context: {"user_phone": ...}
                content = line.split("identity_context:", 1)[1].strip()
                # Remove possible ANSI escape codes or trailing rich formatting
                if "\x1b" in content:
                    content = content.split("\x1b")[0]
                return json.loads(content)
            except Exception:
                pass
    return {}


def _hydrate_run_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    log_path = _safe_path(run.get("log_path"))
    if log_path is None:
        return run
    
    metadata = _extract_metadata_from_log(log_path)
    artifacts = metadata.get("artifacts", {})
    identity = metadata.get("identity", {})
    
    updates: dict[str, Any] = {}
    for field in ARTIFACT_FIELDS:
        if not run.get(field) and artifacts.get(field):
            updates[field] = artifacts[field]
    
    # Hydrate identity fields if missing
    if not run.get("store_id") and metadata.get("store_id"):
        updates["store_id"] = metadata["store_id"]
    if not run.get("phone") and metadata.get("phone"):
        updates["phone"] = metadata["phone"]
    
    id_map = {
        "store_phone": "store_phone",
        "user_name": "user_name",
        "store_name": "store_name"
    }
    for run_key, id_key in id_map.items():
        if not run.get(run_key) and identity.get(id_key):
            updates[run_key] = identity[id_key]
            
    if updates:
        _update_run(int(run["id"]), **updates)
        run = {**run, **updates}
    return run


def _run_simulation(run_id: int, command: list[str], log_path: Path) -> None:
    _update_run(run_id, status="running", started_at=_utc_now(), log_path=str(log_path))
    process = subprocess.Popen(
        command,
        cwd=SIMULATOR_WORKDIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "TERM": os.getenv("TERM", "xterm-256color"),
        },
    )
    with RUN_LOCK:
        RUN_PROCESSES[run_id] = process
    artifacts: dict[str, str] = {}
    pending_artifact_key: str | None = None
    captured_lines: list[str] = []  # Collect lines for post-run parsing
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        assert process.stdout is not None
        for line in process.stdout:
            handle.write(line)
            handle.flush()
            captured_lines.append(line)
            parsed = _parse_artifact_paths(line)
            if parsed:
                key, value = parsed
                if value:
                    artifacts[key] = value
                    pending_artifact_key = None
                else:
                    pending_artifact_key = key
                continue
            if pending_artifact_key:
                candidate = line.strip()
                if _looks_like_artifact_path(candidate):
                    artifacts[pending_artifact_key] = candidate
                    pending_artifact_key = None
    return_code = process.wait()

    # Parse actual identity from captured output
    identity = _parse_identity_from_lines(captured_lines)
    actual_store_id = _parse_store_id_from_lines(captured_lines)
    actual_phone = identity.get("user_phone") or _parse_phone_from_lines(captured_lines)
    actual_store_phone = identity.get("store_phone")
    actual_user_name = identity.get("user_name")
    actual_store_name = identity.get("store_name")

    # If still not found, try to extract from artifact folder name
    if (not actual_store_id or not actual_phone) and artifacts.get("report_path"):
        report_path = Path(artifacts["report_path"])
        folder_name = report_path.parent.name
        # Parse: 20260504T074727-paid-coupon-FZY_926025-user5609
        parts = folder_name.split("-")
        if len(parts) >= 4:
            for i, part in enumerate(parts):
                if part.startswith("user") and i > 0:
                    if not actual_store_id and i > 1 and parts[i - 1] not in ("auto", "no-store"):
                        actual_store_id = parts[i - 1]
                    if not actual_phone:
                        phone_digits = part[4:]  # Remove "user" prefix
                        if phone_digits and phone_digits != "no-user":
                            actual_phone = phone_digits
                    break

    with RUN_LOCK:
        RUN_PROCESSES.pop(run_id, None)

    # Build update fields with store_id and phone
    update_fields: dict[str, Any] = {}
    if actual_store_id:
        update_fields["store_id"] = actual_store_id
    if actual_phone:
        update_fields["phone"] = actual_phone
    if actual_store_phone:
        update_fields["store_phone"] = actual_store_phone
    if actual_user_name:
        update_fields["user_name"] = actual_user_name
    if actual_store_name:
        update_fields["store_name"] = actual_store_name

    if run_id in RUN_CANCELLED:
        RUN_CANCELLED.discard(run_id)
        _update_run(
            run_id,
            status="cancelled",
            finished_at=_utc_now(),
            exit_code=return_code,
            **artifacts,
            **update_fields,
        )
        return
    status = "succeeded" if return_code == 0 else "failed"
    error = None if return_code == 0 else f"Simulation exited with status {return_code}."
    _update_run(
        run_id,
        status=status,
        finished_at=_utc_now(),
        exit_code=return_code,
        error=error,
        **artifacts,
        **update_fields,
    )


def _create_run(request: RunCreateRequest, user_id: Optional[int] = None) -> dict[str, Any]:
    command = _build_command(request)
    created_at = _utc_now()
    
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runs (
                        user_id, flow, plan, timing, mode, store_id, phone, store_phone,
                        user_name, store_name, all_users, no_auto_provision,
                        post_order_actions, extra_args, status, command, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        request.flow,
                        request.plan,
                        request.timing,
                        request.mode,
                        request.store_id,
                        request.phone,
                        None, # store_phone will be updated after run starts
                        None, # user_name will be updated after run starts
                        None, # store_name will be updated after run starts
                        request.all_users,
                        request.no_auto_provision,
                        request.post_order_actions,
                        json.dumps(request.extra_args),
                        "queued",
                        " ".join(command),
                        created_at,
                    ),
                )
                run_id = cursor.fetchone()[0]
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    flow, plan, timing, mode, store_id, phone, store_phone, user_name, store_name,
                    all_users, no_auto_provision, post_order_actions, extra_args, status, command, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.flow,
                    request.plan,
                    request.timing,
                    request.mode,
                    request.store_id,
                    request.phone,
                    None,
                    None,
                    None,
                    int(request.all_users),
                    int(request.no_auto_provision),
                    int(request.post_order_actions) if request.post_order_actions is not None else None,
                    json.dumps(request.extra_args),
                    "queued",
                    " ".join(command),
                    created_at,
                ),
            )
            run_id = int(cursor.lastrowid)
    
    log_path = LOG_DIR / f"run-{run_id}.log"
    thread = threading.Thread(
        target=_run_simulation, args=(run_id, command, log_path), daemon=True
    )
    thread.start()
    return _get_run(run_id)


def _tail_log(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(raw_lines[-lines:])


def _safe_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (Path(SIMULATOR_WORKDIR) / path).resolve()
    else:
        path = path.resolve()
    return path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(_read_text(path))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
    return []


def _events_cache_fingerprint(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    mtime_ns = int(
        getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    )
    return str(path), mtime_ns, int(stat.st_size)


def _prune_events_cache_locked() -> None:
    while len(EVENT_CACHE) > EVENT_CACHE_MAX_ITEMS:
        EVENT_CACHE.popitem(last=False)


def _load_events_cached(path: Path) -> EventCacheEntry:
    cache_key, mtime_ns, size = _events_cache_fingerprint(path)
    with EVENT_CACHE_LOCK:
        existing = EVENT_CACHE.get(cache_key)
        if (
            existing is not None
            and existing.mtime_ns == mtime_ns
            and existing.size == size
        ):
            existing.loaded_at_monotonic = time.monotonic()
            EVENT_CACHE.move_to_end(cache_key)
            return existing

    events = _load_events(path)
    entry = EventCacheEntry(
        path=cache_key,
        mtime_ns=mtime_ns,
        size=size,
        events=events,
        metrics=_event_metrics(events),
        loaded_at_monotonic=time.monotonic(),
    )
    with EVENT_CACHE_LOCK:
        EVENT_CACHE[cache_key] = entry
        EVENT_CACHE.move_to_end(cache_key)
        _prune_events_cache_locked()
    return entry


def _truncate_text(value: str, max_len: int = 500) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    response_preview = event.get("response_preview")
    details = event.get("details")
    compact: dict[str, Any] = {
        "id": event.get("id"),
        "ts": event.get("ts") or event.get("timestamp"),
        "elapsed_ms": event.get("elapsed_ms"),
        "actor": event.get("actor"),
        "action": event.get("action"),
        "category": event.get("category"),
        "ok": event.get("ok"),
        "scenario": event.get("scenario"),
        "order_db_id": event.get("order_db_id"),
        "order_ref": event.get("order_ref"),
        "observed_status": event.get("observed_status"),
        "step": event.get("step"),
        "method": event.get("method"),
        "endpoint": event.get("endpoint"),
        "full_url": event.get("full_url"),
        "http_status": event.get("http_status"),
        "latency_ms": event.get("latency_ms"),
        "channel": event.get("channel"),
    }
    if isinstance(response_preview, str):
        compact["response_preview"] = _truncate_text(response_preview, 600)
    if isinstance(details, str):
        compact["details"] = _truncate_text(details, 400)
    return {key: value for key, value in compact.items() if value is not None}


def _status_breakdown(runs: list[dict[str, Any]]) -> dict[str, int]:
    bucket: dict[str, int] = {
        "queued": 0,
        "running": 0,
        "cancelling": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for run in runs:
        status = str(run.get("status") or "").lower()
        if status in bucket:
            bucket[status] += 1
        else:
            bucket[status] = bucket.get(status, 0) + 1
    return bucket


def _flow_breakdown(runs: list[dict[str, Any]]) -> dict[str, int]:
    bucket: dict[str, int] = {}
    for run in runs:
        flow = str(run.get("flow") or "unknown")
        bucket[flow] = bucket.get(flow, 0) + 1
    return dict(sorted(bucket.items(), key=lambda item: (-item[1], item[0])))


def _event_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    actors: dict[str, int] = {}
    actions: dict[str, int] = {}
    failed_events = 0
    http_calls = 0
    websocket_events = 0
    latency_values: list[int] = []
    for event in events:
        actor = str(event.get("actor") or "unknown")
        action = str(event.get("action") or "unknown")
        actors[actor] = actors.get(actor, 0) + 1
        actions[action] = actions.get(action, 0) + 1
        status = str(event.get("status") or "").lower()
        ok_flag = event.get("ok")
        if isinstance(ok_flag, bool):
            if not ok_flag:
                failed_events += 1
        elif status in {"error", "failed", "failure"}:
            failed_events += 1
        metadata = event.get("metadata")
        saw_http = False
        if isinstance(metadata, dict) and "http_status" in metadata:
            saw_http = True
            latency = metadata.get("latency_ms")
            if isinstance(latency, (int, float)):
                latency_values.append(int(latency))
        if "method" in event or "endpoint" in event or "http_status" in event:
            saw_http = True
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)):
                latency_values.append(int(latency))
        if saw_http:
            http_calls += 1
        if actor == "websocket" or action.startswith("ws_") or "websocket" in action:
            websocket_events += 1
        if event.get("channel"):
            websocket_events += 1
    avg_latency_ms = round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0
    return {
        "total_events": len(events),
        "failed_events": failed_events,
        "http_calls": http_calls,
        "websocket_events": websocket_events,
        "avg_http_latency_ms": avg_latency_ms,
        "top_actors": dict(sorted(actors.items(), key=lambda item: (-item[1], item[0]))[:10]),
        "top_actions": dict(sorted(actions.items(), key=lambda item: (-item[1], item[0]))[:10]),
    }


def _run_autopilot_job() -> None:
    payload = RunCreateRequest(
        flow="doctor",
        plan="sim_actors.json",
        timing="fast",
    )
    try:
        _create_run(payload)
    except Exception:
        # Keep scheduler resilient; errors are visible in API logs.
        return


_init_db()
scheduler = BackgroundScheduler(timezone="UTC")
if _as_bool(os.getenv("SIM_GUI_ENABLE_DAILY_DOCTOR"), default=False):
    scheduler.add_job(
        _run_autopilot_job,
        trigger="interval",
        seconds=AUTO_REFRESH_SECONDS,
        id="doctor-autopilot",
        replace_existing=True,
    )
    scheduler.start()

app = FastAPI(title="Fainzy Simulator Web API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOW_ORIGINS == "*" else [item.strip() for item in ALLOW_ORIGINS.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize authentication if enabled
if AUTH_ENABLED and USE_POSTGRES:
    try:
        init_auth(POSTGRES_URL)
        LOGGER.info("Authentication system initialized")
    except Exception as e:
        LOGGER.error(f"Failed to initialize authentication: {e}")
        AUTH_ENABLED = False


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    path = request.url.path
    if path.startswith(MONITORED_ENDPOINT_PREFIXES):
        if elapsed_ms >= SLOW_REQUEST_THRESHOLD_MS:
            LOGGER.warning(
                "slow request path=%s status=%s elapsed_ms=%.2f",
                path,
                response.status_code,
                elapsed_ms,
            )
        else:
            LOGGER.debug(
                "request path=%s status=%s elapsed_ms=%.2f",
                path,
                response.status_code,
                elapsed_ms,
            )
    return response


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "project_dir": PROJECT_DIR,
        "simulator_workdir": SIMULATOR_WORKDIR,
        "db_path": DB_PATH,
    }


@app.get("/api/v1/flows")
def list_flows() -> dict[str, Any]:
    return {"flows": sorted(FLOW_PRESETS.keys())}


# Authentication endpoints
@app.post("/api/v1/auth/register")
def register_user(user_data: UserCreate) -> dict[str, Any]:
    """Register a new user"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    auth_manager = get_auth_manager()
    try:
        user = auth_manager.create_user(user_data)
        return {"message": "User created successfully", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create user")


@app.post("/api/v1/auth/login")
def login_user(credentials: UserLogin) -> TokenResponse:
    """Authenticate user and return tokens"""
    if not AUTH_ENABLED:
        # Return default tokens for backward compatibility
        return TokenResponse(
            access_token="default-token",
            refresh_token="default-refresh",
            expires_in=900
        )
    
    auth_manager = get_auth_manager()
    user = auth_manager.authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_manager.create_access_token({"sub": str(user['id']), "username": user['username']})
    refresh_token = auth_manager.create_refresh_token(user['id'])
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/v1/auth/refresh")
def refresh_token(payload: RefreshTokenRequest) -> TokenResponse:
    """Refresh access token"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    auth_manager = get_auth_manager()
    tokens = auth_manager.refresh_access_token(payload.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return tokens


@app.post("/api/v1/auth/logout")
def logout(payload: RefreshTokenRequest) -> dict[str, Any]:
    """Logout user by invalidating refresh token"""
    if not AUTH_ENABLED:
        return {"message": "Logged out successfully"}
    
    auth_manager = get_auth_manager()
    success = auth_manager.logout(payload.refresh_token)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to logout")
    
    return {"message": "Logged out successfully"}


@app.get("/api/v1/auth/me")
def get_current_user_profile(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Get current user profile"""
    if not AUTH_ENABLED:
        return {"username": "system", "role": "admin"}
    
    return {
        "id": current_user['id'],
        "username": current_user['username'],
        "email": current_user.get('email'),
        "role": current_user['role'],
        "created_at": current_user['created_at'],
        "last_login": current_user.get('last_login'),
        "preferences": current_user.get('preferences', {})
    }

# Admin endpoints
@app.get("/api/v1/admin/users")
def list_users(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """List all users (admin only)"""
    if not AUTH_ENABLED:
        return {"users": []}
    
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    auth_manager = get_auth_manager()
    users = auth_manager.list_users()
    return {"users": users}

@app.post("/api/v1/admin/users")
def create_user(user_data: UserCreate, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Create a new user (admin only)"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    auth_manager = get_auth_manager()
    try:
        user = auth_manager.create_user(user_data)
        return {"message": "User created successfully", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create user")

@app.put("/api/v1/admin/users/{user_id}")
def update_user(user_id: int, user_data: dict, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Update a user (admin only)"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    auth_manager = get_auth_manager()
    try:
        user = auth_manager.update_user(user_id, user_data)
        return {"message": "User updated successfully", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update user")

@app.delete("/api/v1/admin/users/{user_id}")
def delete_user(user_id: int, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Delete a user (admin only)"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if user_id == current_user['id']:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    auth_manager = get_auth_manager()
    try:
        success = auth_manager.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete user")

@app.post("/api/v1/admin/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Reset user password (admin only)"""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=501, detail="Authentication not enabled")
    
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    auth_manager = get_auth_manager()
    try:
        success = auth_manager.reset_password(user_id, payload.new_password)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "Password reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to reset password")


@app.get("/api/v1/runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: Optional[dict] = Depends(get_optional_user)
) -> dict[str, Any]:
    user_id = current_user.get('id') if current_user else None
    runs = _list_runs(limit=limit, offset=offset, user_id=user_id)
    total = _count_runs(user_id=user_id)
    return {"runs": runs, "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/runs/count")
def count_runs() -> dict[str, Any]:
    return {"count": _count_runs()}


@app.get("/api/v1/dashboard/summary")
def dashboard_summary() -> dict[str, Any]:
    runs = _list_runs(limit=200)
    statuses = _status_breakdown(runs)
    total = len(runs)
    succeeded = statuses.get("succeeded", 0)
    success_rate = round((succeeded / total) * 100, 2) if total else 0.0
    return {
        "total_runs": total,
        "status_breakdown": statuses,
        "flow_breakdown": _flow_breakdown(runs),
        "success_rate": success_rate,
    }


@app.post("/api/v1/runs")
def create_run(request: RunCreateRequest, current_user: Optional[dict] = Depends(get_optional_user)) -> dict[str, Any]:
    user_id = current_user.get('id') if current_user else None
    return _create_run(request, user_id)


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    return _get_run(run_id)


@app.get("/api/v1/runs/{run_id}/log")
def get_run_log(run_id: int, tail: int = Query(default=200, ge=1, le=5000)) -> dict[str, Any]:
    run = _get_run(run_id)
    log_path = run.get("log_path")
    if not log_path:
        return {"run_id": run_id, "log": ""}
    return {"run_id": run_id, "log": _tail_log(Path(log_path), tail)}


@app.get("/api/v1/runs/{run_id}/artifacts/{kind}")
def get_run_artifact(
    run_id: int,
    kind: Literal["report", "story", "events"],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
    compact: bool = Query(default=True),
) -> dict[str, Any]:
    run = _get_run(run_id)
    mapping = {
        "report": run.get("report_path"),
        "story": run.get("story_path"),
        "events": run.get("events_path"),
    }
    path = _safe_path(mapping[kind])
    if path is None or not path.exists():
        return {"run_id": run_id, "kind": kind, "available": False, "content": None}
    if kind in {"report", "story"}:
        return {
            "run_id": run_id,
            "kind": kind,
            "available": True,
            "path": str(path),
            "content": _read_text(path),
        }
    cached = _load_events_cached(path)
    total_count = len(cached.events)
    subset = cached.events[offset : offset + limit]
    if compact:
        subset = [_compact_event(event) for event in subset]
    return {
        "run_id": run_id,
        "kind": kind,
        "available": True,
        "path": str(path),
        "offset": offset,
        "limit": limit,
        "count": len(subset),
        "total_count": total_count,
        "content": subset,
    }


@app.get("/api/v1/runs/{run_id}/metrics")
def get_run_metrics(run_id: int) -> dict[str, Any]:
    run = _get_run(run_id)
    path = _safe_path(run.get("events_path"))
    if path is None or not path.exists():
        return {
            "run_id": run_id,
            "available": False,
            "metrics": {
                "total_events": 0,
                "failed_events": 0,
                "http_calls": 0,
                "websocket_events": 0,
                "top_actors": {},
                "top_actions": {},
            },
        }
    cached = _load_events_cached(path)
    return {"run_id": run_id, "available": True, "metrics": cached.metrics}


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: int) -> dict[str, Any]:
    _get_run(run_id)
    with RUN_LOCK:
        process = RUN_PROCESSES.get(run_id)
        if process is None:
            raise HTTPException(status_code=409, detail=f"Run {run_id} is not active.")
        RUN_CANCELLED.add(run_id)
        process.terminate()
    _update_run(run_id, status="cancelling")
    return {"run_id": run_id, "status": "cancelling"}


@app.delete("/api/v1/runs/{run_id}")
def delete_run(run_id: int) -> dict[str, Any]:
    """Delete a run and its associated folder."""
    run = _get_run(run_id)

    # Check if run is active (process exists and is actually running)
    with RUN_LOCK:
        process = RUN_PROCESSES.get(run_id)
        if process is not None:
            # Check if process is actually still running
            if process.poll() is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Run {run_id} is still active. Cancel the run before deleting."
                )
            # Process has finished but wasn't cleaned up - remove it
            RUN_PROCESSES.pop(run_id, None)
    
    # Get run folder path from log_path or create expected path
    log_path = run.get("log_path")
    run_folder = None
    
    if log_path:
        log_file = Path(log_path)
        # Run folder is the parent of the log file
        run_folder = log_file.parent
    else:
        # Fallback: try to find folder by run ID pattern
        # Look for folders containing run artifacts
        for folder_path in LOG_DIR.iterdir():
            if folder_path.is_dir():
                # Check if this folder might belong to the run
                # by checking if it contains expected files
                if (folder_path / "events.json").exists() or (folder_path / "report.md").exists():
                    # Simple heuristic: check if folder is old enough to be completed
                    # and not recently created (to avoid deleting wrong folder)
                    created_at = run.get("created_at")
                    if created_at:
                        try:
                            from datetime import datetime
                            run_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            folder_time = datetime.fromtimestamp(folder_path.stat().st_mtime)
                            # If folder time is within 1 hour of run time, assume it's the right one
                            if abs((folder_time - run_time).total_seconds()) < 3600:
                                run_folder = folder_path
                                break
                        except Exception:
                            pass
    
    # Delete the run folder if found
    deleted_files = []
    if run_folder and run_folder.exists():
        try:
            # List files before deletion for response
            for file_path in run_folder.rglob("*"):
                if file_path.is_file():
                    deleted_files.append(str(file_path.relative_to(run_folder)))
            
            # Delete the entire folder
            import shutil
            shutil.rmtree(run_folder)
            LOGGER.info(f"Deleted run folder: {run_folder}")
        except Exception as e:
            LOGGER.error(f"Failed to delete run folder {run_folder}: {e}")
            # Continue with database deletion even if folder deletion fails
    
    # Delete from database
    try:
        if USE_POSTGRES:
            conn = _get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM runs WHERE id = %s", (run_id,))
                conn.commit()
            finally:
                conn.close()
        else:
            with DB_LOCK, _db() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()
        LOGGER.info(f"Deleted run {run_id} from database")
    except Exception as e:
        LOGGER.error(f"Failed to delete run {run_id} from database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete run from database: {str(e)}"
        )
    
    return {
        "run_id": run_id,
        "deleted": True,
        "deleted_files": deleted_files,
        "message": f"Run {run_id} and its artifacts have been deleted."
    }
