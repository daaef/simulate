from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from flow_presets import FLOW_PRESETS


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
AUTO_REFRESH_SECONDS = max(5, int(os.getenv("RUN_AUTO_REFRESH_SECONDS", "30")))
ALLOW_ORIGINS = os.getenv("WEB_CORS_ORIGINS", "*")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_LOCK = threading.Lock()
RUN_PROCESSES: dict[int, subprocess.Popen[str]] = {}
RUN_CANCELLED: set[int] = set()
RUN_LOCK = threading.Lock()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
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


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["all_users"] = bool(payload["all_users"])
    payload["no_auto_provision"] = bool(payload["no_auto_provision"])
    if payload["post_order_actions"] is not None:
        payload["post_order_actions"] = bool(payload["post_order_actions"])
    payload["extra_args"] = json.loads(payload["extra_args"] or "[]")
    return payload


def _list_runs(limit: int = 100) -> list[dict[str, Any]]:
    with DB_LOCK, _db() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _get_run(run_id: int) -> dict[str, Any]:
    with DB_LOCK, _db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return _row_to_dict(row)


def _update_run(run_id: int, **fields: Any) -> None:
    if not fields:
        return
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


class RunCreateRequest(BaseModel):
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Literal["trace", "load"] | None = None
    store_id: str | None = None
    phone: str | None = None
    all_users: bool = False
    no_auto_provision: bool = False
    post_order_actions: bool | None = None
    extra_args: list[str] = Field(default_factory=list)


def _build_command(request: RunCreateRequest) -> list[str]:
    if request.flow not in FLOW_PRESETS:
        expected = ", ".join(sorted(FLOW_PRESETS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported flow {request.flow!r}. Expected one of {expected}.",
        )
    command = [
        "python3",
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
    lowered = line.lower()
    if "main: report:" in lowered:
        return "report_path", line.split("main: report:", 1)[1].strip()
    if "main: story:" in lowered:
        return "story_path", line.split("main: story:", 1)[1].strip()
    if "main: events:" in lowered:
        return "events_path", line.split("main: events:", 1)[1].strip()
    return None


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
    )
    with RUN_LOCK:
        RUN_PROCESSES[run_id] = process
    artifacts: dict[str, str] = {}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        assert process.stdout is not None
        for line in process.stdout:
            handle.write(line)
            parsed = _parse_artifact_paths(line)
            if parsed:
                key, value = parsed
                artifacts[key] = value
    return_code = process.wait()
    with RUN_LOCK:
        RUN_PROCESSES.pop(run_id, None)
    if run_id in RUN_CANCELLED:
        RUN_CANCELLED.discard(run_id)
        _update_run(
            run_id,
            status="cancelled",
            finished_at=_utc_now(),
            exit_code=return_code,
            **artifacts,
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
    )


def _create_run(request: RunCreateRequest) -> dict[str, Any]:
    command = _build_command(request)
    created_at = _utc_now()
    with DB_LOCK, _db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (
                flow, plan, timing, mode, store_id, phone, all_users, no_auto_provision,
                post_order_actions, extra_args, status, command, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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


@app.get("/api/v1/runs")
def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"runs": _list_runs(limit=limit)}


@app.post("/api/v1/runs")
def create_run(request: RunCreateRequest) -> dict[str, Any]:
    return _create_run(request)


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

