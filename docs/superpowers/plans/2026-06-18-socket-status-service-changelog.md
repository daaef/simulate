# Changelog — Socket Status Service (2026-06-22)

Implements [the plan](2026-06-18-socket-status-service.md) with the verified review corrections folded in.

## Layer 1 — High-level
Operators now get an at-a-glance view of whether the LastMile `store_orders` and `store_stats` websocket channels are reachable, without keeping a run open. A compact socket badge appears in the nav bar (Up/Degraded/Down/Unknown), an **Overview → Socket Service** panel shows per-socket status, latency, last-checked time, target store, and latest-run websocket evidence, and `/api/v1/alerts` raises a critical `sockets` alert when the monitor is Down. A new, independently-toggleable `socket_failure` email trigger sends (deduped) when the monitor transitions to Down. An API-side APScheduler job probes the sockets every 60s (configurable). The active probe proves connection reachability only — doctor/trace runs remain the end-to-end proof.

## Layer 2 — Low-level
**New files**
- `api/app/socket_monitor.py` — `SocketMonitorConfig`, target resolution (env → `sim_actors.json`), `probe_socket` (bare wss handshake matching the observer), threshold-based status reduction, snapshot building, and DB-backed notification dedupe.
- `web/src/lib/socket-status.ts` + `.test.ts` — badge label/class, tooltip, tone helpers; 3 unit tests.
- `web/src/components/overview/SocketServicePanel.tsx` — Overview panel (anchored `#socket-service`).

**Backend changes**
- `api/requirements.txt` — added `websockets>=12.0` (CRITICAL: the API image lacked it; module import would crash boot).
- `api/app/system/models.py` — `EmailEventTrigger` literal gains `socket_failure`.
- `api/app/main.py` — `EMAIL_EVENT_TRIGGERS`/`SOCKET_MONITOR_NOTIFICATIONS_KEY`; generic `_load/_save_system_setting_json`; env helpers + `_socket_monitor_config`; `_send_socket_failure_email`; `socket_monitor` instance + `_socket_monitor_status_payload` + `_run_socket_monitor_job` (all defined ABOVE the import-time scheduler block per the ordering note); provider registration; `socket-monitor` scheduler job; `socket-monitor-down` alert in `_alerts_payload`.
- `api/app/overview/service.py` — `Callable` import; `_socket_status_provider` global + `configure_socket_status_provider`; `_latest_run_websocket_evidence`; `socket_status()` merging cached snapshot + evidence.
- `api/app/overview/routes.py` — `GET /api/v1/overview/socket-status` (`dashboard:read`).

**Frontend changes**
- `web/src/lib/api.ts` — `SocketMonitorStatus`/`SocketStatusRow`/`SocketStatusResponse` types, `socket_failure` in `EmailEventTrigger`, `fetchSocketStatus()`.
- `web/src/components/AppNav.tsx` — 30s socket poll + badge `Link` to `#socket-service`.
- `web/src/app/(app)/overview/page.tsx` — fetch + render `SocketServicePanel`.
- `web/src/app/(app)/config/page.tsx` — "Socket failure" trigger option.
- `web/src/app/globals.css` — badge + panel styles.

**Config/docs**
- `.env.example`, `docker-compose.yml`, `docker-compose.prod.yml` — `SIM_SOCKET_MONITOR_*` + `LASTMILE_BASE_URL` passthrough (correction: was passed to no service).
- `README.md`, `SIMULATOR_GUIDE.md` — service behavior, env table, single-worker caveat, `socket_failure` email note.
- `tests/test_web_api.py` — `SocketMonitorCoreTests` (6) + `SocketMonitorApiTests` (3).

## Verification
- `SocketMonitorCoreTests`, `SocketMonitorApiTests`, `SystemEmailApiTests`, `OverviewLatestRunTests`: 25 passed.
- Full `tests.test_web_api`: 110 run, 1 failure — `test_new_period_window_contract_fields_and_preview_metadata`, a PRE-EXISTING date-expired test (`future_anchor` hardcoded to 2026-06-10, now past). Confirmed it fails identically with all socket changes stashed.
- Frontend: full vitest suite 63 passed; `npm run build` succeeded.
- Both compose files parse (`docker compose config`).

## Not done / deferred
- No commit/push (commit policy: only on explicit request). New files are untracked.
- Manual in-app verification (Docker up, badge/panel/email) not yet run.
- Prod note: set `SIM_SOCKET_MONITOR_STORE_ID` explicitly — prod compose uses named volumes, so the `sim_actors.json` fallback relies on the image-baked file.
