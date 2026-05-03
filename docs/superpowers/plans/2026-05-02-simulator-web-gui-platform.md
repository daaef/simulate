# Simulator Web GUI Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Dockerized web platform that runs and monitors the simulator end-to-end on Contabo VPS with Nginx.

**Architecture:** Keep the existing Python simulator engine as execution core; add FastAPI control plane with in-process async executor + APScheduler + SQLite/Postgres; build a Next.js frontend for operator and engineering workflows.

**Tech Stack:** Next.js (TypeScript, shadcn/ui, TanStack Query, ECharts), FastAPI, APScheduler, SQLite/Postgres, Docker Compose, Nginx.

---

### Task 1: Repository Scaffold for Web Platform

**Files:**
- Create: `web/`
- Create: `api/`
- Create: `docker-compose.yml`
- Create: `infra/nginx/nginx.conf`
- Modify: `README`/deployment docs (new section)

- [ ] Create service directory structure for `web` and `api`.
- [ ] Add base Dockerfiles for each service.
- [ ] Add Compose definitions for `web`, `api`, `postgres`, and `nginx`.
- [ ] Add healthcheck endpoints and Compose health checks.

### Task 2: Backend Run Domain and API Contracts

**Files:**
- Create: `api/app/main.py`
- Create: `api/app/models/*.py`
- Create: `api/app/schemas/*.py`
- Create: `api/app/routes/*.py`
- Create: `api/alembic/*`

- [ ] Implement `runs`, `run_profiles`, `run_artifacts`, `schedules`, and `users/roles` schemas.
- [ ] Implement REST endpoints for run submission, listing, detail retrieval, and cancellation.
- [ ] Implement profile CRUD endpoints.
- [ ] Implement structured response models for frontend consumption.

### Task 3: Execution Pipeline (API Service)

**Files:**
- Create: `api/app/executor.py`
- Create: `api/app/parsers.py`
- Modify: `api` run lifecycle contracts

- [ ] Implement command rendering from validated run config.
- [ ] Implement simulator subprocess execution with streamed stdout/stderr capture.
- [ ] Parse and persist run state transitions and key metrics.
- [ ] Persist artifact references (`events.json`, `report.md`, `story.md`).
- [ ] Implement retry/failure/cancel timeout handling.

### Task 4: Scheduler and Recurring Runs

**Files:**
- Create: `api/app/scheduler.py`
- Modify: schedule models/routes

- [ ] Implement recurring schedule model and cron validation.
- [ ] Add scheduler job creation/update/delete endpoints.
- [ ] Implement DB-backed enqueue behavior for schedule-triggered runs.
- [ ] Add safeguards for overlap and max concurrency.

### Task 5: Frontend Foundation and Navigation

**Files:**
- Create: `web/src/app/*`
- Create: `web/src/components/*`
- Create: `web/src/lib/api-client.ts`

- [ ] Implement app shell with role-aware navigation.
- [ ] Implement dashboard route and baseline widgets.
- [ ] Implement run history route and detail route skeletons.
- [ ] Implement API client and query caching strategy.

### Task 6: Run Builder + Command Transparency UX

**Files:**
- Create/Modify: run builder pages/components

- [ ] Build preset selector (`doctor`, `full`, `audit`, etc.).
- [ ] Build advanced flags editor for suite/scenario/load options.
- [ ] Show generated command preview before submission.
- [ ] Add validation warnings/errors for incompatible combinations.
- [ ] Add save/clone profile actions.

### Task 7: Live Monitoring UX

**Files:**
- Create/Modify: live run pages/components

- [ ] Implement live log stream panel.
- [ ] Implement status timeline/scenario progress panel.
- [ ] Implement key counters (orders, websocket matches, issues).
- [ ] Implement stop/cancel run action and feedback.
- [ ] Handle reconnect logic for stream interruptions.

### Task 8: Artifact Explorer UX

**Files:**
- Create/Modify: report/story/events pages/components

- [ ] Implement markdown rendering for report and story.
- [ ] Implement events table explorer with filters/search.
- [ ] Implement drill-down event modal for payload/response details.
- [ ] Implement download/export actions for all artifacts.

### Task 9: Dashboard and Analytics UX

**Files:**
- Create/Modify: dashboard pages/components/charts

- [ ] Build daily health summary cards.
- [ ] Build bottleneck endpoint charts and trends.
- [ ] Build failure-type and scenario-verdict trend views.
- [ ] Add run-to-run comparison widgets.

### Task 10: Authentication and Authorization

**Files:**
- Create/Modify: auth models/routes/middleware + frontend guards

- [ ] Implement login/session or JWT flows.
- [ ] Implement RBAC (`admin`, `operator`, `viewer`).
- [ ] Protect sensitive routes/actions by role.
- [ ] Add audit logs for high-impact actions.

### Task 11: Alerting and Notifications

**Files:**
- Create/Modify: alert models/routes/worker notifiers

- [ ] Implement alert rule definitions (severity, trigger conditions).
- [ ] Implement delivery integration(s): Slack/email/webhook as approved.
- [ ] Implement retry and failure visibility for alert delivery.

### Task 12: Production Deployment and Hardening

**Files:**
- Modify/Create: `docker-compose.yml`, `infra/nginx/nginx.conf`, deployment docs

- [ ] Configure Nginx reverse proxy with TLS and websocket/SSE upgrades.
- [ ] Configure persistent volumes and backup routines.
- [ ] Configure environment secret handling and startup checks.
- [ ] Add retention cleanup jobs and safety limits.
- [ ] Validate deployment on Contabo VPS.

### Task 13: Verification and Launch Readiness

**Files:**
- Create/Modify: test suites and runbooks

- [ ] Run backend unit/integration tests.
- [ ] Run frontend component/e2e tests.
- [ ] Execute pilot runs from GUI (`doctor`, `full`, load sample).
- [ ] Verify artifacts consistency against CLI-only baseline.
- [ ] Produce operator runbook and admin maintenance runbook.

### Task 14 (Optional, Scale-Out): Distributed Queue Upgrade

**Files:**
- Create: `worker/`
- Modify: `docker-compose.yml`, `api` run dispatch modules

- [ ] Add Celery worker service.
- [ ] Add Redis queue/pub-sub service.
- [ ] Move execution dispatch from in-process to distributed queue.
- [ ] Re-run reliability and throughput tests.

### Required User Decisions Before Task 1 Implementation

- [ ] Confirm auth model: local auth only vs SSO-ready abstraction now.
- [ ] Confirm alert channels for v1.
- [ ] Confirm artifact retention window and cleanup policy.
- [ ] Confirm artifact storage backend: local volume vs S3-compatible now.
- [ ] Confirm max parallel runs and scheduling overlap policy.
- [x] Confirm queue strategy for v1: keep in-process executor (Celery/Redis deferred).
