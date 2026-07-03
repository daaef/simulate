# Implementation Plan

## Active Workstream: Orders Numeric Reference Lookup Fix (2026-07-03)

### Problem Statement

The Orders page accepts either a database order id or an order reference, but a bare six-digit reference such as `954460` is currently treated as a database `order_id` first. When the LastMile DB-id endpoint fails or returns a gateway-style error for that non-ID, the request can fail before the intended `#954460` reference lookup is attempted.

### Target Behavior

- Six-digit numeric references are looked up as `reference_code=#<number>` first, scoped to the selected store.
- Short numeric database ids keep the DB-id-first lookup behavior.
- If the reference-first path misses, lookup can still fall back to database id for compatibility.
- Transport/timeouts during lookup return an operator-readable API error instead of an unhandled backend failure.

### Existing Behavior

- `service.fetch_by_query("954460")` calls `fetch_by_numeric_id(954460)` first.
- Only a clean no-result response or `404` from the numeric DB-id path triggers fallback to `#954460`.
- `lookup_order` catches LastMile `HTTPError` but not `URLError`/socket timeout transport failures.

### Proposed Approach

1. Add focused backend tests for six-digit numeric reference routing and lookup transport error mapping.
2. Update `fetch_by_query` to classify six-digit numeric input as reference-like and try `fetch_by_reference("#...")` before DB id.
3. Keep existing DB-id-first behavior for shorter numeric input.
4. Catch lookup transport/timeout exceptions in the route and map them to a clear `504`.
5. Update README and SIMULATOR_GUIDE Orders docs with the clarified numeric-reference behavior.

### Files to Modify (Workstream)

| File | Purpose of Change |
|---|---|
| `api/app/orders/service.py` | Reference-like numeric query routing |
| `api/app/orders/routes.py` | Lookup transport/timeout error handling |
| `tests/test_orders_api.py` | Regression coverage for six-digit references and lookup transport errors |
| `README.md` | Orders page lookup behavior docs |
| `SIMULATOR_GUIDE.md` | Orders route operational reference |

### Acceptance Criteria (Workstream)

- [x] `954460` is looked up as `#954460` before database `order_id=954460`.
- [x] Short numeric DB ids still try database lookup first.
- [x] Reference-first miss can still fall back to database id.
- [x] Lookup transport failures return a clear timeout/retry message.
- [x] Focused backend tests pass.

## Active Workstream: Orders Page Auth and Status Fix (2026-06-03)

### Problem Statement

The partially added orders page has the intended UI shape, but its auth/data boundary is brittle: it logs into Fainzy directly from the browser, depends on service helpers that read environment-backed base URLs/paths, treats numeric lookup input only as a DB id, and exposes an incomplete status list.

### Target Behavior

- `/orders` lets an authenticated simulator operator choose a store from `sim_actors.json`, sign in through the simulator API, and persist the returned Fainzy token in browser `localStorage`.
- The page can look up one input value as DB id, `#reference`, or numeric reference fallback.
- Both order tabs can update to any known lifecycle status.
- No new orders-specific environment variables are introduced.

### Existing Behavior

- `web/src/lib/api.ts` calls `https://fainzy.tech/v1/entities/store/login` directly from the browser.
- `api/app/orders/service.py` reads base URLs and plan paths through environment helper functions.
- Numeric lookup input calls `GET /api/v1/orders/lookup?order_id=...` only.
- The status list omits `payment_processing`, `order_processing`, `ready`, robot transit statuses, and `refunded`.

### Proposed Approach

1. Add API routes for `GET /api/v1/orders/stores` and `POST /api/v1/orders/store-login`.
2. Keep Fainzy token persistence in browser `localStorage`, but acquire it through the simulator API.
3. Normalize lookup into one query string on the API and implement numeric DB-id then `#ref` fallback.
4. Expand lifecycle statuses in shared frontend constants.
5. Update the orders page UI to choose from plan stores before login and reuse the same lookup/update flow in both tabs.
6. Add focused backend/frontend tests and update operator docs.

### Files to Modify (Workstream)

| File | Purpose of Change |
|---|---|
| `api/app/orders/service.py` | Store list, store login proxy, no new env, lookup fallback, lifecycle constants |
| `api/app/orders/routes.py` | New stores/login routes and normalized lookup API |
| `web/src/lib/api.ts` | Orders API types, localStorage token helpers, store login through simulator API, lookup helper |
| `web/src/app/(app)/orders/page.tsx` | Store selection/login UX, full lifecycle statuses, unified lookup behavior |
| `tests/test_orders_api.py` | Backend unit coverage for store list/login/lookup/status auth |
| `web/src/lib/orders-api.test.ts` | Frontend helper coverage for storage and lookup/status constants |
| `README.md` | Orders page user-facing docs |
| `SIMULATOR_GUIDE.md` | Orders route operational reference |

### Acceptance Criteria (Workstream)

- [x] Store list comes from `sim_actors.json` without new env variables.
- [x] Store login sends `Store-Request` and extracts token/subentity metadata.
- [x] Lookup supports DB id, hash reference, and numeric-reference fallback.
- [x] Status update uses `PATCH /v1/core/orders/?order_id=...` with `Fainzy-Token`.
- [x] Missing/stale token returns a clear 401/403 path in UI and API.
- [x] Full lifecycle status list is available in both orders tabs.
- [x] README and SIMULATOR_GUIDE describe the new Orders page.

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

## Active Workstream: Universal Order-Closure + WebSocket-Proof Enforcement (2026-05-28)

### Problem Statement

Current runs can complete with open orders (`pending`/`payment_processing` etc.) and still be marked succeeded when process exit stays zero. This breaks operator trust because runtime outcome does not match user-visible order state.

### Target Behavior

- Every created order in any simulator run (`trace` or `load`) ends terminal as exactly one of:
  - `completed`
  - `rejected`
  - `cancelled`
- Websocket evidence is mandatory for order lifecycle proof from placement to terminal status.
- If any created order remains non-terminal after cleanup attempts, the run exits non-zero and is marked failed.

### Existing Behavior

- Per-scenario checks exist, but global end-of-run terminal-order enforcement is missing.
- Websocket gate/coverage checks can remain warning-level and allow success paths with open orders.
- Payment context can drift when store context mutates across scenarios, causing payment-intent failures and stuck orders.

### Proposed Approach

1. Remove payment reliance on mutable global store context and pass per-order explicit store context (`subentity_id`, currency).
2. Add centralized lifecycle finalization used by both `trace` and `load`:
   - identify created non-terminal orders,
   - wait briefly for natural settle,
   - attempt cleanup (cancel first, reject fallback where valid),
   - re-fetch status and record outcome.
3. Enforce hard terminal guard after cleanup; unresolved non-terminal orders raise `RuntimeError`.
4. Tighten websocket lifecycle proof so missing required order websocket proof is run-failing for order-producing runs.
5. Extend report/story output with explicit unresolved-order and cleanup evidence sections.

### Files to Modify (Workstream)

| File | Purpose of Change |
|---|---|
| `trace_runner.py` | Preserve per-scenario store context and ensure no cross-scenario leakage |
| `user_sim.py` | Pass per-order payment context and support cleanup/re-check primitives |
| `stripe_sim.py` | Accept explicit payment store context instead of implicit globals |
| `store_sim.py` | Reuse patch/fetch status helpers for cleanup/revalidation |
| `__main__.py` | Add shared end-of-run lifecycle finalization + hard terminal guard |
| `websocket_observer.py` | Promote strict websocket lifecycle proof outcomes for order-producing runs |
| `reporting.py` | Add cleanup/unresolved summaries into run artifacts |
| `tests/test_simulate.py` | Regression + lifecycle + websocket strictness coverage |
| `README.md` | Document global terminal-order and websocket-proof contract |
| `SIMULATOR_GUIDE.md` | Document operator semantics and failure behavior |

### Acceptance Criteria (Workstream)

- [ ] All created orders in run artifacts end as `completed`, `rejected`, or `cancelled`; otherwise run fails.
- [ ] Payment intent uses correct store/subentity context after alternate-store/coupon-recovery paths.
- [ ] Websocket lifecycle proof gaps for created orders fail order-producing runs.
- [ ] End-of-run cleanup attempts and unresolved orders are visible in `events.json`, `report.md`, and `story.md`.
- [ ] API run status reflects true failed outcome via non-zero simulator exit.

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

## Follow-on Initiative: Config Tabs + Load Runtime Alignment (2026-05-19)

### Goal

Align Config UX and load-mode runtime behavior with operator expectations while keeping API contracts stable.

### Target Behavior

- `/config` is tabbed: Plans, Email, Integration mappings.
- Default `sim_actors.json` row can be loaded in Config the same way GUI plans can.
- `New` clones the currently loaded plan JSON into a draft.
- Load mode hides trace-only controls and mode override.
- Load mode exposes pace presets (`slow=10s`, `normal=3s`, `fast=1s`) that set interval, with manual override preserved.
- Load worker/user assignment is deterministic:
  - `all_users=false`: one selected/default user reused across `N` workers.
  - `all_users=true`: strict round-robin fill across plan users for exactly `N` workers.
- `SIMULATOR_GUIDE.md` is canonical operator doc; `README.md` is quickstart + links.

### Proposed Design

1. Update Config page composition to tabbed layout and isolate per-tab states.
2. Add backend default-plan load branch for `sim_actors.json` sentinel id/path.
3. Change `New` behavior to clone current editor/source plan content.
4. Simplify launcher visibility by resolved mode and add load pace selector.
5. Apply deterministic worker assignment policy in load orchestration.
6. Add regression tests across API, UI, and runtime semantics.
7. Merge docs ownership model (`SIMULATOR_GUIDE.md` canonical, README reduced).

### Files to Modify

| File | Purpose of Change |
|---|---|
| `docs/superpowers/specs/2026-05-19-config-load-ux-and-runtime-alignment-design.md` | Approved design contract for this initiative |
| `web/src/app/(app)/config/page.tsx` | Tabbed Config UX, load/new semantics |
| `api/app/main.py` | Default `sim_actors` load path handling |
| `web/src/components/runs/RunLaunchPanel.tsx` | Load-only field visibility and pace selector |
| `web/src/lib/run-launcher-config.ts` | Help metadata updates for load-only controls |
| `__main__.py` | Deterministic worker assignment orchestration |
| `user_sim.py` | Worker execution alignment, if assignment logic lives here |
| `tests/test_web_api.py` | Default-plan load and config behavior tests |
| `tests/test_simulate.py` | Load assignment semantics tests |
| `README.md` | Quickstart + links only |
| `SIMULATOR_GUIDE.md` | Canonical operator behavior and load semantics |

### Acceptance Criteria

- [ ] Config tabs exist and preserve existing capabilities.
- [ ] Config can load default `sim_actors.json` row without API errors.
- [ ] `New` clones currently loaded plan content into draft.
- [ ] Load flow UI shows no trace-specific settings or mode override.
- [ ] Pace presets map to interval values with manual override retained.
- [ ] Runtime assignment policy matches approved `all_users` semantics.
- [ ] README/SIMULATOR_GUIDE ownership split is applied in one patch.

## Active Workstream: Pending Order Trace Flow (2026-06-02)

### Problem Statement

Operators need a deliberate flow that places live orders and leaves them pending for manual store-app inspection. Current simulator contracts automatically close or clean up non-terminal orders, so a pending-order seeding flow needs an explicit, narrow exception.

### Target Behavior

- `place-order` appears as a CLI/API/web flow.
- The flow runs trace scenario `place_order`.
- `--orders` / `orders` is valid only for this trace flow, defaults to `1`, and is capped at `10`.
- Store and phone remain optional and follow current plan-random behavior when omitted.
- Each seeded order must be created and websocket-verified as `pending`.
- Seeded orders remain pending; standard cleanup is bypassed only for `place_order`.

### Existing Behavior

- `completed` already places an order but drives it through payment, store prep, robot lifecycle, and terminal completion.
- `--orders` is currently load-only in CLI/API/UI validation.
- End-of-run order-closure cleanup attempts to settle, cancel, or reject every non-terminal order.

### Proposed Approach

1. Add flow/scenario metadata (`FLOW_PRESETS`, `TRACE_SCENARIOS`, docs/catalog/help).
2. Tighten validation so `orders` is valid for `place-order` trace runs only, with a max of `10`.
3. Add a trace runner scenario that loops `SIM_ORDERS`, places orders, waits for pending websocket proof, and records seeded-order decisions.
4. Add a narrow `order_contract` skip path for `place_order` orders and record cleanup bypass evidence.
5. Update web launcher UI/help/impact text to expose Orders only for load mode or `place-order`.
6. Add Python and web tests before implementation, then verify with targeted and full suites.

### Files to Modify (Workstream)

| File | Purpose of Change |
|---|---|
| `flow_presets.py` / `scenarios.py` | Add `place-order` preset and `place_order` scenario |
| `__main__.py` / `api/app/main.py` | Validate trace orders only for `place-order` |
| `trace_runner.py` / `order_contract.py` | Seed pending orders and skip cleanup only for this scenario |
| `web/src/app/(app)/runs/page.tsx` / `web/src/components/runs/RunLaunchPanel.tsx` | Show/validate Orders for `place-order` |
| `web/src/lib/*` | Update command preview, help, impact, tests, and types |
| `tests/test_simulate.py` / `tests/test_web_api.py` | Regression coverage |
| `README.md` / `SIMULATOR_GUIDE.md` / `docs/SIMULATOR_CAPABILITIES.md` / `docs/flows/*` | Operator-facing docs |

### Acceptance Criteria (Workstream)

- [ ] `place-order` resolves to `trace` + `place_order`.
- [ ] `place_order` cannot be combined with suites or extra trace scenarios.
- [ ] `orders` is accepted only for `place-order` trace mode and rejects values above `10`.
- [ ] The trace runner places the requested number of orders and requires pending websocket proof.
- [ ] End-of-run cleanup is bypassed only for `place_order` and logged in artifacts.
- [ ] Runs UI exposes Orders for `place-order` and keeps it load-only elsewhere.
- [ ] Docs explain the intentionally pending order behavior and cleanup responsibility.
