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
