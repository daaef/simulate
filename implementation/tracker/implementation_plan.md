# Implementation Plan

## Problem Statement

The current simulator web layer has grown from an MVP into a product surface that now needs stronger structure. Auth is still shaped like a frontend-held token shell, the main page carries too many responsibilities, and new requirements such as single-session auth, protected route groups, scheduling, campaign orchestration, archives, retention, and auditability cannot be cleanly layered onto the existing single-page design.

## Target Behavior

- A dedicated `/auth/login` entry point protects a route-first operations platform.
- Authentication is backend-owned through secure cookie sessions with single active session enforcement.
- Protected app routes are split into `/overview`, `/runs`, `/runs/[id]`, `/schedules`, `/archives`, `/retention`, and `/admin/users`.
- `/overview` is the monitoring-first landing page.
- Runs can be launched from saved profiles, inspected in focused detail pages, rerun from definitions, or rerun from exact immutable execution snapshots.
- Schedules support both simple recurring profiles and advanced campaign-style orchestration through structured builders only.
- Runs follow an explicit lifecycle: `30 days active`, `180 days archived`, then raw artifact purge with retained operational summary.
- Roles `admin`, `operator`, `viewer`, and `auditor` are enforced on the backend.

## Existing Behavior

- Simulator execution, orchestration, and validation are implemented in Python CLI modules.
- The web control plane exists, but the main dashboard route still acts as launcher, console, charts, guide, report reader, events explorer, and admin surface at once.
- Auth has been introduced, but the product structure still reflects the older MVP shape rather than the approved operations-platform model.
- Artifact rendering, monitoring charts, and control-plane basics exist and should be reused where they remain valid.

## Proposed Approach

Redesign the current web control plane in staged slices while keeping the simulator engine intact:

1. Keep Python simulator modules as the execution core.
2. Move auth/session/RBAC into first-class backend-owned subsystems.
3. Replace the single-page UI model with a protected app shell and route-specific pages.
4. Add saved profiles, structured schedules, and campaign orchestration as platform entities.
5. Add archive/retention lifecycle support and retained summaries without changing simulator run semantics.
6. Preserve the current stack: `Next.js + FastAPI + Docker + Nginx`, with APScheduler and no Celery/Redis in v1.

Recommended stack:

- Frontend: Next.js App Router + TypeScript + chart-based operations UI.
- Backend API: FastAPI + service-split routing + auth/session policy layer.
- Queue/Scheduler: In-process task runner + APScheduler.
- Data: Postgres-first operational metadata, keeping SQLite compatibility only where already necessary during migration.
- Artifacts: local volume in v1 with explicit archive/purge lifecycle.

## Architecture / Design Notes

- Auth/session model:
  - server-managed `httpOnly` sessions,
  - single active session per user,
  - backend-enforced RBAC,
  - no silent compatibility fallback for protected routes.
- Route model:
  - public auth route group,
  - protected app shell,
  - overview/runs/schedules/archives/retention/admin route families.
- Run model:
  - `/runs` for execution/history workspace,
  - `/runs/[id]` for forensic detail with tabs,
  - immutable execution snapshots for exact reruns.
- Schedule model:
  - `Simple Schedule` for one saved profile on cadence,
  - `Campaign Schedule` for ordered multi-step orchestration with repeat/spacing/failure policy.
- Retention model:
  - active -> archived -> raw-purged with retained summary and narrative.
- Deployment model:
  - Docker Compose and Nginx remain valid,
  - session cookie and reverse-proxy behavior must be aligned explicitly.

## Files to Modify

| File | Purpose of Change |
|---|---|
| `docs/superpowers/specs/2026-05-06-simulator-operations-platform-redesign.md` | Approved redesign spec |
| `docs/superpowers/plans/2026-05-06-simulator-operations-platform-redesign.md` | Execution-ready phased redesign plan |
| `implementation/tracker/README.md` | Update project goal/scope/status for web planning |
| `implementation/tracker/implementation_plan.md` | Canonical technical plan for redesign effort |
| `implementation/tracker/tasks.md` | Task board for pending implementation phases |
| `implementation/tracker/session_log.md` | Chronological planning and handoff record |
| `api/app/main.py` | To be reduced to app composition/bootstrap |
| `api/app/auth/` | New auth/session/permission subsystem |
| `api/app/runs/` | Run, profile, and execution snapshot routes/services |
| `api/app/schedules/` | Schedule and campaign routes/services |
| `api/app/archives/` | Archive browsing and jobs |
| `api/app/retention/` | Retention policy and purge lifecycle |
| `web/src/app/` | Route-first App Router surfaces |
| `web/src/components/` | Shared app-shell, runs, overview, schedules, archives, retention, admin components |
| `docker-compose.yml` | Service/deployment alignment |
| `infra/nginx/nginx.conf` | Reverse proxy + secure session alignment |

## Implementation Steps

1. Freeze redesign boundaries in docs/tracker and prevent drift.
2. Split backend into auth/runs/schedules/archives/retention/admin route groups.
3. Replace frontend-held token ownership with backend-owned cookie sessions.
4. Implement backend-enforced RBAC and session replacement behavior.
5. Introduce protected app shell and route-first navigation.
6. Migrate the current dashboard into focused `/runs` and `/runs/[id]` experiences.
7. Build monitoring-first `/overview`.
8. Add saved profiles, simple schedules, campaign schedules, and exact execution snapshots.
9. Implement active/archive/purge lifecycle and retained summaries.
10. Separate archives and retention governance UX.
11. Finish admin user lifecycle and in-app alerts.
12. Validate, cut over from old single-page dashboard, and harden deployment behavior.

## Testing Strategy

- Unit tests:
  - auth/session replacement,
  - permission enforcement,
  - schedule validation,
  - campaign failure policy,
  - archive summary generation,
  - retention lifecycle rules.
- Integration tests:
  - login/logout/protected routes,
  - run launch and exact rerun,
  - schedule-triggered runs,
  - archive/purge jobs,
  - alert creation.
- Manual tests:
  - login redirect flow,
  - `/overview` landing,
  - `/runs` launch/history flow,
  - `/runs/[id]` inspection,
  - simple schedule and campaign schedule flows,
  - archive and retention browsing.
- Edge cases:
  - new login invalidates previous session,
  - degraded campaign continues later steps,
  - retained summary still useful after raw purge,
  - old dashboard path can be retired cleanly after parity.

## Rollback Strategy

- Keep the simulator CLI unchanged and callable directly.
- Introduce the new app shell incrementally; do not remove the old page until parity is reached.
- Use reversible migrations for new auth/session/schedule/archive tables.
- Gate raw-artifact purge behavior behind explicit configuration until verified.
- Keep Nginx/session changes reversible and versioned.

## Acceptance Criteria

- [ ] Authentication is backend-owned, cookie-based, and enforces a single active session per user.
- [ ] Protected operational routes live behind a proper app shell with `/auth/login` as the only public entry path.
- [ ] `/overview` functions as the monitoring-first landing page.
- [ ] `/runs` and `/runs/[id]` replace the current overloaded run surface.
- [ ] Saved profiles, simple schedules, and campaign schedules are all supported through structured UI.
- [ ] Exact-execution reruns are supported through immutable execution snapshots.
- [ ] Runs follow the approved `30 days active / 180 days archived / raw purge with retained summary` lifecycle.
- [ ] `admin`, `operator`, `viewer`, and `auditor` roles are enforced on the backend.
- [ ] In-app alerts surface operational and governance issues.
- [ ] The redesigned platform remains Dockerized and deployable behind Nginx without Celery/Redis in v1.

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
