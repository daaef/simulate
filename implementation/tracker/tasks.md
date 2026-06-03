# Implementation Tasks

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked

## Tasks

### Phase 40: Orders Update Status Tab Polish

- [x] Add focused display helper coverage
  - Dependency: User-approved Orders update tab design.
  - Notes: Cover item-name extraction so the second tab can show names only.
  - Completion evidence: `orders-display.test.ts` fails before helper implementation and passes after.

- [x] Add raw JSON pane to both Orders modes
  - Dependency: Existing order lookup state.
  - Notes: Show readable `JSON.stringify(order, null, 2)` output to the right after lookup; stack on narrow widths.
  - Completion evidence: `/orders` builds and route smoke-checks after web rebuild.

- [x] Simplify second tab into direct status update flow
  - Dependency: Existing `OrderItemsTab` state and status update helper.
  - Notes: Rename tab to `Update Status`; remove store panel, `Items Ordered` panel, quantity lines, item prices, and item total row; show item names, total price, select, and `Update Status`.
  - Completion evidence: Source no longer contains `Items & Store` or `Items Ordered`; tests and TypeScript pass.

- [x] Update docs and tracker
  - Dependency: UI behavior stabilized.
  - Notes: Update README, SIMULATOR_GUIDE, spec, plan, and tracker.
  - Completion evidence: Docs mention raw JSON pane and `Update Status` tab behavior.

### Phase 39: Orders LastMile Token Fix

- [x] Add regression coverage for LastMile token selection and invalid-token mapping
  - Dependency: User reported lookup returning `please provide a valid token`.
  - Notes: Store-login response has a 64-character profile token, but LastMile orders require the product-auth `gAAAA...` token used by `store_sim`.
  - Completion evidence: Focused tests fail before service fix.

- [x] Persist the correct LastMile token from orders store sign-in
  - Dependency: Failing regression coverage.
  - Notes: Fetch `/v1/biz/product/authentication/?product=rds` during store sign-in and return that as the browser session token; keep store-login for metadata.
  - Completion evidence: Live lookup with the returned token succeeds against LastMile.

- [x] Map LastMile invalid-token 400 responses to reauth
  - Dependency: Error contract regression coverage.
  - Notes: Existing stale localStorage sessions should clear instead of surfacing a 502-style Fainzy API error.
  - Completion evidence: Route tests pass.

- [x] Run verification and tracker update
  - Dependency: Code fix.
  - Notes: Run focused tests, compile, smoke sign-in + lookup, rebuild API.
  - Completion evidence: Session log records root cause and command results.

### Phase 38: Orders Store Login 1010 Fix

- [x] Add regression coverage for Fainzy store-login request headers and sign-in error mapping
  - Dependency: User reported `/orders` sign-in failure.
  - Notes: Fainzy returns `403 error code: 1010` to the default Python urllib client fingerprint.
  - Completion evidence: Focused test fails before service header fix.

- [x] Implement store-login header fix
  - Dependency: Failing regression coverage.
  - Notes: Send a stable app-compatible `User-Agent` from orders service requests without adding env vars.
  - Completion evidence: Focused backend tests pass and live store-login succeeds from the API container.

- [x] Run verification and tracker update
  - Dependency: Code fix.
  - Notes: Run focused Python tests, compile, web typecheck if frontend untouched optional, and Docker rebuild/smoke.
  - Completion evidence: Session log records root cause and command results.

### Phase 37: Orders Page Auth and Status Fix

- [x] Update implementation tracker for orders workstream
  - Dependency: User-approved plan.
  - Notes: Add focused scope, plan, tasks, and session log entry before implementation.
  - Completion evidence: Tracker files mention Phase 37 Orders Page Auth and Status Fix.

- [x] Add failing tests for orders API and frontend helpers
  - Dependency: Tracker update.
  - Notes: Cover store list, store login proxy, lookup fallback, missing token, status update, localStorage session, and full lifecycle statuses.
  - Completion evidence: Focused tests fail before implementation for missing/new behavior.

- [x] Implement backend orders auth, lookup, and status contract
  - Dependency: Failing backend tests.
  - Notes: Add `stores` and `store-login` routes; remove orders-specific env dependency; add query fallback.
  - Completion evidence: Focused backend tests pass.

- [x] Implement frontend orders helpers and page UX
  - Dependency: Backend contract.
  - Notes: Store selection first, API-backed login, persisted token, unified lookup, full lifecycle status dropdowns.
  - Completion evidence: TypeScript and focused web tests pass.

- [x] Update user-facing docs
  - Dependency: Behavior stabilized.
  - Notes: Update README and SIMULATOR_GUIDE.
  - Completion evidence: Docs describe `/orders`, store token persistence, and no new env vars.

- [x] Run verification and final tracker update
  - Dependency: Implementation and docs.
  - Notes: Run compile, typecheck, focused Python/web tests, and record results.
  - Completion evidence: Session log contains command outputs and remaining risks.

## Next Immediate Task

Phase 40 complete. Next immediate task: manually open `/orders`, look up a live order in both tabs, and visually confirm JSON pane plus direct `Update Status` flow.

### Phase 36: Pending Order Trace Flow

- [x] Add failing tests for `place-order` flow/scenario/API/order-contract/web behavior
  - Dependency: User-approved plan.
  - Notes: Cover resolver, API validation, order cleanup exception, command preview, and launcher help/validation.
  - Completion evidence: Focused tests fail before implementation for missing `place-order` behavior.

- [x] Implement CLI/API trace flow metadata and validation
  - Dependency: Failing tests.
  - Notes: Add `place-order`, `place_order`, and trace-only `orders` exception capped at 10.
  - Completion evidence: Focused Python tests pass.

- [x] Implement trace runner pending seeding and cleanup bypass
  - Dependency: Flow metadata and validation.
  - Notes: Loop `SIM_ORDERS`, call `user_sim.place_order`, require `pending` websocket gate, record seeded/bypass events.
  - Completion evidence: Trace runner and order-contract tests pass.

- [x] Update Runs UI launcher and web helpers
  - Dependency: API/flow contract.
  - Notes: Show Orders for load mode or `place-order`; update validation, command preview, impact/help text.
  - Completion evidence: Web tests pass.

- [x] Update docs
  - Dependency: Behavior stabilized.
  - Notes: Update README, SIMULATOR_GUIDE, SIMULATOR_CAPABILITIES, and flow docs.
  - Completion evidence: Docs mention `place-order`, `place_order`, `--orders` cap, and pending-order responsibility.

- [x] Run verification and final tracker update
  - Dependency: Implementation and docs.
  - Notes: Run planned Python and web tests; record output and remaining risks.
  - Completion evidence: Verification outputs logged in `session_log.md`; full Python suite has one unrelated schedule-window edge failure.

### Phase 35: Universal Order-Closure + WebSocket-Proof Enforcement

- [x] Implement global terminal-order contract across `trace` and `load`
  - Dependency: Tracker update + current runtime assessment.
  - Notes: Every created order must end in `{completed, rejected, cancelled}`; unresolved non-terminal orders must fail run regardless of `failure_policy`.
  - Completion evidence: Shared end-of-run finalization invoked by both modes and enforced by tests.

- [x] Fix payment/store context leakage
  - Dependency: Global terminal contract wiring.
  - Notes: Remove mutable-global context reliance; pass per-order explicit `subentity_id`/currency/store context through payment paths.
  - Completion evidence: Regression test proving no subentity drift after alternate-store coupon recovery.

- [x] Add lifecycle finalization and cleanup attempts
  - Dependency: Cleanup/fetch helpers and order inventory extraction.
  - Notes: Per non-terminal order: natural-settle wait, cancel-first, reject fallback (when valid), re-check.
  - Completion evidence: Tests for cleanup success and cleanup unresolved failure path.

- [x] Enforce strict websocket lifecycle proof for created orders
  - Dependency: Finalization wiring.
  - Notes: Missing/late websocket proof for required order lifecycle checkpoints becomes run-failing for order-producing runs.
  - Completion evidence: Tests where missing websocket terminal proof fails run.

- [x] Update run artifact narratives for cleanup/unresolved evidence
  - Dependency: Finalization + websocket strictness implementation.
  - Notes: Add explicit report/story sections for cleanup attempts and unresolved non-terminal orders.
  - Completion evidence: Report/story assertions in tests.

- [x] Update operator docs for always-on contract
  - Dependency: Runtime behavior complete.
  - Notes: Document no-open-order success rule and websocket lifecycle proof requirement.
  - Completion evidence: `README.md` + `SIMULATOR_GUIDE.md` updated and reviewed.

- [x] Run full verification suite
  - Dependency: All implementation tasks complete.
  - Notes: Targeted new tests + full unit tests + compile + CLI help + diff check.
  - Completion evidence: command outputs recorded in `session_log.md`.

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

- [x] Admin-configured allowed scheduling timezones
  - Dependency: Schedules feature exists.
  - Notes: Add `system_settings` persistence, `GET/PUT /api/v1/system/timezones`, `/admin/system` UI with allowlist toggle + checklist, schedules timezone dropdown backed by policy, and API enforcement on schedule create/update.
  - Completion evidence: `SystemTimezonesApiTests` added; `python3 -m unittest discover -s tests` passes; `cd web && npm run build` passes.

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

### Phase 16: GitHub Deployment Webhook Integration

- [x] Add inbound GitHub deployment webhook endpoint and validation
  - Dependency: Existing API runtime wiring.
  - Notes: Added `POST /api/v1/integrations/github/deployment-complete`, `deployment_status` success gating, repository allowlist checks, and HMAC signature validation.
  - Completion evidence: `api/app/integrations/routes.py`, `api/app/main.py` integration webhook processing path.

- [x] Add integration mapping + trigger persistence with idempotency
  - Dependency: Endpoint validation path.
  - Notes: Added `integration_profile_mappings` and `integration_triggers` tables for SQLite/PostgreSQL with dedupe key `project:environment:deployment_id:sha`.
  - Completion evidence: `api/app/main.py` schema init/migration + trigger create/update/list logic.

- [x] Add async profile launch and terminal-status GitHub callback
  - Dependency: Trigger persistence.
  - Notes: Queued launches resolve profile from `(project, environment)` mapping; terminal run state updates integration trigger and posts GitHub deployment status (`simulator/verification`).
  - Completion evidence: `api/app/main.py` integration launch worker + `_handle_integration_run_terminal_status`.

- [x] Add integration admin APIs
  - Dependency: Mapping persistence.
  - Notes: Added list/upsert/delete mapping endpoints and trigger listing endpoints secured via `system` permissions.
  - Completion evidence: `api/app/integrations/service.py`, `api/app/integrations/routes.py`, runtime registration in `api/app/main.py`.

- [x] Update deployment and operator docs for webhook flow
  - Dependency: Implemented behavior.
  - Notes: Replaced post-deploy script references with webhook setup and env model.
  - Completion evidence: `README.md`, `SIMULATOR_GUIDE.md`, `docs/deployment.md`, `.env.prod.example`.

## Next Immediate Task

Run API tests and a webhook dry-run payload against `POST /api/v1/integrations/github/deployment-complete`, then verify trigger lifecycle transitions and GitHub callback behavior with a valid token.
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

### Phase 17: Run-ID Data Isolation + Schedule Editing

- [x] Enforce strict run artifact/log ownership by run id
  - Dependency: Reproduce stale artifact bleed in `/runs/:id` and inspect hydration + log append behavior.
  - Notes: Ensure in-progress runs cannot hydrate artifact metadata from old run logs; ensure metadata hydration only reads `run-{id}.log`.
  - Completion evidence: `api/app/main.py` now truncates `run-{id}.log` at launch and skips artifact hydration for active statuses; hydration uses `_run_log_path_for_run` guard. Added `test_running_run_does_not_hydrate_artifacts_from_old_log_content`.

- [x] Add edit capability for existing schedules in web UI
  - Dependency: Existing `PUT /api/v1/schedules/{id}` API.
  - Notes: Allow loading an existing schedule into the form, updating fields, and saving changes.
  - Completion evidence: `web/src/app/(app)/schedules/page.tsx` adds `Edit` action, form hydration from selected schedule, save via `updateSchedule`, and cancel-edit reset flow.

- [x] Update docs + tracker + verification
  - Dependency: Implementation complete.
  - Notes: Update `README.md` and `SIMULATOR_GUIDE.md` for schedule edit flow and run-data binding behavior; run backend/frontend tests.
  - Completion evidence: Docs updated in both files; backend tests pass (`RunDeletionSafetyTests` target + `SchedulesApiTests`). Frontend build blocked locally (`next: command not found`).

## Next Immediate Task

Run full frontend verification in the intended container/runtime where Next.js is installed, then manually smoke-test `/runs/{id}` and `/schedules` edit flow.
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

### Phase 31: Remaining Platform Features + UX Upgrade (2026-05-06)

- [x] Implement schedules, campaigns, charts, dark-mode polish, archives/retention pages, admin/alerts polish, and docs
  - Dependency: Phase 28 saved profiles/replay, Phase 29 delete safety, Phase 30 plan-backed config.
  - Notes: User approved the "Remaining Platform Plan With UX Upgrade"; scope includes `api/app/schedules/`, in-process scheduled execution, active navigation, dark-mode contrast, glanceable charts, archive/retention UX, alerts, admin lifecycle polish, and documentation updates.
  - Completion evidence: `docker compose exec api python -m unittest tests.test_web_api -v`, focused schedules/alerts tests, `docker compose exec web npm run build`, `docker compose exec api python -m py_compile ...`, and `git diff --check`.

## Next Immediate Task

Manual smoke: log in, switch dark/light mode, verify active navigation on nested `/runs/<id>`, create/trigger a schedule, inspect archive/retention pages.

### Phase 32: Config/Load UX + Runtime Alignment Design (2026-05-19)

- [x] Complete brainstorming and lock hybrid approach decisions
  - Dependency: User requirements on config tabs, default plan loading, load semantics, and docs merge.
  - Notes: Approved decisions captured section-by-section (behavior contract, implementation surface, validation/docs).
  - Completion evidence: Explicit user approvals in session for hybrid approach and all three design sections.

- [x] Write and self-review formal design spec
  - Dependency: Approved design sections.
  - Notes: Spec captures tabbed Config UX, default `sim_actors` loading fix, `New` clone semantics, load pacing presets, mode-specific UI isolation, round-robin worker policy, and documentation ownership.
  - Completion evidence: `docs/superpowers/specs/2026-05-19-config-load-ux-and-runtime-alignment-design.md`.

- [x] Wait for user review of written design spec
  - Dependency: Spec file written and self-reviewed.
  - Notes: Do not start implementation planning or code changes until user reviews the written spec file.
  - Completion evidence: User approved and requested proceeding, plus accepted additional per-flow docs requirement.

### Phase 33: Config/Load UX + Runtime Alignment Implementation Plan (2026-05-19)

- [x] Write execution-ready implementation plan from approved spec
  - Dependency: Phase 32 design approval.
  - Notes: Include tabbed Config, default-plan load fix, load-only launcher controls, pace presets, deterministic all_users assignment, and per-flow docs pack.
  - Completion evidence: `docs/superpowers/plans/2026-05-19-config-load-ux-and-runtime-alignment.md`.

- [x] Wait for user review of written implementation plan
  - Dependency: Plan file written and self-reviewed.
  - Notes: User approved plan via status-review closeout; implementation already underway (Tasks 1–3 committed).
  - Completion evidence: Plan approved in tracker status review session; inline execution selected.

### Phase 34: Config/Load UX + Runtime Alignment Execution (2026-05-19)

- [x] Task 4: Load-only launcher controls and pace presets
  - Dependency: Phase 33 plan approval.
  - Notes: `load-mode-controls.ts`, `RunLaunchPanel.tsx`, `run-launcher-config.ts`.
  - Completion evidence: Commit `7db14e3`; Vitest 11/11 pass; `npm run build` pass.

- [x] Task 5: Deterministic load worker assignment helper
  - Dependency: Approved load semantics.
  - Notes: `load_worker_assignment.py`, `tests/test_load_worker_assignment.py`.
  - Completion evidence: Commit `89a3442`; `tests.test_load_worker_assignment` 6/6 pass.

- [x] Task 6: Runtime wiring for worker assignment
  - Dependency: Task 5 helper.
  - Notes: `__main__.py`, `user_sim.py`, integration test in `tests/test_simulate.py`.
  - Completion evidence: Commit `91390a5`; `LoadWorkerRuntimeTests` 2/2 pass.

- [x] Task 7: Per-flow operator docs and coverage checker
  - Dependency: Approved docs pack requirement.
  - Notes: `docs/flows/*.md`, `scripts/check_flow_docs.py`.
  - Completion evidence: Commit `98d6747`; `python3 scripts/check_flow_docs.py` -> 16 flow docs present.

- [x] Task 8: Docs ownership merge (README quickstart, SIMULATOR_GUIDE canonical)
  - Dependency: Task 7 flow docs.
  - Notes: `README.md`, `SIMULATOR_GUIDE.md`, implementation plan doc.
  - Completion evidence: Commit `eee047f`; README links to SIMULATOR_GUIDE and docs/flows.

- [x] Task 9: Full verification and tracker closeout
  - Dependency: Tasks 4–8.
  - Notes: Backend/frontend tests, flow docs checker, web build, session log update.
  - Completion evidence: See session log 2026-05-19 03:50; `git diff --check` pass.

## Flow Reliability Hardening (2026-05-19)

- [x] Regression runner (`scripts/run_named_flow_regression.sh` + `.py`)
- [x] Targeted policy tests (`FlowReliabilityPolicyTests` in `tests/test_simulate.py`)
- [x] Coupon retry: skip alternate-store HTTP 5xx and continue; hard-fail only when recovery exhausts with API faults
- [x] Docs (`README.md`, `SIMULATOR_GUIDE.md`, `docs/SIMULATION_TEST_GUIDE.md`, `docs/reports/README.md`)
- [ ] **Your verification:** full live regression + strict spot-check (commands in `session_log.md` 2026-05-19 Flow Reliability entry)

## Next Immediate Task

Run `./scripts/run_named_flow_regression.sh` and strict spot-check flows locally; archive `runs/flow-reliability-*` if desired. Then resume contract-driven runtime/docs sync.
