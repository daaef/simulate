# Simulator Operations Platform Redesign

## Objective

Redesign the current simulator web control plane into a production-grade operations platform with strong authentication, server-enforced RBAC, route-first information architecture, top-tier monitoring UX, structured scheduling, campaign orchestration, and controlled retention/archive lifecycle behavior.

This design replaces the current "single large dashboard page with frontend-held auth state" direction with a proper application shell and backend-owned session model.

## Why This Redesign Is Needed

The current implementation has outgrown its original structure:

- authentication is layered onto the app instead of defining the app boundary,
- the main dashboard route carries too many responsibilities,
- execution, monitoring, admin, guide, and artifact reading are mixed into one page,
- retention, archival, and scheduling are now first-class product requirements,
- the system needs stronger operational auditability than the current frontend-token model provides.

For the next phase, the right move is not to keep extending the current page. The right move is to preserve the stack and rebuild the product structure around clear route, role, and lifecycle boundaries.

## Scope

In scope:

- closed-ops authentication model with admin-created users only,
- single active session per user,
- server-managed cookie sessions,
- four-role RBAC model,
- dedicated auth route group and protected app shell,
- overview/runs/schedules/archives/retention/admin information architecture,
- schedule builder and campaign orchestration model,
- active/archive/purge lifecycle for runs,
- retained summary model after raw artifact purge,
- in-app alerts,
- exact-execution rerun design,
- implementation sequencing recommendations for the current codebase.

Out of scope for this redesign:

- public signup,
- email alerts in v1,
- SSO in v1,
- raw cron entry UI,
- private per-user workspaces,
- multi-region or distributed queue architecture.

## Approved Product Decisions

These decisions are treated as locked for the implementation plan:

- Product type: proper multi-user ops product.
- User creation: username/password with admin-created users only.
- Session model: single active session per user.
- Roles: `admin`, `operator`, `viewer`, `auditor`.
- Auth entry: separate auth route, not inline login inside the main app route.
- Session ownership: server-managed `httpOnly` cookie sessions with refresh rotation.
- Post-login landing: `Operations Overview`, not the runs table.
- Scheduling UX: preset-first with advanced structured builder only.
- Schedule types: `Simple Schedule` and `Campaign Schedule`.
- Campaign failure behavior: configurable per campaign, recommended default is continue remaining steps and mark degraded.
- Notifications in v1: in-app alerts only.
- Visibility model: organization-wide visibility with role-based action control.
- User and schedule deletion: soft delete with restore from UI.
- Run retention: `30 days active`, `180 days archived`, then purge raw artifacts while keeping retained summary data.
- Archive summary: both structured metrics and short narrative summary retained.
- Archive governance: separate `Archives` and `Retention Policies` surfaces.
- Rerun behavior: both `rerun saved definition` and `rerun exact execution`.
- Schedule control: manual trigger, pause/resume, disable.
- Timezone model: per-schedule timezone with platform default.

## Approaches Considered

### Approach A: Keep Extending the Current Single-Page Dashboard

Pros:

- lowest immediate code churn,
- fastest path to ship small fixes.

Cons:

- keeps weak route and auth boundaries,
- worsens page complexity,
- makes scheduling, archives, retention, and admin harder to isolate,
- increases long-term maintenance cost.

### Approach B (Recommended): Route-First Redesign on the Existing Stack

Pros:

- preserves `Next.js + FastAPI + Docker + Nginx`,
- fixes the actual structural problems,
- supports secure auth and top-tier operations UX,
- allows incremental implementation without rewriting the simulator engine.

Cons:

- requires deliberate migration of current page and auth boundaries,
- needs data-model cleanup before advanced features feel coherent.

### Approach C: Full Backend/Frontend Rewrite Before Further Product Work

Pros:

- strongest architectural reset,
- maximum control over long-term layering.

Cons:

- highest delivery cost,
- slows practical progress,
- unnecessary while the current stack is still viable.

Recommendation: Approach B.

## Information Architecture

### Public Auth Area

Public routes:

- `/auth/login`

V1 intentionally excludes public signup and public recovery flows.

Purpose:

- keep authentication isolated from operational content,
- establish a clean entry boundary for admin-created users,
- remove login-state branching from the main application route.

### Protected Application Shell

Protected routes:

- `/overview`
- `/runs`
- `/runs/[id]`
- `/schedules`
- `/archives`
- `/retention`
- `/admin/users`

Optional later routes:

- `/admin/roles`
- `/admin/audit`
- `/settings`

The protected shell should provide:

- persistent left navigation,
- page-level action bar,
- breadcrumbs,
- session/user menu,
- global alert center,
- consistent role-aware action controls.

### Default Landing

Users land on `/overview` after login.

Reason:

- this is now an operations platform first,
- the first screen should answer "what needs attention now?",
- launching runs should be reachable quickly but should not be the home concept.

## Auth and Security Design

## Backend-Owned Sessions

The system should move away from frontend-held tokens in `localStorage`.

Target model:

- server issues `httpOnly`, secure session cookies,
- session rotation happens server-side,
- refresh/session invalidation is owned by the backend,
- frontend reads session status from authenticated API responses instead of trusting browser-stored auth claims.

Reason:

- safer against browser-side credential theft,
- cleaner for single-session enforcement,
- more reliable audit attribution,
- better fit for a serious internal operations platform.

## Single Active Session

Each user can have one active session at a time.

When a user logs in on a new browser or machine:

- the previous session is invalidated,
- the backend records the replacement event,
- future requests from the old session fail and redirect to login.

Reason:

- discourages account sharing,
- strengthens session ownership,
- simplifies investigations and security response.

## Authentication Boundary Rules

- protected routes never render operational content without a valid backend session,
- API authorization is enforced on the server for every protected action,
- frontend role context is advisory for UX only and must never be the source of truth,
- there is no compatibility fallback that silently weakens protection when auth is unavailable.

## Roles and Permission Model

### `admin`

Can:

- create, disable, restore, and manage users,
- launch, cancel, rerun, and manage runs,
- create, edit, pause, disable, restore, and delete schedules,
- manage retention policies,
- browse and restore archives where permitted,
- view all operational and audit data.

### `operator`

Can:

- launch runs,
- rerun saved definitions and exact executions,
- manage schedules and campaigns,
- pause/resume/disable schedules,
- cancel active runs,
- view active, archived, and retained summaries.

Cannot:

- manage users,
- change global retention policy,
- perform admin-only governance actions.

### `viewer`

Can:

- view overview data, active runs, completed runs, reports, stories, events, and schedules.

Cannot:

- launch runs,
- cancel runs,
- modify schedules,
- manage archives or users.

### `auditor`

Can:

- view all operational and historical data,
- access archive summaries and retention results,
- inspect forensic execution snapshots.

Cannot:

- launch runs,
- mutate schedules,
- cancel runs,
- manage users.

Reason to keep `auditor` separate:

- archive and long-term review access often grows into a more specialized permission surface than normal read-only viewing.

## UX Blueprint

## `/overview`

The overview page is the monitoring cockpit.

Primary purpose:

- show operational health,
- highlight what needs action,
- provide short paths into runs, schedules, archives, and retention.

Suggested layout:

1. Top summary band:
   - platform health,
   - active runs,
   - active schedules,
   - degraded campaigns,
   - failures in last 24 hours,
   - archive backlog,
   - purge queue status.
2. Incident/attention section:
   - failed runs,
   - paused schedules,
   - degraded campaigns,
   - session/auth anomalies,
   - retention issues.
3. Trend and distribution section:
   - success rate trend,
   - median/p95 latency,
   - top failing flows,
   - busiest stores/users,
   - storage/archive growth.

This page should answer:

- what is healthy,
- what is broken,
- what needs action now,
- what is getting worse over time.

## `/runs`

The runs page is the execution and history workspace.

Primary elements:

- filter/search toolbar,
- quick launch entry point,
- saved profile entry point,
- dense run table,
- retention state markers,
- action menu for rerun/cancel/open details/archive context.

The table should prioritize:

- status,
- flow type,
- schedule/campaign origin,
- store/user/actor context,
- duration,
- verdict,
- created by,
- created at,
- retention state.

The main runs page should not try to be the forensic detail surface.
Deep inspection belongs in `/runs/[id]`.

## `/runs/[id]`

Recommended tabs:

- `Summary`
- `Timeline`
- `Logs`
- `API & WebSocket`
- `Report`
- `Story`
- `Actors`
- `Execution Snapshot`
- `Retention`

Purpose of each:

- `Summary`: operator-friendly result and key outcomes.
- `Timeline`: state progression and key timestamps.
- `Logs`: raw console/log stream.
- `API & WebSocket`: engineering and audit analysis.
- `Report`: rendered technical report.
- `Story`: simplified narrative artifact.
- `Actors`: resolved user/store/plan identity context.
- `Execution Snapshot`: immutable resolved config that powers exact reruns.
- `Retention`: archive state, purge eligibility, retained summary.

## Schedules and Campaigns

## Schedule Types

### `Simple Schedule`

One saved profile runs on a cadence.

Use for:

- daily doctor,
- weekly full audit,
- targeted recurring smoke tests.

### `Campaign Schedule`

An ordered sequence of profiles with orchestration controls.

Each step includes:

- profile reference,
- resolved execution snapshot capability,
- repeat count,
- spacing interval,
- timeout,
- failure policy.

Use for:

- continuous mixed simulation programs,
- multi-step recurring validation windows,
- business-hour health campaigns.

## Schedule Builder UX

Primary entry should be preset-first:

- hourly,
- daily,
- weekdays,
- weekly,
- monthly,
- custom.

Advanced structured builder expands:

- timezone,
- active date range,
- allowed run windows,
- blackout periods,
- repeat rules,
- spacing between campaign steps,
- execution caps,
- pause/resume,
- disable,
- manual trigger.

Raw cron entry is intentionally excluded.

Reason:

- structured scheduling is safer,
- easier to validate,
- friendlier for non-technical operators,
- still sufficient for the intended platform.

## Campaign Failure Policy

Failure policy must be configurable per campaign.

Recommended default:

- continue remaining steps,
- mark campaign `degraded`,
- surface the failure prominently in alerts and history.

Reason:

- campaigns used for operational coverage should continue collecting evidence even when one step fails.

## Manual and Replay Controls

Every schedule should support:

- manual trigger,
- pause,
- resume,
- disable.

Completed executions should support:

- rerun saved definition,
- rerun exact execution.

Rerun exact execution exists as the forensic/debug option and should be clearly labeled as such.

## Retention, Archive, and Recycling

## Lifecycle Policy

### Active Window

- first 30 days,
- full artifacts available,
- fast access,
- visible in default runs history.

### Archive Window

- days 31 to 180,
- excluded from default active history,
- still queryable,
- acceptable to have slower access if needed.

### Purged Raw Artifact State

- after 180 days,
- raw artifacts are purged,
- retained summary remains,
- narrative summary remains,
- audit and aggregate metadata remain.

## Archive Summary Model

Retained after raw artifact purge:

- verdict,
- flow/run type,
- schedule or campaign source,
- actor/store/user summary,
- duration and key timing,
- aggregated latency metrics,
- counts and top failure signals,
- short human-readable narrative summary,
- audit attribution.

This allows historical review without indefinite raw artifact growth.

## Archive and Retention Screens

### `/archives`

Purpose:

- browse archived runs,
- search retained summaries,
- compare historical behavior,
- rerun saved or exact executions where available.

### `/retention`

Purpose:

- show retention policy,
- show archive queue and purge queue,
- show storage pressure,
- allow admins to monitor or adjust governance behavior.

Reason to separate:

- archive browsing is an operational investigation task,
- retention management is a governance/admin task.

## Deletion and Recovery Model

### Users and Schedules

Deletion should be soft delete with UI restore.

Reason:

- configuration and user lifecycle should stay auditable,
- recovery must be normal product behavior, not a database-only emergency action.

### Runs

Run metadata should not be casually deleted from the product.
Storage control is achieved through archive and purge lifecycle, not routine removal of the historical record.

## Alerts

V1 supports in-app alerts only.

Alert domains should include:

- failed runs,
- degraded campaigns,
- paused or disabled critical schedules,
- retention backlog or purge failures,
- session/auth anomalies,
- infrastructure health problems.

Future email alerts should be documented at repository level as a phase-2 capability, but are not part of this first redesign.

## Data Model Recommendations

Recommended entities:

- `users`
- `roles`
- `role_permissions`
- `user_sessions`
- `run_profiles`
- `schedules`
- `schedule_executions`
- `campaigns`
- `campaign_steps`
- `runs`
- `run_artifacts`
- `run_summaries`
- `retention_policies`
- `archive_jobs`
- `audit_events`
- `in_app_alerts`

Important principle:

- separate queryable operational metadata from large artifact storage,
- precompute retained summaries before raw artifact purge,
- keep immutable execution snapshots for exact reruns.

## Backend Architecture Boundaries

The current `api/app/main.py` should not remain the long-term home for all concerns.

Recommended backend module groups:

- `api/app/auth/`
- `api/app/runs/`
- `api/app/schedules/`
- `api/app/archives/`
- `api/app/retention/`
- `api/app/admin/`
- `api/app/audit/`

The auth subsystem should include:

- session service,
- user service,
- password service,
- permission enforcement,
- login/logout/session-replacement logic.

The simulator engine itself remains the execution core.
The redesign is about product structure and platform boundaries, not replacing simulator semantics.

## Frontend Architecture Boundaries

The current `web/src/app/page.tsx` should be decomposed into route-specific pages and shared app-shell components.

Recommended route families:

- `web/src/app/auth/...`
- `web/src/app/(app)/overview/...`
- `web/src/app/(app)/runs/...`
- `web/src/app/(app)/schedules/...`
- `web/src/app/(app)/archives/...`
- `web/src/app/(app)/retention/...`
- `web/src/app/(app)/admin/...`

Shared frontend modules should include:

- authenticated app shell,
- navigation,
- alert center,
- run tables,
- run detail tabs,
- schedule builders,
- archive explorer,
- role-aware action controls.

## Migration Strategy

Recommended implementation order:

1. Build backend auth/session subsystem and remove weak fallback behavior for protected surfaces.
2. Introduce route-first frontend shell with `/auth/login` and `/overview`.
3. Move the current main page into decomposed `/runs` and `/runs/[id]` surfaces.
4. Introduce saved profiles and structured schedule builder.
5. Add campaign schedule orchestration model.
6. Add archive lifecycle and retained summary model.
7. Add retention governance UI and archive jobs visibility.
8. Add in-app alert center and incident-driven overview polish.

This order is important because:

- auth and route boundaries must exist before deeper operational workflows are layered in,
- retention and archive behavior depend on clear data ownership,
- campaigns and exact reruns depend on stable execution snapshots.

## Risks and Design Guardrails

- Do not preserve the current "everything on one page" structure.
- Do not keep auth truth in frontend `localStorage`.
- Do not expose raw cron as the primary scheduling UX.
- Do not make archive summaries too thin to be operationally useful after purge.
- Do not treat role checks in React as security enforcement.
- Do not make retention policy invisible to admins.

## Success Criteria

- Authentication is a first-class backend boundary with server-managed sessions.
- Operational pages are split into focused routes with clear ownership.
- The app lands on an overview cockpit that surfaces health and attention items immediately.
- Runs, schedules, archives, and retention are separate but connected experiences.
- Campaign scheduling supports structured advanced orchestration without raw cron UX.
- Exact-execution reruns are supported through immutable execution snapshots.
- Archive and purge lifecycle controls storage growth without losing retained operational meaning.
- The platform is materially more secure, more maintainable, and more usable than the current single-page implementation.
