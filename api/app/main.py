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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from flow_presets import FLOW_PRESETS
from .admin.routes import router as admin_router
from .alerts.routes import router as alerts_router
from .alerts.service import configure_runtime as configure_alerts_runtime
from .archives.routes import router as archives_router
from .archives.service import configure_runtime as configure_archives_runtime
from .auth import service as auth_service
from .auth.routes import router as auth_router
from .auth.dependencies import SESSION_COOKIE_NAME
from .retention.routes import router as retention_router
from .retention.service import configure_runtime as configure_retention_runtime
from .schedules.models import ScheduleUpsertRequest
from .schedules.routes import router as schedules_router
from .schedules.service import configure_runtime as configure_schedules_runtime
from .system.models import TimezonePolicyUpdateRequest
from .system.routes import router as system_router
from .system.service import configure_runtime as configure_system_runtime
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
    "/api/v1/schedules",
    "/api/v1/alerts",
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                schedule_type TEXT NOT NULL DEFAULT 'simple',
                status TEXT NOT NULL DEFAULT 'active',
                profile_id INTEGER,
                anchor_start_at TEXT,
                period TEXT,
                stop_rule TEXT,
                end_at TEXT,
                duration_seconds INTEGER,
                runs_per_period INTEGER NOT NULL DEFAULT 1,
                cadence TEXT NOT NULL DEFAULT 'daily',
                timezone TEXT NOT NULL DEFAULT 'UTC',
                active_from TEXT,
                active_until TEXT,
                run_window_start TEXT,
                run_window_end TEXT,
                custom_anchor_at TEXT,
                custom_every_n_days INTEGER,
                blackout_dates TEXT NOT NULL DEFAULT '[]',
                failure_policy TEXT NOT NULL DEFAULT 'continue',
                campaign_steps TEXT NOT NULL DEFAULT '[]',
                last_triggered_at TEXT,
                next_run_at TEXT,
                next_run_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                run_id INTEGER,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
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
    schedule_columns = [row[1] for row in conn.execute("PRAGMA table_info(schedules)").fetchall()]
    if schedule_columns and "custom_anchor_at" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN custom_anchor_at TEXT")
    if schedule_columns and "custom_every_n_days" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN custom_every_n_days INTEGER")
    if schedule_columns and "next_run_reason" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN next_run_reason TEXT")
    if schedule_columns and "anchor_start_at" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN anchor_start_at TEXT")
    if schedule_columns and "period" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN period TEXT")
    if schedule_columns and "stop_rule" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN stop_rule TEXT")
    if schedule_columns and "end_at" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN end_at TEXT")
    if schedule_columns and "duration_seconds" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN duration_seconds INTEGER")
    if schedule_columns and "runs_per_period" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN runs_per_period INTEGER NOT NULL DEFAULT 1")


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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schedules (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    name VARCHAR(160) NOT NULL,
                    description TEXT,
                    schedule_type VARCHAR(20) NOT NULL DEFAULT 'simple',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    profile_id INTEGER REFERENCES run_profiles(id) ON DELETE SET NULL,
                    anchor_start_at TIMESTAMP WITH TIME ZONE,
                    period VARCHAR(20),
                    stop_rule VARCHAR(20),
                    end_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    runs_per_period INTEGER NOT NULL DEFAULT 1,
                    cadence VARCHAR(20) NOT NULL DEFAULT 'daily',
                    timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
                    active_from TIMESTAMP WITH TIME ZONE,
                    active_until TIMESTAMP WITH TIME ZONE,
                    run_window_start VARCHAR(8),
                    run_window_end VARCHAR(8),
                    custom_anchor_at TIMESTAMP WITH TIME ZONE,
                    custom_every_n_days INTEGER,
                    blackout_dates JSONB DEFAULT '[]',
                    failure_policy VARCHAR(20) NOT NULL DEFAULT 'continue',
                    campaign_steps JSONB DEFAULT '[]',
                    last_triggered_at TIMESTAMP WITH TIME ZONE,
                    next_run_at TIMESTAMP WITH TIME ZONE,
                    next_run_reason VARCHAR(64),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS custom_anchor_at TIMESTAMP WITH TIME ZONE")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS custom_every_n_days INTEGER")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS next_run_reason VARCHAR(64)")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS anchor_start_at TIMESTAMP WITH TIME ZONE")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS period VARCHAR(20)")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS stop_rule VARCHAR(20)")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS end_at TIMESTAMP WITH TIME ZONE")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS duration_seconds INTEGER")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS runs_per_period INTEGER NOT NULL DEFAULT 1")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_executions (
                    id SERIAL PRIMARY KEY,
                    schedule_id INTEGER REFERENCES schedules(id) ON DELETE CASCADE,
                    run_id INTEGER,
                    status VARCHAR(20) NOT NULL,
                    detail JSONB DEFAULT '{}',
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    finished_at TIMESTAMP WITH TIME ZONE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


SYSTEM_ALLOWED_TIMEZONES_KEY = "allowed_timezones"


def _available_timezones_sorted() -> list[str]:
    # `zoneinfo.available_timezones()` is the canonical IANA source for this runtime.
    return sorted(available_timezones())


def _coerce_timezone_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        value = parsed
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, bytes)) or item is not None]
    return []


def _get_allowed_timezones_setting() -> list[str] | None:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT value FROM system_settings WHERE key = %s", (SYSTEM_ALLOWED_TIMEZONES_KEY,))
                row = cursor.fetchone()
                if not row:
                    return None
                value = row[0]
                allowed = _coerce_timezone_list(value)
                return allowed
        finally:
            conn.close()
    with DB_LOCK, _db() as conn:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            (SYSTEM_ALLOWED_TIMEZONES_KEY,),
        ).fetchone()
        if row is None:
            return None
        allowed = _coerce_timezone_list(row["value"])
        return allowed


def _set_allowed_timezones_setting(allowed: list[str] | None) -> None:
    now = _utc_now()
    if allowed is None:
        if USE_POSTGRES:
            conn = _get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM system_settings WHERE key = %s", (SYSTEM_ALLOWED_TIMEZONES_KEY,))
                conn.commit()
            finally:
                conn.close()
            return
        with DB_LOCK, _db() as conn:
            conn.execute("DELETE FROM system_settings WHERE key = ?", (SYSTEM_ALLOWED_TIMEZONES_KEY,))
        return

    payload = json.dumps(list(allowed))
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                    """,
                    (SYSTEM_ALLOWED_TIMEZONES_KEY, payload),
                )
            conn.commit()
        finally:
            conn.close()
        return

    with DB_LOCK, _db() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (SYSTEM_ALLOWED_TIMEZONES_KEY, payload, now),
        )


def _system_timezones_payload() -> dict[str, Any]:
    available = _available_timezones_sorted()
    allowed = _get_allowed_timezones_setting()
    if allowed is None:
        return {
            "mode": "all",
            "allowed_timezones": None,
            "available_timezones": available,
        }
    return {
        "mode": "allowlist",
        "allowed_timezones": allowed,
        "available_timezones": available,
    }


def _validate_timezone_policy_update(request: TimezonePolicyUpdateRequest) -> tuple[str, list[str] | None]:
    available = set(_available_timezones_sorted())
    mode = request.mode or "all"
    if mode == "all":
        return ("all", None)

    allowed = request.allowed_timezones or []
    normalized = [str(item).strip() for item in allowed if str(item).strip()]
    unknown = sorted({item for item in normalized if item not in available})
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown timezones: {', '.join(unknown[:8])}")
    return ("allowlist", normalized)


def _set_system_timezones_policy(request: TimezonePolicyUpdateRequest) -> dict[str, Any]:
    mode, allowed = _validate_timezone_policy_update(request)
    if mode == "all":
        _set_allowed_timezones_setting(None)
        return _system_timezones_payload()
    _set_allowed_timezones_setting(allowed or [])
    return _system_timezones_payload()


def _validate_schedule_timezone(requested: str | None) -> None:
    tz = (requested or "").strip()
    if not tz:
        raise HTTPException(status_code=400, detail="Timezone is required.")
    available = set(_available_timezones_sorted())
    if tz not in available:
        raise HTTPException(status_code=400, detail="Timezone must be a valid IANA timezone.")
    allowed = _get_allowed_timezones_setting()
    if allowed is not None and tz not in set(allowed):
        raise HTTPException(status_code=400, detail="Timezone is not allowed by system policy.")

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


def _model_payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _jsonable_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _load_json_field(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value or "null") or fallback
        except json.JSONDecodeError:
            return fallback
    return value


def _schedule_row_to_dict_any(row) -> dict[str, Any]:
    payload = dict(row)
    payload["blackout_dates"] = _load_json_field(payload.get("blackout_dates"), [])
    payload["campaign_steps"] = _load_json_field(payload.get("campaign_steps"), [])
    for key in (
        "anchor_start_at",
        "end_at",
        "active_from",
        "active_until",
        "custom_anchor_at",
        "last_triggered_at",
        "next_run_at",
        "created_at",
        "updated_at",
    ):
        payload[key] = _jsonable_datetime(payload.get(key))
    custom_every_n_days = payload.get("custom_every_n_days")
    payload["custom_every_n_days"] = int(custom_every_n_days) if custom_every_n_days is not None else None
    runs_per_period = payload.get("runs_per_period")
    payload["runs_per_period"] = int(runs_per_period) if runs_per_period is not None else 1
    duration_seconds = payload.get("duration_seconds")
    payload["duration_seconds"] = int(duration_seconds) if duration_seconds is not None else None
    payload["requested_runs_per_period"] = payload["runs_per_period"]
    payload["feasible_runs_per_period"] = payload["runs_per_period"]
    payload["schedule_warnings"] = []
    payload["current_period_runs"] = []
    if payload.get("period") and payload.get("anchor_start_at"):
        bundle = _calculate_new_contract_bundle(payload, datetime.now(timezone.utc))
        payload["requested_runs_per_period"] = bundle["requested_runs_per_period"]
        payload["feasible_runs_per_period"] = bundle["feasible_runs_per_period"]
        payload["schedule_warnings"] = bundle["schedule_warnings"]
        payload["current_period_runs"] = bundle["current_period_runs"]
        # Keep persisted scheduling state authoritative for scheduler due-checks.
        # Hydration preview metadata must not erase stored next_run_at/next_run_reason.
        if payload.get("next_run_reason") is None:
            payload["next_run_reason"] = bundle["next_run_reason"]
    if payload.get("next_run_reason") is None:
        payload["next_run_reason"] = "computed" if payload.get("next_run_at") else "no_future_run"
    payload["execution_mode_label"] = "automatic" if _schedule_is_automatic(payload) else "manual_only"
    return payload


def _schedule_execution_row_to_dict_any(row) -> dict[str, Any]:
    payload = dict(row)
    payload["detail"] = _load_json_field(payload.get("detail"), {})
    for key in ("started_at", "finished_at"):
        payload[key] = _jsonable_datetime(payload.get(key))
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


def _datetime_as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_schedule_request(request: ScheduleUpsertRequest) -> None:
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Schedule name is required.")

    _validate_schedule_timezone(request.timezone)

    active_from = _parse_run_timestamp(request.active_from)
    active_until = _parse_run_timestamp(request.active_until)
    if request.active_from and active_from is None:
        raise HTTPException(status_code=400, detail="Active from must be a valid ISO date-time.")
    if request.active_until and active_until is None:
        raise HTTPException(status_code=400, detail="Active until must be a valid ISO date-time.")
    active_from_utc = _datetime_as_utc(active_from)
    active_until_utc = _datetime_as_utc(active_until)
    if active_from_utc and active_until_utc and active_until_utc <= active_from_utc:
        raise HTTPException(status_code=400, detail="Active until must be after active from.")

    for field_name, value in (
        ("Run window start", request.run_window_start),
        ("Run window end", request.run_window_end),
    ):
        if value:
            parsed_time = _parse_schedule_time(value)
            if parsed_time is None or not (0 <= parsed_time[0] <= 23 and 0 <= parsed_time[1] <= 59):
                raise HTTPException(status_code=400, detail=f"{field_name} must use HH:MM 24-hour time.")

    for blackout_date in request.blackout_dates:
        try:
            datetime.strptime(blackout_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Blackout dates must use YYYY-MM-DD format.") from None

    using_new_contract = bool(request.period or request.anchor_start_at or request.stop_rule or request.end_at or request.duration_seconds is not None)
    if using_new_contract:
        anchor_start_at = _parse_run_timestamp(request.anchor_start_at)
        if anchor_start_at is None:
            raise HTTPException(status_code=400, detail="anchor_start_at is required and must be a valid ISO date-time.")
        if request.period not in {"hourly", "daily", "weekly", "monthly"}:
            raise HTTPException(status_code=400, detail="period must be one of hourly, daily, weekly, monthly.")
        if request.stop_rule not in {"never", "end_at", "duration"}:
            raise HTTPException(status_code=400, detail="stop_rule must be one of never, end_at, duration.")
        if request.runs_per_period < 1:
            raise HTTPException(status_code=400, detail="runs_per_period must be >= 1.")
        if request.stop_rule == "end_at":
            end_at = _parse_run_timestamp(request.end_at)
            if end_at is None:
                raise HTTPException(status_code=400, detail="end_at is required when stop_rule is end_at.")
            if end_at.astimezone(timezone.utc) <= anchor_start_at.astimezone(timezone.utc):
                raise HTTPException(status_code=400, detail="end_at must be after anchor_start_at.")
        elif request.end_at is not None:
            raise HTTPException(status_code=400, detail="end_at is only allowed when stop_rule is end_at.")
        if request.stop_rule == "duration":
            if request.duration_seconds is None or int(request.duration_seconds) <= 0:
                raise HTTPException(status_code=400, detail="duration_seconds must be > 0 when stop_rule is duration.")
        elif request.duration_seconds is not None:
            raise HTTPException(status_code=400, detail="duration_seconds is only allowed when stop_rule is duration.")

    if request.cadence == "custom":
        custom_anchor_at = _parse_run_timestamp(request.custom_anchor_at)
        if custom_anchor_at is None:
            raise HTTPException(status_code=400, detail="Custom cadence requires a valid custom_anchor_at ISO date-time.")
        if request.custom_every_n_days is None or int(request.custom_every_n_days) < 1:
            raise HTTPException(status_code=400, detail="Custom cadence requires custom_every_n_days >= 1.")
    else:
        if request.custom_anchor_at is not None or request.custom_every_n_days is not None:
            raise HTTPException(
                status_code=400,
                detail="custom_anchor_at/custom_every_n_days are only allowed when cadence is custom.",
            )

    if request.schedule_type == "simple":
        if request.profile_id is None:
            raise HTTPException(status_code=400, detail="Simple schedules require a run profile.")
        _get_run_profile(int(request.profile_id))
        return
    if not request.campaign_steps:
        raise HTTPException(status_code=400, detail="Campaign schedules require at least one campaign step.")
    for step in request.campaign_steps:
        _get_run_profile(int(step.profile_id))


def _schedule_timezone(schedule: dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo(str(schedule.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _schedule_reference(schedule: dict[str, Any], reference: Optional[datetime] = None) -> datetime:
    base = reference or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(_schedule_timezone(schedule))


def _parse_schedule_time(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        hour, minute = value.split(":", 1)
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        return None


def _schedule_is_automatic(schedule: dict[str, Any]) -> bool:
    if schedule.get("period") and schedule.get("anchor_start_at"):
        return True
    cadence = str(schedule.get("cadence") or "daily")
    if cadence != "custom":
        return True
    anchor = _parse_run_timestamp(schedule.get("custom_anchor_at"))
    every = schedule.get("custom_every_n_days")
    try:
        days = int(every) if every is not None else None
    except (TypeError, ValueError):
        days = None
    return bool(anchor and days and days >= 1)


def _window_bounds_minutes(schedule: dict[str, Any]) -> tuple[int, int] | None:
    start = _parse_schedule_time(schedule.get("run_window_start"))
    end = _parse_schedule_time(schedule.get("run_window_end"))
    if not start or not end:
        return None
    return start[0] * 60 + start[1], end[0] * 60 + end[1]


def _minutes_in_window(schedule: dict[str, Any], value: datetime) -> bool:
    bounds = _window_bounds_minutes(schedule)
    if bounds is None:
        return True
    start_minutes, end_minutes = bounds
    current_minutes = value.hour * 60 + value.minute
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


def _window_start_for_local_date(schedule: dict[str, Any], value_date: date, timezone_info: ZoneInfo) -> datetime | None:
    bounds = _window_bounds_minutes(schedule)
    if bounds is None:
        return None
    start_minutes, _ = bounds
    return datetime(
        value_date.year,
        value_date.month,
        value_date.day,
        start_minutes // 60,
        start_minutes % 60,
        tzinfo=timezone_info,
    )


def _schedule_in_window(schedule: dict[str, Any], reference: Optional[datetime] = None) -> bool:
    return _minutes_in_window(schedule, _schedule_reference(schedule, reference))


def _schedule_blackout(schedule: dict[str, Any], reference: Optional[datetime] = None) -> bool:
    local_now = _schedule_reference(schedule, reference)
    blackout_dates = set(schedule.get("blackout_dates") or [])
    return local_now.date().isoformat() in blackout_dates


def _cadence_delta(cadence: str) -> timedelta | None:
    if cadence == "hourly":
        return timedelta(hours=1)
    if cadence == "daily":
        return timedelta(days=1)
    if cadence == "weekdays":
        return timedelta(days=1)
    if cadence == "weekly":
        return timedelta(days=7)
    if cadence == "monthly":
        return timedelta(days=30)
    return None


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return int((next_month - timedelta(days=1)).day)


def _with_same_time(target_date: date, source: datetime, timezone_info: ZoneInfo) -> datetime:
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        source.hour,
        source.minute,
        source.second,
        source.microsecond,
        tzinfo=timezone_info,
    )


def _period_window_bounds(period: str, local_reference: datetime) -> tuple[datetime, datetime]:
    timezone_info = local_reference.tzinfo or timezone.utc
    if period == "hourly":
        start = local_reference.replace(minute=0, second=0, microsecond=0)
        return start, start + timedelta(hours=1)
    if period == "daily":
        start = local_reference.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "weekly":
        start = (local_reference - timedelta(days=local_reference.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if period == "monthly":
        start = local_reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    # fallback daily
    start = local_reference.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _calculate_new_contract_bundle(schedule: dict[str, Any], reference: Optional[datetime] = None) -> dict[str, Any]:
    timezone_info = _schedule_timezone(schedule)
    local_reference = _schedule_reference(schedule, reference)
    anchor_start_at = _parse_run_timestamp(schedule.get("anchor_start_at"))
    period = str(schedule.get("period") or "")
    stop_rule = str(schedule.get("stop_rule") or "never")
    runs_per_period = int(schedule.get("runs_per_period") or 1)
    if anchor_start_at is None or period not in {"hourly", "daily", "weekly", "monthly"}:
        return {
            "next_run_at": None,
            "next_run_reason": "no_future_run",
            "current_period_runs": [],
            "requested_runs_per_period": runs_per_period,
            "feasible_runs_per_period": 0,
            "schedule_warnings": ["Missing or invalid new scheduling fields."],
        }
    anchor_local = anchor_start_at.astimezone(timezone_info)
    window_start, window_end = _period_window_bounds(period, local_reference)
    window_seconds = max(1.0, (window_end - window_start).total_seconds())
    candidates: list[datetime] = []
    last_triggered_at = _parse_run_timestamp(schedule.get("last_triggered_at"))
    # First run is explicitly anchored to the user-provided Start At time.
    if last_triggered_at is None:
        candidates.append(anchor_local)
    if runs_per_period <= 1:
        anchor_window_start, _ = _period_window_bounds(period, anchor_local)
        offset = max(0.0, (anchor_local - anchor_window_start).total_seconds())
        base = window_start + timedelta(seconds=min(offset, window_seconds - 1))
        candidates = [base]
    else:
        step = window_seconds / runs_per_period
        for idx in range(runs_per_period):
            candidates.append(window_start + timedelta(seconds=idx * step))
    filtered: list[datetime] = []
    warnings: list[str] = []
    for candidate in candidates:
        if candidate < anchor_local:
            continue
        if not _minutes_in_window(schedule, candidate):
            continue
        if candidate.date().isoformat() in set(schedule.get("blackout_dates") or []):
            continue
        filtered.append(candidate)
    if stop_rule == "end_at":
        end_at = _parse_run_timestamp(schedule.get("end_at"))
        if end_at:
            end_local = end_at.astimezone(timezone_info)
            filtered = [item for item in filtered if item <= end_local]
    elif stop_rule == "duration":
        duration_seconds = int(schedule.get("duration_seconds") or 0)
        end_local = anchor_local + timedelta(seconds=duration_seconds)
        filtered = [item for item in filtered if item <= end_local]
    future = [item for item in filtered if item.astimezone(timezone.utc) >= local_reference.astimezone(timezone.utc)]
    if not future:
        if period == "hourly":
            next_reference = local_reference + timedelta(hours=1)
        elif period == "daily":
            next_reference = local_reference + timedelta(days=1)
        elif period == "weekly":
            next_reference = local_reference + timedelta(days=7)
        else:
            next_reference = local_reference + timedelta(days=32)
            next_reference = next_reference.replace(day=1)
        next_start, next_end = _period_window_bounds(period, next_reference)
        next_window_seconds = max(1.0, (next_end - next_start).total_seconds())
        next_candidates: list[datetime] = []
        if runs_per_period <= 1:
            anchor_window_start, _ = _period_window_bounds(period, anchor_local)
            offset = max(0.0, (anchor_local - anchor_window_start).total_seconds())
            next_candidates = [next_start + timedelta(seconds=min(offset, next_window_seconds - 1))]
        else:
            next_step = next_window_seconds / runs_per_period
            for idx in range(runs_per_period):
                next_candidates.append(next_start + timedelta(seconds=idx * next_step))
        for candidate in next_candidates:
            if candidate < anchor_local:
                continue
            if not _minutes_in_window(schedule, candidate):
                continue
            if candidate.date().isoformat() in set(schedule.get("blackout_dates") or []):
                continue
            if stop_rule == "end_at":
                end_at = _parse_run_timestamp(schedule.get("end_at"))
                if end_at and candidate > end_at.astimezone(timezone_info):
                    continue
            elif stop_rule == "duration":
                duration_seconds = int(schedule.get("duration_seconds") or 0)
                end_local = anchor_local + timedelta(seconds=duration_seconds)
                if candidate > end_local:
                    continue
            future.append(candidate)
            break
    if len(filtered) < runs_per_period:
        warnings.append("Requested runs per period exceed feasible runs under current constraints.")
    next_run = future[0].astimezone(timezone.utc).isoformat() if future else None
    reason = "computed" if next_run else "no_future_run"
    return {
        "next_run_at": next_run,
        "next_run_reason": reason,
        "current_period_runs": [item.astimezone(timezone.utc).isoformat() for item in filtered],
        "requested_runs_per_period": runs_per_period,
        "feasible_runs_per_period": len(filtered),
        "schedule_warnings": warnings,
    }


def _next_automatic_candidate(schedule: dict[str, Any], local_reference: datetime) -> datetime | None:
    cadence = str(schedule.get("cadence") or "daily")
    timezone_info = _schedule_timezone(schedule)
    active_from = _parse_run_timestamp(schedule.get("active_from"))
    active_from_local = active_from.astimezone(timezone_info) if active_from else None
    anchor = active_from_local or local_reference
    if cadence == "custom":
        custom_anchor = _parse_run_timestamp(schedule.get("custom_anchor_at"))
        every = schedule.get("custom_every_n_days")
        if custom_anchor is None or every is None:
            return None
        try:
            step_days = int(every)
        except (TypeError, ValueError):
            return None
        if step_days < 1:
            return None
        custom_anchor_local = custom_anchor.astimezone(timezone_info)
        candidate = custom_anchor_local
        while candidate <= local_reference:
            candidate += timedelta(days=step_days)
        return candidate
    if cadence == "hourly":
        candidate = local_reference.replace(
            minute=anchor.minute,
            second=anchor.second,
            microsecond=anchor.microsecond,
        )
        if candidate <= local_reference:
            candidate += timedelta(hours=1)
        return candidate
    if cadence == "daily":
        candidate = _with_same_time(local_reference.date(), anchor, timezone_info)
        if candidate <= local_reference:
            candidate += timedelta(days=1)
        return candidate
    if cadence == "weekdays":
        candidate = _with_same_time(local_reference.date(), anchor, timezone_info)
        if candidate <= local_reference:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate
    if cadence == "weekly":
        anchor_weekday = anchor.weekday()
        days_ahead = (anchor_weekday - local_reference.weekday()) % 7
        candidate = _with_same_time(local_reference.date() + timedelta(days=days_ahead), anchor, timezone_info)
        if candidate <= local_reference:
            candidate += timedelta(days=7)
        return candidate
    if cadence == "monthly":
        anchor_day = anchor.day
        candidate_year = local_reference.year
        candidate_month = local_reference.month
        for _ in range(24):
            month_last_day = _last_day_of_month(candidate_year, candidate_month)
            day = min(anchor_day, month_last_day)
            candidate = datetime(
                candidate_year,
                candidate_month,
                day,
                anchor.hour,
                anchor.minute,
                anchor.second,
                anchor.microsecond,
                tzinfo=timezone_info,
            )
            if candidate > local_reference:
                return candidate
            if candidate_month == 12:
                candidate_month = 1
                candidate_year += 1
            else:
                candidate_month += 1
        return None
    return None


def _calculate_next_run(schedule: dict[str, Any], reference: Optional[datetime] = None) -> tuple[str | None, str]:
    if schedule.get("period") and schedule.get("anchor_start_at"):
        bundle = _calculate_new_contract_bundle(schedule, reference)
        return bundle["next_run_at"], bundle["next_run_reason"]
    if not _schedule_is_automatic(schedule):
        return None, "no_future_run"
    timezone_info = _schedule_timezone(schedule)
    local_reference = _schedule_reference(schedule, reference)
    active_until = _parse_run_timestamp(schedule.get("active_until"))
    active_until_local = active_until.astimezone(timezone_info) if active_until else None
    blackout_dates = set(schedule.get("blackout_dates") or [])
    shifted = False
    blackout_skipped = False
    candidate = _next_automatic_candidate(schedule, local_reference)
    for _ in range(366):
        if candidate is None:
            return None, "no_future_run"
        if active_until_local and candidate > active_until_local:
            return None, "outside_active_range"
        if not _minutes_in_window(schedule, candidate):
            shifted = True
            window_start = _window_start_for_local_date(schedule, candidate.date(), timezone_info)
            if window_start is None:
                window_start = candidate
            if window_start < candidate and _window_bounds_minutes(schedule) is not None:
                window_start += timedelta(days=1)
            candidate = window_start
            continue
        if candidate.date().isoformat() in blackout_dates:
            blackout_skipped = True
            candidate = candidate + timedelta(days=1)
            if candidate <= local_reference:
                candidate = local_reference + timedelta(minutes=1)
            continue
        reason = "computed"
        if blackout_skipped:
            reason = "blackout_skipped"
        elif shifted:
            reason = "shifted_to_window_start"
        return candidate.astimezone(timezone.utc).isoformat(), reason
    return None, "no_future_run"


def _calculate_next_run_at(
    schedule: dict[str, Any],
    reference: Optional[datetime] = None,
) -> str | None:
    next_run_at, _ = _calculate_next_run(schedule, reference)
    return next_run_at


def _schedule_fields_from_request(
    request: ScheduleUpsertRequest,
    user_id: Optional[int],
    updated_at: str,
) -> dict[str, Any]:
    _validate_schedule_request(request)
    steps = [_model_payload(step) for step in request.campaign_steps]
    profile_id = int(request.profile_id) if request.profile_id is not None else None
    if request.schedule_type == "campaign":
        profile_id = None
    else:
        steps = []
    fields: dict[str, Any] = {
        "name": request.name.strip(),
        "description": request.description,
        "schedule_type": request.schedule_type,
        "profile_id": profile_id,
        "anchor_start_at": request.anchor_start_at,
        "period": request.period,
        "stop_rule": request.stop_rule,
        "end_at": request.end_at,
        "duration_seconds": request.duration_seconds,
        "runs_per_period": request.runs_per_period,
        "cadence": request.cadence,
        "timezone": request.timezone.strip() or "UTC",
        "active_from": request.active_from,
        "active_until": request.active_until,
        "run_window_start": request.run_window_start,
        "run_window_end": request.run_window_end,
        "custom_anchor_at": request.custom_anchor_at,
        "custom_every_n_days": request.custom_every_n_days,
        "blackout_dates": json.dumps(request.blackout_dates),
        "failure_policy": request.failure_policy,
        "campaign_steps": json.dumps(steps),
        "updated_at": updated_at,
    }
    next_run_at, next_run_reason = _calculate_next_run(
        {
            **fields,
            "blackout_dates": request.blackout_dates,
            "campaign_steps": steps,
        },
        _parse_run_timestamp(updated_at),
    )
    fields["next_run_at"] = next_run_at
    fields["next_run_reason"] = next_run_reason
    persisted_user_id = _resolve_persisted_user_id(user_id)
    if persisted_user_id is not None:
        fields["user_id"] = persisted_user_id
    return fields


def _list_schedules(include_deleted: bool = False) -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                if include_deleted:
                    cursor.execute("SELECT * FROM schedules ORDER BY updated_at DESC, id DESC")
                else:
                    cursor.execute(
                        "SELECT * FROM schedules WHERE status <> %s ORDER BY updated_at DESC, id DESC",
                        ("deleted",),
                    )
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            if include_deleted:
                rows = conn.execute("SELECT * FROM schedules ORDER BY updated_at DESC, id DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE status <> ? ORDER BY updated_at DESC, id DESC",
                    ("deleted",),
                ).fetchall()
    return {"schedules": [_schedule_row_to_dict_any(row) for row in rows]}


def _get_schedule(schedule_id: int) -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT * FROM schedules WHERE id = %s", (schedule_id,))
                row = cursor.fetchone()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found.")
    return _schedule_row_to_dict_any(row)


def _create_schedule(request: ScheduleUpsertRequest, user_id: Optional[int] = None) -> dict[str, Any]:
    created_at = _utc_now()
    fields = _schedule_fields_from_request(request, user_id, created_at)
    fields["created_at"] = created_at
    fields["status"] = "active"
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                keys = list(fields.keys())
                values = [fields[key] for key in keys]
                placeholders = ", ".join(["%s"] * len(keys))
                cursor.execute(
                    f"INSERT INTO schedules ({', '.join(keys)}) VALUES ({placeholders}) RETURNING *",
                    values,
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            keys = list(fields.keys())
            values = [fields[key] for key in keys]
            placeholders = ", ".join(["?"] * len(keys))
            cursor = conn.execute(
                f"INSERT INTO schedules ({', '.join(keys)}) VALUES ({placeholders})",
                values,
            )
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return {"schedule": _schedule_row_to_dict_any(row)}


def _update_schedule(
    schedule_id: int,
    request: ScheduleUpsertRequest,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    _get_schedule(schedule_id)
    fields = _schedule_fields_from_request(request, user_id, _utc_now())
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                keys = list(fields.keys())
                values = [fields[key] for key in keys]
                assignment = ", ".join(f"{key} = %s" for key in keys)
                cursor.execute(
                    f"UPDATE schedules SET {assignment} WHERE id = %s RETURNING *",
                    (*values, schedule_id),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            keys = list(fields.keys())
            values = [fields[key] for key in keys]
            assignment = ", ".join(f"{key} = ?" for key in keys)
            conn.execute(
                f"UPDATE schedules SET {assignment} WHERE id = ?",
                (*values, schedule_id),
            )
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return {"schedule": _schedule_row_to_dict_any(row)}


def _set_schedule_status(schedule_id: int, status: str) -> dict[str, Any]:
    if status not in {"active", "paused", "disabled", "deleted"}:
        raise HTTPException(status_code=400, detail=f"Unsupported schedule status {status!r}.")
    schedule = _get_schedule(schedule_id)
    updated_at = _utc_now()
    if status == "active":
        next_run_at, next_run_reason = _calculate_next_run(schedule, _parse_run_timestamp(updated_at))
    else:
        next_run_at, next_run_reason = (None, "no_future_run")
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "UPDATE schedules SET status = %s, next_run_at = %s, next_run_reason = %s, updated_at = %s WHERE id = %s RETURNING *",
                    (status, next_run_at, next_run_reason, updated_at, schedule_id),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            conn.execute(
                "UPDATE schedules SET status = ?, next_run_at = ?, next_run_reason = ?, updated_at = ? WHERE id = ?",
                (status, next_run_at, next_run_reason, updated_at, schedule_id),
            )
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return {"schedule": _schedule_row_to_dict_any(row)}


def _record_schedule_execution(
    schedule_id: int,
    run_id: Optional[int],
    status: str,
    detail: dict[str, Any],
    started_at: str,
    finished_at: Optional[str] = None,
) -> dict[str, Any]:
    detail_payload = json.dumps(detail)
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO schedule_executions (schedule_id, run_id, status, detail, started_at, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (schedule_id, run_id, status, detail_payload, started_at, finished_at),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_executions (schedule_id, run_id, status, detail, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, run_id, status, detail_payload, started_at, finished_at),
            )
            row = conn.execute("SELECT * FROM schedule_executions WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return _schedule_execution_row_to_dict_any(row)


def _list_schedule_executions(limit: int = 10) -> list[dict[str, Any]]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM schedule_executions ORDER BY started_at DESC, id DESC LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule_executions ORDER BY started_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_schedule_execution_row_to_dict_any(row) for row in rows]


def _trigger_schedule_logic(schedule_id: int, user_id: Optional[int] = None) -> dict[str, Any]:
    schedule = _get_schedule(schedule_id)
    if schedule["status"] in {"disabled", "deleted"}:
        raise HTTPException(status_code=409, detail=f"Schedule {schedule_id} is {schedule['status']}.")
    started_at = _utc_now()
    runs: list[dict[str, Any]] = []
    try:
        if schedule["schedule_type"] == "campaign":
            for step_index, step in enumerate(schedule.get("campaign_steps") or [], start=1):
                repeat_count = int(step.get("repeat_count") or 1)
                profile_id = int(step["profile_id"])
                for repeat_index in range(1, repeat_count + 1):
                    launched = _launch_run_profile(profile_id, user_id)["run"]
                    launched["campaign_step_index"] = step_index
                    launched["campaign_repeat_index"] = repeat_index
                    runs.append(launched)
        else:
            launched = _launch_run_profile(int(schedule["profile_id"]), user_id)["run"]
            runs.append(launched)
    except Exception as exc:
        execution = _record_schedule_execution(
            schedule_id,
            runs[0]["id"] if runs else None,
            "failed",
            {"error": str(exc), "run_ids": [run["id"] for run in runs]},
            started_at,
            _utc_now(),
        )
        raise HTTPException(status_code=500, detail={"execution": execution, "error": str(exc)}) from exc

    finished_at = _utc_now()
    execution = _record_schedule_execution(
        schedule_id,
        runs[0]["id"] if runs else None,
        "launched",
        {
            "schedule_type": schedule["schedule_type"],
            "run_ids": [run["id"] for run in runs],
        },
        started_at,
        finished_at,
    )
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE schedules SET last_triggered_at = %s, updated_at = %s WHERE id = %s",
                    (started_at, finished_at, schedule_id),
                )
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            conn.execute(
                "UPDATE schedules SET last_triggered_at = ?, updated_at = ? WHERE id = ?",
                (started_at, finished_at, schedule_id),
            )
    payload = {
        "schedule": _get_schedule(schedule_id),
        "execution": execution,
        "runs": runs,
    }
    if runs:
        payload["run"] = runs[0]
    return payload


def _schedule_summary_payload() -> dict[str, Any]:
    schedules = _list_schedules(include_deleted=True)["schedules"]
    status_breakdown: dict[str, int] = {}
    type_breakdown: dict[str, int] = {}
    for schedule in schedules:
        status = str(schedule.get("status") or "unknown")
        schedule_type = str(schedule.get("schedule_type") or "unknown")
        status_breakdown[status] = status_breakdown.get(status, 0) + 1
        type_breakdown[schedule_type] = type_breakdown.get(schedule_type, 0) + 1
    visible_count = sum(count for status, count in status_breakdown.items() if status != "deleted")
    degraded_campaigns = sum(
        1
        for schedule in schedules
        if schedule.get("schedule_type") == "campaign"
        and schedule.get("status") != "deleted"
        and not schedule.get("campaign_steps")
    )
    return {
        "total": visible_count,
        "status_breakdown": status_breakdown,
        "type_breakdown": type_breakdown,
        "health": {
            "active": status_breakdown.get("active", 0),
            "paused": status_breakdown.get("paused", 0),
            "disabled": status_breakdown.get("disabled", 0),
            "degraded_campaigns": degraded_campaigns,
        },
        "recent_executions": _list_schedule_executions(limit=10),
    }


def _update_schedule_next_run(
    schedule_id: int,
    next_run_at: str | None,
    next_run_reason: str = "computed",
    updated_at: Optional[str] = None,
) -> None:
    updated_at = updated_at or _utc_now()
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE schedules SET next_run_at = %s, next_run_reason = %s, updated_at = %s WHERE id = %s",
                    (next_run_at, next_run_reason, updated_at, schedule_id),
                )
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            conn.execute(
                "UPDATE schedules SET next_run_at = ?, next_run_reason = ?, updated_at = ? WHERE id = ?",
                (next_run_at, next_run_reason, updated_at, schedule_id),
            )


def _schedule_is_due(schedule: dict[str, Any], reference: datetime) -> bool:
    if schedule.get("status") != "active":
        return False
    next_run_at = _parse_run_timestamp(schedule.get("next_run_at"))
    if next_run_at is None or next_run_at > reference:
        return False
    active_from = _parse_run_timestamp(schedule.get("active_from"))
    active_until = _parse_run_timestamp(schedule.get("active_until"))
    if active_from and reference < active_from:
        return False
    if active_until and reference > active_until:
        _set_schedule_status(int(schedule["id"]), "disabled")
        return False
    return True


def _run_scheduled_jobs() -> None:
    reference = datetime.now(timezone.utc)
    for schedule in _list_schedules(include_deleted=False)["schedules"]:
        if not _schedule_is_due(schedule, reference):
            continue
        if _schedule_blackout(schedule, reference) or not _schedule_in_window(schedule, reference):
            next_run_at, next_run_reason = _calculate_next_run(schedule, reference)
            _update_schedule_next_run(
                int(schedule["id"]),
                next_run_at,
                next_run_reason,
            )
            continue
        try:
            _trigger_schedule_logic(int(schedule["id"]))
        except Exception as exc:
            LOGGER.error("scheduled trigger failed schedule_id=%s error=%s", schedule.get("id"), exc)
        finally:
            next_run_at, next_run_reason = _calculate_next_run(schedule, reference)
            _update_schedule_next_run(
                int(schedule["id"]),
                next_run_at,
                next_run_reason,
            )


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


def _run_age_days(run: dict[str, Any]) -> int | None:
    created_at = _parse_run_timestamp(run.get("created_at"))
    if created_at is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - created_at).total_seconds() // 86400))


def _run_lifecycle_state(run: dict[str, Any]) -> str:
    age_days = _run_age_days(run)
    if age_days is None or age_days < ACTIVE_RETENTION_DAYS:
        return "active"
    if age_days < ARCHIVE_RETENTION_DAYS:
        return "archive_candidate"
    return "raw_purge_candidate"


def _retained_summary_fields() -> list[str]:
    return [
        "verdict",
        "flow",
        "schedule_or_campaign_source",
        "actor_summary",
        "duration",
        "latency",
        "top_failure_signals",
        "narrative",
        "audit_attribution",
    ]


def _retained_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    snapshot = run.get("execution_snapshot") if isinstance(run.get("execution_snapshot"), dict) else {}
    status = str(run.get("status") or "unknown")
    started_at = _parse_run_timestamp(run.get("started_at"))
    finished_at = _parse_run_timestamp(run.get("finished_at"))
    duration_seconds = None
    if started_at and finished_at:
        duration_seconds = max(0, round((finished_at - started_at).total_seconds(), 2))
    failure_signals = []
    if run.get("error"):
        failure_signals.append(str(run["error"]))
    return {
        "verdict": status,
        "flow": run.get("flow"),
        "schedule_or_campaign_source": snapshot.get("source") or "manual_or_profile",
        "actor_summary": {
            "store_id": run.get("store_id"),
            "phone": run.get("phone"),
            "store_name": run.get("store_name"),
            "user_name": run.get("user_name"),
        },
        "duration": {
            "seconds": duration_seconds,
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
        },
        "latency": {"avg_http_latency_ms": None},
        "top_failure_signals": failure_signals,
        "narrative": f"{run.get('flow', 'simulation')} run {run.get('id')} ended as {status}.",
        "audit_attribution": {
            "run_id": run.get("id"),
            "created_at": run.get("created_at"),
            "artifact_available": any(run.get(field) for field in ARTIFACT_FIELDS) or bool(run.get("log_path")),
        },
    }


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
    enriched = [
        {
            **run,
            "lifecycle_state": _run_lifecycle_state(run),
            "age_days": _run_age_days(run),
            "retained_summary": _retained_run_summary(run),
        }
        for run in page
    ]
    return {
        "runs": enriched,
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
        "lifecycle_states": {
            "active": len(buckets["active"]),
            "archive_candidate": len(buckets["archive"]),
            "raw_purge_candidate": len(buckets["purge"]),
        },
        "retained_summary_fields": _retained_summary_fields(),
        "purge_safety": {
            "mode": "manual-review",
            "raw_artifact_purge_enabled": False,
            "retained_summary_required": True,
        },
        "status": "observation-only",
    }


def _alerts_payload() -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    runs = _list_runs(limit=200)
    now = _utc_now()
    for run in runs:
        status = str(run.get("status") or "").lower()
        if status == "failed":
            alerts.append(
                {
                    "id": f"run-{run['id']}-failed",
                    "domain": "runs",
                    "severity": "critical",
                    "title": f"Run {run['id']} failed",
                    "message": run.get("error") or f"{run.get('flow', 'simulation')} failed.",
                    "href": f"/runs/{run['id']}",
                    "created_at": run.get("finished_at") or run.get("created_at") or now,
                }
            )
    buckets = _retention_buckets(runs)
    if buckets["archive"] or buckets["purge"]:
        alerts.append(
            {
                "id": "retention-backlog",
                "domain": "retention",
                "severity": "warning" if buckets["purge"] else "info",
                "title": "Retention queue needs review",
                "message": f"{len(buckets['archive'])} archive candidates and {len(buckets['purge'])} raw purge candidates.",
                "href": "/retention",
                "created_at": now,
            }
        )
    for schedule in _list_schedules(include_deleted=False)["schedules"]:
        status = str(schedule.get("status") or "")
        if status == "paused":
            alerts.append(
                {
                    "id": f"schedule-{schedule['id']}-paused",
                    "domain": "schedules",
                    "severity": "warning",
                    "title": f"{schedule['name']} is paused",
                    "message": "Scheduled execution is paused until it is resumed.",
                    "href": "/schedules",
                    "created_at": schedule.get("updated_at") or now,
                }
            )
        if schedule.get("schedule_type") == "campaign" and not schedule.get("campaign_steps"):
            alerts.append(
                {
                    "id": f"schedule-{schedule['id']}-degraded",
                    "domain": "schedules",
                    "severity": "warning",
                    "title": f"{schedule['name']} campaign is degraded",
                    "message": "Campaign schedule has no executable steps.",
                    "href": "/schedules",
                    "created_at": schedule.get("updated_at") or now,
                }
            )
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda item: (severity_order.get(str(item["severity"]), 3), str(item.get("created_at") or "")), reverse=False)
    return {"alerts": alerts, "total": len(alerts)}


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
scheduler.add_job(
    _run_scheduled_jobs,
    trigger="interval",
    seconds=60,
    id="schedule-runner",
    replace_existing=True,
)
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
configure_schedules_runtime(
    list_schedules=lambda include_deleted: _list_schedules(include_deleted),
    summary=lambda: _schedule_summary_payload(),
    create_schedule=lambda request, user_id: _create_schedule(request, user_id),
    update_schedule=lambda schedule_id, request, user_id: _update_schedule(schedule_id, request, user_id),
    set_status=lambda schedule_id, status: _set_schedule_status(schedule_id, status),
    trigger_schedule=lambda schedule_id, user_id: _trigger_schedule_logic(schedule_id, user_id),
)
configure_alerts_runtime(
    list_alerts=lambda: _alerts_payload(),
)
configure_simulation_plans_runtime(
    list_plans=lambda: _list_simulation_plans_payload(),
    get_plan=lambda plan_id: _get_simulation_plan_payload(plan_id),
    create_plan=lambda request: _create_simulation_plan(request),
    update_plan=lambda plan_id, request: _update_simulation_plan(plan_id, request),
    delete_plan=lambda plan_id: _delete_simulation_plan(plan_id),
)
configure_system_runtime(
    get_timezones_policy=lambda: _system_timezones_payload(),
    set_timezones_policy=lambda request: _set_system_timezones_policy(request),
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
app.include_router(schedules_router)
app.include_router(alerts_router)
app.include_router(simulation_plans_router)
app.include_router(system_router)
