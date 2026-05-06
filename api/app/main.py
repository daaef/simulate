from __future__ import annotations

import logging
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from flow_presets import FLOW_PRESETS
from .admin.routes import router as admin_router
from .archives.routes import router as archives_router
from .archives.service import configure_runtime as configure_archives_runtime
from .auth import service as auth_service
from .auth.routes import router as auth_router
from .auth.dependencies import SESSION_COOKIE_NAME
from .retention.routes import router as retention_router
from .retention.service import configure_runtime as configure_retention_runtime
from .simulation_plans.models import SimulationPlanUpsertRequest
from .simulation_plans.routes import router as simulation_plans_router
from .simulation_plans.service import configure_runtime as configure_simulation_plans_runtime
from .runs.models import RunCreateRequest
from .runs.routes import (
    router as runs_router,
    list_flows,
    list_runs,
    count_runs,
    dashboard_summary,
    create_run,
    get_run,
    get_run_log,
    get_run_artifact,
    get_run_metrics,
    cancel_run,
    delete_run,
)
from .runs.service import configure_runtime as configure_runs_runtime

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


SIMULATOR_WORKDIR = os.getenv("SIMULATOR_WORKDIR", "/workspace")
PROJECT_DIR = os.getenv("SIMULATOR_PROJECT_DIR", "/workspace/simulate")
DB_PATH = os.getenv("RUN_DB_PATH", "/workspace/simulate/runs/web-gui.sqlite")
LOG_DIR = Path(os.getenv("RUN_LOG_DIR", "/workspace/simulate/runs/web-gui"))
SIMULATION_PLANS_DIR = Path(
    os.getenv("SIM_GUI_PLANS_DIR", str(Path(PROJECT_DIR) / "runs" / "gui-plans"))
)
AUTO_REFRESH_SECONDS = max(5, int(os.getenv("RUN_AUTO_REFRESH_SECONDS", "30")))
ALLOW_ORIGINS = os.getenv("WEB_CORS_ORIGINS", "*")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
SIMULATION_PLANS_DIR.mkdir(parents=True, exist_ok=True)

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
SIMULATION_PLAN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


@dataclass
class EventCacheEntry:
    path: str
    mtime_ns: int
    size: int
    events: list[dict[str, Any]]
    metrics: dict[str, Any]
    loaded_at_monotonic: float


EVENT_CACHE: "OrderedDict[str, EventCacheEntry]" = OrderedDict()
ACTIVE_RETENTION_DAYS = 30
ARCHIVE_RETENTION_DAYS = 180


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
        _migrate_postgres_schema()
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
                error TEXT,
                execution_snapshot TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                flow TEXT NOT NULL,
                plan TEXT NOT NULL,
                timing TEXT NOT NULL,
                mode TEXT,
                store_id TEXT,
                phone TEXT,
                all_users INTEGER NOT NULL DEFAULT 0,
                no_auto_provision INTEGER NOT NULL DEFAULT 0,
                post_order_actions INTEGER,
                extra_args TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
    if "execution_snapshot" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN execution_snapshot TEXT")
    profile_columns = [row[1] for row in conn.execute("PRAGMA table_info(run_profiles)").fetchall()]
    if profile_columns and "description" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN description TEXT")


def _migrate_postgres_schema() -> None:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS store_phone TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_name TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS store_name TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS execution_snapshot JSONB")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS run_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    name VARCHAR(120) NOT NULL,
                    description TEXT,
                    flow VARCHAR(50) NOT NULL,
                    plan VARCHAR(255) NOT NULL,
                    timing VARCHAR(20) NOT NULL,
                    mode VARCHAR(20),
                    store_id VARCHAR(50),
                    phone VARCHAR(20),
                    all_users BOOLEAN NOT NULL DEFAULT FALSE,
                    no_auto_provision BOOLEAN NOT NULL DEFAULT FALSE,
                    post_order_actions BOOLEAN,
                    extra_args JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        conn.commit()
    finally:
        conn.close()

def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["all_users"] = bool(payload["all_users"])
    payload["no_auto_provision"] = bool(payload["no_auto_provision"])
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
    if payload.get("execution_snapshot"):
        payload["execution_snapshot"] = json.loads(payload["execution_snapshot"])
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
        snapshot = payload.get("execution_snapshot")
        if isinstance(snapshot, str) and snapshot:
            payload["execution_snapshot"] = json.loads(snapshot)
        return payload


def _profile_row_to_dict_any(row) -> dict[str, Any]:
    payload = dict(row)
    payload["all_users"] = bool(payload["all_users"])
    payload["no_auto_provision"] = bool(payload["no_auto_provision"])
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    extra_args = payload.get("extra_args")
    if isinstance(extra_args, str):
        payload["extra_args"] = json.loads(extra_args or "[]")
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


def _resolve_persisted_user_id(user_id: Optional[int]) -> Optional[int]:
    if user_id is None:
        return None
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
                row = cursor.fetchone()
                return user_id if row else None
        finally:
            conn.close()
    return user_id


def _list_run_profiles() -> list[dict[str, Any]]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT * FROM run_profiles ORDER BY updated_at DESC, id DESC")
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute("SELECT * FROM run_profiles ORDER BY updated_at DESC, id DESC").fetchall()
    return [_profile_row_to_dict_any(row) for row in rows]


def _get_run_profile(profile_id: int) -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT * FROM run_profiles WHERE id = %s", (profile_id,))
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail=f"Run profile {profile_id} not found.")
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute("SELECT * FROM run_profiles WHERE id = ?", (profile_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run profile {profile_id} not found.")
    return _profile_row_to_dict_any(row)

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
    store_id: str | None = None


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


def _build_execution_snapshot(request: RunCreateRequest, command: list[str], created_at: str) -> dict[str, Any]:
    return {
        "version": 1,
        "flow": request.flow,
        "plan": request.plan,
        "timing": request.timing,
        "mode": request.mode,
        "store_id": request.store_id,
        "phone": request.phone,
        "all_users": request.all_users,
        "no_auto_provision": request.no_auto_provision,
        "post_order_actions": request.post_order_actions,
        "extra_args": request.extra_args,
        "command": " ".join(command),
        "created_at": created_at,
    }


def _profile_request_to_run_request(profile: dict[str, Any]) -> RunCreateRequest:
    return RunCreateRequest(
        flow=profile["flow"],
        plan=profile["plan"],
        timing=profile["timing"],
        mode=profile.get("mode"),
        store_id=profile.get("store_id"),
        phone=profile.get("phone"),
        all_users=bool(profile.get("all_users")),
        no_auto_provision=bool(profile.get("no_auto_provision")),
        post_order_actions=profile.get("post_order_actions"),
        extra_args=list(profile.get("extra_args") or []),
    )


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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
    execution_snapshot = _build_execution_snapshot(request, command, created_at)
    persisted_user_id = _resolve_persisted_user_id(user_id)
    
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runs (
                        user_id, flow, plan, timing, mode, store_id, phone, store_phone,
                        user_name, store_name, all_users, no_auto_provision,
                        post_order_actions, extra_args, status, command, created_at, execution_snapshot
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        persisted_user_id,
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
                        json.dumps(execution_snapshot),
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
                    all_users, no_auto_provision, post_order_actions, extra_args, status, command, created_at, execution_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(execution_snapshot),
                ),
            )
            run_id = int(cursor.lastrowid)
    
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"run-{run_id}.log"
    thread = threading.Thread(
        target=_run_simulation, args=(run_id, command, log_path), daemon=True
    )
    thread.start()
    return _get_run(run_id)


def _list_run_profiles_payload() -> dict[str, Any]:
    return {"profiles": _list_run_profiles()}


def _create_run_profile(request, user_id: Optional[int] = None) -> dict[str, Any]:
    created_at = _utc_now()
    persisted_user_id = _resolve_persisted_user_id(user_id)
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO run_profiles (
                        user_id, name, description, flow, plan, timing, mode, store_id, phone,
                        all_users, no_auto_provision, post_order_actions, extra_args, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        persisted_user_id,
                        request.name,
                        request.description,
                        request.flow,
                        request.plan,
                        request.timing,
                        request.mode,
                        request.store_id,
                        request.phone,
                        request.all_users,
                        request.no_auto_provision,
                        request.post_order_actions,
                        json.dumps(request.extra_args),
                        created_at,
                        created_at,
                    ),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO run_profiles (
                    user_id, name, description, flow, plan, timing, mode, store_id, phone,
                    all_users, no_auto_provision, post_order_actions, extra_args, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persisted_user_id,
                    request.name,
                    request.description,
                    request.flow,
                    request.plan,
                    request.timing,
                    request.mode,
                    request.store_id,
                    request.phone,
                    int(request.all_users),
                    int(request.no_auto_provision),
                    int(request.post_order_actions) if request.post_order_actions is not None else None,
                    json.dumps(request.extra_args),
                    created_at,
                    created_at,
                ),
            )
            row = conn.execute("SELECT * FROM run_profiles WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return {"profile": _profile_row_to_dict_any(row)}


def _update_run_profile(profile_id: int, request, user_id: Optional[int] = None) -> dict[str, Any]:
    _get_run_profile(profile_id)
    updated_at = _utc_now()
    fields = {
        "name": request.name,
        "description": request.description,
        "flow": request.flow,
        "plan": request.plan,
        "timing": request.timing,
        "mode": request.mode,
        "store_id": request.store_id,
        "phone": request.phone,
        "all_users": request.all_users,
        "no_auto_provision": request.no_auto_provision,
        "post_order_actions": request.post_order_actions,
        "extra_args": json.dumps(request.extra_args),
        "updated_at": updated_at,
    }
    persisted_user_id = _resolve_persisted_user_id(user_id)
    if persisted_user_id is not None:
        fields["user_id"] = persisted_user_id

    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                keys = list(fields.keys())
                values = [fields[key] for key in keys]
                assignment = ", ".join(f"{key} = %s" for key in keys)
                cursor.execute(
                    f"UPDATE run_profiles SET {assignment} WHERE id = %s RETURNING *",
                    (*values, profile_id),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        keys = list(fields.keys())
        values = [fields[key] for key in keys]
        assignment = ", ".join(f"{key} = ?" for key in keys)
        with DB_LOCK, _db() as conn:
            conn.execute(
                f"UPDATE run_profiles SET {assignment} WHERE id = ?",
                (*values, profile_id),
            )
            row = conn.execute("SELECT * FROM run_profiles WHERE id = ?", (profile_id,)).fetchone()
    return {"profile": _profile_row_to_dict_any(row)}


def _delete_run_profile(profile_id: int) -> dict[str, Any]:
    _get_run_profile(profile_id)
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM run_profiles WHERE id = %s", (profile_id,))
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            conn.execute("DELETE FROM run_profiles WHERE id = ?", (profile_id,))
    return {"profile_id": profile_id, "deleted": True}


def _launch_run_profile(profile_id: int, user_id: Optional[int] = None) -> dict[str, Any]:
    profile = _get_run_profile(profile_id)
    request = _profile_request_to_run_request(profile)
    run = _create_run(request, user_id)
    return {"profile": profile, "run": run}


def _run_execution_snapshot_payload(run_id: int) -> dict[str, Any]:
    run = _get_run(run_id)
    snapshot = run.get("execution_snapshot") or {}
    return {"run_id": run_id, "available": bool(snapshot), "snapshot": snapshot}


def _replay_run_logic(run_id: int, user_id: Optional[int] = None) -> dict[str, Any]:
    run = _get_run(run_id)
    snapshot = run.get("execution_snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        raise HTTPException(status_code=409, detail=f"Run {run_id} does not have a replayable execution snapshot.")
    request = RunCreateRequest(
        flow=snapshot["flow"],
        plan=snapshot["plan"],
        timing=snapshot["timing"],
        mode=snapshot.get("mode"),
        store_id=snapshot.get("store_id"),
        phone=snapshot.get("phone"),
        all_users=bool(snapshot.get("all_users")),
        no_auto_provision=bool(snapshot.get("no_auto_provision")),
        post_order_actions=snapshot.get("post_order_actions"),
        extra_args=list(snapshot.get("extra_args") or []),
    )
    replayed_run = _create_run(request, user_id)
    return {"source_run_id": run_id, "run": replayed_run, "snapshot": snapshot}


def _simulation_plans_dir() -> Path:
    SIMULATION_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return SIMULATION_PLANS_DIR


def _slugify_plan_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:64] or "simulation-plan"


def _validate_plan_id(plan_id: str) -> str:
    if not SIMULATION_PLAN_ID_PATTERN.match(plan_id):
        raise HTTPException(status_code=404, detail=f"Simulation plan {plan_id!r} not found.")
    return plan_id


def _simulation_plan_path(plan_id: str) -> Path:
    safe_id = _validate_plan_id(plan_id)
    return _simulation_plans_dir() / f"{safe_id}.json"


def _launchable_plan_path(path: Path) -> str:
    return f"runs/gui-plans/{path.name}"


def _validate_simulation_plan_content(content: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise HTTPException(status_code=400, detail="Simulation plan content must be a JSON object.")
    try:
        from run_plan import PlanValidationError, RunPlan

        plan = RunPlan.from_dict(content)
        plan.validate(strict=False)
    except PlanValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid simulation plan: {exc}") from exc
    return dict(content)


def _read_simulation_plan_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Simulation plan {path.stem!r} not found.") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Stored simulation plan {path.stem!r} is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Stored simulation plan {path.stem!r} must be a JSON object.")
    return payload


def _simulation_plan_payload(path: Path) -> dict[str, Any]:
    content = _read_simulation_plan_file(path)
    name = str(content.get("name") or path.stem.replace("-", " ").title())
    return {
        "id": path.stem,
        "name": name,
        "path": _launchable_plan_path(path),
        "content": content,
    }


def _list_simulation_plans_payload() -> dict[str, Any]:
    plans = [
        _simulation_plan_payload(path)
        for path in sorted(_simulation_plans_dir().glob("*.json"))
        if path.is_file()
    ]
    return {"plans": plans}


def _get_simulation_plan_payload(plan_id: str) -> dict[str, Any]:
    return {"plan": _simulation_plan_payload(_simulation_plan_path(plan_id))}


def _next_simulation_plan_path(name: str) -> Path:
    base = _slugify_plan_name(name)
    candidate = _simulation_plan_path(base)
    suffix = 2
    while candidate.exists():
        candidate = _simulation_plan_path(f"{base}-{suffix}")
        suffix += 1
    return candidate


def _write_simulation_plan(path: Path, request: SimulationPlanUpsertRequest) -> dict[str, Any]:
    content = _validate_simulation_plan_content(request.content)
    content["name"] = request.name.strip()
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"plan": _simulation_plan_payload(path)}


def _create_simulation_plan(request: SimulationPlanUpsertRequest) -> dict[str, Any]:
    return _write_simulation_plan(_next_simulation_plan_path(request.name), request)


def _update_simulation_plan(plan_id: str, request: SimulationPlanUpsertRequest) -> dict[str, Any]:
    path = _simulation_plan_path(plan_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Simulation plan {plan_id!r} not found.")
    return _write_simulation_plan(path, request)


def _delete_simulation_plan(plan_id: str) -> dict[str, Any]:
    path = _simulation_plan_path(plan_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Simulation plan {plan_id!r} not found.")
    path.unlink()
    return {"plan_id": plan_id, "deleted": True}


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


def _parse_run_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def _retention_buckets(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    active_cutoff = ACTIVE_RETENTION_DAYS
    archive_cutoff = ARCHIVE_RETENTION_DAYS
    buckets = {"active": [], "archive": [], "purge": []}
    for run in runs:
        created_at = _parse_run_timestamp(run.get("created_at"))
        if created_at is None:
            buckets["active"].append(run)
            continue
        age_days = max(0, int((now - created_at).total_seconds() // 86400))
        if age_days < active_cutoff:
            buckets["active"].append(run)
        elif age_days < archive_cutoff:
            buckets["archive"].append(run)
        else:
            buckets["purge"].append(run)
    return buckets


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


def _dashboard_summary_payload() -> dict[str, Any]:
    runs = _list_runs(limit=200)
    statuses = _status_breakdown(runs)
    total = len(runs)
    succeeded = statuses.get("succeeded", 0)
    success_rate = round((succeeded / total) * 100, 2) if total else 0.0
    buckets = _retention_buckets(runs)
    now = datetime.now(timezone.utc)
    recent_failures = 0
    active_runs = 0
    degraded_runs = 0
    for run in runs:
        status = str(run.get("status") or "").lower()
        if status in {"queued", "running", "cancelling"}:
            active_runs += 1
        if status == "failed":
            created_at = _parse_run_timestamp(run.get("created_at"))
            if created_at and (now - created_at).total_seconds() <= 86400:
                recent_failures += 1
            degraded_runs += 1
    return {
        "total_runs": total,
        "status_breakdown": statuses,
        "flow_breakdown": _flow_breakdown(runs),
        "success_rate": success_rate,
        "active_runs": active_runs,
        "failed_last_24h": recent_failures,
        "degraded_runs": degraded_runs,
        "archive_backlog": len(buckets["archive"]),
        "purge_backlog": len(buckets["purge"]),
    }


def _archives_summary_payload() -> dict[str, Any]:
    runs = _list_runs(limit=500)
    buckets = _retention_buckets(runs)
    return {
        "policy_days": {"active": ACTIVE_RETENTION_DAYS, "archive": ARCHIVE_RETENTION_DAYS},
        "counts": {
            "active": len(buckets["active"]),
            "archive_ready": len(buckets["archive"]),
            "purge_ready": len(buckets["purge"]),
        },
    }


def _archives_runs_payload(limit: int, offset: int) -> dict[str, Any]:
    runs = _list_runs(limit=500)
    buckets = _retention_buckets(runs)
    archive_runs = buckets["archive"] + buckets["purge"]
    page = archive_runs[offset : offset + limit]
    return {
        "runs": page,
        "total": len(archive_runs),
        "limit": limit,
        "offset": offset,
    }


def _retention_summary_payload() -> dict[str, Any]:
    runs = _list_runs(limit=500)
    buckets = _retention_buckets(runs)
    raw_artifact_runs = sum(1 for run in runs if any(run.get(field) for field in ARTIFACT_FIELDS) or run.get("log_path"))
    return {
        "policies": {
            "active_days": ACTIVE_RETENTION_DAYS,
            "archive_days": ARCHIVE_RETENTION_DAYS,
        },
        "queue": {
            "archive_ready": len(buckets["archive"]),
            "purge_ready": len(buckets["purge"]),
            "artifact_backed_runs": raw_artifact_runs,
        },
        "status": "observation-only",
    }


def _run_log_payload(run_id: int, tail: int) -> dict[str, Any]:
    run = _get_run(run_id)
    log_path = run.get("log_path")
    if not log_path:
        return {"run_id": run_id, "log": ""}
    return {"run_id": run_id, "log": _tail_log(Path(log_path), tail)}


def _run_artifact_payload(
    run_id: int,
    kind: Literal["report", "story", "events"],
    offset: int,
    limit: int,
    compact: bool,
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
        "total_count": len(cached.events),
        "content": subset,
    }


def _run_metrics_payload(run_id: int) -> dict[str, Any]:
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


def _cancel_run_logic(run_id: int) -> dict[str, Any]:
    _get_run(run_id)
    with RUN_LOCK:
        process = RUN_PROCESSES.get(run_id)
        if process is None:
            raise HTTPException(status_code=409, detail=f"Run {run_id} is not active.")
        RUN_CANCELLED.add(run_id)
        process.terminate()
    _update_run(run_id, status="cancelling")
    return {"run_id": run_id, "status": "cancelling"}


def _protected_delete_dirs() -> set[Path]:
    project_root = Path(PROJECT_DIR).resolve()
    workdir_root = Path(SIMULATOR_WORKDIR).resolve()
    log_dir = LOG_DIR.resolve()
    return {
        project_root,
        workdir_root,
        project_root / "runs",
        log_dir,
    }


def _record_deleted_file(file_path: Path, deleted_files: list[str]) -> None:
    deleted_files.append(str(file_path))


def _delete_expected_file(file_path: Path, deleted_files: list[str], missing_files: list[str]) -> None:
    if file_path.exists():
        file_path.unlink()
        _record_deleted_file(file_path, deleted_files)
        return
    missing_files.append(str(file_path))


def _delete_artifact_paths(
    artifact_paths: list[Path],
    deleted_files: list[str],
    missing_files: list[str],
) -> None:
    if not artifact_paths:
        return

    artifact_dirs = {path.parent for path in artifact_paths}
    if len(artifact_dirs) == 1:
        artifact_dir = next(iter(artifact_dirs))
        if artifact_dir.exists() and artifact_dir.is_dir() and artifact_dir.resolve() not in _protected_delete_dirs():
            for file_path in artifact_dir.rglob("*"):
                if file_path.is_file():
                    _record_deleted_file(file_path, deleted_files)
            shutil.rmtree(artifact_dir)
            for file_path in artifact_paths:
                if not file_path.exists() and str(file_path) not in deleted_files:
                    missing_files.append(str(file_path))
            LOGGER.info(f"Deleted run artifact folder: {artifact_dir}")
            return

    for file_path in artifact_paths:
        _delete_expected_file(file_path, deleted_files, missing_files)


def _delete_run_logic(run_id: int) -> dict[str, Any]:
    run = _get_run(run_id)

    with RUN_LOCK:
        process = RUN_PROCESSES.get(run_id)
        if process is not None:
            if process.poll() is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Run {run_id} is still active. Cancel the run before deleting."
                )
            RUN_PROCESSES.pop(run_id, None)

    deleted_files: list[str] = []
    missing_files: list[str] = []

    log_path = _safe_path(run.get("log_path"))
    if log_path is not None:
        try:
            _delete_expected_file(log_path, deleted_files, missing_files)
        except Exception as exc:
            LOGGER.error(f"Failed to delete run log {log_path}: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to delete run log: {str(exc)}")

    artifact_paths = [
        path
        for field in ARTIFACT_FIELDS
        if (path := _safe_path(run.get(field))) is not None
    ]
    try:
        _delete_artifact_paths(artifact_paths, deleted_files, missing_files)
    except Exception as exc:
        LOGGER.error(f"Failed to delete run artifacts for run {run_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to delete run artifacts: {str(exc)}")

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
    except Exception as exc:
        LOGGER.error(f"Failed to delete run {run_id} from database: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete run from database: {str(exc)}"
        )

    return {
        "run_id": run_id,
        "deleted": True,
        "deleted_files": deleted_files,
        "missing_files": missing_files,
        "message": f"Run {run_id} and its available artifacts have been deleted."
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
auth_service.init_auth_system(POSTGRES_URL, USE_POSTGRES)
configure_runs_runtime(
    list_flows=lambda: {"flows": sorted(FLOW_PRESETS.keys())},
    list_runs=lambda limit, offset: {"runs": _list_runs(limit=limit, offset=offset), "total": _count_runs(), "limit": limit, "offset": offset},
    count_runs=lambda: {"count": _count_runs()},
    dashboard_summary=lambda: _dashboard_summary_payload(),
    create_run=lambda request, user_id: _create_run(request, user_id),
    get_run=lambda run_id: _get_run(run_id),
    get_run_log=lambda run_id, tail: _run_log_payload(run_id, tail),
    get_run_artifact=lambda run_id, kind, offset, limit, compact: _run_artifact_payload(run_id, kind, offset, limit, compact),
    get_run_metrics=lambda run_id: _run_metrics_payload(run_id),
    cancel_run=lambda run_id: _cancel_run_logic(run_id),
    delete_run=lambda run_id: _delete_run_logic(run_id),
    list_profiles=lambda: _list_run_profiles_payload(),
    create_profile=lambda request, user_id: _create_run_profile(request, user_id),
    update_profile=lambda profile_id, request, user_id: _update_run_profile(profile_id, request, user_id),
    delete_profile=lambda profile_id: _delete_run_profile(profile_id),
    launch_profile=lambda profile_id, user_id: _launch_run_profile(profile_id, user_id),
    get_execution_snapshot=lambda run_id: _run_execution_snapshot_payload(run_id),
    replay_run=lambda run_id, user_id: _replay_run_logic(run_id, user_id),
)
configure_archives_runtime(
    summary=lambda: _archives_summary_payload(),
    list_runs=lambda limit, offset: _archives_runs_payload(limit, offset),
)
configure_retention_runtime(
    summary=lambda: _retention_summary_payload(),
)
configure_simulation_plans_runtime(
    list_plans=lambda: _list_simulation_plans_payload(),
    get_plan=lambda plan_id: _get_simulation_plan_payload(plan_id),
    create_plan=lambda request: _create_simulation_plan(request),
    update_plan=lambda plan_id, request: _update_simulation_plan(plan_id, request),
    delete_plan=lambda plan_id: _delete_simulation_plan(plan_id),
)


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


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(runs_router)
app.include_router(archives_router)
app.include_router(retention_router)
app.include_router(simulation_plans_router)
