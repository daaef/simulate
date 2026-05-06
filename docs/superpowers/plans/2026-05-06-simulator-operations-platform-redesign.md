# Simulator Operations Platform Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the current simulator web control plane into a secure, route-first operations platform with server-managed auth, protected app shell, overview-first UX, structured scheduling, campaign orchestration, and archive/retention lifecycle controls.

**Architecture:** Keep the current `Next.js + FastAPI + Docker + Nginx` stack and the existing simulator CLI execution core, but restructure the product around backend-owned sessions, normalized operational metadata, dedicated route groups, and separate surfaces for overview, runs, schedules, archives, retention, and admin. Implement in staged slices so each stage leaves the system running and testable.

**Tech Stack:** Next.js App Router, React, FastAPI, PostgreSQL, SQLite compatibility where already present, APScheduler, Docker Compose, Nginx, cookie-based sessions, RBAC middleware, markdown artifact rendering, chart-based monitoring UI.

---

### Task 1: Freeze Product Boundaries and Remove Design Drift

**Files:**
- Modify: `implementation/tracker/README.md`
- Modify: `implementation/tracker/implementation_plan.md`
- Modify: `implementation/tracker/tasks.md`
- Modify: `ARCHITECTURE.md`
- Reference: `docs/superpowers/specs/2026-05-06-simulator-operations-platform-redesign.md`

- [ ] Update tracker goal and status so the canonical target is the operations-platform redesign, not the older generic web-GUI MVP.
- [ ] Update `implementation/tracker/implementation_plan.md` to summarize the approved decisions:
  - admin-created users only,
  - single active session,
  - cookie-based sessions,
  - route-first app shell,
  - `/overview` landing,
  - `Simple Schedule` plus `Campaign Schedule`,
  - `30 days active / 180 days archived / raw purge`.
- [ ] Add a concise redesign note to `ARCHITECTURE.md` so future implementation does not accidentally continue the single-page dashboard pattern.
- [ ] Verify no plan/doc contradiction remains between:
  - `docs/superpowers/specs/2026-05-02-simulator-web-gui-platform-design.md`
  - `docs/superpowers/specs/2026-05-06-simulator-operations-platform-redesign.md`
  - this plan file.

### Task 2: Establish Backend Domain Boundaries

**Files:**
- Create: `api/app/auth/__init__.py`
- Create: `api/app/auth/models.py`
- Create: `api/app/auth/routes.py`
- Create: `api/app/auth/service.py`
- Create: `api/app/auth/session_store.py`
- Create: `api/app/runs/routes.py`
- Create: `api/app/runs/service.py`
- Create: `api/app/schedules/routes.py`
- Create: `api/app/schedules/service.py`
- Create: `api/app/archives/routes.py`
- Create: `api/app/archives/service.py`
- Create: `api/app/retention/routes.py`
- Create: `api/app/retention/service.py`
- Create: `api/app/admin/routes.py`
- Modify: `api/app/main.py`

- [ ] Split `api/app/main.py` routing responsibilities into explicit modules:
  - auth,
  - runs,
  - schedules,
  - archives,
  - retention,
  - admin.
- [ ] Keep `main.py` as composition/bootstrap only:
  - app creation,
  - middleware wiring,
  - route inclusion,
  - health endpoints.
- [ ] Define service boundaries so route handlers stay thin and operational rules live in service modules.
- [ ] Preserve the current simulator execution behavior while moving orchestration code behind these modules instead of rewriting the engine.

### Task 3: Replace Frontend-Held Tokens with Backend-Owned Sessions

**Files:**
- Create: `api/app/auth/cookies.py`
- Create: `api/app/auth/dependencies.py`
- Modify: `api/auth.py`
- Modify: `api/app/main.py`
- Modify: `web/src/contexts/AuthContext.tsx`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/components/AuthGuard.tsx`

- [ ] Replace `localStorage` access-token ownership in [AuthContext.tsx](/Users/mars/FAINZY/simulate/web/src/contexts/AuthContext.tsx) with a session-status model:
  - login request,
  - logout request,
  - current-session fetch,
  - loading/expired/session-replaced states.
- [ ] Move token/session truth to `httpOnly` cookies issued by the backend.
- [ ] Implement single active session logic:
  - a new login invalidates the prior session,
  - backend records replacement,
  - old session gets rejected consistently.
- [ ] Remove compatibility behavior that silently weakens auth for protected surfaces.
- [ ] Keep one explicit exception only if still required:
  - clearly documented unauthenticated dev/health endpoints.

### Task 4: Build RBAC as a Backend-Enforced Policy Layer

**Files:**
- Create: `api/app/auth/permissions.py`
- Create: `api/app/auth/policies.py`
- Modify: `api/app/auth/routes.py`
- Modify: `api/app/admin/routes.py`
- Modify: `web/src/contexts/RoleContext.tsx`
- Modify: `web/src/components/RoleBasedComponent.tsx`
- Modify: `web/src/components/AdminDashboard.tsx`

- [ ] Normalize the approved roles:
  - `admin`,
  - `operator`,
  - `viewer`,
  - `auditor`.
- [ ] Define backend permission checks for:
  - launch run,
  - cancel run,
  - manage schedule,
  - manage retention,
  - manage users,
  - view archive,
  - inspect execution snapshot.
- [ ] Keep the frontend role context as presentation logic only.
- [ ] Ensure every mutating API route uses server-side permission checks even if the UI already hides the action.
- [ ] Add an audit trail for:
  - login,
  - logout,
  - session replacement,
  - run launch,
  - run cancel,
  - schedule create/update/pause/disable,
  - user create/disable/restore.

### Task 5: Introduce Route-First App Shell

**Files:**
- Create: `web/src/app/auth/login/page.tsx`
- Create: `web/src/app/(app)/layout.tsx`
- Create: `web/src/app/(app)/overview/page.tsx`
- Create: `web/src/app/(app)/runs/page.tsx`
- Create: `web/src/app/(app)/runs/[id]/page.tsx`
- Create: `web/src/app/(app)/schedules/page.tsx`
- Create: `web/src/app/(app)/archives/page.tsx`
- Create: `web/src/app/(app)/retention/page.tsx`
- Create: `web/src/app/(app)/admin/users/page.tsx`
- Create: `web/src/components/app-shell/*`
- Modify: `web/src/app/layout.tsx`
- Modify: `web/src/app/page.tsx`

- [ ] Stop treating `web/src/app/page.tsx` as the permanent product surface.
- [ ] Convert `/` into either:
  - a redirect to `/overview` when authenticated,
  - a redirect to `/auth/login` when not authenticated.
- [ ] Build a protected app layout with:
  - persistent navigation,
  - top command/action bar,
  - alert center slot,
  - user/session menu.
- [ ] Move login into its own route at `/auth/login`.
- [ ] Keep the existing page available only as a temporary migration surface during cutover, then retire it once `/overview`, `/runs`, and `/runs/[id]` reach feature parity.

### Task 6: Split the Current Dashboard into Focused Run Surfaces

**Files:**
- Create: `web/src/components/runs/RunTable.tsx`
- Create: `web/src/components/runs/RunFilters.tsx`
- Create: `web/src/components/runs/RunLaunchPanel.tsx`
- Create: `web/src/components/runs/RunStatusBadges.tsx`
- Create: `web/src/components/runs/RunDetailTabs.tsx`
- Create: `web/src/components/runs/RunSummaryTab.tsx`
- Create: `web/src/components/runs/RunTimelineTab.tsx`
- Create: `web/src/components/runs/RunLogsTab.tsx`
- Create: `web/src/components/runs/RunApiWsTab.tsx`
- Create: `web/src/components/runs/RunArtifactsTab.tsx`
- Create: `web/src/components/runs/RunExecutionSnapshotTab.tsx`
- Modify: `web/src/app/(app)/runs/page.tsx`
- Modify: `web/src/app/(app)/runs/[id]/page.tsx`
- Modify: `web/src/lib/api.ts`

- [ ] Treat `/runs` as execution/history workspace:
  - filterable run table,
  - quick launch entry,
  - rerun actions,
  - retention-state visibility.
- [ ] Treat `/runs/[id]` as forensic detail surface with approved tab structure:
  - Summary,
  - Timeline,
  - Logs,
  - API & WebSocket,
  - Report,
  - Story,
  - Actors,
  - Execution Snapshot,
  - Retention.
- [ ] Move the current mixed inspector logic out of the monolithic page and into route-scoped components with clearer responsibility.
- [ ] Preserve all currently valuable artifact rendering behavior while reorganizing ownership.

### Task 7: Build the Overview as a Monitoring Cockpit

**Files:**
- Create: `web/src/components/overview/OverviewSummaryBand.tsx`
- Create: `web/src/components/overview/IncidentQueue.tsx`
- Create: `web/src/components/overview/TrendPanels.tsx`
- Create: `web/src/components/overview/AttentionCards.tsx`
- Create: `web/src/components/overview/StorageAndRetentionPanel.tsx`
- Modify: `web/src/app/(app)/overview/page.tsx`
- Modify: `api/app/runs/service.py`
- Modify: `api/app/archives/service.py`
- Modify: `api/app/retention/service.py`

- [ ] Build `/overview` around action-first monitoring, not generic dashboard cards.
- [ ] Add top-band metrics:
  - platform health,
  - active runs,
  - active schedules,
  - degraded campaigns,
  - failures last 24h,
  - archive backlog,
  - purge queue status.
- [ ] Add incident/attention sections for:
  - failed runs,
  - paused schedules,
  - degraded campaigns,
  - retention issues,
  - session/auth anomalies.
- [ ] Add trend views for:
  - success rate,
  - latency,
  - top failing flows,
  - archive/storage growth.
- [ ] Ensure `/overview` answers "what needs attention now?" inside one screen.

### Task 8: Introduce Saved Profiles and Structured Launch Boundaries

**Files:**
- Create: `api/app/runs/profile_models.py`
- Create: `api/app/runs/profile_routes.py`
- Create: `web/src/components/profiles/*`
- Modify: `web/src/components/runs/RunLaunchPanel.tsx`
- Modify: `web/src/lib/api.ts`

- [ ] Add saved run profiles as first-class entities separate from one-off run launches.
- [ ] Support:
  - create,
  - clone,
  - edit,
  - disable,
  - launch now.
- [ ] Keep quick-launch UX, but anchor advanced usage around reusable profiles.
- [ ] Ensure saved profiles are the building block for schedules and campaigns, not duplicated configuration forms.

### Task 9: Implement Simple Schedules with Structured Builder UX

**Files:**
- Create: `web/src/components/schedules/SimpleScheduleBuilder.tsx`
- Create: `web/src/components/schedules/ScheduleFormShared.tsx`
- Create: `web/src/components/schedules/ScheduleList.tsx`
- Create: `web/src/components/schedules/ScheduleHistory.tsx`
- Modify: `web/src/app/(app)/schedules/page.tsx`
- Modify: `api/app/schedules/routes.py`
- Modify: `api/app/schedules/service.py`

- [ ] Implement `Simple Schedule` as one saved profile on a cadence.
- [ ] Use preset-first UX:
  - hourly,
  - daily,
  - weekdays,
  - weekly,
  - monthly,
  - custom.
- [ ] Expose advanced structured controls without raw cron:
  - timezone,
  - active date range,
  - allowed run windows,
  - blackout periods.
- [ ] Add manual trigger, pause, resume, disable, and soft delete/restore controls.

### Task 10: Implement Campaign Schedules and Execution Policy

**Files:**
- Create: `api/app/schedules/campaign_models.py`
- Create: `api/app/schedules/campaign_routes.py`
- Create: `web/src/components/schedules/CampaignBuilder.tsx`
- Create: `web/src/components/schedules/CampaignStepEditor.tsx`
- Modify: `web/src/app/(app)/schedules/page.tsx`
- Modify: `api/app/schedules/service.py`

- [ ] Add `Campaign Schedule` as an advanced schedule type.
- [ ] Each campaign step should store:
  - profile reference,
  - repeat count,
  - spacing interval,
  - timeout,
  - failure policy,
  - execution snapshot behavior.
- [ ] Default failure policy should be:
  - continue remaining steps,
  - mark campaign degraded.
- [ ] Make failure behavior configurable per campaign while keeping the default opinionated.
- [ ] Ensure schedule history distinguishes:
  - simple schedule runs,
  - campaign executions,
  - degraded-but-complete campaigns.

### Task 11: Add Exact-Execution Snapshots and Replay

**Files:**
- Create: `api/app/runs/execution_snapshot.py`
- Modify: `api/app/runs/service.py`
- Modify: `api/app/schedules/service.py`
- Modify: `web/src/components/runs/RunExecutionSnapshotTab.tsx`
- Modify: `web/src/components/runs/RunTable.tsx`

- [ ] Persist immutable execution snapshots per completed run.
- [ ] Support two replay actions:
  - rerun saved definition,
  - rerun exact execution.
- [ ] Make exact rerun clearly labeled as the forensic/debug path.
- [ ] Ensure snapshots survive archive state until raw-purge rules say otherwise.

### Task 12: Implement Archive Lifecycle and Retained Summary Model

**Files:**
- Create: `api/app/archives/models.py`
- Create: `api/app/archives/jobs.py`
- Create: `api/app/retention/models.py`
- Create: `web/src/components/archives/*`
- Create: `web/src/components/retention/*`
- Modify: `api/app/runs/service.py`
- Modify: `reporting.py`

- [ ] Introduce explicit run lifecycle states:
  - active,
  - archived,
  - raw-purged with retained summary.
- [ ] Implement the approved policy:
  - 30 days active,
  - 180 days archived,
  - then raw artifact purge.
- [ ] Precompute retained summary content before purge:
  - verdict,
  - flow,
  - schedule/campaign source,
  - actor summary,
  - key timing,
  - aggregated latency,
  - top failure signals,
  - short narrative summary.
- [ ] Ensure purge removes raw-heavy artifacts without destroying historical operational meaning.

### Task 13: Separate Archives and Retention Governance UX

**Files:**
- Modify: `web/src/app/(app)/archives/page.tsx`
- Modify: `web/src/app/(app)/retention/page.tsx`
- Modify: `web/src/components/archives/*`
- Modify: `web/src/components/retention/*`

- [ ] Build `/archives` as a searchable historical browsing surface:
  - archived runs,
  - retained summaries,
  - historical comparison,
  - replay actions where available.
- [ ] Build `/retention` as an admin governance surface:
  - policy view,
  - archive backlog,
  - purge queue,
  - storage pressure,
  - restore controls for soft-deleted schedules and users only.
- [ ] Keep these pages separate in navigation and mental model.

### Task 14: Complete Admin User Lifecycle

**Files:**
- Modify: `api/app/auth/routes.py`
- Modify: `api/auth.py`
- Modify: `web/src/components/AdminDashboard.tsx`
- Create: `web/src/components/admin/UserTable.tsx`
- Create: `web/src/components/admin/UserEditor.tsx`
- Create: `web/src/components/admin/RoleBadge.tsx`
- Modify: `web/src/app/(app)/admin/users/page.tsx`

- [ ] Support admin-created users only.
- [ ] Add soft delete/restore for users in UI.
- [ ] Keep signup unavailable in public routes.
- [ ] Make single-session enforcement visible enough for admins to reason about session replacement behavior.
- [ ] Ensure admin UX focuses on safe lifecycle operations, not generic account features.

### Task 15: Add In-App Alerts as a Product Surface

**Files:**
- Create: `api/app/alerts/models.py`
- Create: `api/app/alerts/routes.py`
- Create: `api/app/alerts/service.py`
- Create: `web/src/components/alerts/*`
- Modify: `web/src/app/(app)/layout.tsx`
- Modify: `web/src/app/(app)/overview/page.tsx`

- [ ] Implement in-app alert generation for:
  - failed runs,
  - degraded campaigns,
  - paused critical schedules,
  - retention backlog/purge failures,
  - session/auth anomalies.
- [ ] Add a visible alert center in the protected shell.
- [ ] Keep email alert design out of v1 implementation, but add a repo-wide documentation note describing the future extension point.

### Task 16: Production Hardening and Deployment Alignment

**Files:**
- Modify: `docker-compose.yml`
- Modify: `infra/nginx/nginx.conf`
- Modify: `api/Dockerfile`
- Modify: `web/Dockerfile`
- Create: `README.md` sections or `docs/reference/*`

- [ ] Align Docker/Nginx config with the new route/session model.
- [ ] Ensure cookie security settings work correctly behind Nginx.
- [ ] Add startup validation for auth/session configuration.
- [ ] Verify websocket/SSE/live-monitoring behavior still works through the new shell and routing structure.
- [ ] Document local and VPS bring-up for the redesigned platform.

### Task 17: Verification, Migration Cutover, and Cleanup

**Files:**
- Modify: `tests/*`
- Modify: `web/src/app/page.tsx`
- Modify: `implementation/tracker/*`
- Modify: `SIMULATOR_GUIDE.md`

- [ ] Add backend tests for:
  - session replacement,
  - RBAC enforcement,
  - schedule execution rules,
  - archive/purge lifecycle,
  - exact rerun snapshots.
- [ ] Add frontend tests for:
  - auth redirect flow,
  - protected shell,
  - runs table/detail navigation,
  - schedule builder,
  - archive and retention pages.
- [ ] Perform manual end-to-end checks:
  - login,
  - launch run,
  - view run detail,
  - create simple schedule,
  - create campaign schedule,
  - pause/resume/disable,
  - archive browsing,
  - retained-summary view.
- [ ] Decommission the old single-page dashboard path once feature parity is achieved.
- [ ] Update operator/developer documentation for the new information architecture.

## Testing Strategy

- Unit tests:
  - auth/session replacement,
  - cookie/session helpers,
  - RBAC policy checks,
  - schedule rule validation,
  - campaign execution policy,
  - archive summary generation,
  - purge eligibility.
- Integration tests:
  - protected-route API access,
  - login/logout/session invalidation,
  - run launch and replay,
  - schedule-triggered execution,
  - archive/purge jobs,
  - alert creation.
- Manual tests:
  - login redirect and logout flow,
  - overview-first landing,
  - run launch from `/runs`,
  - run forensic inspection at `/runs/[id]`,
  - simple and campaign schedule creation,
  - archived run browsing,
  - soft-delete/restore of schedules and users.
- Edge cases:
  - login from second browser invalidates first,
  - rerun exact execution after schedule definition has changed,
  - campaign degradation with continued downstream steps,
  - archive summary available after raw artifact purge,
  - retention backlog visible when purge job fails.

## Rollback Strategy

- Keep the simulator CLI and existing execution core unchanged throughout the redesign.
- Introduce the new app shell and routes incrementally; do not delete the old single-page surface until the new route set is working.
- Use reversible DB migrations for new auth/session/schedule/archive tables.
- Gate destructive retention behavior behind explicit configuration until verified.
- Keep route migration behind predictable redirects so users can be moved gradually.

## Acceptance Criteria

- [ ] Authentication is backend-owned, cookie-based, and enforces a single active session per user.
- [ ] Protected operational routes live behind a proper app shell and `/auth/login` is the only public entry path.
- [ ] `/overview` functions as the monitoring-first landing page.
- [ ] `/runs` and `/runs/[id]` replace the current overloaded single-page run UX.
- [ ] Saved profiles support both direct execution and schedule reuse.
- [ ] `Simple Schedule` and `Campaign Schedule` are both supported through structured builders only.
- [ ] Exact-execution reruns are supported through immutable execution snapshots.
- [ ] Archived and raw-purged runs retain meaningful operational summaries.
- [ ] `/archives` and `/retention` are separate role-aware surfaces.
- [ ] `admin`, `operator`, `viewer`, and `auditor` roles are enforced on the backend.
- [ ] In-app alerts surface operational failures and governance issues.
- [ ] The redesigned platform remains Dockerized and deployable behind Nginx without introducing Celery/Redis in v1.
