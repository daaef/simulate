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
import hashlib
import hmac
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from apscheduler.schedulers.background import BackgroundScheduler
from email_validator import EmailNotValidError, validate_email
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from flow_presets import FLOW_PRESETS, flow_capabilities
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
from .system.email_sender import SmtpConfig, send_plain_text_email
from .system.models import EmailSettingsUpdateRequest, TimezonePolicyUpdateRequest
from .system.routes import router as system_router
from .system.service import configure_runtime as configure_system_runtime
from .simulation_plans.models import SimulationPlanUpsertRequest
from .simulation_plans.routes import router as simulation_plans_router
from .simulation_plans.service import configure_runtime as configure_simulation_plans_runtime
from .integrations.models import IntegrationMappingUpsertRequest
from .integrations.routes import router as integrations_router
from .integrations.service import configure_runtime as configure_integrations_runtime
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
from .overview.routes import router as overview_router
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


def _json_env(value: str, default: Any) -> Any:
    raw = os.getenv(value)
    if raw is None or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Invalid JSON in %s; falling back to default.", value)
        return default


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
SIMULATOR_WEBHOOK_PROJECT_SECRETS = _json_env("SIMULATOR_WEBHOOK_PROJECT_SECRETS", {})
SIMULATOR_WEBHOOK_REPO_ALLOWLIST = _json_env("SIMULATOR_WEBHOOK_REPO_ALLOWLIST", {})
SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT = os.getenv("SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT", "production")
GITHUB_STATUS_TOKEN = os.getenv("GITHUB_STATUS_TOKEN", "").strip()
GITHUB_STATUS_API_BASE = os.getenv("GITHUB_STATUS_API_BASE", "https://api.github.com").rstrip("/")
GITHUB_STATUS_CONTEXT = os.getenv("GITHUB_STATUS_CONTEXT", "simulator/verification")
SIMULATOR_EXTERNAL_BASE_URL = os.getenv("SIMULATOR_EXTERNAL_BASE_URL", "").rstrip("/")
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
EMAIL_SETTINGS_KEY = "email_notifications"
EMAIL_EVENT_TRIGGERS = {"run_failed", "schedule_launch_failed", "critical_alert"}
EMAIL_TEST_COOLDOWN_SECONDS = max(10, int(os.getenv("SIM_EMAIL_TEST_COOLDOWN_SECONDS", "30")))
EMAIL_EVENT_DEDUPE_WINDOW_SECONDS = max(60, int(os.getenv("SIM_EMAIL_EVENT_DEDUPE_WINDOW_SECONDS", "600")))
EMAIL_EVENT_LOCK = threading.Lock()
EMAIL_TEST_LAST_SENT_AT = 0.0
EMAIL_EVENT_LAST_SENT: dict[str, float] = {}


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
                enforce_websocket_gates INTEGER NOT NULL DEFAULT 0,
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
                execution_snapshot TEXT,
                trigger_source TEXT,
                trigger_label TEXT,
                trigger_context TEXT NOT NULL DEFAULT '{}',
                profile_id INTEGER,
                schedule_id INTEGER,
                integration_trigger_id INTEGER,
                launched_by_user_id INTEGER
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
                suite TEXT,
                scenarios TEXT NOT NULL DEFAULT '[]',
                store_id TEXT,
                phone TEXT,
                all_users INTEGER NOT NULL DEFAULT 0,
                strict_plan INTEGER NOT NULL DEFAULT 0,
                skip_app_probes INTEGER NOT NULL DEFAULT 0,
                skip_store_dashboard_probes INTEGER NOT NULL DEFAULT 0,
                no_auto_provision INTEGER NOT NULL DEFAULT 0,
                enforce_websocket_gates INTEGER NOT NULL DEFAULT 0,
                post_order_actions INTEGER,
                users INTEGER,
                orders INTEGER,
                interval REAL,
                reject REAL,
                continuous INTEGER NOT NULL DEFAULT 0,
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
                repeat TEXT,
                all_day INTEGER NOT NULL DEFAULT 0,
                recurrence_config TEXT NOT NULL DEFAULT '{}',
                run_slots TEXT NOT NULL DEFAULT '[]',
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
                execution_chain_key TEXT,
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integration_profile_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                environment TEXT NOT NULL,
                profile_id INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project, environment)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integration_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                environment TEXT NOT NULL,
                repository TEXT NOT NULL,
                sha TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                deployment_status_id TEXT,
                dedupe_key TEXT NOT NULL UNIQUE,
                event_name TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                run_id INTEGER,
                github_status_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
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
    if "trigger_source" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN trigger_source TEXT")
    if "trigger_label" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN trigger_label TEXT")
    if "trigger_context" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN trigger_context TEXT NOT NULL DEFAULT '{}'")
    if "profile_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN profile_id INTEGER")
    if "schedule_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN schedule_id INTEGER")
    if "integration_trigger_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN integration_trigger_id INTEGER")
    schedule_execution_columns = [row[1] for row in conn.execute("PRAGMA table_info(schedule_executions)").fetchall()]
    if "execution_chain_key" not in schedule_execution_columns:
        conn.execute("ALTER TABLE schedule_executions ADD COLUMN execution_chain_key TEXT")
    if "launched_by_user_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN launched_by_user_id INTEGER")
    if "enforce_websocket_gates" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN enforce_websocket_gates INTEGER NOT NULL DEFAULT 0")
    profile_columns = [row[1] for row in conn.execute("PRAGMA table_info(run_profiles)").fetchall()]
    if profile_columns and "description" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN description TEXT")
    if profile_columns and "suite" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN suite TEXT")
    if profile_columns and "scenarios" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN scenarios TEXT NOT NULL DEFAULT '[]'")
    if profile_columns and "strict_plan" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN strict_plan INTEGER NOT NULL DEFAULT 0")
    if profile_columns and "skip_app_probes" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN skip_app_probes INTEGER NOT NULL DEFAULT 0")
    if profile_columns and "skip_store_dashboard_probes" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN skip_store_dashboard_probes INTEGER NOT NULL DEFAULT 0")
    if profile_columns and "enforce_websocket_gates" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN enforce_websocket_gates INTEGER NOT NULL DEFAULT 0")
    if profile_columns and "users" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN users INTEGER")
    if profile_columns and "orders" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN orders INTEGER")
    if profile_columns and "interval" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN interval REAL")
    if profile_columns and "reject" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN reject REAL")
    if profile_columns and "continuous" not in profile_columns:
        conn.execute("ALTER TABLE run_profiles ADD COLUMN continuous INTEGER NOT NULL DEFAULT 0")
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
    if schedule_columns and "repeat" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN repeat TEXT")
    if schedule_columns and "all_day" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN all_day INTEGER NOT NULL DEFAULT 0")
    if schedule_columns and "recurrence_config" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN recurrence_config TEXT NOT NULL DEFAULT '{}'")
    if schedule_columns and "run_slots" not in schedule_columns:
        conn.execute("ALTER TABLE schedules ADD COLUMN run_slots TEXT NOT NULL DEFAULT '[]'")
    mapping_columns = [row[1] for row in conn.execute("PRAGMA table_info(integration_profile_mappings)").fetchall()]
    if mapping_columns and "enabled" not in mapping_columns:
        conn.execute("ALTER TABLE integration_profile_mappings ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
    trigger_columns = [row[1] for row in conn.execute("PRAGMA table_info(integration_triggers)").fetchall()]
    if trigger_columns and "deployment_status_id" not in trigger_columns:
        conn.execute("ALTER TABLE integration_triggers ADD COLUMN deployment_status_id TEXT")
    if trigger_columns and "github_status_url" not in trigger_columns:
        conn.execute("ALTER TABLE integration_triggers ADD COLUMN github_status_url TEXT")


def _migrate_postgres_schema() -> None:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS store_phone TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_name TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS store_name TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS execution_snapshot JSONB")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(32)")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS trigger_label TEXT")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS trigger_context JSONB DEFAULT '{}'::jsonb")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS profile_id INTEGER")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS schedule_id INTEGER")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS integration_trigger_id INTEGER")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS launched_by_user_id INTEGER")
            cursor.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS enforce_websocket_gates BOOLEAN NOT NULL DEFAULT FALSE")
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
                    suite VARCHAR(80),
                    scenarios JSONB DEFAULT '[]',
                    store_id VARCHAR(50),
                    phone VARCHAR(20),
                    all_users BOOLEAN NOT NULL DEFAULT FALSE,
                    strict_plan BOOLEAN NOT NULL DEFAULT FALSE,
                    skip_app_probes BOOLEAN NOT NULL DEFAULT FALSE,
                    skip_store_dashboard_probes BOOLEAN NOT NULL DEFAULT FALSE,
                    no_auto_provision BOOLEAN NOT NULL DEFAULT FALSE,
                    enforce_websocket_gates BOOLEAN NOT NULL DEFAULT FALSE,
                    post_order_actions BOOLEAN,
                    users INTEGER,
                    orders INTEGER,
                    interval DOUBLE PRECISION,
                    reject DOUBLE PRECISION,
                    continuous BOOLEAN NOT NULL DEFAULT FALSE,
                    extra_args JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS enforce_websocket_gates BOOLEAN NOT NULL DEFAULT FALSE")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS suite VARCHAR(80)")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS scenarios JSONB DEFAULT '[]'::jsonb")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS strict_plan BOOLEAN NOT NULL DEFAULT FALSE")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS skip_app_probes BOOLEAN NOT NULL DEFAULT FALSE")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS skip_store_dashboard_probes BOOLEAN NOT NULL DEFAULT FALSE")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS users INTEGER")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS orders INTEGER")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS interval DOUBLE PRECISION")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS reject DOUBLE PRECISION")
            cursor.execute("ALTER TABLE run_profiles ADD COLUMN IF NOT EXISTS continuous BOOLEAN NOT NULL DEFAULT FALSE")
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
                    repeat VARCHAR(20),
                    all_day BOOLEAN NOT NULL DEFAULT FALSE,
                    recurrence_config JSONB DEFAULT '{}'::jsonb,
                    run_slots JSONB DEFAULT '[]'::jsonb,
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
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS repeat VARCHAR(20)")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS all_day BOOLEAN NOT NULL DEFAULT FALSE")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS recurrence_config JSONB DEFAULT '{}'::jsonb")
            cursor.execute("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS run_slots JSONB DEFAULT '[]'::jsonb")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_executions (
                    id SERIAL PRIMARY KEY,
                    schedule_id INTEGER REFERENCES schedules(id) ON DELETE CASCADE,
                    run_id INTEGER,
                    execution_chain_key TEXT,
                    status VARCHAR(20) NOT NULL,
                    detail JSONB DEFAULT '{}',
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    finished_at TIMESTAMP WITH TIME ZONE
                )
                """
            )
            cursor.execute("ALTER TABLE schedule_executions ADD COLUMN IF NOT EXISTS execution_chain_key TEXT")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_profile_mappings (
                    id SERIAL PRIMARY KEY,
                    project VARCHAR(120) NOT NULL,
                    environment VARCHAR(120) NOT NULL,
                    profile_id INTEGER NOT NULL REFERENCES run_profiles(id) ON DELETE CASCADE,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    UNIQUE(project, environment)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_triggers (
                    id SERIAL PRIMARY KEY,
                    project VARCHAR(120) NOT NULL,
                    environment VARCHAR(120) NOT NULL,
                    repository VARCHAR(255) NOT NULL,
                    sha VARCHAR(80) NOT NULL,
                    deployment_id VARCHAR(80) NOT NULL,
                    deployment_status_id VARCHAR(80),
                    dedupe_key VARCHAR(300) NOT NULL UNIQUE,
                    event_name VARCHAR(80) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    reason TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                    github_status_url TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMP WITH TIME ZONE
                )
                """
            )
            cursor.execute("ALTER TABLE integration_profile_mappings ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE")
            cursor.execute("ALTER TABLE integration_triggers ADD COLUMN IF NOT EXISTS deployment_status_id VARCHAR(80)")
            cursor.execute("ALTER TABLE integration_triggers ADD COLUMN IF NOT EXISTS github_status_url TEXT")
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


def _normalize_email_value(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    try:
        valid = validate_email(cleaned, check_deliverability=False)
    except EmailNotValidError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid email address: {cleaned}") from exc
    return valid.normalized


def _normalize_recipients(value: Any) -> list[str]:
    raw_items: list[str]
    if isinstance(value, str):
        raw_items = re.split(r"[,\n]+", value)
    elif isinstance(value, list):
        raw_items = [str(item) for item in value if str(item).strip()]
    else:
        raw_items = []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        email = _normalize_email_value(item)
        if not email or email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


def _normalize_event_triggers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    triggers = [str(item).strip() for item in value if str(item).strip()]
    unknown = sorted({item for item in triggers if item not in EMAIL_EVENT_TRIGGERS})
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown email triggers: {', '.join(unknown)}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in triggers:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _default_email_settings() -> dict[str, Any]:
    return {
        "email_enabled": False,
        "email_from_email": "",
        "email_from_name": "",
        "email_subject_prefix": "",
        "email_recipients": [],
        "email_event_triggers": [],
    }


def _normalize_email_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base = _default_email_settings()
    merged = {**base, **(payload or {})}
    email_from_email = _normalize_email_value(merged.get("email_from_email") or "") if merged.get("email_from_email") else ""
    recipients = _normalize_recipients(merged.get("email_recipients") or [])
    triggers = _normalize_event_triggers(merged.get("email_event_triggers") or [])
    normalized = {
        "email_enabled": bool(merged.get("email_enabled")),
        "email_from_email": email_from_email,
        "email_from_name": str(merged.get("email_from_name") or "").strip(),
        "email_subject_prefix": str(merged.get("email_subject_prefix") or "").strip(),
        "email_recipients": recipients,
        "email_event_triggers": triggers,
    }
    if normalized["email_enabled"]:
        if not normalized["email_from_email"]:
            raise HTTPException(status_code=400, detail="email_from_email is required when email is enabled.")
        if not normalized["email_recipients"]:
            raise HTTPException(status_code=400, detail="At least one recipient is required when email is enabled.")
    return normalized


def _load_email_settings() -> dict[str, Any]:
    raw: dict[str, Any] | None = None
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT value FROM system_settings WHERE key = %s", (EMAIL_SETTINGS_KEY,))
                row = cursor.fetchone()
                if row:
                    raw = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (EMAIL_SETTINGS_KEY,)).fetchone()
            if row is not None:
                raw = json.loads(row["value"] or "{}")
    return _normalize_email_settings_payload(raw or {})


def _save_email_settings(settings_payload: dict[str, Any]) -> None:
    normalized = _normalize_email_settings_payload(settings_payload)
    payload = json.dumps(normalized)
    now = _utc_now()
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
                    (EMAIL_SETTINGS_KEY, payload),
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
            (EMAIL_SETTINGS_KEY, payload, now),
        )


def _get_email_settings_payload() -> dict[str, Any]:
    return _load_email_settings()


def _set_email_settings_payload(request: EmailSettingsUpdateRequest) -> dict[str, Any]:
    parsed = request.model_dump()
    parsed["email_recipients"] = request.email_recipients
    _save_email_settings(parsed)
    return _load_email_settings()


def _load_smtp_config() -> SmtpConfig:
    missing: list[str] = []
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    tls_mode = os.getenv("SMTP_TLS_MODE", "").strip().lower()
    if not host:
        missing.append("SMTP_HOST")
    if not port_raw:
        missing.append("SMTP_PORT")
    if not username:
        missing.append("SMTP_USERNAME")
    if not password:
        missing.append("SMTP_PASSWORD")
    if not tls_mode:
        missing.append("SMTP_TLS_MODE")
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing SMTP environment values: {', '.join(missing)}")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="SMTP_PORT must be an integer.") from exc
    if tls_mode not in {"starttls", "ssl"}:
        raise HTTPException(status_code=503, detail="SMTP_TLS_MODE must be 'starttls' or 'ssl'.")
    return SmtpConfig(host=host, port=port, username=username, password=password, tls_mode=tls_mode)


def _build_email_subject(prefix: str, event_type: str, title: str) -> str:
    base = f"[{event_type}] {title}"
    cleaned_prefix = prefix.strip()
    return f"{cleaned_prefix} {base}".strip() if cleaned_prefix else base


def _trigger_source_label(trigger_source: str | None) -> str:
    source = str(trigger_source or "").strip().lower()
    mapping = {
        "github": "github webhook",
        "schedule": "schedule",
        "profile": "profile launch",
        "manual": "manual",
        "replay": "replay",
    }
    return mapping.get(source, source or "N/A")


def _launch_context_lines(run: dict[str, Any]) -> list[str]:
    trigger_context = run.get("trigger_context") if isinstance(run.get("trigger_context"), dict) else {}
    profile_name = str(trigger_context.get("profile_name") or "").strip()
    profile_id = run.get("profile_id") or trigger_context.get("profile_id")
    profile_value = profile_name or (f"Profile #{profile_id}" if profile_id is not None else "N/A")

    trigger_value = _trigger_source_label(run.get("trigger_source"))
    project = str(trigger_context.get("project") or "").strip() if isinstance(trigger_context, dict) else ""
    repository = str(trigger_context.get("repository") or "").strip() if isinstance(trigger_context, dict) else ""
    project_value = project or "N/A"
    repository_value = repository or "N/A"

    lines = [
        f"Profile: {profile_value}",
        f"Trigger: {trigger_value}",
        f"Project: {project_value}",
        f"Repository: {repository_value}",
    ]
    if str(run.get("trigger_source") or "").strip().lower() == "schedule":
        schedule_name = str(trigger_context.get("schedule_name") or "").strip()
        schedule_id = run.get("schedule_id") or trigger_context.get("schedule_id")
        schedule_value = schedule_name or (f"#{schedule_id}" if schedule_id is not None else "N/A")
        lines.append(f"Schedule: {schedule_value}")
    return lines


def _schedule_launch_context_lines(schedule: dict[str, Any], profile_name: str | None, profile_id: int | None) -> list[str]:
    profile_value = (profile_name or "").strip() or (f"Profile #{profile_id}" if profile_id is not None else "N/A")
    schedule_name = str(schedule.get("name") or "").strip()
    schedule_id = schedule.get("id")
    schedule_value = schedule_name or (f"#{schedule_id}" if schedule_id is not None else "N/A")
    return [
        f"Profile: {profile_value}",
        "Trigger: schedule",
        "Project: N/A",
        "Repository: N/A",
        f"Schedule: {schedule_value}",
    ]


def _email_observability_footer_lines() -> list[str]:
    return [
        "",
        "---",
        "How to read this (observability):",
        "- A failed run means the **simulation process** did not complete successfully (Down for that check). Open the run URL in the web UI for logs and artifacts.",
        "- **GET /healthz** only confirms the simulator **API process** is up (control plane). It does **not** prove last-mile HTTP/WebSocket services are healthy—use doctor/trace runs for end-to-end proof.",
        "See SIMULATOR_GUIDE.md sections \"Health contract\" and \"Which simulation flow should I use?\".",
    ]


def _send_email_notification(
    event_type: str,
    title: str,
    lines: list[str],
    dedupe_key: str | None = None,
    ignore_trigger_gate: bool = False,
) -> dict[str, Any]:
    settings = _load_email_settings()
    if not settings.get("email_enabled"):
        return {"sent": False, "reason": "email_disabled"}
    configured_triggers = set(settings.get("email_event_triggers") or [])
    if not ignore_trigger_gate:
        if event_type not in configured_triggers and not (event_type == "run_failed" and "critical_alert" in configured_triggers):
            return {"sent": False, "reason": "trigger_not_enabled"}

    if dedupe_key:
        now = time.monotonic()
        with EMAIL_EVENT_LOCK:
            last_sent = EMAIL_EVENT_LAST_SENT.get(dedupe_key, 0.0)
            if now - last_sent < EMAIL_EVENT_DEDUPE_WINDOW_SECONDS:
                return {"sent": False, "reason": "deduped"}
            EMAIL_EVENT_LAST_SENT[dedupe_key] = now
            stale = [key for key, value in EMAIL_EVENT_LAST_SENT.items() if now - value > EMAIL_EVENT_DEDUPE_WINDOW_SECONDS * 4]
            for key in stale:
                EMAIL_EVENT_LAST_SENT.pop(key, None)

    smtp = _load_smtp_config()
    sender = settings.get("email_from_email") or ""
    recipients = list(settings.get("email_recipients") or [])
    if not sender or not recipients:
        raise HTTPException(status_code=400, detail="Email sender and recipients must be configured before sending.")
    subject = _build_email_subject(settings.get("email_subject_prefix") or "", event_type, title)
    body = "\n".join(lines).strip()
    response = send_plain_text_email(
        smtp,
        sender_email=sender,
        sender_name=settings.get("email_from_name") or "",
        recipients=recipients,
        subject=subject,
        body=body,
    )
    return {"sent": True, "recipients": recipients, "subject": subject, **response}


def _send_test_email_payload() -> dict[str, Any]:
    global EMAIL_TEST_LAST_SENT_AT
    now = time.monotonic()
    with EMAIL_EVENT_LOCK:
        elapsed = now - EMAIL_TEST_LAST_SENT_AT
        if elapsed < EMAIL_TEST_COOLDOWN_SECONDS:
            wait_for = max(1, int(EMAIL_TEST_COOLDOWN_SECONDS - elapsed))
            raise HTTPException(status_code=429, detail=f"Please wait {wait_for}s before sending another test email.")
        EMAIL_TEST_LAST_SENT_AT = now
    timestamp = _utc_now()
    return _send_email_notification(
        "run_failed",
        "Simulator test email",
        [
            "This is a simulator test email.",
            f"Timestamp: {timestamp}",
            "If you received this, SMTP configuration is working.",
        ],
        dedupe_key=f"email-test-{int(now // EMAIL_TEST_COOLDOWN_SECONDS)}",
        ignore_trigger_gate=True,
    )


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
    payload["enforce_websocket_gates"] = bool(payload.get("enforce_websocket_gates"))
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
    if payload.get("execution_snapshot"):
        payload["execution_snapshot"] = json.loads(payload["execution_snapshot"])
    if payload.get("trigger_context"):
        payload["trigger_context"] = json.loads(payload["trigger_context"])
    else:
        payload["trigger_context"] = {}
    return payload


def _row_to_dict_any(row) -> dict[str, Any]:
    """Convert database row to dict, supporting both SQLite and PostgreSQL"""
    if USE_POSTGRES:
        payload = dict(row)
        if payload.get("trigger_context") is None:
            payload["trigger_context"] = {}
        payload["enforce_websocket_gates"] = bool(payload.get("enforce_websocket_gates"))
        return payload
    else:
        # SQLite returns Row objects
        payload = dict(row)
        payload["all_users"] = bool(payload["all_users"])
        payload["no_auto_provision"] = bool(payload["no_auto_provision"])
        payload["enforce_websocket_gates"] = bool(payload.get("enforce_websocket_gates"))
        if payload["post_order_actions"] is not None:
            payload["post_order_actions"] = bool(payload["post_order_actions"])
        payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
        snapshot = payload.get("execution_snapshot")
        if isinstance(snapshot, str) and snapshot:
            payload["execution_snapshot"] = json.loads(snapshot)
        trigger_context = payload.get("trigger_context")
        if isinstance(trigger_context, str) and trigger_context:
            payload["trigger_context"] = json.loads(trigger_context)
        elif trigger_context is None:
            payload["trigger_context"] = {}
        return payload


def _profile_row_to_dict_any(row) -> dict[str, Any]:
    payload = dict(row)
    payload["all_users"] = bool(payload["all_users"])
    payload["strict_plan"] = bool(payload.get("strict_plan"))
    payload["skip_app_probes"] = bool(payload.get("skip_app_probes"))
    payload["skip_store_dashboard_probes"] = bool(payload.get("skip_store_dashboard_probes"))
    payload["no_auto_provision"] = bool(payload["no_auto_provision"])
    payload["enforce_websocket_gates"] = bool(payload.get("enforce_websocket_gates"))
    payload["continuous"] = bool(payload.get("continuous"))
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    scenarios = payload.get("scenarios")
    if isinstance(scenarios, str):
        payload["scenarios"] = json.loads(scenarios or "[]")
    elif scenarios is None:
        payload["scenarios"] = []
    payload["users"] = int(payload["users"]) if payload.get("users") is not None else None
    payload["orders"] = int(payload["orders"]) if payload.get("orders") is not None else None
    payload["interval"] = float(payload["interval"]) if payload.get("interval") is not None else None
    payload["reject"] = float(payload["reject"]) if payload.get("reject") is not None else None
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
    payload["recurrence_config"] = _load_json_field(payload.get("recurrence_config"), {})
    payload["run_slots"] = _load_json_field(payload.get("run_slots"), [])
    payload["all_day"] = bool(payload.get("all_day"))
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
    status = str(fields.get("status") or "").lower()
    if status == "failed":
        try:
            run = _get_run(run_id)
            trigger_label = _trigger_source_label(run.get("trigger_source"))
            _send_email_notification(
                "run_failed",
                f"{trigger_label}: run {run_id} failed",
                [
                    *_launch_context_lines(run),
                    f"Run ID: {run_id}",
                    f"Flow: {run.get('flow')}",
                    f"Status: {run.get('status')}",
                    f"Finished At: {run.get('finished_at') or _utc_now()}",
                    f"Error: {run.get('error') or 'Simulation failed.'}",
                    f"Run URL: /runs/{run_id}",
                    *_email_observability_footer_lines(),
                ],
                dedupe_key=f"run-failed:{run_id}",
            )
        except Exception as exc:
            LOGGER.warning("Failed to send run failure email run_id=%s error=%s", run_id, exc)
    if status in TERMINAL_RUN_STATUSES:
        try:
            _handle_integration_run_terminal_status(run_id, status)
        except Exception as exc:
            LOGGER.warning("Failed integration terminal-status callback for run %s: %s", run_id, exc)

@dataclass
class ScheduledRun:
    flow: str
    plan: str
    timing: str
    store_id: str | None = None


def _flows_payload() -> dict[str, Any]:
    capabilities = flow_capabilities()
    return {
        "flows": sorted(FLOW_PRESETS.keys()),
        "capabilities": capabilities,
    }


def _build_command(request: RunCreateRequest) -> list[str]:
    if request.flow not in FLOW_PRESETS:
        expected = ", ".join(sorted(FLOW_PRESETS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported flow {request.flow!r}. Expected one of {expected}.",
        )
    preset = FLOW_PRESETS[request.flow]
    resolved_mode = request.mode or str(preset.get("mode") or "trace")
    if resolved_mode not in {"trace", "load"}:
        raise HTTPException(status_code=400, detail=f"Unsupported mode {resolved_mode!r}. Expected trace or load.")
    if request.reject is not None and not 0.0 <= request.reject <= 1.0:
        raise HTTPException(status_code=400, detail="reject must be between 0.0 and 1.0.")
    if request.users is not None and request.users < 1:
        raise HTTPException(status_code=400, detail="users must be >= 1.")
    if request.orders is not None and request.orders < 1:
        raise HTTPException(status_code=400, detail="orders must be >= 1.")
    if resolved_mode == "trace" and request.continuous:
        raise HTTPException(status_code=400, detail="continuous is only supported in load mode.")
    if resolved_mode == "trace" and any(
        value is not None for value in (request.users, request.orders, request.interval, request.reject)
    ):
        raise HTTPException(
            status_code=400,
            detail="users/orders/interval/reject are only supported in load mode.",
        )
    if resolved_mode == "load" and (request.suite or request.scenarios):
        raise HTTPException(
            status_code=400,
            detail="suite/scenarios are only supported in trace mode.",
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
    if request.suite:
        command.extend(["--suite", request.suite])
    for scenario in request.scenarios or []:
        if scenario:
            command.extend(["--scenario", scenario])
    if request.store_id:
        command.extend(["--store", request.store_id])
    if request.phone:
        command.extend(["--phone", request.phone])
    if request.all_users:
        command.append("--all-users")
    if request.strict_plan:
        command.append("--strict-plan")
    if request.skip_app_probes:
        command.append("--skip-app-probes")
    if request.skip_store_dashboard_probes:
        command.append("--skip-store-dashboard-probes")
    if request.no_auto_provision:
        command.append("--no-auto-provision")
    if request.enforce_websocket_gates:
        command.append("--enforce-websocket-gates")
    if request.post_order_actions:
        command.append("--post-order-actions")
    if request.users is not None:
        command.extend(["--users", str(request.users)])
    if request.orders is not None:
        command.extend(["--orders", str(request.orders)])
    if request.interval is not None:
        command.extend(["--interval", str(request.interval)])
    if request.reject is not None:
        command.extend(["--reject", str(request.reject)])
    if request.continuous:
        command.append("--continuous")
    if request.extra_args:
        command.extend(request.extra_args)
    return command


def _build_execution_snapshot(request: RunCreateRequest, command: list[str], created_at: str) -> dict[str, Any]:
    return {
        "version": 2,
        "flow": request.flow,
        "plan": request.plan,
        "timing": request.timing,
        "mode": request.mode,
        "suite": request.suite,
        "scenarios": request.scenarios,
        "store_id": request.store_id,
        "phone": request.phone,
        "all_users": request.all_users,
        "strict_plan": request.strict_plan,
        "skip_app_probes": request.skip_app_probes,
        "skip_store_dashboard_probes": request.skip_store_dashboard_probes,
        "no_auto_provision": request.no_auto_provision,
        "enforce_websocket_gates": request.enforce_websocket_gates,
        "post_order_actions": request.post_order_actions,
        "users": request.users,
        "orders": request.orders,
        "interval": request.interval,
        "reject": request.reject,
        "continuous": request.continuous,
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
        suite=profile.get("suite"),
        scenarios=list(profile.get("scenarios") or []),
        store_id=profile.get("store_id"),
        phone=profile.get("phone"),
        all_users=bool(profile.get("all_users")),
        strict_plan=bool(profile.get("strict_plan")),
        skip_app_probes=bool(profile.get("skip_app_probes")),
        skip_store_dashboard_probes=bool(profile.get("skip_store_dashboard_probes")),
        no_auto_provision=bool(profile.get("no_auto_provision")),
        enforce_websocket_gates=bool(profile.get("enforce_websocket_gates")),
        post_order_actions=profile.get("post_order_actions"),
        users=profile.get("users"),
        orders=profile.get("orders"),
        interval=profile.get("interval"),
        reject=profile.get("reject"),
        continuous=bool(profile.get("continuous")),
        extra_args=list(profile.get("extra_args") or []),
        trigger_source="profile",
        trigger_label=f"Profile launch: {profile.get('name') or profile.get('id')}",
        trigger_context={
            "profile_id": profile.get("id"),
            "profile_name": profile.get("name"),
        },
        profile_id=profile.get("id"),
    )


def _apply_profile_launch_trigger_overlay(request: RunCreateRequest, overlay: dict[str, Any]) -> None:
    """Merge automation trigger fields onto a profile-derived run request (e.g. GitHub webhooks)."""
    ts = overlay.get("trigger_source")
    if ts in ("manual", "profile", "schedule", "github", "replay"):
        request.trigger_source = ts
    if "trigger_label" in overlay and overlay["trigger_label"] is not None:
        request.trigger_label = str(overlay["trigger_label"])
    if overlay.get("integration_trigger_id") is not None:
        request.integration_trigger_id = int(overlay["integration_trigger_id"])
    if overlay.get("schedule_id") is not None:
        request.schedule_id = int(overlay["schedule_id"])
    extra_ctx = overlay.get("trigger_context")
    if isinstance(extra_ctx, dict) and extra_ctx:
        merged = dict(request.trigger_context or {})
        merged.update(extra_ctx)
        request.trigger_context = merged


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
    
    trigger_source = request.trigger_source or "manual"
    trigger_label = request.trigger_label or "Manual launch"
    trigger_context = request.trigger_context or {}

    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runs (
                        user_id, flow, plan, timing, mode, store_id, phone, store_phone,
                        user_name, store_name, all_users, no_auto_provision,
                        enforce_websocket_gates, post_order_actions, extra_args, status, command, created_at, execution_snapshot,
                        trigger_source, trigger_label, trigger_context, profile_id, schedule_id,
                        integration_trigger_id, launched_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        request.enforce_websocket_gates,
                        request.post_order_actions,
                        json.dumps(request.extra_args),
                        "queued",
                        " ".join(command),
                        created_at,
                        json.dumps(execution_snapshot),
                        trigger_source,
                        trigger_label,
                        json.dumps(trigger_context),
                        request.profile_id,
                        request.schedule_id,
                        request.integration_trigger_id,
                        request.launched_by_user_id if request.launched_by_user_id is not None else persisted_user_id,
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
                    all_users, no_auto_provision, enforce_websocket_gates, post_order_actions, extra_args, status, command, created_at, execution_snapshot,
                    trigger_source, trigger_label, trigger_context, profile_id, schedule_id, integration_trigger_id, launched_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(request.enforce_websocket_gates),
                    int(request.post_order_actions) if request.post_order_actions is not None else None,
                    json.dumps(request.extra_args),
                    "queued",
                    " ".join(command),
                    created_at,
                    json.dumps(execution_snapshot),
                    trigger_source,
                    trigger_label,
                    json.dumps(trigger_context),
                    request.profile_id,
                    request.schedule_id,
                    request.integration_trigger_id,
                    request.launched_by_user_id if request.launched_by_user_id is not None else persisted_user_id,
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
                        user_id, name, description, flow, plan, timing, mode, suite, scenarios, store_id, phone,
                        all_users, strict_plan, skip_app_probes, skip_store_dashboard_probes, no_auto_provision,
                        enforce_websocket_gates, post_order_actions, users, orders, interval, reject, continuous,
                        extra_args, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        request.suite,
                        json.dumps(request.scenarios),
                        request.store_id,
                        request.phone,
                        request.all_users,
                        request.strict_plan,
                        request.skip_app_probes,
                        request.skip_store_dashboard_probes,
                        request.no_auto_provision,
                        request.enforce_websocket_gates,
                        request.post_order_actions,
                        request.users,
                        request.orders,
                        request.interval,
                        request.reject,
                        request.continuous,
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
                    user_id, name, description, flow, plan, timing, mode, suite, scenarios, store_id, phone,
                    all_users, strict_plan, skip_app_probes, skip_store_dashboard_probes, no_auto_provision,
                    enforce_websocket_gates, post_order_actions, users, orders, interval, reject, continuous,
                    extra_args, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persisted_user_id,
                    request.name,
                    request.description,
                    request.flow,
                    request.plan,
                    request.timing,
                    request.mode,
                    request.suite,
                    json.dumps(request.scenarios),
                    request.store_id,
                    request.phone,
                    int(request.all_users),
                    int(request.strict_plan),
                    int(request.skip_app_probes),
                    int(request.skip_store_dashboard_probes),
                    int(request.no_auto_provision),
                    int(request.enforce_websocket_gates),
                    int(request.post_order_actions) if request.post_order_actions is not None else None,
                    request.users,
                    request.orders,
                    request.interval,
                    request.reject,
                    int(request.continuous),
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
        "suite": request.suite,
        "scenarios": json.dumps(request.scenarios),
        "store_id": request.store_id,
        "phone": request.phone,
        "all_users": request.all_users,
        "strict_plan": request.strict_plan,
        "skip_app_probes": request.skip_app_probes,
        "skip_store_dashboard_probes": request.skip_store_dashboard_probes,
        "no_auto_provision": request.no_auto_provision,
        "enforce_websocket_gates": request.enforce_websocket_gates,
        "post_order_actions": request.post_order_actions,
        "users": request.users,
        "orders": request.orders,
        "interval": request.interval,
        "reject": request.reject,
        "continuous": request.continuous,
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


def _launch_run_profile(
    profile_id: int,
    user_id: Optional[int] = None,
    trigger_overlay: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    profile = _get_run_profile(profile_id)
    request = _profile_request_to_run_request(profile)
    request.launched_by_user_id = user_id
    if trigger_overlay:
        _apply_profile_launch_trigger_overlay(request, trigger_overlay)
    run = _create_run(request, user_id)
    return {"profile": profile, "run": run}


def _integration_mapping_row_to_dict_any(row: Any) -> dict[str, Any]:
    payload = dict(row)
    payload["enabled"] = bool(payload.get("enabled"))
    return payload


def _list_integration_mappings() -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM integration_profile_mappings ORDER BY project ASC, environment ASC, id ASC"
                )
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                "SELECT * FROM integration_profile_mappings ORDER BY project ASC, environment ASC, id ASC"
            ).fetchall()
    return {"mappings": [_integration_mapping_row_to_dict_any(row) for row in rows]}


def _upsert_integration_mapping(request: IntegrationMappingUpsertRequest, user_id: Optional[int] = None) -> dict[str, Any]:
    _ = user_id
    _get_run_profile(int(request.profile_id))
    project = request.project.strip().lower()
    environment = request.environment.strip().lower()
    now = _utc_now()
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO integration_profile_mappings (project, environment, profile_id, enabled, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project, environment)
                    DO UPDATE SET profile_id = EXCLUDED.profile_id, enabled = EXCLUDED.enabled, updated_at = EXCLUDED.updated_at
                    RETURNING *
                    """,
                    (project, environment, request.profile_id, request.enabled, now, now),
                )
                row = cursor.fetchone()
            conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            conn.execute(
                """
                INSERT INTO integration_profile_mappings (project, environment, profile_id, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, environment) DO UPDATE
                SET profile_id = excluded.profile_id, enabled = excluded.enabled, updated_at = excluded.updated_at
                """,
                (project, environment, request.profile_id, int(request.enabled), now, now),
            )
            row = conn.execute(
                "SELECT * FROM integration_profile_mappings WHERE project = ? AND environment = ?",
                (project, environment),
            ).fetchone()
    return {"mapping": _integration_mapping_row_to_dict_any(row)}


def _delete_integration_mapping(mapping_id: int) -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM integration_profile_mappings WHERE id = %s", (mapping_id,))
                deleted = cursor.rowcount > 0
            conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            cursor = conn.execute("DELETE FROM integration_profile_mappings WHERE id = ?", (mapping_id,))
            deleted = cursor.rowcount > 0
    return {"mapping_id": mapping_id, "deleted": deleted}


def _list_integration_triggers(limit: int, offset: int) -> dict[str, Any]:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM integration_triggers ORDER BY id DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                rows = cursor.fetchall()
                cursor.execute("SELECT COUNT(*) FROM integration_triggers")
                total = cursor.fetchone()[0]
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                "SELECT * FROM integration_triggers ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total_row = conn.execute("SELECT COUNT(*) FROM integration_triggers").fetchone()
            total = int(total_row[0]) if total_row else 0
    return {
        "triggers": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _match_project_for_repository(repository: str) -> str | None:
    repo = repository.strip().lower()
    allowlist = SIMULATOR_WEBHOOK_REPO_ALLOWLIST if isinstance(SIMULATOR_WEBHOOK_REPO_ALLOWLIST, dict) else {}
    for project, repos in allowlist.items():
        if not isinstance(repos, list):
            continue
        normalized_repos = {str(item).strip().lower() for item in repos if str(item).strip()}
        if repo in normalized_repos:
            return str(project).strip().lower()
    return None


def _verify_github_signature(project: str, body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    secret_map = SIMULATOR_WEBHOOK_PROJECT_SECRETS if isinstance(SIMULATOR_WEBHOOK_PROJECT_SECRETS, dict) else {}
    secret = str(secret_map.get(project, "")).strip()
    if not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(digest, provided)


def _integration_mapping_for(project: str, environment: str) -> dict[str, Any] | None:
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM integration_profile_mappings
                    WHERE project = %s AND environment = %s
                    """,
                    (project, environment),
                )
                row = cursor.fetchone()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute(
                """
                SELECT * FROM integration_profile_mappings
                WHERE project = ? AND environment = ?
                """,
                (project, environment),
            ).fetchone()
    if row is None:
        return None
    return _integration_mapping_row_to_dict_any(row)


def _create_integration_trigger(
    *,
    project: str,
    environment: str,
    repository: str,
    sha: str,
    deployment_id: str,
    deployment_status_id: str | None,
    event_name: str,
    dedupe_key: str,
    status: str,
    reason: str | None,
    payload: dict[str, Any],
    github_status_url: str | None,
) -> tuple[dict[str, Any], bool]:
    created_at = _utc_now()
    payload_json = json.dumps(payload)
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM integration_triggers WHERE dedupe_key = %s
                    """,
                    (dedupe_key,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    return dict(existing), False
                cursor.execute(
                    """
                    INSERT INTO integration_triggers (
                        project, environment, repository, sha, deployment_id, deployment_status_id,
                        dedupe_key, event_name, status, reason, payload, github_status_url, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    RETURNING *
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
                        github_status_url,
                        created_at,
                        created_at,
                    ),
                )
                row = cursor.fetchone()
            conn.commit()
            return dict(row), True
        finally:
            conn.close()
    with DB_LOCK, _db() as conn:
        existing = conn.execute(
            "SELECT * FROM integration_triggers WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if existing is not None:
            return dict(existing), False
        cursor = conn.execute(
            """
            INSERT INTO integration_triggers (
                project, environment, repository, sha, deployment_id, deployment_status_id,
                dedupe_key, event_name, status, reason, payload, github_status_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                github_status_url,
                created_at,
                created_at,
            ),
        )
        row = conn.execute("SELECT * FROM integration_triggers WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
        return dict(row), True


def _update_integration_trigger(trigger_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = _utc_now()
    keys = list(fields.keys())
    values = [fields[key] for key in keys]
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                assignment = ", ".join(f"{key} = %s" for key in keys)
                cursor.execute(
                    f"UPDATE integration_triggers SET {assignment} WHERE id = %s",
                    (*values, trigger_id),
                )
            conn.commit()
        finally:
            conn.close()
        return
    with DB_LOCK, _db() as conn:
        assignment = ", ".join(f"{key} = ?" for key in keys)
        conn.execute(
            f"UPDATE integration_triggers SET {assignment} WHERE id = ?",
            (*values, trigger_id),
        )


def _github_status_url_from_payload(payload: dict[str, Any]) -> str | None:
    status = payload.get("deployment_status")
    if isinstance(status, dict):
        value = status.get("statuses_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _enqueue_integration_profile_launch(
    trigger_id: int,
    profile_id: int,
    *,
    project: str,
    environment: str,
    repository: str,
) -> None:
    def _runner() -> None:
        try:
            profile = _get_run_profile(profile_id)
            request = _profile_request_to_run_request(profile)
            request.trigger_source = "github"
            request.trigger_label = f"GitHub integration: {project}/{environment}"
            request.trigger_context = {
                "project": project,
                "environment": environment,
                "repository": repository,
                "integration_trigger_id": trigger_id,
                "profile_id": profile_id,
                "profile_name": profile.get("name"),
            }
            request.integration_trigger_id = trigger_id
            request.profile_id = profile_id
            run = _create_run(request, None)
            run_id = int(run["id"])
            _update_integration_trigger(trigger_id, status="launched", run_id=run_id)
        except Exception as exc:
            _update_integration_trigger(
                trigger_id,
                status="failed",
                reason=f"launch_failed:{exc}",
                finished_at=_utc_now(),
            )

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


def _normalize_deployment_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    deployment = payload.get("deployment") if isinstance(payload.get("deployment"), dict) else {}
    deployment_status = payload.get("deployment_status") if isinstance(payload.get("deployment_status"), dict) else {}
    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    repository_full_name = str(repository.get("full_name") or "").strip().lower()
    environment = str(deployment.get("environment") or "").strip().lower()
    sha = str(deployment.get("sha") or "").strip()
    deployment_id = str(deployment.get("id") or "").strip()
    deployment_status_id = str(deployment_status.get("id") or "").strip() or None
    state = str(deployment_status.get("state") or "").strip().lower()
    return {
        "repository": repository_full_name,
        "environment": environment,
        "sha": sha,
        "deployment_id": deployment_id,
        "deployment_status_id": deployment_status_id,
        "state": state,
    }


def _process_github_deployment_webhook(body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    event_name = str(headers.get("x-github-event") or "").strip().lower()
    signature = headers.get("x-hub-signature-256")
    if event_name != "deployment_status":
        return {"accepted": False, "status": "rejected", "reason": "unsupported_event"}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"accepted": False, "status": "rejected", "reason": "invalid_json"}

    normalized = _normalize_deployment_webhook_payload(payload)
    repository = normalized["repository"]
    environment = normalized["environment"]
    sha = normalized["sha"]
    deployment_id = normalized["deployment_id"]
    deployment_status_id = normalized["deployment_status_id"]
    state = normalized["state"]
    if not repository or not environment or not sha or not deployment_id:
        return {"accepted": False, "status": "rejected", "reason": "missing_required_fields"}
    project = _match_project_for_repository(repository)
    if not project:
        return {"accepted": False, "status": "rejected", "reason": "repository_not_allowlisted", "repository": repository}
    if not _verify_github_signature(project, body, signature):
        return {"accepted": False, "status": "rejected", "reason": "invalid_signature", "repository": repository}
    if state != "success":
        return {"accepted": False, "status": "rejected", "reason": "non_success_state", "repository": repository}

    dedupe_key = f"{project}:{environment}:{deployment_id}:{sha}"
    github_status_url = _github_status_url_from_payload(payload)
    trigger, created = _create_integration_trigger(
        project=project,
        environment=environment,
        repository=repository,
        sha=sha,
        deployment_id=deployment_id,
        deployment_status_id=deployment_status_id,
        event_name=event_name,
        dedupe_key=dedupe_key,
        status="validated",
        reason=None,
        payload=payload,
        github_status_url=github_status_url,
    )
    if not created:
        return {
            "accepted": True,
            "status": "duplicate",
            "trigger_id": trigger["id"],
            "run_id": trigger.get("run_id"),
            "project": project,
            "environment": environment,
            "repository": repository,
        }

    mapping = _integration_mapping_for(project, environment)
    if mapping is None:
        _update_integration_trigger(trigger["id"], status="rejected", reason="mapping_not_found", finished_at=_utc_now())
        return {
            "accepted": False,
            "status": "rejected",
            "reason": "mapping_not_found",
            "trigger_id": trigger["id"],
            "project": project,
            "environment": environment,
            "repository": repository,
        }
    if not mapping.get("enabled", True):
        _update_integration_trigger(trigger["id"], status="rejected", reason="mapping_disabled", finished_at=_utc_now())
        return {
            "accepted": False,
            "status": "rejected",
            "reason": "mapping_disabled",
            "trigger_id": trigger["id"],
            "project": project,
            "environment": environment,
            "repository": repository,
        }

    _update_integration_trigger(trigger["id"], status="queued", reason=None)
    _enqueue_integration_profile_launch(
        int(trigger["id"]),
        int(mapping["profile_id"]),
        project=project,
        environment=environment,
        repository=repository,
    )
    return {
        "accepted": True,
        "status": "queued",
        "trigger_id": trigger["id"],
        "project": project,
        "environment": environment,
        "repository": repository,
    }


def _post_github_deployment_status(trigger: dict[str, Any], run: dict[str, Any]) -> None:
    status_url = str(trigger.get("github_status_url") or "").strip()
    repository = str(trigger.get("repository") or "").strip()
    if not status_url and repository and trigger.get("deployment_id"):
        encoded_repo = urllib_parse.quote(repository, safe="")
        status_url = f"{GITHUB_STATUS_API_BASE}/repos/{encoded_repo}/deployments/{trigger['deployment_id']}/statuses"
    if not status_url or not GITHUB_STATUS_TOKEN:
        return

    run_id = run.get("id")
    run_status = str(run.get("status") or "").lower()
    state = "success" if run_status == "succeeded" else "failure"
    run_url = f"{SIMULATOR_EXTERNAL_BASE_URL}/runs/{run_id}" if SIMULATOR_EXTERNAL_BASE_URL else None
    body = {
        "state": state,
        "description": f"Simulator run {run_status}",
        "context": GITHUB_STATUS_CONTEXT,
    }
    if run_url:
        body["target_url"] = run_url
    data = json.dumps(body).encode("utf-8")
    req = urllib_request.Request(
        status_url,
        data=data,
        headers={
            "Authorization": f"Bearer {GITHUB_STATUS_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "fainzy-simulator",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            _ = response.read()
    except urllib_error.URLError as exc:
        LOGGER.warning("Failed to post GitHub deployment status for trigger %s: %s", trigger.get("id"), exc)


def _handle_integration_run_terminal_status(run_id: int, status: str) -> None:
    if status not in TERMINAL_RUN_STATUSES:
        return
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM integration_triggers
                    WHERE run_id = %s AND status IN ('launched', 'queued')
                    ORDER BY id DESC
                    """,
                    (run_id,),
                )
                triggers = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_triggers
                WHERE run_id = ? AND status IN ('launched', 'queued')
                ORDER BY id DESC
                """,
                (run_id,),
            ).fetchall()
            triggers = [dict(row) for row in rows]
    if not triggers:
        return

    run = _get_run(run_id)
    final_status = "completed" if status == "succeeded" else "failed"
    for trigger in triggers:
        _update_integration_trigger(trigger["id"], status=final_status, reason=None, finished_at=_utc_now())
        thread = threading.Thread(target=_post_github_deployment_status, args=(trigger, run), daemon=True)
        thread.start()


def _datetime_as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


WEEKDAY_TO_INT: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_slot_time(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    parsed = _parse_schedule_time(value)
    if parsed is None:
        return None
    hour, minute = parsed
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _weekday_index(value: Any) -> int | None:
    if isinstance(value, int) and 0 <= value <= 6:
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in WEEKDAY_TO_INT:
            return WEEKDAY_TO_INT[key]
    return None


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

    using_new_contract = bool(
        request.period
        or request.anchor_start_at
        or request.stop_rule
        or request.end_at
        or request.duration_seconds is not None
        or request.repeat
        or request.run_slots
        or request.all_day
    )
    if using_new_contract:
        anchor_start_at = _parse_run_timestamp(request.anchor_start_at)
        if anchor_start_at is None:
            raise HTTPException(status_code=400, detail="anchor_start_at is required and must be a valid ISO date-time.")
        if request.period not in {"daily", "weekly", "monthly"}:
            raise HTTPException(status_code=400, detail="period must be one of daily, weekly, monthly.")
        if request.repeat not in {"none", "daily", "weekly", "monthly", "annually", "weekdays", "custom"}:
            raise HTTPException(status_code=400, detail="repeat must be one of none, daily, weekly, monthly, annually, weekdays, custom.")
        if request.stop_rule not in {"never", "end_at", "duration"}:
            raise HTTPException(status_code=400, detail="stop_rule must be one of never, end_at, duration.")
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
        if request.repeat == "custom":
            recurrence = request.recurrence_config or {}
            weekdays = recurrence.get("weekdays")
            if not isinstance(weekdays, list) or not weekdays:
                raise HTTPException(status_code=400, detail="custom repeat requires recurrence_config.weekdays.")
            for weekday in weekdays:
                if _weekday_index(weekday) is None:
                    raise HTTPException(status_code=400, detail="custom repeat weekdays must be monday..sunday.")
            if request.stop_rule != "end_at":
                raise HTTPException(status_code=400, detail="custom repeat requires stop_rule=end_at.")

        seen_slots: set[str] = set()
        if not request.all_day:
            if not request.run_slots:
                raise HTTPException(status_code=400, detail="run_slots must include at least one slot when all_day=false.")
            for slot in request.run_slots:
                time_value = _parse_slot_time(slot.get("time"))
                if time_value is None:
                    raise HTTPException(status_code=400, detail="Each run slot requires valid HH:MM time.")
                if request.period == "daily":
                    key = f"{time_value[0]:02d}:{time_value[1]:02d}"
                elif request.period == "weekly":
                    weekday = _weekday_index(slot.get("weekday"))
                    if weekday is None:
                        raise HTTPException(status_code=400, detail="Weekly run slots require weekday.")
                    key = f"{weekday}:{time_value[0]:02d}:{time_value[1]:02d}"
                else:
                    kind = str(slot.get("kind") or "")
                    if kind == "day_of_month":
                        day = int(slot.get("day") or 0)
                        if day < 1 or day > 31:
                            raise HTTPException(status_code=400, detail="Monthly day_of_month slots require day between 1 and 31.")
                        key = f"dom:{day}:{time_value[0]:02d}:{time_value[1]:02d}"
                    elif kind == "weekday_ordinal":
                        ordinal = int(slot.get("ordinal") or 0)
                        weekday = _weekday_index(slot.get("weekday"))
                        if ordinal < 1 or ordinal > 5 or weekday is None:
                            raise HTTPException(status_code=400, detail="Monthly weekday_ordinal slots require ordinal 1..5 and weekday.")
                        key = f"ord:{ordinal}:{weekday}:{time_value[0]:02d}:{time_value[1]:02d}"
                    else:
                        raise HTTPException(status_code=400, detail="Monthly run slots require kind day_of_month or weekday_ordinal.")
                if key in seen_slots:
                    raise HTTPException(status_code=400, detail="Duplicate run slots are not allowed.")
                seen_slots.add(key)

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

    if request.schedule_type == "simple" and request.profile_id is None:
        raise HTTPException(status_code=400, detail="Simple schedules require a run profile.")
    if request.schedule_type == "simple" and request.profile_id is not None:
        _get_run_profile(int(request.profile_id))
    for step in request.campaign_steps:
        _get_run_profile(int(step.profile_id))
    if request.schedule_type == "campaign" and not request.campaign_steps:
        raise HTTPException(status_code=400, detail="Campaign schedules require at least one campaign step.")


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


def _shift_into_run_window(
    schedule: dict[str, Any],
    candidate: datetime,
    timezone_info: ZoneInfo,
) -> tuple[datetime, bool]:
    bounds = _window_bounds_minutes(schedule)
    if bounds is None:
        return candidate, False

    start_minutes, end_minutes = bounds
    current_minutes = candidate.hour * 60 + candidate.minute

    # Non-wrapping window (e.g., 08:00-18:00)
    if start_minutes <= end_minutes:
        if start_minutes <= current_minutes <= end_minutes:
            return candidate, False
        if current_minutes < start_minutes:
            shifted = _window_start_for_local_date(schedule, candidate.date(), timezone_info) or candidate
            return shifted, True
        shifted = _window_start_for_local_date(schedule, candidate.date() + timedelta(days=1), timezone_info) or candidate
        return shifted, True

    # Wrapping window (e.g., 22:00-02:00) -> allowed if >= start OR <= end
    if current_minutes >= start_minutes or current_minutes <= end_minutes:
        return candidate, False
    shifted = _window_start_for_local_date(schedule, candidate.date(), timezone_info) or candidate
    if shifted <= candidate:
        shifted = _window_start_for_local_date(schedule, candidate.date() + timedelta(days=1), timezone_info) or candidate
    return shifted, True


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


def _nth_weekday_of_month(year: int, month: int, weekday: int, ordinal: int, tzinfo: ZoneInfo) -> datetime | None:
    first = datetime(year, month, 1, tzinfo=tzinfo)
    shift = (weekday - first.weekday()) % 7
    day = 1 + shift + (ordinal - 1) * 7
    if day > _last_day_of_month(year, month):
        return None
    return datetime(year, month, day, tzinfo=tzinfo)


def _date_matches_repeat(local_dt: datetime, anchor_local: datetime, repeat: str, recurrence: dict[str, Any]) -> bool:
    if repeat == "none":
        return local_dt.date() == anchor_local.date()
    if repeat == "daily":
        return True
    if repeat == "weekdays":
        return local_dt.weekday() < 5
    if repeat == "weekly":
        return local_dt.weekday() == anchor_local.weekday()
    if repeat == "annually":
        return (local_dt.month, local_dt.day) == (anchor_local.month, anchor_local.day)
    if repeat == "monthly":
        return True
    if repeat == "custom":
        weekdays = recurrence.get("weekdays") or []
        target_weekdays = {_weekday_index(item) for item in weekdays}
        target_weekdays.discard(None)
        return local_dt.weekday() in target_weekdays
    return False


def _daily_or_weekly_slot_datetimes(day_start: datetime, period: str, slots: list[dict[str, Any]]) -> list[datetime]:
    out: list[datetime] = []
    if period == "daily":
        for slot in slots:
            parsed = _parse_slot_time(slot.get("time"))
            if parsed is None:
                continue
            out.append(day_start.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0))
        return out
    for slot in slots:
        weekday = _weekday_index(slot.get("weekday"))
        parsed = _parse_slot_time(slot.get("time"))
        if weekday is None or parsed is None:
            continue
        target_day = day_start + timedelta(days=(weekday - day_start.weekday()) % 7)
        out.append(target_day.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0))
    return out


def _monthly_slot_datetimes(day_start: datetime, slots: list[dict[str, Any]]) -> list[datetime]:
    out: list[datetime] = []
    for slot in slots:
        parsed = _parse_slot_time(slot.get("time"))
        if parsed is None:
            continue
        kind = str(slot.get("kind") or "")
        if kind == "day_of_month":
            day = int(slot.get("day") or 0)
            if 1 <= day <= _last_day_of_month(day_start.year, day_start.month):
                out.append(day_start.replace(day=day, hour=parsed[0], minute=parsed[1], second=0, microsecond=0))
        elif kind == "weekday_ordinal":
            ordinal = int(slot.get("ordinal") or 0)
            weekday = _weekday_index(slot.get("weekday"))
            if 1 <= ordinal <= 5 and weekday is not None:
                day_candidate = _nth_weekday_of_month(day_start.year, day_start.month, weekday, ordinal, day_start.tzinfo or timezone.utc)
                if day_candidate is not None:
                    out.append(day_candidate.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0))
    return out


def _calculate_new_contract_bundle(schedule: dict[str, Any], reference: Optional[datetime] = None) -> dict[str, Any]:
    timezone_info = _schedule_timezone(schedule)
    local_reference = _schedule_reference(schedule, reference)
    anchor_start_at = _parse_run_timestamp(schedule.get("anchor_start_at"))
    period = str(schedule.get("period") or "")
    stop_rule = str(schedule.get("stop_rule") or "never")
    repeat = str(schedule.get("repeat") or "daily")
    run_slots = schedule.get("run_slots") or []
    recurrence = schedule.get("recurrence_config") or {}
    all_day = bool(schedule.get("all_day"))
    runs_per_period = int(schedule.get("runs_per_period") or max(1, len(run_slots) or 1))
    if anchor_start_at is None or period not in {"hourly", "daily", "weekly", "monthly"}:
        return {
            "next_run_at": None,
            "next_run_reason": "no_future_run",
            "current_period_runs": [],
            "requested_runs_per_period": runs_per_period,
            "feasible_runs_per_period": 0,
            "schedule_warnings": ["Missing or invalid new scheduling fields."],
        }
    if period == "hourly":
        period = "daily"
    anchor_local = anchor_start_at.astimezone(timezone_info)
    window_start, window_end = _period_window_bounds(period, local_reference)
    candidates: list[datetime] = []
    if all_day:
        candidates = [window_start]
    elif run_slots:
        if period == "daily":
            candidates = _daily_or_weekly_slot_datetimes(window_start, "daily", run_slots)
        elif period == "weekly":
            candidates = _daily_or_weekly_slot_datetimes(window_start, "weekly", run_slots)
        else:
            candidates = _monthly_slot_datetimes(window_start, run_slots)
    else:
        candidates = [anchor_local]

    filtered: list[datetime] = []
    warnings: list[str] = []
    shifted_to_window = False
    blackout_skipped = False
    for candidate in candidates:
        if not _date_matches_repeat(candidate, anchor_local, repeat, recurrence):
            continue
        candidate, shifted = _shift_into_run_window(schedule, candidate, timezone_info)
        shifted_to_window = shifted_to_window or shifted
        if candidate < anchor_local:
            continue
        if candidate.date().isoformat() in set(schedule.get("blackout_dates") or []):
            blackout_skipped = True
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
        cursor = local_reference
        for _ in range(65):
            if period == "daily":
                cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "weekly":
                cursor = (cursor + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
                cursor = cursor - timedelta(days=cursor.weekday())
            else:
                cursor = (cursor + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if all_day:
                next_candidates = [cursor]
            elif run_slots:
                if period == "daily":
                    next_candidates = _daily_or_weekly_slot_datetimes(cursor, "daily", run_slots)
                elif period == "weekly":
                    next_candidates = _daily_or_weekly_slot_datetimes(cursor, "weekly", run_slots)
                else:
                    next_candidates = _monthly_slot_datetimes(cursor, run_slots)
            else:
                next_candidates = [cursor.replace(hour=anchor_local.hour, minute=anchor_local.minute, second=0, microsecond=0)]
            for candidate in next_candidates:
                if candidate < anchor_local:
                    continue
                if not _date_matches_repeat(candidate, anchor_local, repeat, recurrence):
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
            if future:
                break
    if len(filtered) < runs_per_period:
        warnings.append("Requested runs per period exceed feasible runs under current constraints.")
    next_run = future[0].astimezone(timezone.utc).isoformat() if future else None
    if not next_run:
        reason = "no_future_run"
    elif blackout_skipped:
        reason = "blackout_skipped"
    elif shifted_to_window:
        reason = "shifted_to_window_start"
    else:
        reason = "computed"
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
    # Campaign-first normalization: simple requests become one-step campaigns.
    if request.schedule_type == "simple":
        if request.profile_id is None:
            raise HTTPException(status_code=400, detail="Simple schedules require a run profile.")
        if not steps:
            steps = [
                {
                    "profile_id": int(request.profile_id),
                    "repeat_count": 1,
                    "spacing_seconds": 0,
                    "timeout_seconds": 900,
                    "failure_policy": request.failure_policy,
                    "execution_mode": "saved_profile",
                }
            ]
    if not steps:
        raise HTTPException(status_code=400, detail="Campaign schedules require at least one campaign step.")
    fields: dict[str, Any] = {
        "name": request.name.strip(),
        "description": request.description,
        "schedule_type": "campaign",
        "profile_id": None,
        "anchor_start_at": request.anchor_start_at,
        "period": request.period,
        "stop_rule": request.stop_rule,
        "end_at": request.end_at,
        "duration_seconds": request.duration_seconds,
        "runs_per_period": max(1, int(request.runs_per_period or len(request.run_slots) or 1)),
        "repeat": request.repeat,
        "all_day": bool(request.all_day),
        "recurrence_config": json.dumps(request.recurrence_config or {}),
        "run_slots": json.dumps(request.run_slots or []),
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
            "recurrence_config": request.recurrence_config or {},
            "run_slots": request.run_slots or [],
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
    execution_chain_key: Optional[str],
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
                    INSERT INTO schedule_executions (schedule_id, run_id, execution_chain_key, status, detail, started_at, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (schedule_id, run_id, execution_chain_key, status, detail_payload, started_at, finished_at),
                )
                row = cursor.fetchone()
                conn.commit()
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_executions (schedule_id, run_id, execution_chain_key, status, detail, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, run_id, execution_chain_key, status, detail_payload, started_at, finished_at),
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


def _run_status_map(run_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not run_ids:
        return {}
    unique_ids = sorted({int(run_id) for run_id in run_ids})
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT id, status, finished_at FROM runs WHERE id = ANY(%s)",
                    (unique_ids,),
                )
                rows = cursor.fetchall()
        finally:
            conn.close()
    else:
        placeholders = ", ".join(["?"] * len(unique_ids))
        with DB_LOCK, _db() as conn:
            rows = conn.execute(
                f"SELECT id, status, finished_at FROM runs WHERE id IN ({placeholders})",
                tuple(unique_ids),
            ).fetchall()
    payload: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        run_id = int(item["id"])
        payload[run_id] = {
            "status": str(item.get("status") or "unknown"),
            "finished_at": _jsonable_datetime(item.get("finished_at")),
        }
    return payload


def _trigger_schedule_logic(schedule_id: int, user_id: Optional[int] = None) -> dict[str, Any]:
    schedule = _get_schedule(schedule_id)
    if schedule["status"] in {"disabled", "deleted"}:
        raise HTTPException(status_code=409, detail=f"Schedule {schedule_id} is {schedule['status']}.")
    started_at = _utc_now()
    execution_chain_key = f"schedule-{schedule_id}-{time.time_ns()}"
    runs: list[dict[str, Any]] = []
    _record_schedule_execution(
        schedule_id,
        None,
        execution_chain_key,
        "queued",
        {"message": "Schedule accepted and queued for launch."},
        started_at,
        None,
    )
    _record_schedule_execution(
        schedule_id,
        None,
        execution_chain_key,
        "started",
        {"message": "Schedule launch execution started."},
        started_at,
        None,
    )
    try:
        if schedule["schedule_type"] == "campaign":
            for step_index, step in enumerate(schedule.get("campaign_steps") or [], start=1):
                repeat_count = int(step.get("repeat_count") or 1)
                profile_id = int(step["profile_id"])
                for repeat_index in range(1, repeat_count + 1):
                    profile = _get_run_profile(profile_id)
                    request = _profile_request_to_run_request(profile)
                    request.trigger_source = "schedule"
                    request.trigger_label = f"Schedule: {schedule.get('name') or schedule_id}"
                    request.trigger_context = {
                        "schedule_id": schedule_id,
                        "schedule_name": schedule.get("name"),
                        "schedule_type": schedule.get("schedule_type"),
                        "campaign_step_index": step_index,
                        "campaign_repeat_index": repeat_index,
                        "profile_id": profile_id,
                        "profile_name": profile.get("name"),
                    }
                    request.profile_id = profile_id
                    request.schedule_id = schedule_id
                    request.launched_by_user_id = user_id
                    launched = _create_run(request, user_id)
                    launched["campaign_step_index"] = step_index
                    launched["campaign_repeat_index"] = repeat_index
                    runs.append(launched)
        else:
            profile_id = int(schedule["profile_id"])
            profile = _get_run_profile(profile_id)
            request = _profile_request_to_run_request(profile)
            request.trigger_source = "schedule"
            request.trigger_label = f"Schedule: {schedule.get('name') or schedule_id}"
            request.trigger_context = {
                "schedule_id": schedule_id,
                "schedule_name": schedule.get("name"),
                "schedule_type": schedule.get("schedule_type"),
                "profile_id": profile_id,
                "profile_name": profile.get("name"),
            }
            request.profile_id = profile_id
            request.schedule_id = schedule_id
            request.launched_by_user_id = user_id
            launched = _create_run(request, user_id)
            runs.append(launched)
    except Exception as exc:
        failed_profile_name: str | None = None
        failed_profile_id: int | None = None
        if runs:
            first_run = runs[0]
            trigger_context = first_run.get("trigger_context") if isinstance(first_run.get("trigger_context"), dict) else {}
            failed_profile_name = str(trigger_context.get("profile_name") or "") or None
            raw_profile_id = first_run.get("profile_id") or trigger_context.get("profile_id")
            try:
                failed_profile_id = int(raw_profile_id) if raw_profile_id is not None else None
            except (TypeError, ValueError):
                failed_profile_id = None
        elif schedule.get("schedule_type") == "simple" and schedule.get("profile_id") is not None:
            try:
                failed_profile_id = int(schedule.get("profile_id"))
                failed_profile_name = str(_get_run_profile(failed_profile_id).get("name") or "") or None
            except Exception:
                failed_profile_id = int(schedule.get("profile_id")) if schedule.get("profile_id") is not None else None

        try:
            _send_email_notification(
                "schedule_launch_failed",
                f"Schedule {schedule_id} launch failed",
                [
                    *_schedule_launch_context_lines(schedule, failed_profile_name, failed_profile_id),
                    f"Schedule ID: {schedule_id}",
                    f"Status: failed",
                    f"Timestamp: {_utc_now()}",
                    f"Error: {exc}",
                    "Schedules URL: /schedules",
                    *_email_observability_footer_lines(),
                ],
                dedupe_key=f"schedule-launch-failed:{schedule_id}:{started_at}",
            )
        except Exception as email_exc:
            LOGGER.warning("Failed to send schedule failure email schedule_id=%s error=%s", schedule_id, email_exc)
        execution = _record_schedule_execution(
            schedule_id,
            runs[0]["id"] if runs else None,
            execution_chain_key,
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
        execution_chain_key,
        "launched",
        {
            "schedule_type": schedule["schedule_type"],
            "run_ids": [run["id"] for run in runs],
            "message": "Run launch submitted successfully.",
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
    schedule_phase_rank = {"queued": 1, "started": 2, "launched": 3, "failed": 4}
    execution_rows = _list_schedule_executions(limit=500)
    latest_by_schedule: dict[int, dict[str, Any]] = {}
    for execution in execution_rows:
        schedule_id = int(execution.get("schedule_id") or 0)
        if schedule_id <= 0:
            continue
        candidate_started = _parse_run_timestamp(execution.get("started_at"))
        candidate_rank = schedule_phase_rank.get(str(execution.get("status") or ""), 0)
        current = latest_by_schedule.get(schedule_id)
        if current is None:
            latest_by_schedule[schedule_id] = execution
            continue
        current_started = _parse_run_timestamp(current.get("started_at"))
        if current_started is None and candidate_started is not None:
            latest_by_schedule[schedule_id] = execution
            continue
        if current_started is not None and candidate_started is not None:
            if candidate_started > current_started:
                latest_by_schedule[schedule_id] = execution
                continue
            if candidate_started == current_started:
                current_rank = schedule_phase_rank.get(str(current.get("status") or ""), 0)
                if candidate_rank > current_rank:
                    latest_by_schedule[schedule_id] = execution
                    continue
        if current_started is None and candidate_started is None:
            current_rank = schedule_phase_rank.get(str(current.get("status") or ""), 0)
            if candidate_rank > current_rank:
                latest_by_schedule[schedule_id] = execution
    run_ids = [
        int(execution["run_id"])
        for execution in latest_by_schedule.values()
        if execution.get("run_id") is not None
    ]
    run_status_by_id = _run_status_map(run_ids)
    visible_schedules = [schedule for schedule in schedules if schedule.get("status") != "deleted"]
    recent_schedule_states: list[dict[str, Any]] = []
    for schedule in visible_schedules:
        schedule_id = int(schedule.get("id") or 0)
        latest_execution = latest_by_schedule.get(schedule_id)
        latest_run_id = int(latest_execution["run_id"]) if latest_execution and latest_execution.get("run_id") is not None else None
        run_meta = run_status_by_id.get(latest_run_id) if latest_run_id is not None else None
        recent_schedule_states.append(
            {
                "schedule_id": schedule_id,
                "schedule_name": schedule.get("name"),
                "schedule_phase": str((latest_execution or {}).get("status") or "queued"),
                "latest_run_id": latest_run_id,
                "latest_run_status": run_meta.get("status") if run_meta else None,
                "last_triggered_at": schedule.get("last_triggered_at"),
                "latest_run_finished_at": (run_meta or {}).get("finished_at"),
            }
        )
    recent_schedule_states.sort(
        key=lambda item: _parse_run_timestamp(item.get("last_triggered_at")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
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
        "recent_schedule_states": recent_schedule_states,
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
        suite=snapshot.get("suite"),
        scenarios=list(snapshot.get("scenarios") or []),
        store_id=snapshot.get("store_id"),
        phone=snapshot.get("phone"),
        all_users=bool(snapshot.get("all_users")),
        strict_plan=bool(snapshot.get("strict_plan")),
        skip_app_probes=bool(snapshot.get("skip_app_probes")),
        skip_store_dashboard_probes=bool(snapshot.get("skip_store_dashboard_probes")),
        no_auto_provision=bool(snapshot.get("no_auto_provision")),
        enforce_websocket_gates=bool(snapshot.get("enforce_websocket_gates")),
        post_order_actions=snapshot.get("post_order_actions"),
        users=snapshot.get("users"),
        orders=snapshot.get("orders"),
        interval=snapshot.get("interval"),
        reject=snapshot.get("reject"),
        continuous=bool(snapshot.get("continuous")),
        extra_args=list(snapshot.get("extra_args") or []),
        trigger_source="replay",
        trigger_label=f"Replay of run #{run_id}",
        trigger_context={
            "source_run_id": run_id,
            "source_flow": snapshot.get("flow"),
            "source_plan": snapshot.get("plan"),
        },
        launched_by_user_id=user_id,
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
        "reason_code": event.get("reason_code"),
        "reason_message": event.get("reason_message"),
        "next_action": event.get("next_action"),
        "run_continued": event.get("run_continued"),
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

    last_successful_run: dict[str, Any] | None = None
    last_failed_run: dict[str, Any] | None = None
    for run in runs:
        status = str(run.get("status") or "").lower()
        rid = run.get("id")
        if rid is None:
            continue
        if status == "succeeded" and last_successful_run is None:
            last_successful_run = {
                "id": int(rid),
                "flow": run.get("flow"),
                "finished_at": run.get("finished_at") or run.get("created_at"),
                "plan": run.get("plan"),
            }
        if status == "failed" and last_failed_run is None:
            err = run.get("error")
            preview = (str(err) if err else "Simulation failed.")[:240]
            last_failed_run = {
                "id": int(rid),
                "flow": run.get("flow"),
                "finished_at": run.get("finished_at") or run.get("created_at"),
                "error_preview": preview,
                "plan": run.get("plan"),
            }
        if last_successful_run is not None and last_failed_run is not None:
            break

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
        "last_successful_run": last_successful_run,
        "last_failed_run": last_failed_run,
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
    list_flows=lambda: _flows_payload(),
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
    launch_profile=lambda profile_id, user_id, trigger_overlay=None: _launch_run_profile(
        profile_id, user_id, trigger_overlay
    ),
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
    get_email_settings=lambda: _get_email_settings_payload(),
    set_email_settings=lambda request: _set_email_settings_payload(request),
    send_test_email=lambda: _send_test_email_payload(),
)
configure_integrations_runtime(
    list_mappings=lambda: _list_integration_mappings(),
    upsert_mapping=lambda request, user_id: _upsert_integration_mapping(request, user_id),
    delete_mapping=lambda mapping_id: _delete_integration_mapping(mapping_id),
    list_triggers=lambda limit, offset: _list_integration_triggers(limit, offset),
    process_github_deployment_webhook=lambda body, headers: _process_github_deployment_webhook(body, headers),
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
app.include_router(integrations_router)
app.include_router(overview_router)
