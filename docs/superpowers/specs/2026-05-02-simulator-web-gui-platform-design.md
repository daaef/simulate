# Simulator Web GUI Platform Design

## Objective

Design a production-grade, user-friendly web application that operates the simulator end-to-end: run creation, live execution monitoring, report/story/events analysis, scheduling, and operational alerting. The platform must be Dockerized and deployable on a Contabo VPS behind Nginx.

## Scope

In scope:

- GUI for all existing simulator flows and supported command combinations.
- Live run execution UX with logs and status visualization.
- GUI rendering for `report.md`, `story.md`, and `events.json`.
- Scheduler, saved run profiles, and run history.
- Role-based access controls and secure deployment defaults.
- Docker + Nginx deployment blueprint for Contabo.

Out of scope (design phase):

- Full implementation code.
- Rewriting simulator engine behavior.
- Multi-region/high-availability orchestration.

## User Personas

1. Operations Operator:
   - Needs one-click daily doctor/full runs.
   - Needs simple pass/fail dashboards and actionable failures.
2. Engineering Investigator:
   - Needs deep trace navigation, latency bottlenecks, websocket mismatches, payload context.
3. Platform Admin:
   - Needs user/role management, retention policies, scheduling controls, and infrastructure health.

## Constraints

- Existing Python simulator CLI is source of truth for run semantics.
- Must run on a single VPS initially.
- Must support both beginner operators and technical investigators.
- Must preserve immutable run evidence for audits/debugging.

## Approaches Considered

### Approach A (Recommended): Next.js + FastAPI + In-Process Executor + APScheduler + SQLite/Postgres

Pros:

- Easiest local bring-up on a PC with minimal moving parts.
- Best balance between UX richness and operational simplicity.
- Fastest path to production without extra queue infrastructure.
- Clean path to scale later (add Celery/Redis only when required).

Cons:

- Less horizontal scaling capacity on day one.
- Requires discipline around bounded in-process concurrency.

### Approach B: Next.js + FastAPI + Celery + Redis + Postgres (Scale-First)

Pros:

- Better out-of-the-box distribution for many concurrent long jobs.
- Strong queue semantics and retry tooling.

Cons:

- More setup and more services to manage from day one.
- Adds unnecessary complexity for immediate local testing goals.

### Approach C: Django + HTMX Monolith

Pros:

- Lower moving parts than a split frontend/backend stack.

Cons:

- Lower UX ceiling for rich operational dashboards.
- Harder to match the desired polished app-like experience.

Recommendation: Approach A.

## System Architecture (Recommended)

Services:

- `web`: Next.js frontend.
- `api`: FastAPI control plane + in-process run executor + APScheduler.
- `postgres`: run metadata, profiles, users, audit logs (SQLite allowed for local dev).
- `artifact_volume`: persisted run artifacts.
- `nginx`: TLS reverse proxy for frontend and API.

Execution flow:

1. User creates run profile from GUI.
2. API validates and persists run request.
3. API executor starts simulator subprocess from DB run state.
4. API streams logs/status/events to UI channels.
5. API stores parsed summaries and artifact references.
6. UI shows live stream + post-run analytics.

## UX Blueprint

Primary surfaces:

1. Overview Dashboard:
   - Daily health verdicts, error trends, bottlenecks, websocket health.
2. Run Builder:
   - Presets + advanced flag editor + command preview.
   - Validation warnings before submission.
3. Live Run Console:
   - Streaming logs, status timeline, per-order counters, cancel/retry actions.
4. Run History:
   - Filter by flow, verdict, store, user, date, duration.
5. Run Details:
   - Tabs: Summary, Scenarios, Orders, Websockets, Findings, Raw Events.
6. Reports/Stories Viewer:
   - Markdown render with export/download.
7. Events Explorer:
   - JSON table with search/filter by actor/action/status/http code.
8. Schedules:
   - Recurring runs + blackout windows + run limits.
9. Alerts:
   - Configure channels and severity thresholds.
10. Admin:
   - Users, roles, retention, concurrency caps, secrets status.

## Security Model

- Auth: secure session/JWT with hashed credentials or SSO-ready abstraction.
- Authorization: RBAC (`admin`, `operator`, `viewer`).
- Secret handling: env-vars or secret files only.
- Transport security: HTTPS with strong TLS defaults via Nginx.
- Audit: immutable run audit logs for sensitive actions.

## Reliability and Scale Model

- DB-backed run queue with bounded in-process worker slots.
- Per-run timeout and graceful cancellation.
- Concurrency controls (`max_workers`, `max_parallel_runs`).
- Health checks for all services.
- Artifact retention policy and cleanup jobs.
- Backup strategy for Postgres and artifacts.

## Data Model (High-Level)

- `users`, `roles`, `sessions`
- `run_profiles` (preset/custom command schema)
- `runs` (state machine, timing, verdict, references)
- `run_events` (indexed event facts)
- `run_artifacts` (paths/hashes/format)
- `schedules` (cron config, enabled state, last/next run)
- `alerts` + `alert_deliveries`

## Deployment Blueprint (Contabo + Nginx)

- Docker Compose stack with persistent named volumes.
- Nginx reverse proxy:
  - `/` -> `web`
  - `/api` -> `api`
  - websocket/SSE upgrade support for live streams.
- TLS cert management (Let's Encrypt + renewal job).
- Firewall:
  - expose 80/443 only.
  - lock internal service ports to Docker network.
- Monitoring:
  - service health endpoint checks.
  - optional Prometheus/Grafana integration (phase-gated).

## Non-Functional Targets

- Startup to run submission: < 5 clicks for daily doctor.
- Live log latency: near-real-time (< 2s target).
- UI available during long runs without blocking.
- Run artifact retention and retrieval deterministic and auditable.

## Decision Gates Requiring User Sign-Off

1. Auth model:
   - Local auth only (v1) vs SSO-ready from day one.
2. Alert channels:
   - Slack only vs Slack + email + webhook.
3. Retention:
   - 30/90/180-day policies for artifacts and event rows.
4. Artifact backend:
   - local disk first vs S3-compatible immediately.
5. Queue strategy:
   - Keep in-process executor for v1 or add Celery/Redis in v1.

## Success Criteria

- Operators can run, monitor, and analyze simulations with no CLI usage.
- Daily doctor operational workflow is fully web-native.
- Platform is deployable and maintainable on Contabo VPS with Docker + Nginx.
- Architecture supports incremental future growth without major redesign.
