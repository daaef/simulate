# Fainzy Simulator Standup Deck Outline

Date: Thursday, May 14, 2026  
Audience: Engineering team  
Duration: 15+ minutes

## Slide 1 — Changes Made on Tuesday, May 13, 2026

- SMTP + email notification system landed end-to-end.
- New email settings surfaced in web Config and backed by system APIs (`GET/PUT /api/v1/system/email`, `POST /api/v1/system/email/test`).
- Deployment and compose wiring updated to pass SMTP environment variables in local and production stacks.
- Observability contract clarified and enforced in docs/UI: `Up`, `Degraded`, `Down` + explicit `/healthz` scope.
- Runs and overview observability quality improved (critical findings focus, context chips, launch attribution).
- WebSocket/order-status handling improved in observer and scenario progression.
- Trace/user simulation coverage and profile management improved for richer run evidence.

Source commits (May 13 only):
- `36cd65e`: SMTP deployment configuration
- `0e593a2`: observability + health contract enhancements
- `61bada2`: email settings + SMTP configuration
- `9b85f72`: websocket observer and order status handling improvements
- `768883f`: trace runner/user simulation coverage and profile improvements

## Slide 2 — What This Project Is (From Ground Up)

- A simulator platform to continuously validate ordering flows across user, store, and robot perspectives.
- Two runtime styles:
  - deterministic proof runs (`trace` / presets like `doctor`)
  - traffic/churn simulation (`load`)
- Operates as a daily operational doctor with evidence artifacts (`events.json`, `report.md`, `story.md`).

## Slide 3 — Health Contract and Signal Semantics

- `Up`: control plane usable + recent successful doctor/trace within team policy window.
- `Degraded`: partial risk (alerts/backlog/warnings) but not complete service-blocking failure.
- `Down`: blocking failure (failed run, no auth, cannot launch, critical ordering progression broken).
- `/healthz` only proves FastAPI/control-plane process health; it does not prove last-mile HTTP/websocket/order completion integrity.

## Slide 4 — Architecture Layer 1: Simulation Engine (CLI)

- Core orchestration: `__main__.py` chooses flow/mode/scenarios and writes artifacts.
- Actor simulators:
  - `user_sim.py`: OTP/auth, ordering actions, user websocket.
  - `store_sim.py`: store actions (accept/reject/ready), store websocket.
  - `robot_sim.py`: delivery lifecycle transitions.
- Deterministic workflow and assertions: `trace_runner.py`.
- Passive protocol validation: `websocket_observer.py`.

## Slide 5 — Architecture Layer 2: API Control Plane (FastAPI)

- Authenticated operator APIs for:
  - run orchestration and run metadata
  - flow capability metadata (`/api/v1/flows`)
  - schedules, alerts, retention, archive, admin/system settings
  - email configuration and test-send endpoints
- Runs store launch attribution and context metadata for UI observability.

## Slide 6 — Architecture Layer 3: Web UI + Persistence

- Next.js operator UI routes: Overview, Runs, Config, Schedules, Archives, Retention, Admin.
- Role-aware operations (admin/operator/runner/viewer/auditor).
- PostgreSQL stores control-plane data; run artifacts and GUI plans stored under `runs/`.
- UI shows API health separately from run-level process success/failure.

## Slide 7 — End-to-End Runtime Data Flow (Launch to Execution)

- Operator selects plan + flow/mode in Runs UI.
- UI sends launch request to API; API starts simulation run.
- Simulation resolves configuration precedence:
  1) explicit CLI/launch args
  2) selected plan JSON
  3) `.env` fallback for secrets/deployment/auth cache
  4) built-in defaults
- Simulators execute HTTP and websocket-driven behavior; trace gates progression by required status events.

## Slide 8 — End-to-End Runtime Data Flow (Evidence and Outcomes)

- Every run emits:
  - `events.json`: full event ledger
  - `report.md`: technical/operational summary
  - `story.md`: narrative digest
- Overview/Runs render run outcomes, critical findings, and launch context chips (`profile`, `schedule`, integration `route`).
- Failures surface through UI status, alerting, and optional email triggers.

## Slide 9 — Operator Surfaces and Responsibilities

- Overview: posture dashboard, findings, trends, alert visibility.
- Runs: launch/manage/replay/delete runs, watch logs, inspect artifacts, save profiles.
- Config: GUI plan management + non-secret email notification settings.
- Schedules: campaign-first schedule automation, pause/resume/disable/restore/manual trigger.

## Slide 10 — Scheduling and Attribution Semantics

- Preferred schedule contract centers on `anchor_start_at`, `period`, `repeat`, `stop_rule`, `run_slots`, blackout constraints.
- Scheduler computes feasibility and warnings (`requested_runs_per_period`, `feasible_runs_per_period`, `schedule_warnings`).
- Recent executions expose schedule phase and latest run status chips.
- Launch attribution tracks trigger source (`manual`, `schedule`, `github`, `profile`) for post-incident traceability.

## Slide 11 — Observability Model

- Critical findings are intentionally availability-focused (server/API/network/websocket availability), reducing business-noise in top-level incident cues.
- Full raw findings still preserved in artifacts for deep triage.
- Interpretation ladder:
  - `/healthz` failing => simulator stack/control-plane issue.
  - `/healthz` ok + run failed => product-path/process issue.
  - websocket 502 on `wss://lastmile...` => upstream gateway/proxy boundary issue.

## Slide 12 — Alerting and Email Notification Model

- Configurable triggers: `run_failed`, `schedule_launch_failed`, `critical_alert`.
- SMTP secrets remain environment-only (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_TLS_MODE`).
- Test endpoint has cooldown enforcement to limit notification noise.
- Failure emails include launch context (`Profile`, `Trigger`, `Project`, `Repository`, optional `Schedule`).

## Slide 13 — Deployment and Runtime Topology

- Local: `docker compose up -d --build` (`web`, `api`, `postgres`, `nginx` stack).
- Production: GitHub Actions SSH deploy using `docker-compose.prod.yml` and host-managed `.env.prod`.
- Persistent volumes preserve DB, run artifacts, and GUI plans.
- Typical prod binding defaults to loopback-hosted endpoint (`127.0.0.1:8090`) unless intentionally exposed.

## Slide 14 — Integration-Driven Verification Runs

- Supports GitHub deployment-complete webhook integration (`/api/v1/integrations/github/deployment-complete`).
- Successful upstream deployment events can trigger simulator verification runs.
- Trigger records are idempotent and include source context in run metadata/UI.

## Slide 15 — Risks, Sharp Edges, and What to Watch Next

- Websocket gateway failures (notably `HTTP 502`) can indicate upstream last-mile proxy issues outside this repo.
- `strict_plan` + invalid plan can intentionally convert best-effort execution into hard fail behavior.
- Websocket gate enforcement trade-off:
  - off: warning-first continuity (less false-red)
  - on: fail-fast truth (higher sensitivity/noise)
- Key operational watchpoints:
  - schedule warnings growth
  - retention/archive backlog trend
  - repeated run-failure clusters by flow/scenario

## Slide 16 — Close: Operational Runbook for Daily Use

- Daily health proof path: run `doctor` with team-approved plan.
- Regression path: narrow `trace` suite/scenarios.
- Load path: `load` mode for churn/stress signals.
- Escalation heuristic:
  - control-plane down -> fix stack first
  - control-plane up but doctor down -> investigate product-path layers
  - websocket 502 cluster -> validate last-mile gateway before simulator changes
