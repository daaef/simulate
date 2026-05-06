# Implementation Tasks

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked

## Tasks

### Phase 1: Preparation

- [x] Inspect current simulator structure and supplied session files
  - Dependency: None
  - Notes: Reviewed CLI, config, actors, trace runner, recorder, tests, architecture, and prompt sections of four app-session files.
  - Completion evidence: `rg --files`, `sed` reads of key Python/docs/session files.

- [x] Initialize implementation tracker
  - Dependency: Repository inspection
  - Notes: Created required tracker files and linked Superpowers spec/plan documents.
  - Completion evidence: `implementation/tracker/README.md`, `implementation_plan.md`, `tasks.md`, `session_log.md`.

- [x] Write Superpowers design spec and implementation plan
  - Dependency: Tracker initialization
  - Notes: Save to `docs/superpowers/specs/2026-04-30-production-simulator-upgrade-design.md` and `docs/superpowers/plans/2026-04-30-production-simulator-upgrade.md`.
  - Completion evidence: Spec and plan files exist under `docs/superpowers/`.

### Phase 2: Implementation

- [x] Add JSON run-plan parser
  - Dependency: Tests for plan behavior
  - Notes: Support input users with phone/GPS/options and stores with store IDs.
  - Completion evidence: `RunPlanTests` and full unit suite pass.

- [x] Add health summary and bottleneck metrics
  - Dependency: Tests for report metrics
  - Notes: Include HTTP status groups, latency percentiles, slow endpoints, websocket match rates, issue severity counts.
  - Completion evidence: `HealthSummaryTests` and report generation tests pass.

- [x] Add real-app probes
  - Dependency: Probe tests
  - Notes: Config/product auth, pricing, cards, coupons, active orders, service-area, menu sides, store stats/top customers.
  - Completion evidence: `AppProbeTests` pass; trace/load wiring added.

- [x] Add post-order actions
  - Dependency: Completed-order context
  - Notes: Receipt, review, reorder after completed order.
  - Completion evidence: `PostOrderActionTests` pass; `receipt_review_reorder` wiring added.

- [x] Wire daily audit and friendly presets
  - Dependency: Probe and post-order modules
  - Notes: Add presets for `doctor`, `full`, `setup`, `load`, targeted probes.
  - Completion evidence: Flow preset tests and CLI help pass.

### Phase 3: Testing

- [x] Run unit tests
  - Dependency: Implementation
  - Notes: `python3 -m unittest discover -s tests`
  - Completion evidence: `python3 -m unittest discover -s tests` exited 0 with 18 tests.

- [x] Run compile check
  - Dependency: Implementation
  - Notes: `PYTHONPYCACHEPREFIX=/tmp/fainzy-pycache python3 -m py_compile *.py`
  - Completion evidence: `PYTHONPYCACHEPREFIX=/tmp/fainzy-pycache python3 -m py_compile *.py` exited 0.

- [x] Run CLI help
  - Dependency: Implementation
  - Notes: `python3 -m simulate --help` from parent or equivalent import-safe command.
  - Completion evidence: `python3 -m simulate --help` exited 0 from `/Users/mars/FAINZY`.

### Phase 4: Cleanup / Documentation

- [x] Update architecture docs
  - Dependency: Implementation
  - Notes: Reflect new modules and daily doctor flow.
  - Completion evidence: `ARCHITECTURE.md` updated with modules, presets, JSON plan, report sections, env flags.

- [x] Write complete guidebook
  - Dependency: Implementation
  - Notes: Must explain use, concepts, scenarios, reports, assumptions, limitations, and rebuild details for non-programmers.
  - Completion evidence: `SIMULATOR_GUIDE.md` created.

- [x] Final tracker update
  - Dependency: Validation
  - Notes: Log commands/results, changed files, blockers, and next task.
  - Completion evidence: Latest session log entry added and task board updated.

### Phase 5: Live Validation Gap Fixes

- [x] Fix trace setup ordering for stores with no menu
  - Dependency: Live doctor run failure on Ask Me Restaurant Jos
  - Notes: `doctor` currently bootstraps user fixtures before `store_first_setup`, so `/menu` returning `[]` aborts before the simulator can create category/menu.
  - Completion evidence: `TraceBootstrapTests.test_store_setup_runs_before_fixture_bootstrap_when_requested` passes; full unit suite passes.

- [x] Fix relative `--plan` path resolution from parent directory
  - Dependency: User command used `--plan simulate/sim_actors.json` from `/Users/mars/FAINZY`.
  - Notes: Current resolver treats relative plan paths as relative to package dir, producing `/simulate/simulate/sim_actors.json`.
  - Completion evidence: `RunPlanTests.test_config_plan_path_prefers_existing_cwd_relative_path` passes; explicit parent-directory path check prints `/Users/mars/FAINZY/simulate/sim_actors.json`.

- [x] Add regression tests and validation
  - Dependency: Implementation fixes
  - Notes: Cover store setup before fixture bootstrap and cwd-relative plan paths.
  - Completion evidence: `python3 -m unittest discover -s tests` exits 0 with 20 tests; compile, CLI help, and `git diff --check` pass.

### Phase 6: Default App-Like Self-Healing Setup

- [x] Add failing tests for default setup/menu preflight
  - Dependency: User approved changing default behavior on 2026-05-01.
  - Notes: Cover trace scenarios that need fixtures but do not explicitly request `store_first_setup`, and cover menu provisioning with old mutation flags false.
  - Completion evidence: Focused tests failed before implementation: auto preflight missing, menu create missing, setup payload status/location overwritten.

- [x] Implement default self-healing provisioning
  - Dependency: Failing regression tests.
  - Notes: Add a default-on config flag, keep old mutation flags as compatibility overrides, and preserve backend profile values in setup payloads.
  - Completion evidence: Focused tests pass after implementation.

- [x] Update guide/tracker and run validation
  - Dependency: Implementation.
  - Notes: Compile, focused tests, full unit suite, CLI help, whitespace check.
  - Completion evidence: `python3 -m unittest discover -s tests` ran 23 tests and exited 0; compile, CLI help, and `git diff --check` exited 0.

### Phase 7: Delivery GPS Separation Fix

- [x] Add failing tests for delivery GPS handling
  - Dependency: Live `doctor` failure on 2026-05-01.
  - Notes: Store selection must not overwrite `SIM_LAT/SIM_LNG`; selected user GPS may set delivery coordinates; load mode should not pass store GPS to fixture bootstrap.
  - Completion evidence: `RunPlanTests.test_store_selection_does_not_override_delivery_gps` and `RunPlanTests.test_selected_user_gps_sets_delivery_gps` failed before implementation.

- [x] Implement delivery GPS separation
  - Dependency: Failing tests.
  - Notes: Keep store GPS in plan/store session only; use user/default GPS for `/v1/entities/locations/<lng>/<lat>/`.
  - Completion evidence: Focused tests pass after implementation; dry command config check keeps `.env` delivery coordinates for `FZY_926025`.

- [x] Update docs/tracker and validate
  - Dependency: Implementation.
  - Notes: Run focused tests, full suite, compile, CLI help, whitespace check.
  - Completion evidence: `python3 -m unittest discover -s tests` ran 25 tests and exited 0; compile, CLI help, and `git diff --check` exited 0.

## Next Immediate Task

### Phase 8: Store Setup Console Visibility

- [x] Show automatic store setup in the live console
  - Dependency: User observed `setup=false` was repaired in the report but not visible in terminal output.
  - Notes: Add regression coverage and operator-facing `store:` messages around store setup detection, submission, and confirmation.
  - Completion evidence: `StoreSetupConsoleTests.test_store_setup_submission_is_visible_in_console`, full unit suite, compile, CLI help, and `git diff --check` pass.

## Next Immediate Task

### Phase 9: App Autopilot Defaults

- [x] Add app-like store and coupon selection defaults
  - Dependency: User approved making commands accept real app inputs while simulator chooses store/coupon/setup/menu decisions by default.
  - Notes: Add TDD coverage for trace store fallback, coupon auto-selection, and coupon-covered free payment routing.
  - Completion evidence: `TraceBootstrapTests.test_trace_auto_selects_next_planned_store_when_default_fixture_fails`, `AppAutopilotTests`, full unit suite, compile, CLI help, and `git diff --check` pass.

## Next Immediate Task

Run live `doctor` without `--store` when ready to prove app-autopilot chooses a usable planned store against the backend.

### Phase 10: Live Decision Console Logs

- [x] Print checkout and post-order user decisions in the live console
  - Dependency: User ran `full` audit and saw report evidence but not terminal logs for free order, receipt, review rating, and reorder.
  - Notes: Add TDD coverage for console output in checkout payment route, free-order completion, and post-order actions.
  - Completion evidence: `DecisionConsoleLogTests`, full unit suite, compile check, CLI help, and `git diff --check` pass.

## Next Immediate Task

Run `python3 -m simulate full --plan sim_actors.json --timing fast` to confirm the new live decision lines against the backend.

### Phase 11: Store App Visibility Parity

- [x] Match store-app availability and complete menu setup behavior
  - Dependency: User observed simulator-created orders/menu are not visible in the store app.
  - Notes: Trace store-app session endpoints for status toggles and menu payload shape; add TDD coverage for opening closed stores, restoring original status, and creating full non-image menu payloads.
  - Completion evidence: `StoreSetupPayloadTests`, full unit suite, compile check, CLI help, and `git diff --check` pass.

## Next Immediate Task

### Phase 12: Guidebook + Store Update/Reporting Upgrade

- [x] Add setup-true store profile update mutation path
  - Dependency: User requirement to mirror real store app update flow for already-setup stores.
  - Notes: `ensure_store_setup` now calls `submit_store_update` when `setup=true` and auto-provision is enabled; mutation is skipped when auto-provision is disabled.
  - Completion evidence: `StoreSetupPayloadTests.test_setup_true_auto_provision_submits_store_update`, `StoreSetupPayloadTests.test_setup_true_without_auto_provision_skips_store_update`.

- [x] Add user/store identity context to report operational tables
  - Dependency: User requirement for operator correlation without payload digging.
  - Notes: Recorder now carries identity context and renders identity columns in Scenario Verdicts, Order Lifecycle, Websocket Assertions, and Developer Findings.
  - Completion evidence: `RecorderTests.test_status_path_and_report_generation` asserts identity columns and values in report output.

- [x] Rewrite simulator guide command coverage and references
  - Dependency: User request for exhaustive command matrix plus detailed command/parameter explanations.
  - Notes: Replaced guide sections with validated command matrix, incompatibility rules, detailed command patterns, full parameter reference, coverage map, timing ranges, and report identity behavior.
  - Completion evidence: `SIMULATOR_GUIDE.md` updated end-to-end and verified with unit/compile/help checks.

## Next Immediate Task

### Phase 13: Web GUI Platform Planning (Docker + VPS + Nginx)

- [x] Produce architecture design spec for web-based simulator control plane
  - Dependency: User approval to proceed with planning.
  - Notes: Capture stack choice, deployment topology, UX surfaces, security and reliability model.
  - Completion evidence: `docs/superpowers/specs/2026-05-02-simulator-web-gui-platform-design.md`.

- [x] Produce execution-ready implementation plan for phased delivery
  - Dependency: Architecture spec draft.
  - Notes: Include backend/frontend/worker/deployment/testing phases and acceptance criteria.
  - Completion evidence: `docs/superpowers/plans/2026-05-02-simulator-web-gui-platform.md`.

- [x] Capture decision gates that require user sign-off before coding
  - Dependency: Architecture and implementation plan drafts.
  - Notes: User approved proceeding with simplified local-first architecture; queue strategy resolved as in-process executor for v1 (Celery/Redis deferred).
  - Completion evidence: Decision checklist section in spec/plan, tracker session log, and explicit user "proceed" approval.

### Phase 14: Web GUI Implementation (Local-First Scaffold)

- [x] Scaffold dockerized web/api/nginx app with no Celery/Redis dependency
  - Dependency: Phase 13 completion.
  - Notes: Added FastAPI run-control API, Next.js GUI shell, Dockerfiles, compose stack, and Nginx reverse proxy.
  - Completion evidence: `api/app/main.py`, `web/src/app/page.tsx`, `docker-compose.yml`, `infra/nginx/nginx.conf`, plus compile/test/help checks.

- [~] Add scheduler, persistence hardening, and richer run detail pages
  - Dependency: Initial scaffold.
  - Notes: Implemented richer run detail pages and artifact explorer tabs; scheduler hardening and profile CRUD remain.
  - Completion evidence: `web/src/app/page.tsx`, `web/src/lib/api.ts`, `api/app/main.py`, UI now exposes report/story/events + metrics tabs.

### Phase 15: Web GUI UX/Monitoring Expansion

- [x] Preserve a presentation snapshot of Docker MVP web app
  - Dependency: Phase 14 scaffold.
  - Notes: Archived MVP web/api/infra/compose state to dedicated folder before continuing feature work.
  - Completion evidence: `snapshots/mvp-web-gui-v1/` with `README.md`.

- [x] Add live monitoring, stop actions, charts, and artifact UX
  - Dependency: Phase 14 scaffold.
  - Notes: Added unbuffered subprocess streaming, per-run stop controls, dashboard status/flow charts, run metrics, and report/story/events inspector tabs.
  - Completion evidence: `api/app/main.py` new endpoints (`/dashboard/summary`, `/artifacts/*`, `/metrics`), `web/src/app/page.tsx` redesigned UI, `web/src/app/globals.css` chart/log styling.

- [x] Reorder dashboard layout per UX feedback
  - Dependency: Phase 15 monitoring UI.
  - Notes: Moved `Recent Runs` section to appear immediately before the status/flow chart section.
  - Completion evidence: `web/src/app/page.tsx` order is now Start/Live -> Recent Runs -> Status/Flow Charts -> Run Inspector.

- [x] Fix tab layout and add report-history selection UX
  - Dependency: Phase 15 monitoring UI.
  - Notes: Fixed horizontal tab rendering by overriding global button width and added an "Available Reports" table inside the report tab to browse older/newer report artifacts by run.
  - Completion evidence: `web/src/app/globals.css` (`.tabs button` width override), `web/src/app/page.tsx` (report history table + view action), `web/src/lib/api.ts` (runs limit increased to 200).

- [x] Fix missing report/story/events data for completed runs
  - Dependency: Phase 15 monitoring UI.
  - Notes: Artifact parser now handles wrapped multiline `main: events/report/story` output and backfills empty artifact fields from stored run logs.
  - Completion evidence: `api/app/main.py` (`_capture_artifacts_from_lines`, `_hydrate_run_artifacts`), and container verification shows runs #1/#2 now have populated artifact paths.

- [x] Render report/story as markdown and present events as API-doc style
  - Dependency: Phase 15 monitoring UI.
  - Notes: Switched report/story rendering from raw preformatted text to markdown rendering, normalized event parsing for recorder schema (`ts`, `ok`, `method`, `endpoint`), and added dedicated API-call table with method/status/latency for documentation-like inspection.

### Phase 16: Plan-Backed Simulator Configuration

- [x] Extend JSON run plans with non-sensitive simulator defaults
  - Dependency: User approval on 2026-05-06.
  - Notes: Keep CLI command syntax unchanged; precedence is explicit CLI flags, then selected plan, then `.env`, then built-in defaults.
  - Completion evidence: `tests.test_simulate.RunPlanTests` focused cases pass; full `tests.test_simulate` passes; `python3 -m simulate --help` passes.

- [x] Add GUI-owned plan storage and plan editor
  - Dependency: Plan schema/config support.
  - Notes: Store generated plans under `runs/gui-plans/`; reject secrets/tokens/passwords from plan content.
  - Completion evidence: `docker compose exec api python -m unittest tests.test_web_api.SimulationPlansApiTests -v` passes; `docker compose exec web npm run build` passes and includes `/config`.

- [x] Update docs for `.env` versus plan responsibilities
  - Dependency: Implementation behavior.
  - Notes: README and SIMULATOR_GUIDE must explain the new workflow.
  - Completion evidence: `README.md`, `SIMULATOR_GUIDE.md`, `ARCHITECTURE.md`, `.env.example`, and `sim_actors.json` updated; `git diff --check` passes.

## Next Immediate Task

Review unrelated existing auth-session worktree changes before starting the next feature slice.
  - Completion evidence: `web/package.json` (`react-markdown`, `remark-gfm`), `web/src/app/page.tsx` markdown + API-call/event-stream views, `web/src/app/globals.css` markdown/method badge styles, `api/app/main.py` metrics/events normalization.

- [x] Fix long-document freeze in report/events inspector
  - Dependency: Phase 15 monitoring UI.
  - Notes: Removed heavy all-tab polling, added lazy tab loading, paginated compact events API payloads, and chunked markdown rendering for very long reports.
  - Completion evidence: `web/src/app/page.tsx` lazy-load effects + pagination/chunk controls, `api/app/main.py` paginated `events` artifact endpoint with compact rows, container verification shows `metrics_total=336` and events page `120/336`.

- [x] Add in-GUI flow/planning/command-combination reference section
  - Dependency: Existing dashboard layout and run-form controls.
  - Notes: Added a dedicated "Flow Planner & Command Guide" section with tabs for Flow Matrix, Command Patterns, Flag Reference, Plan JSON template + timing ranges, combination validity rules, and common failure signatures/remediation. Also added a dynamic command preview in Start Run form.
  - Completion evidence: `web/src/lib/command-guide.ts`, `web/src/app/page.tsx`, `web/src/app/globals.css`, and `docker compose exec web npx tsc --noEmit` passed.

- [~] Complete remaining platform features
  - Dependency: UX monitoring expansion.
  - Notes: Profile CRUD, schedule CRUD UI/API, auth/RBAC, alerting, deployment hardening, and full e2e verification still pending.
  - Completion evidence: Pending.

## Next Immediate Task

Continue remaining platform features: profile/schedule CRUD and auth/alert/deployment hardening phases.

### Phase 16: Contract-Driven Runtime/Docs Sync

- [ ] Define and add canonical simulator contract file
  - Dependency: Phase 15 baseline and current flow/flag behavior.
  - Notes: Create `docs/contract/simulator_contract.yaml` with flow mappings, flag constraints, fallback/selection policy, and known failure signatures.
  - Completion evidence: Contract file added and schema validation test passes.

- [ ] Implement contract loader and runtime parity checks
  - Dependency: Contract file exists.
  - Notes: Add typed loader module and tests that assert contract entries match runtime mappings in CLI/API.
  - Completion evidence: New `tests/test_contract_runtime.py` green.

- [ ] Replace hardcoded command-guide data with contract-derived data
  - Dependency: Contract loader implemented.
  - Notes: Remove duplicated flow/flag matrices from frontend source and source it from backend contract endpoint or generated TS artifact.
  - Completion evidence: GUI guide renders unchanged content sourced from contract data.

- [ ] Generate operator/developer docs from contract
  - Dependency: Contract schema finalized.
  - Notes: Add `scripts/generate_simulator_docs.py` to render sections for `SIMULATOR_GUIDE.md` and `docs/reference/simulator_runtime_reference.md`.
  - Completion evidence: Generated docs include flow matrix, command patterns, flags, combo rules, and selection policy.

- [ ] Add release drift gate
  - Dependency: Doc generation path implemented.
### Phase 17: Auth + UI Reliability Check (2026-05-05)

- [x] Validate auth endpoint request contracts used by GUI
  - Dependency: Existing auth API routes and AuthContext client calls.
  - Notes: Confirmed mismatch on `refresh/logout/reset-password` (frontend sends JSON body, backend expected query params) and fixed backend models to accept JSON payload.
  - Completion evidence: `api/app/main.py` adds `RefreshTokenRequest` and `ResetPasswordRequest`, endpoints now parse body payloads.

- [x] Fix optional-auth behavior for non-admin dashboard endpoints
  - Dependency: Auth dependency wiring.
  - Notes: `HTTPBearer` default `auto_error=True` blocked unauthenticated `/runs` requests; changed to `auto_error=False` and enforced explicit required-auth checks in `get_current_user`.
  - Completion evidence: `/api/v1/runs` now responds without bearer token where optional auth is intended.

- [x] Fix JWT verification and admin user update bugs in auth manager
  - Dependency: `api/auth.py` token and DB helpers.
  - Notes: Replaced invalid `jwt.JWTError` catch with `jwt.PyJWTError`; fixed `update_user` to use `DictCursor` so dict conversion is valid.
  - Completion evidence: `api/auth.py` patched and API logs no longer show handler errors for invalid-token paths.

- [x] Fix UI-side auth guard DOM side effect
  - Dependency: Web auth guard component.
  - Notes: Removed module-scope `document` usage and moved style injection into `useEffect` with cleanup.
  - Completion evidence: `web/src/components/AuthGuard.tsx` patched; web build passes.

- [x] Rebuild and verify containerized stack
  - Dependency: Backend/frontend code fixes.
  - Notes: Rebuilt `api/web/nginx` and ran auth/API smoke checks.
  - Completion evidence: `docker compose up -d --build api web nginx`; curl checks show correct status semantics (`401` for invalid login/refresh, `200` on `/healthz`, `200` on unauthenticated `/api/v1/runs` optional path).

### Phase 18: Enhanced Identity Logging & Debugging (2026-05-05)

- [~] Ensure complete store and phone information in logs and GUI
  - Dependency: Phase 15.
  - Notes: Capture names and full phone numbers via JSON markers and expanded DB schema.
  - Completion evidence: Web GUI shows names and full phones in "Recent Runs".
- [x] Fix `NameError: name 'console' is not defined` in `reporting.py`
  - Dependency: Initial Phase 18 changes.
  - Notes: Imported/defined `console` in `reporting.py`.
  - Completion evidence: `python3 -m py_compile reporting.py` passes and user reported crash is resolved.
- [ ] Verify complete identity capture in web dashboard
  - Dependency: Implementation and fix.
  - Notes: Run a doctor simulation and check dashboard.
  - Completion evidence: Run details show full identity.

### Phase 19: Operations Platform Redesign Spec (2026-05-06)

- [x] Produce approved redesign spec for auth, routing, runs UX, schedules, and retention
  - Dependency: User design approvals collected through brainstorming.
  - Notes: Locked decisions include admin-created users only, single active session, cookie-based sessions, overview landing, route-first app shell, structured scheduling, campaign mode, rerun-exact execution, and active/archive/purge lifecycle.
  - Completion evidence: `docs/superpowers/specs/2026-05-06-simulator-operations-platform-redesign.md`

- [x] Wait for user review of the written redesign spec
  - Dependency: Spec file written and self-reviewed.
  - Notes: No implementation should begin until the user reviews and approves the spec document.
  - Completion evidence: User explicitly approves the spec file.

### Phase 20: Operations Platform Redesign Implementation Plan (2026-05-06)

- [x] Write execution-ready redesign plan for study
  - Dependency: Approved redesign spec.
  - Notes: Plan should sequence auth/session foundation first, then route migration, runs split, overview, schedules/campaigns, archive/retention, and admin/alerts.
  - Completion evidence: `docs/superpowers/plans/2026-05-06-simulator-operations-platform-redesign.md`

- [x] Update tracker canonical plan to align with redesign
  - Dependency: New redesign plan written.
  - Notes: `implementation/tracker/implementation_plan.md` and `README.md` should reflect the new operations-platform target rather than the older generic web-GUI plan.
  - Completion evidence: tracker docs reference the 2026-05-06 redesign spec and plan.

- [x] Wait for user study/review of the redesign implementation plan
  - Dependency: Plan file written and self-reviewed.
  - Notes: No code implementation should start until the user studies and approves the plan.
  - Completion evidence: User explicitly approves the plan or requests revisions.

### Phase 21: Operations Platform Redesign Execution - Auth/Route Foundation (2026-05-06)

- [x] Implement backend-owned session foundation and route-first auth entry
  - Dependency: Approved redesign spec and approved redesign implementation plan.
  - Notes: First slice covers cookie-backed auth session truth, single-session replacement mechanics, `/auth/login` entry flow, root redirect behavior, and removing frontend bearer-token ownership from the protected app surface.
  - Completion evidence: `tests.test_web_api.CookieSessionAuthTests` and full `tests.test_web_api` pass in the API container, `docker compose exec web npm run build` passes, `/auth/login`, `/overview`, `/runs`, `/schedules`, `/archives`, `/retention`, and `/admin/users` routes now build under the protected app shell.

## Next Immediate Task

Start backend route/service decomposition and RBAC normalization so auth/session ownership no longer lives as a thin layer on top of the monolithic `api/app/main.py`.

### Phase 22: Backend Auth/Admin Decomposition + RBAC Base (2026-05-06)

- [x] Extract auth and admin route logic out of `api/app/main.py`
  - Dependency: Phase 21 auth/session foundation completed.
  - Notes: Added dedicated auth dependencies, auth router, auth service wrapper, auth policy helpers, and admin router while keeping current runtime behavior intact.
  - Completion evidence: `api/app/auth/*`, `api/app/admin/routes.py`, and slimmer `api/app/main.py` compile and route tests pass.

- [x] Add backend RBAC regression coverage and permission gates
  - Dependency: Extracted auth dependencies/policies.
  - Notes: Added session-protected route tests for anonymous rejection plus viewer read/admin denial; moved protected runs/dashboard/admin endpoints onto backend permission helpers.
  - Completion evidence: `tests.test_web_api` passes with 8 tests in the API container.

- [x] Normalize role interpretation for current surfaces
  - Dependency: Backend policy helpers.
  - Notes: Backend treats legacy `user` as `operator`; frontend role context now recognizes `admin`, `operator`, `viewer`, and `auditor` while preserving `isUser` as a compatibility alias.
  - Completion evidence: `web/src/contexts/RoleContext.tsx` updated and web production build passes.

## Next Immediate Task

Start the runs-domain decomposition: move runs endpoints/services out of `api/app/main.py`, then begin replacing the temporary `/runs` migration surface with the real workspace/detail split.

### Phase 23: Runs-Domain Route Extraction (2026-05-06)

- [x] Extract runs API route handlers out of `api/app/main.py`
  - Dependency: Phase 22 backend auth/admin decomposition.
  - Notes: Added `api/app/runs/routes.py`, `models.py`, and `service.py`; `main.py` now configures runtime callbacks and includes the runs router instead of owning all runs handlers directly.
  - Completion evidence: `tests.test_web_api` passes after extraction and web production build still passes.

- [x] Preserve compatibility for existing tests and runtime helpers during extraction
  - Dependency: Runs route extraction.
  - Notes: Re-exported route handler names through `api.app.main` imports, preserved `SESSION_COOKIE_NAME` on `main`, and configured runtime callbacks via late-binding lambdas so test patches against `web_api._get_run` and related helpers still work.
  - Completion evidence: Existing `tests.test_web_api.EventsCacheTests` and `CookieSessionAuthTests` remain green without test rewrites.

## Next Immediate Task

Start the real `/runs` workspace decomposition on the frontend: split the migrated MVP page into focused run-table, launch, and inspector components, then move `/runs/[id]` toward the approved forensic tab model.

### Phase 24: `/runs` Frontend Workspace Split - Part 1 (2026-05-06)

- [x] Extract the migrated `/runs` workspace into focused components without changing behavior
  - Dependency: Phase 23 runs-domain route extraction.
  - Notes: Moved launch form, live console, flow planner guide, recent-runs table, statistics, and delete confirmation modal into dedicated `web/src/components/runs/*` components while keeping route behavior and polling logic in the page.
  - Completion evidence: `web/src/app/(app)/runs/page.tsx` is materially slimmer and `docker compose exec web npm run build` passes.

- [x] Preserve current run-launch, console, and recent-runs behavior during the split
  - Dependency: Component extraction.
  - Notes: The page still owns fetch/poll/state orchestration; extracted components are presentational and callback-driven to minimize regression risk before the next route-level redesign slice.
  - Completion evidence: Build succeeds and existing `/runs` route output remains functionally unchanged.

## Next Immediate Task

Start `/runs/[id]` forensic decomposition: extract summary/tabs/artifact viewers into dedicated detail components, then move the route closer to the approved operator/forensics information architecture.

### Phase 25: `/runs/[id]` Detail Decomposition - Part 1 (2026-05-06)

- [x] Extract detail header, overview, and artifact/event/log surfaces into dedicated components
  - Dependency: Phase 24 `/runs` frontend workspace split.
  - Notes: Added `web/src/components/runs/detail/*` components for the header, overview, markdown artifact rendering, events panel, and log panel; the route still owns fetch and tab state to keep this slice low-risk.
  - Completion evidence: `web/src/app/(app)/runs/[id]/page.tsx` is materially slimmer and `docker compose exec web npm run build` passes.

- [x] Preserve current detail-page fetch behavior during the split
  - Dependency: Detail component extraction.
  - Notes: Existing metrics/report/story/events/log loading behavior remains in the page, with no route contract changes.
  - Completion evidence: Web production build passes after extraction with no API changes required.

## Next Immediate Task

Start the actual forensic UX upgrade for `/runs/[id]`: replace the generic tab panel with a more explicit operator/engineering information hierarchy and prepare for execution-snapshot and identity-rich detail sections.

### Phase 26: `/runs/[id]` Forensic UX Upgrade - Part 1 (2026-05-06)

- [x] Replace generic detail tabs with explicit operator/forensics surfaces
  - Dependency: Phase 25 `/runs/[id]` detail decomposition.
  - Notes: Reframed the route into `Overview`, `Story`, `Technical Report`, `Traffic`, `Console`, and `Execution` surfaces with explicit descriptions instead of the previous generic tab labels.
  - Completion evidence: `web/src/components/runs/detail/RunDetailTabNav.tsx` exists and `docker compose exec web npm run build` passes.

- [x] Add execution-context detail section for replay/archive readiness
  - Dependency: New detail information hierarchy.
  - Notes: Added execution snapshot panel showing actor identity, resolved inputs, command string, and artifact availability/paths so the route now carries the frontend shape needed for future exact-rerun and archive-summary work.
  - Completion evidence: `web/src/components/runs/detail/RunExecutionSnapshotPanel.tsx` exists and renders from current `RunRow` data.

- [x] Enrich overview tab with top actor/action breakdowns
  - Dependency: Existing metrics support.
  - Notes: The overview now surfaces `top_actors` and `top_actions` from `RunMetrics`, making the page more useful for operator diagnosis without opening raw artifacts first.
  - Completion evidence: `RunDetailOverview.tsx` renders top lists and build passes.

## Next Immediate Task

Move back to backend/platform entities: add saved run profiles and immutable execution-snapshot storage so the current frontend execution surface can be backed by real replay data instead of only the command string.

### Phase 27: Close Remaining Partial Foundation Gaps (2026-05-06)

- [x] Finish backend route-domain split for archives and retention
  - Dependency: Prior auth/runs decomposition.
  - Notes: Added `api/app/archives/*` and `api/app/retention/*` modules, wired them through `api/app/main.py`, and exposed summary endpoints guarded by backend permissions.
  - Completion evidence: `/api/v1/archives/summary`, `/api/v1/archives/runs`, and `/api/v1/retention/summary` are routed through dedicated modules and `tests.test_web_api` passes.

- [x] Persist execution snapshots on run creation
  - Dependency: Existing run creation flow.
  - Notes: Added `execution_snapshot` storage to the run record and runtime schema migrations for SQLite/PostgreSQL; execution tab now reads actual stored snapshot data where available.
  - Completion evidence: `RunExecutionSnapshotTests.test_create_run_persists_execution_snapshot` passes.

- [x] Upgrade `/overview` from placeholder to real monitoring cockpit
  - Dependency: Archive/retention summary APIs and dashboard metrics.
  - Notes: Overview now shows attention queue, active/failure/archive/purge counts, archive-window and retention-queue summaries, platform status, and flow distribution.
  - Completion evidence: `web/src/app/(app)/overview/page.tsx` updated and `docker compose exec web npm run build` passes.

## Next Immediate Task

Start the first truly not-done platform block: saved run profiles and immutable execution-snapshot/replay APIs, then schedule entities on top of that.

### Phase 28: Saved Profiles + Replay APIs (2026-05-06)

- [x] Add backend persistence and APIs for saved run profiles
  - Dependency: Phase 27 closed the route-domain and execution-snapshot foundation.
  - Notes: Added `run_profiles` storage for SQLite/PostgreSQL, profile CRUD endpoints under the runs domain, and direct profile launch API support.
  - Completion evidence: `RunProfilesApiTests.test_profile_crud_launch_and_replay` passes.

- [x] Expose persisted execution snapshots through replay-oriented APIs
  - Dependency: Existing `execution_snapshot` persistence on runs.
  - Notes: Added execution snapshot fetch endpoint and exact replay endpoint that creates a new run from the stored snapshot payload instead of reconstructing from UI state.
  - Completion evidence: `RunProfilesApiTests.test_profile_crud_launch_and_replay` covers snapshot fetch and replay.

- [x] Add minimal runs-workspace UI for saved profiles and replay
  - Dependency: Backend profile/replay APIs.
  - Notes: `/runs` now includes a Saved Profiles panel to save/load/update/launch/delete reusable run definitions; `/runs/[id]` execution tab can replay the exact run from its stored snapshot.
  - Completion evidence: `web/src/components/runs/RunProfilesPanel.tsx`, `web/src/app/(app)/runs/page.tsx`, `web/src/app/(app)/runs/[id]/page.tsx`, and `docker compose exec web npm run build` pass.

## Next Immediate Task

Start schedule and campaign persistence on top of the new profile and replay primitives, then replace the `/schedules` placeholder with real profile-backed schedule management.

### Phase 29: Unsafe Run Deletion Fix (2026-05-06)

- [x] Fix run deletion so it only removes selected-run files
  - Dependency: User reported deleting run #1 emptied run #5 live console.
  - Notes: Add regression tests for shared GUI logs, artifact folder isolation, and missing log-dir recreation before production changes.
  - Completion evidence: `RunDeletionSafetyTests` pass; full `tests.test_web_api` passes; API restarted and `/healthz` returns 200.

## Next Immediate Task

Monitor future run deletes from the web UI; already-deleted GUI log files cannot be recovered without backups.

### Phase 30: Local Env Cleanup Into Plan Defaults (2026-05-06)

- [x] Move non-sensitive local `.env` behavior into `sim_actors.json`
  - Dependency: Plan-backed config support from Phase 16.
  - Notes: Preserve effective defaults for user phone, store, delivery GPS, runtime/rule/payment/fixture settings; keep secrets and deployment URLs in `.env`.
  - Completion evidence: Config resolution check returns `+2348166675609`, `FZY_926025`, subentity `7`, delivery GPS, trace/doctor/fast defaults; `tests.test_simulate` passes; CLI help passes; GUI command builder omits `--phone` when blank.

## Next Immediate Task

Use plan-backed values for future CLI/GUI runs; keep `.env` free of actor/run-behavior keys.
