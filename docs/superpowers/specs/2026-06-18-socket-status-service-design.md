# Socket Status Service Design

Date: 2026-06-18
Status: Approved direction, pending implementation plan
Approved option: Option 2, cached server-side socket monitor plus latest-run context

## Goal

Add an operator-facing socket status service that shows whether the LastMile order and stats websocket channels are currently reachable, and allow socket failures to trigger the existing configurable email notification system.

The visible result should be:

- A compact navigation-bar socket badge.
- A detailed Socket Service panel on `/overview`.
- A new email trigger that operators can disable independently from run-failure emails.

## Context

The simulator already records websocket evidence during doctor and trace runs through `WebsocketObserver`. Run detail and Overview pages already classify websocket event gaps and gate failures into critical and operational findings.

The current email system is configured from `Config -> Email` and supports these triggers:

- `run_failed`
- `schedule_launch_failed`
- `critical_alert`

Run-failure email sends are currently tied to run terminal status updates. A socket monitor must not depend on a user keeping Overview open.

Relevant version facts from repo files:

- Web frontend: Next.js 14.2.33, React 18.3.1, TypeScript 5.8.3, Vitest 3.1.4.
- API: FastAPI 0.115.5, Uvicorn 0.32.1, APScheduler 3.10.4, Python 3.11 image.
- Websocket client dependency: `websockets>=12.0`.
- Local API image command uses Uvicorn workers by default; production compose pins API workers to 1.

## Scope

Required active socket checks:

- `store_orders`: `/ws/soc/store_<store_id>/`
- `store_stats`: `/ws/soc/store_statistics_<store_id>/`

Latest-run evidence may still show broader run websocket coverage, including `user_orders`, because run artifacts already record that source when applicable.

## Non-Goals

- No new always-open websocket daemon.
- No attempt to validate order lifecycle messages outside a run.
- No store/user impersonation through websocket messages.
- No replacement for doctor or trace runs as the end-to-end health proof.
- No new SMTP provider or email delivery system.

## Recommended Architecture

### 1. Socket Monitor Service

Add a small API-side service that periodically probes the required websocket targets and stores a cached status snapshot.

Behavior:

- Resolve `store_id` from `SIM_SOCKET_MONITOR_STORE_ID` when set, otherwise from `sim_actors.json` `defaults.store_id`.
- Build the websocket root from the same LastMile base URL convention used by the simulator websocket observer.
- Open each websocket long enough to prove the connection handshake succeeds.
- Close the websocket immediately after the check.
- Record latency, checked timestamp, failure reason, and consecutive failure count per socket.
- Return `unknown` when the monitor is disabled, no store can be resolved, or no probe has completed.

Suggested defaults:

- `SIM_SOCKET_MONITOR_ENABLED=true`
- `SIM_SOCKET_MONITOR_INTERVAL_SECONDS=60`
- `SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS=5`
- `SIM_SOCKET_MONITOR_FAILURE_THRESHOLD=2`

The monitor should be conservative: one transient failed probe should mark the socket `degraded`, not immediately `down`.

### 2. Cached API Contract

Add:

```text
GET /api/v1/overview/socket-status
```

Permission:

- `dashboard:read`, because AppNav and Overview should be visible to normal operators.

Response shape:

```json
{
  "enabled": true,
  "status": "up",
  "checked_at": "2026-06-18T12:00:00+00:00",
  "target": {
    "store_id": "FZY_586940",
    "source": "sim_actors.json defaults.store_id",
    "base_url": "https://lastmile.fainzy.tech"
  },
  "required": [
    {
      "key": "store_orders",
      "label": "Orders",
      "status": "up",
      "latency_ms": 180,
      "failure_streak": 0,
      "reason": null
    },
    {
      "key": "store_stats",
      "label": "Stats",
      "status": "up",
      "latency_ms": 155,
      "failure_streak": 0,
      "reason": null
    }
  ],
  "latest_run_evidence": {
    "status": "up",
    "run_id": 123,
    "run_status": "succeeded",
    "matched": 18,
    "expected": 18,
    "missed": 0
  }
}
```

Status rules:

- `up`: all required sockets connect.
- `degraded`: at least one required socket has a transient failure below threshold.
- `down`: at least one required socket failure persists at or above threshold.
- `unknown`: monitor disabled, target missing, first probe pending, or probe state unavailable.

The top-level `status` is the active monitor status used by AppNav. Latest-run evidence is separate historical context shown on Overview, not an automatic nav downgrade.

### 3. Navigation UI

Add a compact socket badge near the existing AppNav links.

States:

- `Sockets Up`: green.
- `Sockets Degraded`: yellow.
- `Sockets Down`: red.
- `Sockets Unknown`: neutral.

Interaction:

- Link or title points to `/overview#socket-service`.
- Tooltip includes the last checked time and failing socket names when applicable.
- Poll every 30 seconds in AppNav. Do not block navigation rendering on this request.

### 4. Overview UI

Add a Socket Service panel near the Latest Run Command Center.

Panel content:

- Overall socket monitor state.
- Per-socket rows for Orders and Stats.
- Last checked time.
- Store id and target source.
- Failure reason for any degraded/down socket.
- Latest-run websocket evidence summary as a separate historical signal.
- Clear empty/unknown text when no target is configured.

Recommended placement:

- Use the approved Option A layout: quiet nav badge plus detailed Overview panel.
- Anchor panel with `id="socket-service"` so the nav badge can deep-link to it.

### 5. Email Trigger

Add a new email event trigger:

```text
socket_failure
```

Config UI label:

```text
Socket failure
```

Send rule:

- Send only when socket monitor status transitions into `down`.
- Do not send on a single transient failure.
- Do not send when email is disabled or `socket_failure` is unchecked.
- Include store id, failing sockets, failure reasons, last checked time, current status URL, and the observability footer used by existing failure emails.

Deduplication:

- Existing in-memory email dedupe is not sufficient for a scheduled monitor because API workers can duplicate scheduled work.
- Store socket notification state in `system_settings` under a dedicated key such as `socket_monitor_notifications`.
- Persist at least `last_notification_signature`, `last_notification_at`, and `last_down_started_at`.
- Only send another socket failure email if the failing socket signature changes or the configured dedupe window has elapsed.

### 6. Alerts

Add a socket alert row to `/api/v1/alerts` when cached monitor status is `down`.

Alert:

- domain: `sockets`
- severity: `critical`
- href: `/overview#socket-service`

Use `degraded` as warning only if the UI already has enough signal to avoid noise.

## Data Flow

1. APScheduler runs the socket monitor job at the configured interval.
2. The monitor resolves the store target.
3. The monitor probes `store_orders` and `store_stats`.
4. The monitor updates cached/persisted status.
5. If status transitions into `down`, the monitor evaluates `socket_failure` notification rules.
6. AppNav polls `/api/v1/overview/socket-status` for the compact badge.
7. Overview fetches the same endpoint and renders the detailed Socket Service panel.
8. Latest-run websocket evidence remains sourced from existing run artifacts and Overview metrics.

## Error Handling

- Connection timeout: record socket as failed with timeout reason.
- DNS/TLS/connect exception: record failed with sanitized reason.
- Missing store id: return `unknown`, no email.
- Monitor disabled: return `unknown`, no email.
- Email send failure: log warning, keep socket status accurate.
- Endpoint failure: AppNav falls back to `Sockets Unknown`; Overview shows retryable error state through existing page error handling.

## Scenario Matrix

| Scenario | Preconditions | Expected outcome | Failure or worst case | Detection | Mitigation |
| --- | --- | --- | --- | --- | --- |
| Happy path | Store id resolves and both sockets connect | Nav shows `Sockets Up`; Overview rows show Orders and Stats up | Probe latency is slow but succeeds | Cached status has both rows up | Show latency and last checked time |
| Transient socket failure | One probe fails once | Nav shows degraded; no email | Brief false warning | Failure streak below threshold | Require repeated failures before `down` |
| Sustained socket failure | Required socket fails at or above threshold | Nav shows down; Overview lists reason; optional email sends | Duplicate email from multiple workers | Persisted notification signature and timestamp | DB-backed notification dedupe |
| Missing target config | No `SIM_SOCKET_MONITOR_STORE_ID` and no `sim_actors.json` default store | Status unknown | Operator may think monitor is broken | Target source is absent in payload | Overview explains how target is resolved |
| Email trigger disabled | Socket status transitions to down | UI and alerts update; no email | Operator expected an email | Email settings show unchecked trigger | Config page can re-enable `Socket failure` |
| Latest run evidence misses websocket events | Active probe up but latest run has misses | Nav still reflects active probe; Overview shows latest-run warning context | Confusion between current socket reachability and run lifecycle proof | Overview separates active probe and latest-run evidence | Copy clarifies probe is connection-only |
| Rollback | Feature reverted or monitor disabled | Existing run, alert, and email behavior remains | Stale socket status remains | Monitor disabled or code removed | UI treats missing status as unknown |

## Blast Radius

Likely affected areas:

- API scheduler and system settings.
- Overview API routes and service payloads.
- Alerts payload.
- Email settings validation and email trigger UI.
- AppNav and Overview page rendering.
- README and SIMULATOR_GUIDE because user-facing behavior, env vars, and notifications change.

Existing run launch, run detail, doctor/trace websocket evidence, and Orders page behavior should remain unchanged.

## Verification Plan

Backend:

- Unit-test target resolution from env and `sim_actors.json`.
- Unit-test status reduction: up, degraded, down, unknown.
- Unit-test API payload shape for `/api/v1/overview/socket-status`.
- Unit-test `socket_failure` accepted in email settings.
- Unit-test socket failure email fires only after threshold and respects disabled trigger.
- Unit-test persisted dedupe prevents repeated sends for the same failure signature.
- Unit-test alert payload includes socket alert when monitor is down.

Frontend:

- Type-check and build the web app.
- Add Vitest coverage for socket status formatting and badge label selection.
- Verify AppNav renders each status without layout shift.
- Verify Overview panel renders loading, up, degraded, down, and unknown states.

Manual:

- Run app locally.
- Confirm `/overview` shows Socket Service.
- Confirm AppNav badge deep-links to `#socket-service`.
- Mock or force a failed socket target and confirm down/degraded UI.
- Enable `Socket failure` email trigger and confirm one deduped notification.

## Documentation Updates

Update:

- `README.md`: overview of socket status service and email trigger.
- `SIMULATOR_GUIDE.md`: operator interpretation, config/env vars, and notification behavior.

Document that the active probe proves websocket connection reachability only. Doctor/trace runs remain the source for end-to-end order lifecycle proof.
