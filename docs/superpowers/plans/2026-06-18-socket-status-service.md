# Socket Status Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cached server-side socket monitor for store order/stat sockets, expose it in AppNav and Overview, and add a configurable `socket_failure` email trigger.

**Architecture:** Add a focused API monitor module that probes `store_orders` and `store_stats`, stores the current snapshot in memory, and uses persisted `system_settings` notification state for cross-worker email dedupe. Expose the snapshot through an Overview endpoint, render a compact nav badge and detailed Overview panel, and keep latest-run websocket evidence as separate historical context.

**Tech Stack:** Python 3.11, FastAPI 0.115.5, APScheduler 3.10.4, `websockets>=12.0`, Next.js 14.2.33, React 18.3.1, TypeScript 5.8.3, Vitest 3.1.4.

**Commit Policy:** Do not commit during execution unless the user explicitly requests commits. Use the checkpoint steps as review points instead of automatic commits.

---

## Review corrections (2026-06-22, verified against codebase)

The plan was verified against the actual repo. All integration points match except the following — these are REQUIRED additions:

1. **CRITICAL — add `websockets` to `api/requirements.txt`.** `websockets` is only in the root `requirements.txt`, not the API image. `api/app/socket_monitor.py` does `import websockets` and `main.py` imports it at startup, so without this the API fails to boot. Add `websockets>=12.0` (matching root) — this is now Task 1, Step 0, and the API image must be rebuilt.
2. **MEDIUM — pass `LASTMILE_BASE_URL` into the API container.** It is currently passed to no compose service; the monitor falls back to the hardcoded `https://lastmile.fainzy.tech`. Add the env passthrough in Task 5, Step 4 so non-default environments probe the correct host.
3. **CAVEAT — single-worker assumption.** The cached snapshot and `_failure_streaks` are in-memory per worker. DB-backed `system_settings` dedupe prevents duplicate emails across workers, but the displayed badge can flap if API workers > 1. Production pins workers to 1; document this in README/SIMULATOR_GUIDE (Task 5).
4. **ORDERING — the APScheduler `scheduler` starts at import time (main.py ~line 6578).** The `socket_monitor` instance, its callbacks (`_send_socket_failure_email`, `_socket_monitor_status_payload`, `_run_socket_monitor_job`), and `overview_service.configure_socket_status_provider(...)` must all be defined ABOVE that `scheduler.add_job` block in Task 2, Step 6.

Confirmed non-issues: `sim_actors.json` IS mounted into the API container (`./:/workspace/simulate`, `SIMULATOR_PROJECT_DIR=/workspace/simulate`), so target fallback works; the Task 2 integration test's `matched:1/missed:0` expectations are correct against the real `_websocket_summary`.

---

## File Structure

- Create `api/app/socket_monitor.py`: pure monitor configuration, target resolution, websocket probing, status reduction, and notification decision logic.
- Modify `api/app/main.py`: create the monitor instance, persist notification state in `system_settings`, wire the APScheduler job, add socket alert payload, add `socket_failure` email send callback.
- Modify `api/app/overview/service.py`: add a socket status provider hook and latest-run websocket evidence helper.
- Modify `api/app/overview/routes.py`: add `GET /api/v1/overview/socket-status`.
- Modify `api/app/system/models.py`: add `socket_failure` to allowed email trigger literals.
- Modify `tests/test_web_api.py`: add monitor, API, email trigger, alert, and dedupe tests.
- Modify `web/src/lib/api.ts`: add socket status types and `fetchSocketStatus()`.
- Create `web/src/lib/socket-status.ts`: frontend status labels, CSS tone selection, tooltip text, and timestamp helpers.
- Create `web/src/lib/socket-status.test.ts`: Vitest coverage for status formatting and badge labels.
- Modify `web/src/components/AppNav.tsx`: fetch socket status and render compact badge/link.
- Create `web/src/components/overview/SocketServicePanel.tsx`: detailed Overview socket monitor panel.
- Modify `web/src/app/(app)/overview/page.tsx`: fetch and render Socket Service panel.
- Modify `web/src/app/(app)/config/page.tsx`: add `Socket failure` email trigger option.
- Modify `web/src/app/globals.css`: add socket badge and panel row styles.
- Modify `README.md` and `SIMULATOR_GUIDE.md`: document socket monitor, env vars, status interpretation, and email trigger.
- Modify `.env.example`: add socket monitor env vars.
- Modify `docker-compose.yml` and `docker-compose.prod.yml`: pass socket monitor env vars into the API container.

---

### Task 1: Backend Socket Monitor Core

**Files:**
- Modify: `api/requirements.txt`
- Create: `api/app/socket_monitor.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 0: Add the `websockets` dependency to the API image**

`api/app/socket_monitor.py` imports `websockets`, but the API image does not install it. Add to `api/requirements.txt` (match the root pin):

```text
websockets>=12.0
```

Rebuild the API image before any container run (`docker compose build api` or `--build`). For local `python3 -m unittest`, ensure `websockets` is importable in the active venv (it is already a root dependency).

- [ ] **Step 1: Write failing monitor unit tests**

Append this test class near the existing API-focused tests in `tests/test_web_api.py`:

```python
class SocketMonitorCoreTests(unittest.TestCase):
    def test_resolves_store_target_from_env_first(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = pathlib.Path(tmpdir) / "sim_actors.json"
            plan.write_text(json.dumps({"defaults": {"store_id": "FZY_FROM_PLAN"}}), encoding="utf-8")
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech",
                store_id="FZY_FROM_ENV",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            target = resolve_socket_target(config)

        self.assertEqual(target["store_id"], "FZY_FROM_ENV")
        self.assertEqual(target["source"], "SIM_SOCKET_MONITOR_STORE_ID")
        self.assertEqual(target["base_url"], "https://lastmile.fainzy.tech")

    def test_resolves_store_target_from_plan_default(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = pathlib.Path(tmpdir) / "sim_actors.json"
            plan.write_text(json.dumps({"defaults": {"store_id": "FZY_FROM_PLAN"}}), encoding="utf-8")
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech/",
                store_id="",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            target = resolve_socket_target(config)

        self.assertEqual(target["store_id"], "FZY_FROM_PLAN")
        self.assertEqual(target["source"], "sim_actors.json defaults.store_id")
        self.assertEqual(target["base_url"], "https://lastmile.fainzy.tech")

    def test_missing_store_target_returns_none(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech",
                store_id="",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            self.assertIsNone(resolve_socket_target(config))

    def test_reduces_socket_rows_to_overall_status(self) -> None:
        from api.app.socket_monitor import reduce_socket_status

        self.assertEqual(reduce_socket_status([{"status": "up"}, {"status": "up"}]), "up")
        self.assertEqual(reduce_socket_status([{"status": "up"}, {"status": "degraded"}]), "degraded")
        self.assertEqual(reduce_socket_status([{"status": "down"}, {"status": "up"}]), "down")
        self.assertEqual(reduce_socket_status([]), "unknown")

    def test_snapshot_uses_failure_threshold(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, SocketMonitor

        config = SocketMonitorConfig(
            enabled=True,
            project_dir=ROOT,
            lastmile_base_url="https://lastmile.fainzy.tech",
            store_id="FZY_TEST",
            interval_seconds=60,
            connect_timeout_seconds=5.0,
            failure_threshold=2,
            notification_dedupe_seconds=600,
        )
        sent: list[dict[str, object]] = []
        monitor = SocketMonitor(
            config=config,
            send_failure_email=lambda snapshot: sent.append(snapshot) or {"sent": True},
            load_notification_state=lambda: {},
            save_notification_state=lambda payload: None,
            now=lambda: "2026-06-18T12:00:00+00:00",
            now_epoch=lambda: 1000.0,
        )

        first = monitor.build_snapshot_from_probe_results(
            [
                {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
                {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
            ]
        )
        second = monitor.build_snapshot_from_probe_results(
            [
                {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
                {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
            ]
        )

        self.assertEqual(first["status"], "degraded")
        self.assertEqual(second["status"], "down")
        self.assertEqual(second["required"][0]["failure_streak"], 2)
        self.assertEqual(len(sent), 1)

    def test_notification_dedupe_uses_persisted_signature_and_window(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, SocketMonitor

        state: dict[str, object] = {}
        sent: list[dict[str, object]] = []
        epoch = {"value": 1000.0}
        config = SocketMonitorConfig(
            enabled=True,
            project_dir=ROOT,
            lastmile_base_url="https://lastmile.fainzy.tech",
            store_id="FZY_TEST",
            interval_seconds=60,
            connect_timeout_seconds=5.0,
            failure_threshold=1,
            notification_dedupe_seconds=600,
        )
        monitor = SocketMonitor(
            config=config,
            send_failure_email=lambda snapshot: sent.append(snapshot) or {"sent": True},
            load_notification_state=lambda: dict(state),
            save_notification_state=lambda payload: state.update(payload),
            now=lambda: "2026-06-18T12:00:00+00:00",
            now_epoch=lambda: epoch["value"],
        )
        failed_probe = [
            {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
            {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
        ]

        monitor.build_snapshot_from_probe_results(failed_probe)
        monitor.build_snapshot_from_probe_results(failed_probe)
        epoch["value"] = 1701.0
        monitor.build_snapshot_from_probe_results(failed_probe)

        self.assertEqual(len(sent), 2)
```

- [ ] **Step 2: Run monitor tests and confirm they fail**

Run:

```bash
python3 -m unittest tests.test_web_api.SocketMonitorCoreTests -v
```

Expected: fails with `ModuleNotFoundError` or missing `api.app.socket_monitor` symbols.

- [ ] **Step 3: Create `api/app/socket_monitor.py`**

Add this file:

```python
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
```

- [ ] **Step 4: Run monitor tests and confirm they pass**

Run:

```bash
python3 -m unittest tests.test_web_api.SocketMonitorCoreTests -v
```

Expected: all tests in `SocketMonitorCoreTests` pass.

- [ ] **Step 5: Checkpoint review**

Run:

```bash
git diff -- api/app/socket_monitor.py tests/test_web_api.py
```

Expected: diff only contains the socket monitor module and its focused tests. Do not commit unless the user explicitly requested commits.

---

### Task 2: API Route, Scheduler, Alerts, and Email Wiring

**Files:**
- Modify: `api/app/main.py`
- Modify: `api/app/overview/service.py`
- Modify: `api/app/overview/routes.py`
- Modify: `api/app/system/models.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 1: Write failing API/email integration tests**

Append these tests to `tests/test_web_api.py` after `SocketMonitorCoreTests` or near `SystemEmailApiTests`:

```python
class SocketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.client.close()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()

    def test_socket_status_endpoint_returns_cached_status_and_latest_evidence(self) -> None:
        status_payload = {
            "enabled": True,
            "status": "up",
            "checked_at": "2026-06-18T12:00:00+00:00",
            "target": {"store_id": "FZY_1", "source": "SIM_SOCKET_MONITOR_STORE_ID", "base_url": "https://lastmile.fainzy.tech"},
            "required": [{"key": "store_orders", "label": "Orders", "status": "up", "latency_ms": 10, "failure_streak": 0, "reason": None}],
            "reason": None,
        }
        run = {"id": 44, "status": "succeeded"}
        events = [
            {"id": 1, "actor": "store", "action": "mark_ready", "expect_websocket": True, "websocket_match": {"matched": True}},
            {"id": 2, "actor": "websocket", "category": "websocket", "details": {"source": "store_orders"}},
        ]
        with mock.patch.object(overview_service, "_socket_status_provider", return_value=status_payload):
            with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
                with mock.patch.object(overview_service, "_load_events", return_value=(events, [], {})):
                    response = self.client.get("/api/v1/overview/socket-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "up")
        self.assertEqual(payload["latest_run_evidence"]["run_id"], 44)
        self.assertEqual(payload["latest_run_evidence"]["matched"], 1)
        self.assertEqual(payload["latest_run_evidence"]["missed"], 0)

    def test_socket_down_adds_alert(self) -> None:
        with mock.patch.object(
            web_api,
            "_socket_monitor_status_payload",
            return_value={
                "enabled": True,
                "status": "down",
                "checked_at": "2026-06-18T12:00:00+00:00",
                "target": {"store_id": "FZY_1"},
                "required": [{"key": "store_stats", "label": "Stats", "status": "down", "reason": "timeout"}],
            },
        ):
            response = self.client.get("/api/v1/alerts")

        self.assertEqual(response.status_code, 200)
        alerts = response.json()["alerts"]
        self.assertTrue(any(alert["id"] == "socket-monitor-down" and alert["domain"] == "sockets" for alert in alerts))

    def test_email_settings_accept_socket_failure_trigger(self) -> None:
        response = self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["socket_failure"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email_event_triggers"], ["socket_failure"])
```

- [ ] **Step 2: Run API/email tests and confirm they fail**

Run:

```bash
python3 -m unittest tests.test_web_api.SocketMonitorApiTests -v
```

Expected: failures for missing route/provider and unknown `socket_failure` trigger.

- [ ] **Step 3: Add socket trigger to email models**

In `api/app/system/models.py`, replace:

```python
EmailEventTrigger = Literal["run_failed", "schedule_launch_failed", "critical_alert"]
```

with:

```python
EmailEventTrigger = Literal["run_failed", "schedule_launch_failed", "critical_alert", "socket_failure"]
```

In `api/app/main.py`, replace:

```python
EMAIL_EVENT_TRIGGERS = {"run_failed", "schedule_launch_failed", "critical_alert"}
```

with:

```python
EMAIL_EVENT_TRIGGERS = {"run_failed", "schedule_launch_failed", "critical_alert", "socket_failure"}
SOCKET_MONITOR_NOTIFICATIONS_KEY = "socket_monitor_notifications"
```

- [ ] **Step 4: Wire Overview socket status provider**

In `api/app/overview/service.py`, add `Callable` to the imports:

```python
from typing import Any, Callable, Literal
```

Add this provider state and functions after the constants:

```python
_socket_status_provider: Callable[[], dict[str, Any]] | None = None


def configure_socket_status_provider(provider: Callable[[], dict[str, Any]]) -> None:
    global _socket_status_provider
    _socket_status_provider = provider


def _latest_run_websocket_evidence() -> dict[str, Any]:
    run = _load_latest_run()
    if run is None:
        return {"status": "unknown", "run_id": None, "run_status": None, "matched": 0, "expected": 0, "missed": 0}
    try:
        events, _artifact_issues, _run_meta = _load_events(int(run["id"]))
        summary = _websocket_summary(events)
    except Exception:
        return {"status": "unknown", "run_id": run.get("id"), "run_status": run.get("status"), "matched": 0, "expected": 0, "missed": 0}
    missed = int(summary.get("missed") or 0)
    expected = int(summary.get("expected") or 0)
    matched = int(summary.get("matched") or 0)
    status = "up" if expected > 0 and missed == 0 else "degraded" if missed > 0 else "unknown"
    return {
        "status": status,
        "run_id": run.get("id"),
        "run_status": run.get("status"),
        "matched": matched,
        "expected": expected,
        "missed": missed,
    }


def socket_status() -> dict[str, Any]:
    if _socket_status_provider is None:
        payload = {
            "enabled": False,
            "status": "unknown",
            "checked_at": None,
            "target": None,
            "required": [],
            "reason": "provider_not_configured",
        }
    else:
        payload = _socket_status_provider()
    return {**payload, "latest_run_evidence": _latest_run_websocket_evidence()}
```

- [ ] **Step 5: Add Overview route**

In `api/app/overview/routes.py`, add:

```python
@router.get("/api/v1/overview/socket-status")
def socket_status(
    current_user: dict = Depends(require_permission("dashboard", "read")),
) -> dict[str, Any]:
    return service.socket_status()
```

- [ ] **Step 6: Instantiate and schedule the monitor in `api/app/main.py`**

Add imports near other local imports:

```python
from .overview import service as overview_service
from .socket_monitor import SocketMonitor, SocketMonitorConfig, unknown_snapshot
```

Add helpers near the email settings helpers:

```python
def _load_system_setting_json(key: str, default: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] | None = None
    if USE_POSTGRES:
        conn = _get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
                row = cursor.fetchone()
                if row:
                    raw = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        finally:
            conn.close()
    else:
        with DB_LOCK, _db() as conn:
            row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
            if row is not None:
                raw = json.loads(row["value"] or "{}")
    return raw if isinstance(raw, dict) else dict(default)


def _save_system_setting_json(key: str, payload: dict[str, Any]) -> None:
    value = json.dumps(payload)
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
                    (key, value),
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
            (key, value, now),
        )
```

Add monitor config helpers after env constants:

```python
def _int_env(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _float_env(name: str, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _socket_monitor_config() -> SocketMonitorConfig:
    return SocketMonitorConfig(
        enabled=_as_bool(os.getenv("SIM_SOCKET_MONITOR_ENABLED"), default=True),
        project_dir=Path(PROJECT_DIR),
        lastmile_base_url=os.getenv("LASTMILE_BASE_URL", "https://lastmile.fainzy.tech"),
        store_id=os.getenv("SIM_SOCKET_MONITOR_STORE_ID", ""),
        interval_seconds=_int_env("SIM_SOCKET_MONITOR_INTERVAL_SECONDS", 60, 15),
        connect_timeout_seconds=_float_env("SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS", 5.0, 1.0),
        failure_threshold=_int_env("SIM_SOCKET_MONITOR_FAILURE_THRESHOLD", 2, 1),
        notification_dedupe_seconds=EMAIL_EVENT_DEDUPE_WINDOW_SECONDS,
    )
```

Add email/status callbacks before scheduler setup:

```python
def _send_socket_failure_email(snapshot: dict[str, Any]) -> dict[str, Any]:
    target = snapshot.get("target") or {}
    failing = [
        f"{row.get('label') or row.get('key')}: {row.get('reason') or row.get('status')}"
        for row in snapshot.get("required", [])
        if row.get("status") == "down"
    ]
    return _send_email_notification(
        "socket_failure",
        f"Socket failure: {target.get('store_id') or 'unknown store'}",
        [
            f"Store ID: {target.get('store_id') or 'unknown'}",
            f"Target source: {target.get('source') or 'unknown'}",
            f"Checked At: {snapshot.get('checked_at') or _utc_now()}",
            f"Status: {snapshot.get('status')}",
            "Failing sockets:",
            *(f"- {item}" for item in failing),
            "Status URL: /overview#socket-service",
            *_email_observability_footer_lines(),
        ],
        dedupe_key=None,
    )


socket_monitor = SocketMonitor(
    config=_socket_monitor_config(),
    send_failure_email=_send_socket_failure_email,
    load_notification_state=lambda: _load_system_setting_json(SOCKET_MONITOR_NOTIFICATIONS_KEY, {}),
    save_notification_state=lambda payload: _save_system_setting_json(SOCKET_MONITOR_NOTIFICATIONS_KEY, payload),
)


def _socket_monitor_status_payload() -> dict[str, Any]:
    try:
        return socket_monitor.current_status()
    except Exception:
        return unknown_snapshot(enabled=False, reason="socket_monitor_unavailable")


def _run_socket_monitor_job() -> None:
    try:
        socket_monitor.run_once_sync()
    except Exception as exc:
        LOGGER.warning("socket monitor job failed error=%s", exc)
```

Register provider before middleware/router setup:

```python
overview_service.configure_socket_status_provider(_socket_monitor_status_payload)
```

Add scheduler job near existing scheduler jobs:

```python
scheduler.add_job(
    _run_socket_monitor_job,
    trigger="interval",
    seconds=socket_monitor.config.interval_seconds,
    id="socket-monitor",
    replace_existing=True,
)
```

- [ ] **Step 7: Add socket alert**

In `_alerts_payload()` in `api/app/main.py`, after `now = _utc_now()`, insert:

```python
    socket_status = _socket_monitor_status_payload()
    if socket_status.get("status") == "down":
        failing = [
            str(row.get("label") or row.get("key"))
            for row in socket_status.get("required", [])
            if row.get("status") == "down"
        ]
        alerts.append(
            {
                "id": "socket-monitor-down",
                "domain": "sockets",
                "severity": "critical",
                "title": "Socket monitor down",
                "message": f"Required sockets failing: {', '.join(failing) or 'unknown'}.",
                "href": "/overview#socket-service",
                "created_at": socket_status.get("checked_at") or now,
            }
        )
```

- [ ] **Step 8: Run API/email tests and confirm they pass**

Run:

```bash
python3 -m unittest tests.test_web_api.SocketMonitorApiTests tests.test_web_api.SystemEmailApiTests -v
```

Expected: all selected tests pass.

- [ ] **Step 9: Checkpoint review**

Run:

```bash
git diff -- api/app/main.py api/app/overview/service.py api/app/overview/routes.py api/app/system/models.py tests/test_web_api.py
```

Expected: diff shows socket route/provider, scheduler job, alert entry, email trigger literal, and tests only. Do not commit unless explicitly requested.

---

### Task 3: Frontend API Types and Formatting Utilities

**Files:**
- Modify: `web/src/lib/api.ts`
- Create: `web/src/lib/socket-status.ts`
- Create: `web/src/lib/socket-status.test.ts`

- [ ] **Step 1: Write failing Vitest tests**

Create `web/src/lib/socket-status.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  socketBadgeClass,
  socketBadgeLabel,
  socketStatusTooltip,
  type SocketStatusResponse,
} from "./socket-status";

const baseStatus: SocketStatusResponse = {
  enabled: true,
  status: "up",
  checked_at: "2026-06-18T12:00:00+00:00",
  target: { store_id: "FZY_1", source: "SIM_SOCKET_MONITOR_STORE_ID", base_url: "https://lastmile.fainzy.tech" },
  required: [
    { key: "store_orders", label: "Orders", status: "up", latency_ms: 10, failure_streak: 0, reason: null },
    { key: "store_stats", label: "Stats", status: "up", latency_ms: 12, failure_streak: 0, reason: null },
  ],
  reason: null,
  latest_run_evidence: { status: "up", run_id: 1, run_status: "succeeded", matched: 2, expected: 2, missed: 0 },
};

describe("socket status formatting", () => {
  it("returns badge labels by status", () => {
    expect(socketBadgeLabel({ ...baseStatus, status: "up" })).toBe("Sockets Up");
    expect(socketBadgeLabel({ ...baseStatus, status: "degraded" })).toBe("Sockets Degraded");
    expect(socketBadgeLabel({ ...baseStatus, status: "down" })).toBe("Sockets Down");
    expect(socketBadgeLabel({ ...baseStatus, status: "unknown" })).toBe("Sockets Unknown");
  });

  it("returns badge classes by status", () => {
    expect(socketBadgeClass({ ...baseStatus, status: "up" })).toBe("socket-status-badge socket-status-badge--up");
    expect(socketBadgeClass({ ...baseStatus, status: "down" })).toBe("socket-status-badge socket-status-badge--down");
  });

  it("includes failing socket names in tooltip", () => {
    const tooltip = socketStatusTooltip({
      ...baseStatus,
      status: "down",
      required: [
        { key: "store_orders", label: "Orders", status: "down", latency_ms: null, failure_streak: 2, reason: "timeout" },
        { key: "store_stats", label: "Stats", status: "up", latency_ms: 12, failure_streak: 0, reason: null },
      ],
    });

    expect(tooltip).toContain("Sockets Down");
    expect(tooltip).toContain("Orders");
    expect(tooltip).toContain("timeout");
  });
});
```

- [ ] **Step 2: Run frontend tests and confirm they fail**

Run:

```bash
cd web
npm test -- socket-status.test.ts
```

Expected: fails because `web/src/lib/socket-status.ts` does not exist.

- [ ] **Step 3: Add API types and fetch function**

In `web/src/lib/api.ts`, add near the email types:

```typescript
export type SocketMonitorStatus = "up" | "degraded" | "down" | "unknown" | string;

export type SocketStatusRow = {
  key: string;
  label: string;
  status: SocketMonitorStatus;
  latency_ms?: number | null;
  failure_streak?: number;
  reason?: string | null;
};

export type SocketStatusResponse = {
  enabled: boolean;
  status: SocketMonitorStatus;
  checked_at?: string | null;
  target?: {
    store_id?: string | null;
    source?: string | null;
    base_url?: string | null;
  } | null;
  required: SocketStatusRow[];
  reason?: string | null;
  latest_run_evidence?: {
    status?: SocketMonitorStatus;
    run_id?: number | null;
    run_status?: string | null;
    matched?: number;
    expected?: number;
    missed?: number;
  } | null;
};
```

Add near other fetchers:

```typescript
export async function fetchSocketStatus(): Promise<SocketStatusResponse> {
  return unwrap<SocketStatusResponse>(
    await fetch("/api/v1/overview/socket-status", withSession()),
    "socket-status"
  );
}
```

- [ ] **Step 4: Create socket status formatter**

Create `web/src/lib/socket-status.ts`:

```typescript
import { formatDateTime } from "./time-format";
import type { SocketStatusResponse, SocketMonitorStatus } from "./api";

export type { SocketStatusResponse, SocketMonitorStatus };

function normalized(status: SocketMonitorStatus | null | undefined): string {
  return String(status || "unknown").toLowerCase();
}

export function socketBadgeLabel(status: Pick<SocketStatusResponse, "status"> | null | undefined): string {
  const value = normalized(status?.status);
  if (value === "up") return "Sockets Up";
  if (value === "degraded") return "Sockets Degraded";
  if (value === "down") return "Sockets Down";
  return "Sockets Unknown";
}

export function socketBadgeClass(status: Pick<SocketStatusResponse, "status"> | null | undefined): string {
  const value = normalized(status?.status);
  if (value === "up") return "socket-status-badge socket-status-badge--up";
  if (value === "degraded") return "socket-status-badge socket-status-badge--degraded";
  if (value === "down") return "socket-status-badge socket-status-badge--down";
  return "socket-status-badge socket-status-badge--unknown";
}

export function socketStatusTooltip(status: SocketStatusResponse | null | undefined): string {
  if (!status) return "Socket status unavailable";
  const lines = [socketBadgeLabel(status)];
  if (status.checked_at) lines.push(`Last checked: ${formatDateTime(status.checked_at)}`);
  const failing = status.required.filter((row) => normalized(row.status) === "down" || normalized(row.status) === "degraded");
  if (failing.length) {
    lines.push(
      `Attention: ${failing
        .map((row) => `${row.label || row.key}${row.reason ? ` (${row.reason})` : ""}`)
        .join(", ")}`
    );
  }
  return lines.join(" · ");
}

export function socketStatusTone(status: SocketMonitorStatus | null | undefined): "success" | "warning" | "danger" | "info" {
  const value = normalized(status);
  if (value === "up") return "success";
  if (value === "degraded") return "warning";
  if (value === "down") return "danger";
  return "info";
}
```

- [ ] **Step 5: Run frontend tests and confirm they pass**

Run:

```bash
cd web
npm test -- socket-status.test.ts
```

Expected: `socket-status.test.ts` passes.

- [ ] **Step 6: Checkpoint review**

Run:

```bash
git diff -- web/src/lib/api.ts web/src/lib/socket-status.ts web/src/lib/socket-status.test.ts
```

Expected: diff contains API type/fetch additions and pure formatting utility/tests. Do not commit unless explicitly requested.

---

### Task 4: AppNav Badge and Overview Socket Panel

**Files:**
- Modify: `web/src/components/AppNav.tsx`
- Create: `web/src/components/overview/SocketServicePanel.tsx`
- Modify: `web/src/app/(app)/overview/page.tsx`
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Add AppNav socket fetch and badge**

In `web/src/components/AppNav.tsx`, replace the import:

```typescript
import { fetchDashboardSummary } from "../lib/api";
```

with:

```typescript
import { fetchDashboardSummary, fetchSocketStatus, type SocketStatusResponse } from "../lib/api";
import { socketBadgeClass, socketBadgeLabel, socketStatusTooltip } from "../lib/socket-status";
```

Add state after `activeRunCount`:

```typescript
  const [socketStatus, setSocketStatus] = useState<SocketStatusResponse | null>(null);
```

Add this effect after the active-run effect:

```typescript
  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetchSocketStatus()
        .then((payload) => {
          if (!cancelled) setSocketStatus(payload);
        })
        .catch(() => {
          if (!cancelled) setSocketStatus(null);
        });
    };

    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);
```

Add this link just before `</nav>`:

```tsx
      <Link
        href="/overview#socket-service"
        className={socketBadgeClass(socketStatus)}
        title={socketStatusTooltip(socketStatus)}
        aria-label={socketBadgeLabel(socketStatus)}
      >
        {socketBadgeLabel(socketStatus)}
      </Link>
```

- [ ] **Step 2: Create Overview socket panel**

Create `web/src/components/overview/SocketServicePanel.tsx`:

```tsx
"use client";

import type { SocketStatusResponse } from "../../lib/api";
import { formatDateTime } from "../../lib/time-format";
import { socketStatusTone } from "../../lib/socket-status";

function statusClass(status: string | null | undefined): string {
  const tone = socketStatusTone(status);
  if (tone === "success") return "status-success";
  if (tone === "warning") return "status-warning";
  if (tone === "danger") return "status-danger";
  return "status-info";
}

export default function SocketServicePanel({
  status,
}: {
  status: SocketStatusResponse | null;
}) {
  if (!status) {
    return (
      <section id="socket-service" className="panel socket-service-panel" aria-labelledby="socket-service-title">
        <div className="section-heading-row">
          <h2 id="socket-service-title" className="section-title">Socket Service</h2>
          <span className="status-pill status-info">unknown</span>
        </div>
        <div className="chart-empty">Socket monitor status is unavailable.</div>
      </section>
    );
  }

  const evidence = status.latest_run_evidence;

  return (
    <section id="socket-service" className="panel socket-service-panel" aria-labelledby="socket-service-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Realtime Monitor</p>
          <h2 id="socket-service-title" className="section-title">Socket Service</h2>
        </div>
        <span className={`status-pill ${statusClass(status.status)}`}>{status.status}</span>
      </div>

      <div className="socket-service-meta">
        <span>Last checked: <strong>{formatDateTime(status.checked_at, { fallback: "not checked yet" })}</strong></span>
        <span>Store: <strong>{status.target?.store_id || "not configured"}</strong></span>
        <span>Target: <strong>{status.target?.source || status.reason || "unknown"}</strong></span>
      </div>

      {status.required.length ? (
        <div className="socket-service-rows">
          {status.required.map((row) => (
            <div key={row.key} className="socket-service-row">
              <div>
                <strong>{row.label}</strong>
                <p className="muted">{row.key}</p>
              </div>
              <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
              <span className="muted">{row.latency_ms != null ? `${row.latency_ms}ms` : "no latency"}</span>
              <span className="muted">{row.reason || "healthy"}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="chart-empty">No socket target is configured for active probing.</div>
      )}

      <div className="socket-service-evidence">
        <h3 className="subsection-title">Latest run websocket evidence</h3>
        {evidence?.run_id ? (
          <p className="muted">
            Run #{evidence.run_id} ({evidence.run_status || "unknown"}) matched {evidence.matched ?? 0}/
            {evidence.expected ?? 0} expected websocket event{(evidence.expected ?? 0) === 1 ? "" : "s"}.
            {(evidence.missed ?? 0) > 0 ? ` Missed: ${evidence.missed}.` : ""}
          </p>
        ) : (
          <p className="muted">No latest-run websocket evidence is available yet.</p>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Fetch and render panel on Overview**

In `web/src/app/(app)/overview/page.tsx`, add import:

```typescript
import SocketServicePanel from "../../../components/overview/SocketServicePanel";
```

Add `fetchSocketStatus` and type to the API imports:

```typescript
  fetchSocketStatus,
  type SocketStatusResponse,
```

Add state:

```typescript
  const [socketStatus, setSocketStatus] = useState<SocketStatusResponse | null>(null);
```

In `loadOverview`, add `socketStatusPayload` to the `Promise.all` destructuring and fetch list:

```typescript
        socketStatusPayload,
```

and:

```typescript
        fetchSocketStatus(),
```

After `setLatestRunOverview(latestRunPayload);`, add:

```typescript
      setSocketStatus(socketStatusPayload);
```

Render after `<LatestRunCommandCenter overview={latestRunOverview} />`:

```tsx
      <SocketServicePanel status={socketStatus} />
```

- [ ] **Step 4: Add CSS**

Append to `web/src/app/globals.css` near the nav live indicator styles:

```css
.socket-status-badge {
  align-items: center;
  border: 1px solid var(--border-primary);
  border-radius: 999px;
  display: inline-flex;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  padding: 7px 10px;
  text-decoration: none;
  white-space: nowrap;
}

.socket-status-badge--up {
  background: color-mix(in srgb, var(--chart-success) 14%, transparent);
  color: var(--chart-success);
}

.socket-status-badge--degraded {
  background: color-mix(in srgb, var(--chart-warning) 16%, transparent);
  color: var(--chart-warning);
}

.socket-status-badge--down {
  background: color-mix(in srgb, var(--chart-danger) 14%, transparent);
  color: var(--chart-danger);
}

.socket-status-badge--unknown {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.socket-service-panel {
  scroll-margin-top: 96px;
}

.socket-service-meta {
  color: var(--text-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  font-size: 13px;
}

.socket-service-rows {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.socket-service-row {
  align-items: center;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(120px, 1fr) auto auto minmax(120px, 1fr);
  padding: 10px 12px;
}

.socket-service-row p {
  margin: 2px 0 0;
}

.socket-service-evidence {
  border-top: 1px solid var(--border-primary);
  margin-top: 14px;
  padding-top: 12px;
}

@media (max-width: 720px) {
  .socket-service-row {
    align-items: start;
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run type/build checks**

Run:

```bash
cd web
npm test -- socket-status.test.ts
npm run build
```

Expected: test passes and Next.js build succeeds.

- [ ] **Step 6: Checkpoint review**

Run:

```bash
git diff -- web/src/components/AppNav.tsx web/src/components/overview/SocketServicePanel.tsx 'web/src/app/(app)/overview/page.tsx' web/src/app/globals.css
```

Expected: diff contains socket badge, Overview panel, and focused styling only. Do not commit unless explicitly requested.

---

### Task 5: Config Trigger UI and Documentation

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/app/(app)/config/page.tsx`
- Modify: `README.md`
- Modify: `SIMULATOR_GUIDE.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: Add frontend trigger type and Config option**

In `web/src/lib/api.ts`, replace:

```typescript
export type EmailEventTrigger = "run_failed" | "schedule_launch_failed" | "critical_alert";
```

with:

```typescript
export type EmailEventTrigger = "run_failed" | "schedule_launch_failed" | "critical_alert" | "socket_failure";
```

In `web/src/app/(app)/config/page.tsx`, replace `EMAIL_TRIGGER_OPTIONS` with:

```typescript
const EMAIL_TRIGGER_OPTIONS: { value: EmailEventTrigger; label: string }[] = [
  { value: "run_failed", label: "Run failed" },
  { value: "schedule_launch_failed", label: "Schedule launch failed" },
  { value: "critical_alert", label: "Critical alert (mapped to run failed)" },
  { value: "socket_failure", label: "Socket failure" },
];
```

- [ ] **Step 2: Document README behavior**

In `README.md`, add this short section after the existing Run reporting section:

```markdown
## Socket status service (web UI)

The authenticated web UI includes a lightweight socket status monitor for the store order and store stats websocket channels. The navigation bar shows a compact socket badge, and **Overview -> Socket Service** shows per-socket status, last check time, target store, and latest-run websocket evidence.

The active probe proves websocket connection reachability only. Doctor/trace runs remain the proof for end-to-end ordering lifecycle events.

Optional email notifications can include the `socket_failure` trigger from **Config -> Email**. Socket failure emails are sent only after repeated required-socket failures and are deduped.
```

- [ ] **Step 3: Document guide behavior and env vars**

In `SIMULATOR_GUIDE.md`, under `Operator observability (read first)`, add:

```markdown
### Socket status service

The web UI has a cached socket monitor for two required LastMile websocket channels:

- `store_orders`: `/ws/soc/store_<store_id>/`
- `store_stats`: `/ws/soc/store_statistics_<store_id>/`

The AppNav badge reports the active monitor state:

- **Sockets Up:** both required sockets connected on the last probe.
- **Sockets Degraded:** at least one required socket failed below the failure threshold.
- **Sockets Down:** at least one required socket failed at or above the failure threshold.
- **Sockets Unknown:** monitor disabled, target missing, or first probe pending.

The **Overview -> Socket Service** panel also shows latest-run websocket evidence. That evidence is historical run context and is intentionally separate from the active connection probe.

Environment controls:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIM_SOCKET_MONITOR_ENABLED` | `true` | Enable API-side socket probing. |
| `SIM_SOCKET_MONITOR_STORE_ID` | empty | Explicit store id to probe; falls back to `sim_actors.json` `defaults.store_id`. |
| `SIM_SOCKET_MONITOR_INTERVAL_SECONDS` | `60` | Probe interval; minimum 15 seconds. |
| `SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS` | `5` | Per-socket connection timeout. |
| `SIM_SOCKET_MONITOR_FAILURE_THRESHOLD` | `2` | Consecutive failures before status becomes Down and email can fire. |
```

In the `System Settings: Email Notifications` section, update the trigger list to include `socket_failure`:

```markdown
- `email_event_triggers` (`run_failed`, `schedule_launch_failed`, `critical_alert`, `socket_failure`)
```

Add this note near the existing email notes:

```markdown
- `socket_failure` sends only when the socket monitor transitions to Down after the configured failure threshold. It can be disabled independently from run failure emails.
```

- [ ] **Step 4: Add env examples and compose pass-through**

Add these variables to `.env.example` near the websocket settings:

```env
SIM_SOCKET_MONITOR_ENABLED=true
SIM_SOCKET_MONITOR_STORE_ID=
SIM_SOCKET_MONITOR_INTERVAL_SECONDS=60
SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS=5
SIM_SOCKET_MONITOR_FAILURE_THRESHOLD=2
```

Add these environment entries to the `api` service in `docker-compose.yml` and `docker-compose.prod.yml`. Note `LASTMILE_BASE_URL` is included because the monitor probes that host and it is not currently passed to the API container (without it the monitor always falls back to the hardcoded default):

```yaml
      LASTMILE_BASE_URL: ${LASTMILE_BASE_URL:-https://lastmile.fainzy.tech}
      SIM_SOCKET_MONITOR_ENABLED: ${SIM_SOCKET_MONITOR_ENABLED:-true}
      SIM_SOCKET_MONITOR_STORE_ID: ${SIM_SOCKET_MONITOR_STORE_ID:-}
      SIM_SOCKET_MONITOR_INTERVAL_SECONDS: ${SIM_SOCKET_MONITOR_INTERVAL_SECONDS:-60}
      SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS: ${SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS:-5}
      SIM_SOCKET_MONITOR_FAILURE_THRESHOLD: ${SIM_SOCKET_MONITOR_FAILURE_THRESHOLD:-2}
```

- [ ] **Step 5: Run docs/UI checks**

Run:

```bash
cd web
npm test -- socket-status.test.ts
npm run build
```

Expected: test and build pass after trigger type update.

- [ ] **Step 6: Checkpoint review**

Run:

```bash
git diff -- web/src/lib/api.ts 'web/src/app/(app)/config/page.tsx' README.md SIMULATOR_GUIDE.md .env.example docker-compose.yml docker-compose.prod.yml
```

Expected: diff contains only trigger type/label and docs updates. Do not commit unless explicitly requested.

---

### Task 6: Final Verification

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
python3 -m unittest tests.test_web_api.SocketMonitorCoreTests tests.test_web_api.SocketMonitorApiTests tests.test_web_api.SystemEmailApiTests tests.test_web_api.OverviewLatestRunTests -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader backend smoke tests**

Run:

```bash
python3 -m unittest tests.test_web_api -v
```

Expected: full `test_web_api` suite passes.

- [ ] **Step 3: Run frontend tests and build**

Run:

```bash
cd web
npm test -- socket-status.test.ts
npm run build
```

Expected: Vitest socket status test passes and Next.js build succeeds.

- [ ] **Step 4: Optional local app verification**

If the Docker stack is already available, run:

```bash
docker compose up -d --build
```

Then open:

```text
http://localhost:8080/overview
```

Expected:

- AppNav shows a socket badge.
- Badge links to `/overview#socket-service`.
- Overview shows the Socket Service panel.
- `Config -> Email` includes `Socket failure`.

- [ ] **Step 5: Final diff review**

Run:

```bash
git status --short
git diff --stat
```

Expected: changed files match this plan. `.superpowers/` brainstorming artifacts may remain untracked from the design session and should not be included in implementation work unless the user explicitly wants them kept.
