# Implementation Plan

## Problem Statement

The simulator currently runs as a CLI-first system with markdown/json artifacts. Operators want a production-grade web GUI that can run every simulator command, schedule and monitor runs, and present reports/stories/events in a user-friendly way, while being Dockerized and deployable on a Contabo VPS behind Nginx.

## Target Behavior

- A web app can launch all existing simulator flows and custom command combinations without manual terminal work.
- Operators can create, save, clone, schedule, and run simulation profiles from a GUI.
- Live run telemetry (logs, status transitions, API/websocket metrics) is visible in real time.
- Reports, stories, and events are first-class GUI views with searchable/filterable drill-down.
- The platform is Dockerized, production-deployable on Contabo + Nginx, and secured for operational use.
- The architecture supports future growth (more workers, alerting, longer retention, optional object storage) without major redesign.

## Existing Behavior

- Simulator execution, orchestration, and validation are implemented in Python CLI modules.
- Artifacts are generated per run as `events.json`, `report.md`, and `story.md`.
- No web control plane exists.
- No job queue, scheduler UI, role-based web auth, or GUI artifact explorer exists.
- Deployment and operations are manual CLI-oriented.

## Proposed Approach

Build a thin but robust web control plane around the existing simulator engine:

1. Keep Python simulator modules as the execution core.
2. Add a Python FastAPI backend for run orchestration, artifact indexing, and APIs.
3. Use an in-process asynchronous run executor (bounded worker pool) instead of a distributed queue for v1.
4. Use APScheduler for recurring runs in v1.
5. Build a Next.js (TypeScript) frontend with shadcn/ui + charting for operations UX.
6. Containerize frontend/backend/postgres(optional)/nginx and deploy behind Nginx.

Recommended stack (best long-term fit here):

- Frontend: Next.js App Router + TypeScript + shadcn/ui + TanStack Query + ECharts.
- Backend API: FastAPI + Pydantic + SQLAlchemy + Alembic.
- Queue/Scheduler: In-process task runner + APScheduler (Celery/Redis is phase-2 only if scale requires it).
- Data: SQLite for local PC testing; Postgres for VPS production metadata + artifact indices.
- Artifacts: local volume in v1, S3-compatible storage abstraction ready for migration.

## Architecture / Design Notes

- Command execution model:
  - Backend stores canonical run config.
  - Backend executor renders validated CLI command and executes subprocess with streamed stdout/stderr.
  - Parsed events are ingested live and persisted.
- Observability model:
  - Store raw logs and parsed key metrics separately.
  - Keep source artifacts immutable for audit.
  - Expose derived metrics for fast dashboards.
- UX model:
  - Two levels: Operator view (simple) and Engineer view (deep trace).
  - Guided “Run Builder” defaults to safe/recommended modes.
  - Advanced mode allows explicit suite/scenario flag tuning.
- Security model:
  - Role-based auth (admin/operator/viewer).
  - Signed API sessions/JWT, CSRF protection, strict CORS policy.
  - Secrets only via environment variables; never in DB plain text.
- Reliability model:
  - Idempotent run submission keys.
  - Concurrency caps and FIFO scheduling from DB-backed run states.
  - Graceful cancellation and timeout handling.
  - Health probes for all services.
- Deployment model:
  - Docker Compose for v1 production on one VPS.
  - Nginx TLS reverse proxy with websocket/SSE pass-through.
  - Persistent volumes for DB and artifacts.

## Files to Modify

| File | Purpose of Change |
|---|---|
| `docs/superpowers/specs/2026-05-02-simulator-web-gui-platform-design.md` | Architecture/design spec |
| `docs/superpowers/plans/2026-05-02-simulator-web-gui-platform.md` | Execution-ready phased implementation plan |
| `implementation/tracker/README.md` | Update project goal/scope/status for web planning |
| `implementation/tracker/implementation_plan.md` | Canonical technical plan for web platform |
| `implementation/tracker/tasks.md` | Task board for pending implementation phases |
| `implementation/tracker/session_log.md` | Chronological planning and handoff record |
| `docker-compose.yml` (planned) | Multi-service deployment definition |
| `infra/nginx/nginx.conf` (planned) | Reverse proxy + TLS + websocket config |
| `web/` (planned) | Next.js frontend app |
| `api/` (planned) | FastAPI service |
| `api/app/executor.py` (planned) | Async run executor and scheduler integration |

## Implementation Steps

1. Finalize architecture decisions (auth model, retention, alert channels, storage backend, concurrency limits).
2. Scaffold monorepo layout for `web`, `api`, and shared config modules.
3. Build backend run-model schema, run lifecycle APIs, and artifact indexing APIs.
4. Build backend execution pipeline for simulator subprocesses and log/event streaming.
5. Build scheduler and recurring run engine with APScheduler.
6. Build frontend Run Builder, Profiles, and Run History pages.
7. Build live run console page (logs + status timeline + key metrics).
8. Build report/story/events explorer pages with search/filter/download.
9. Build dashboard pages for daily health, bottlenecks, trend charts, and failure summaries.
10. Add authentication, roles, and route/API authorization.
11. Dockerize services and add Nginx reverse proxy config for VPS deployment.
12. Add backup/retention jobs, observability hooks, and production hardening.
13. Validate with end-to-end tests and perform pilot deployment.

## Testing Strategy

- Unit tests:
  - Backend request validation, command rendering, parsing pipelines, permission checks.
  - Frontend components for run builder, tables, filters, and state transitions.
- Integration tests:
  - API + scheduler + DB orchestration.
  - Real simulator subprocess lifecycle in controlled test mode.
  - Scheduler-triggered run creation and execution.
- Manual tests:
  - End-to-end “run doctor from GUI” flow.
  - Report/story/events deep navigation.
  - Failure/cancel/timeout scenarios.
  - Deployment on Contabo with Nginx TLS.
- Edge cases:
  - API process restart mid-run, partial artifact writes, duplicate run submissions.
  - High log volume streaming, connection drops, stale websocket/SSE sessions.
  - Disk pressure and retention cleanup safety.

## Rollback Strategy

- Keep CLI simulator unchanged and callable directly.
- Roll back web platform by stopping web/api services while preserving artifact volumes.
- Revert schema migrations with controlled Alembic downgrade path.
- Maintain versioned deployment tags and reversible Nginx configs.

## Acceptance Criteria

- [ ] Web UI can execute all simulator flow presets and custom trace/load combinations.
- [ ] Operators can create/save/schedule run profiles without editing CLI flags manually.
- [ ] Live run telemetry is visible in GUI with stream continuity and failure states.
- [ ] Reports, stories, and events are fully navigable/searchable in GUI.
- [ ] Platform runs in Docker on Contabo VPS behind Nginx with TLS and health checks.
- [ ] Role-based access control is implemented for admin/operator/viewer paths.
- [ ] Retention and backup strategy is implemented and documented.
- [ ] The solution passes end-to-end validation against at least one real doctor run.
- [ ] Local PC bring-up requires only `docker compose up` with no Redis/Celery dependency.
