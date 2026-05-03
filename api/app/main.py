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
ARTIFACT_FIELDS = ("report_path", "story_path", "events_path")


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
    runs = [_row_to_dict(row) for row in rows]
    return [_hydrate_run_artifacts(run) for run in runs]


def _get_run(run_id: int) -> dict[str, Any]:
    with DB_LOCK, _db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return _hydrate_run_artifacts(_row_to_dict(row))


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


def _extract_artifacts_from_log(log_path: Path) -> dict[str, str]:
    if not log_path.exists():
        return {}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return _capture_artifacts_from_lines(lines)


def _hydrate_run_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    if all(run.get(field) for field in ARTIFACT_FIELDS):
        return run
    log_path = _safe_path(run.get("log_path"))
    if log_path is None:
        return run
    artifacts = _extract_artifacts_from_log(log_path)
    updates: dict[str, str] = {}
    for field in ARTIFACT_FIELDS:
        if not run.get(field) and artifacts.get(field):
            updates[field] = artifacts[field]
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
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        assert process.stdout is not None
        for line in process.stdout:
            handle.write(line)
            handle.flush()
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
    events = _load_events(path)
    total_count = len(events)
    subset = events[offset : offset + limit]
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
    events = _load_events(path)
    return {"run_id": run_id, "available": True, "metrics": _event_metrics(events)}


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
