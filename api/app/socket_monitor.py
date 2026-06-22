from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import websockets


SocketStatus = str
REQUIRED_SOCKETS = (
    ("store_orders", "Orders", "/ws/soc/store_{store_id}/"),
    ("store_stats", "Stats", "/ws/soc/store_statistics_{store_id}/"),
)


@dataclass(frozen=True)
class SocketMonitorConfig:
    enabled: bool
    project_dir: Path
    lastmile_base_url: str
    store_id: str
    interval_seconds: int
    connect_timeout_seconds: float
    failure_threshold: int
    notification_dedupe_seconds: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def websocket_root(base_url: str) -> str:
    parsed = urlparse((base_url or "").rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}".rstrip("/")


def resolve_socket_target(config: SocketMonitorConfig) -> dict[str, str] | None:
    env_store = (config.store_id or "").strip()
    base_url = (config.lastmile_base_url or "https://lastmile.fainzy.tech").rstrip("/")
    if env_store:
        return {"store_id": env_store, "source": "SIM_SOCKET_MONITOR_STORE_ID", "base_url": base_url}

    plan_path = config.project_dir / "sim_actors.json"
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    defaults = payload.get("defaults") if isinstance(payload, dict) else {}
    plan_store = str((defaults or {}).get("store_id") or "").strip()
    if not plan_store:
        return None
    return {"store_id": plan_store, "source": "sim_actors.json defaults.store_id", "base_url": base_url}


def reduce_socket_status(rows: list[dict[str, Any]]) -> SocketStatus:
    statuses = {str(row.get("status") or "unknown").lower() for row in rows}
    if not rows or "unknown" in statuses:
        return "unknown"
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    return "up"


def unknown_snapshot(enabled: bool, reason: str, checked_at: str | None = None) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "status": "unknown",
        "checked_at": checked_at,
        "target": None,
        "required": [],
        "reason": reason,
    }


async def probe_socket(url: str, timeout_seconds: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with websockets.connect(url, open_timeout=timeout_seconds, close_timeout=1):
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "reason": None}
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "reason": str(exc)[:240] or exc.__class__.__name__}


class SocketMonitor:
    def __init__(
        self,
        *,
        config: SocketMonitorConfig,
        send_failure_email: Callable[[dict[str, Any]], dict[str, Any]],
        load_notification_state: Callable[[], dict[str, Any]],
        save_notification_state: Callable[[dict[str, Any]], None],
        now: Callable[[], str] = utc_now,
        now_epoch: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self._send_failure_email = send_failure_email
        self._load_notification_state = load_notification_state
        self._save_notification_state = save_notification_state
        self._now = now
        self._now_epoch = now_epoch
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = unknown_snapshot(config.enabled, "probe_pending")
        self._failure_streaks: dict[str, int] = {key: 0 for key, _, _ in REQUIRED_SOCKETS}

    def current_status(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._snapshot))

    def build_snapshot_from_probe_results(self, probe_results: list[dict[str, Any]]) -> dict[str, Any]:
        target = resolve_socket_target(self.config)
        checked_at = self._now()
        if not self.config.enabled:
            snapshot = unknown_snapshot(False, "monitor_disabled", checked_at)
        elif target is None:
            snapshot = unknown_snapshot(True, "missing_store_target", checked_at)
        else:
            by_key = {str(item.get("key")): item for item in probe_results}
            rows: list[dict[str, Any]] = []
            for key, label, _path in REQUIRED_SOCKETS:
                result = by_key.get(key) or {"ok": False, "latency_ms": None, "reason": "probe_missing"}
                if result.get("ok"):
                    self._failure_streaks[key] = 0
                    status = "up"
                else:
                    self._failure_streaks[key] = self._failure_streaks.get(key, 0) + 1
                    status = "down" if self._failure_streaks[key] >= self.config.failure_threshold else "degraded"
                rows.append(
                    {
                        "key": key,
                        "label": label,
                        "status": status,
                        "latency_ms": result.get("latency_ms"),
                        "failure_streak": self._failure_streaks[key],
                        "reason": result.get("reason"),
                    }
                )
            snapshot = {
                "enabled": True,
                "status": reduce_socket_status(rows),
                "checked_at": checked_at,
                "target": target,
                "required": rows,
                "reason": None,
            }
        with self._lock:
            self._snapshot = snapshot
        self._maybe_send_failure_email(snapshot)
        return json.loads(json.dumps(snapshot))

    async def run_once(self) -> dict[str, Any]:
        target = resolve_socket_target(self.config)
        if not self.config.enabled or target is None:
            return self.build_snapshot_from_probe_results([])
        root = websocket_root(target["base_url"])
        probe_results: list[dict[str, Any]] = []
        for key, label, path_template in REQUIRED_SOCKETS:
            url = f"{root}{path_template.format(store_id=target['store_id'])}"
            result = await probe_socket(url, self.config.connect_timeout_seconds)
            probe_results.append({"key": key, "label": label, **result})
        return self.build_snapshot_from_probe_results(probe_results)

    def run_once_sync(self) -> dict[str, Any]:
        return asyncio.run(self.run_once())

    def _failure_signature(self, snapshot: dict[str, Any]) -> str:
        failed = [
            f"{row.get('key')}:{row.get('reason') or row.get('status')}"
            for row in snapshot.get("required", [])
            if row.get("status") == "down"
        ]
        return "|".join(sorted(failed))

    def _maybe_send_failure_email(self, snapshot: dict[str, Any]) -> None:
        if snapshot.get("status") != "down":
            return
        signature = self._failure_signature(snapshot)
        if not signature:
            return
        state = self._load_notification_state()
        now_value = self._now()
        now_epoch = float(self._now_epoch())
        last_epoch = 0.0
        try:
            last_epoch = float(state.get("last_notification_epoch") or 0.0)
        except (TypeError, ValueError):
            last_epoch = 0.0
        if (
            state.get("last_notification_signature") == signature
            and now_epoch - last_epoch < self.config.notification_dedupe_seconds
        ):
            return
        self._send_failure_email(snapshot)
        state.update(
            {
                "last_notification_signature": signature,
                "last_notification_at": now_value,
                "last_notification_epoch": now_epoch,
                "last_down_started_at": state.get("last_down_started_at") or now_value,
            }
        )
        self._save_notification_state(state)
