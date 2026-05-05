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

## Follow-on Initiative: Contract-Driven Runtime + Docs

### Goal

Eliminate drift between simulator behavior and guide documents by making one contract file the source of truth for flow semantics, default/fallback selection rules, flag constraints, and command mapping.

### Target Behavior

- CLI, web run builder, and published guide all derive from the same contract.
- Behavior for blank `--store`/`--phone` is explicit and tested by mode.
- Release verification fails when generated docs and runtime mappings diverge.

### Proposed Design

1. Add `docs/contract/simulator_contract.yaml` with:
   - flow presets and resolved mode/suite/scenarios,
   - supported flags and incompatibility rules,
   - actor-selection policy by mode (`trace` deterministic, `load` optional random/round-robin strategy),
   - artifact expectations and failure signature mappings.
2. Add a lightweight contract loader module used by:
   - CLI flow/flag validation path,
   - web `Flow Planner & Command Guide` renderer,
   - docs generation script.
3. Generate guide sections from contract into:
   - `SIMULATOR_GUIDE.md` (operator-focused),
   - `docs/reference/simulator_runtime_reference.md` (developer-focused).
4. Add guardrail tests:
   - contract schema validation,
   - contract-to-runtime mapping parity,
   - selection behavior tests for no-phone/no-store paths by mode.
5. Add release verification target:
   - `make verify` runs backend tests, frontend type/build checks, contract doc generation, and fails on dirty git state.

### Files to Add / Modify

| File | Purpose of Change |
|---|---|
| `docs/contract/simulator_contract.yaml` | Canonical runtime/docs contract |
| `docs/reference/simulator_runtime_reference.md` | Generated/derived developer reference |
| `SIMULATOR_GUIDE.md` | Generated/updated operator guide sections |
| `scripts/generate_simulator_docs.py` | Contract-to-doc generator |
| `contract_runtime.py` (new module) | Contract parser + typed access helpers |
| `__main__.py` | Consume contract mappings for flow/flag semantics |
| `api/app/main.py` | Optional contract-driven guide endpoint payloads |
| `web/src/lib/command-guide.ts` | Replace hardcoded guide data with contract-derived API data |
| `tests/test_contract_runtime.py` | Contract schema/parity/selection tests |
| `Makefile` | Add `verify` target including drift check |

### Acceptance Criteria (Follow-on)

- [ ] One contract file defines flows/flags/selection policy and validates in CI.
- [ ] `SIMULATOR_GUIDE.md` and GUI guide sections are generated from contract data.
- [ ] Trace mode default actor selection remains deterministic and explicitly documented.
- [ ] Load mode selection policy is configurable and explicitly documented (deterministic/round-robin/random strategy).
- [ ] `make verify` fails on docs/runtime drift.

## Follow-on Initiative: Enhanced Identity Logging & Reliability (2026-05-05)

### Goal
Ensure that simulation run history and reports consistently capture complete identity information (names, phone numbers) for stores and users, and fix any regressions or bugs introduced during this process.

### Target Behavior
- Web GUI displays full store and user names and phone numbers in the "Recent Runs" table.
- Simulation runs are reliable and do not crash with `NameError` or other basic regressions.
- Complete identity markers are emitted in logs for API consumption.

### Proposed Design
1. Update `user_sim.py` to fetch full user profiles.
2. Update `reporting.py` to propagate and log full identity snapshots in JSON.
3. Update `api/app/main.py` to parse JSON markers and migrate database schema.
4. Update web frontend to display enriched metadata.
5. Fix `NameError: name 'console' is not defined` in `reporting.py`.

### Files to Modify
| File | Purpose of Change |
|---|---|
| `reporting.py` | Add console identity logging and fix NameError |
| `user_sim.py` | Fetch full user profiles |
| `api/app/main.py` | Expand schema and update parser |
| `web/src/lib/api.ts` | Update RunRow types |
| `web/src/app/page.tsx` | Update dashboard table |

### Acceptance Criteria
- [ ] Simulation runs successfully without crashing.
- [ ] Web GUI shows full names and phone numbers for both user and store.
- [ ] Database schema is correctly migrated.
