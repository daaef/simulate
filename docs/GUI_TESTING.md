# Simulator web GUI — manual test guide

This document is a **from-the-ground-up manual test checklist** for the authenticated **Next.js operator UI** (`web/src/app`). It is derived from the current UI components and client behavior (especially `RunLaunchPanel.tsx`, `web/src/app/(app)/runs/page.tsx`, `RunProfilesPanel.tsx`, `RecentRunsTable.tsx`, run detail under `runs/[id]/`, and `RoleContext.tsx`). For **every CLI flag and scenario name** as implemented by the backend, use [SIMULATOR_CAPABILITIES.md](SIMULATOR_CAPABILITIES.md); the GUI does **not** expose every backend knob (notably **`extra_args`** is API-only—there is no field on Start Run).

**Roles (what to expect in the UI):**

| Role | `runs` create (Start Run, profiles) | `runs` cancel (Stop) | `runs` delete/archive | profile archive/restore | schedule delete/restore | integration mapping archive/restore |
|------|-------------------------------------|----------------------|-----------------------|-------------------------|-------------------------|------------------------------------|
| **admin** | Yes | Yes | Yes | Yes | Yes | Yes |
| **operator** | Yes | Yes | Yes | Yes | Yes | No |
| **runner** | Yes | **No** permission in `ROLE_PERMISSIONS` | No | No | No | No |
| **viewer** / **auditor** | No | No | No | No | No | No |

The **Recent Runs** table always renders **Stop** and **Delete** actions; permission failures appear as errors after the action—verify behavior for non-admin users.

---

## 0) Prerequisites

1. Bring up the stack (see [README.md](../README.md)): e.g. `docker compose up -d --build`.
2. Open the web UI (default `http://localhost:8080`).
3. Sign in with a user whose role you intend to test (default admin: `admin` / `admin123` per README).
4. Ensure **`GET /api/v1/flows`** would succeed (Runs page loads flow dropdown). If it fails, you see an error sourced from `flows` load.
5. Have at least one **valid plan**: default `sim_actors.json`, or a GUI plan under `runs/gui-plans/` listed after **Config** has registered plans. Plans must include `users[]` and `stores[]` that match real last-mile credentials in `.env` / API environment for runs to succeed; structural tests can still use invalid combos to assert **validation errors**.

---

## 1) Authentication and shell

| Step | Action | Pass criteria |
|------|--------|----------------|
| 1.1 | Open `/auth/login`, sign in | Redirect to `/overview` (or intended post-login route). |
| 1.2 | Use **Theme toggle** | Theme switches; persists on refresh (local storage). |
| 1.3 | **AppNav** | `Overview`, `Runs`, `Config`, `Schedules`, `Archives`, `Retention`, `Admin` present per role; active route highlighted. |
| 1.4 | **Sign out** from profile menu | Returns to login; protected routes redirect. |

---

## 2) `/runs` — layout and health

| Step | Action | Pass criteria |
|------|--------|----------------|
| 2.1 | Open **Runs** | Header shows; **API health** reflects `/healthz` polling (~10s). |
| 2.2 | Break API (stop `api` container) | Health shows failure; error surface for `healthz` / runs refresh as implemented. |
| 2.3 | **Run statistics** | Summary cards/charts load when dashboard API succeeds. |
| 2.4 | **Viewer** (no `runs` create) | **Start Run** / **Saved Profiles** blocks hidden; message about contacting admin. **Recent Runs** still visible if `runs` read allowed. |

---

## 3) Start Run — layout and field help

| Step | Action | Pass criteria |
|------|--------|----------------|
| 3.0.1 | Open **Start Run** (operator/admin) | **Active runs** strip is at the top; **Live Console** is full width below it; **Launch settings** form and **Field help** sidebar are below the console. |
| 3.0.2 | With no active runs | **Active runs** panel shows eyebrow, title “No runs in progress”, helper text, and **Go to launch settings** button (not a bare muted line). |
| 3.0.13 | With no active runs | **Live Console** is collapsed by default; header shows “No run selected”. Expand to view log area. |
| 3.0.3 | Start or select an active run | Active run chip appears; clicking a chip selects that run for the console (same as **Console** in Recent Runs). |
| 3.0.4 | Focus **Flow** and select `doctor` | Sidebar shows **Selected** with `doctor` and doctor-specific copy immediately; **All options** is collapsed by default. |
| 3.0.5 | Expand **All options** | Full options table appears; the `doctor` row is highlighted. |
| 3.0.6 | Change any launch field, then wait ~1s | **Run summary** appears in the sidebar (severity badge, summary lines, warnings). Brief “Updating run summary…” while debouncing. |
| 3.0.7 | Check below command preview | There is **no** Execution Impact panel under **Resolved command preview** (run summary lives in the sidebar only). |
| 3.0.8 | Blur away from the form | Field help returns to idle intro links; **Run summary** remains visible after debounce. |
| 3.0.9 | Narrow viewport (&lt; ~1024px) | Field help can collapse behind **Show** / **Hide**; focusing a field auto-expands help. |
| 3.0.10 | Leave **Store** empty with `sim_actors.json`, wait ~1s | **Resolved scope** shows plan default store `FZY_926025` with source “plan default”. |
| 3.0.11 | Type store `FZY_999` in **Store**, wait ~1s | **Resolved scope** shows `FZY_999` with source “form override” (scope is not duplicated inside **Run summary** details). |
| 3.0.12 | Clear **Phone** (plan default), wait ~1s | **Resolved scope** shows default phone from plan with “plan default” or “first user in plan” source tag. |

---

## 4) Start Run — core controls (every user with `runs` create)

These map to `RunCreateRequest` in `web/src/lib/api.ts`.

### 4.1 Flow and derived mode

| Step | Action | Pass criteria |
|------|--------|----------------|
| 3.1.1 | Open **Flow** dropdown | Options match `GET /api/v1/flows` → `flows` array (sorted preset names). |
| 3.1.2 | Select each flow in turn | **Resolved mode** (`trace` or `load`) matches `capabilities[flow].resolved_mode`. |
| 3.1.3 | Switch `load` ↔ `trace` preset | Load-only inputs (**Users**, **Orders**, **Interval**, **Reject**, **Continuous**) appear only when resolved mode is `load`. **Suite** / **Scenarios** disabled unless trace. |

**Exhaustive flow list:** Use the Flow dropdown as the source of truth (same as `FLOW_PRESETS` keys). Minimum smoke: run **`doctor`** once and **`load`** once; full matrix: one launched run per flow (or dry-run via command preview only where runs are expensive).

### 4.2 Timing

| Step | Action | Pass criteria |
|------|--------|----------------|
| 3.2.1 | Toggle **Timing** `fast` / `realistic` | **Resolved command preview** includes `--timing fast` or `--timing realistic`. |

### 4.3 Plan

| Step | Action | Pass criteria |
|------|--------|----------------|
| 3.3.1 | **Plan** dropdown | `sim_actors.json` plus every `SimulationPlan` from Config (`fetchSimulationPlans`). |
| 3.3.2 | Remove a plan from server then refresh | If current plan invalid, form resets to `sim_actors.json` (`allowedPlanPaths` effect on `runs/page.tsx`). |

### 4.4 Store ID and Phone

| Step | Action | Pass criteria |
|------|--------|----------------|
| 3.4.1 | Leave blank | Preview has no `--store` / `--phone`. |
| 3.4.2 | Enter store and phone from plan | Preview shows `--store` and `--phone`; run succeeds against last-mile when values ∈ plan. |
| 3.4.3 | Enter values **not** in plan | Run fails with plan-scope error (simulator validates). |
| 3.4.4 | Focus **Store ID** or **Phone** with a plan actor selected | Field help **Selected** lists detail rows (name, GPS, etc.); no metadata grid under the dropdown. **Resolved scope** still previews defaults when fields are blank. |

---

## 5) Advanced Mode Overrides

| Step | Action | Pass criteria |
|------|--------|----------------|
| 4.1 | Expand **Show Advanced Mode Overrides** | **Mode Override**, **Suite (trace only)**, **Scenarios (trace only)** visible. |
| 4.2 | **Mode Override** = `load` on a trace-default flow | Resolved mode shows `load`; suite/scenarios cleared in form logic; load inputs visible. |
| 4.3 | **Mode Override** = `trace` on `load` flow | Trace inputs enabled; load numeric fields cleared when switching to trace in override handler. |
| 4.4 | **Suite** dropdown | Options = `capabilities[flow].available_suites` (all trace suite keys for trace flows). |
| 4.5 | **Scenarios** multi-select | Options = `available_scenarios` (full `TRACE_SCENARIOS` list for trace). Cmd-click / shift per OS to select multiple; preview lists one `--scenario` per selection. |
| 4.6 | **hasAdvancedOverrides** hint | With mode/suite/scenarios set, UI shows overridden resolved mode indicator (see `RunLaunchPanel` “overridden” label when `hasAdvancedOverrides`). |

---

## 6) Load-only numeric fields

When **resolved mode** is `load`:

| Step | Field | Suggested test value | Pass criteria (preview + API) |
|------|-------|----------------------|--------------------------------|
| 5.1 | **Users** | `2` | `--users 2` |
| 5.2 | **Orders** | `3` | `--orders 3` |
| 5.3 | **Interval (sec)** | `5` or `2.5` | `--interval …` |
| 5.4 | **Reject Rate** | `0` | `--reject 0` |
| 5.5 | **Continuous** | checked | `--continuous` present |
| 5.6 | Reject `1.5` or `-0.1` | Red **modeValidationError**: reject must be 0–1. |
| 5.7 | Users `0` or Orders `0` | Validation error users/orders ≥ 1. |

---

## 7) Checkboxes (shared + mode-gated)

Toggle each and confirm **Resolved command preview** (`commandPreview` on `runs/page.tsx`):

| Checkbox | CLI when checked | Notes |
|----------|------------------|--------|
| **All Users** | `--all-users` | |
| **Strict Plan** | `--strict-plan` | |
| **Skip App Probes** | `--skip-app-probes` | |
| **Skip Store Dashboard Probes** | `--skip-store-dashboard-probes` | |
| **No Auto Provision** | `--no-auto-provision` | |
| **Post-Order Actions** | `--post-order-actions` | |
| **Continuous** | `--continuous` | Only in load mode in UI |
| **Enforce Websocket Gates** | `--enforce-websocket-gates` | When **unchecked**, preview does **not** emit `--no-enforce-websocket-gates` (matches API `_build_command`). |

**Combinations:** Pick one trace run with **only** `Enforce Websocket Gates`; one with **Strict Plan** + **Skip App Probes**; one load run with **All Users** + **Continuous** (careful—infinite until stop).

---

## 8) Client-side validation matrix (`modeValidationError`)

These block **Start Simulation** (button disabled) on `runs/page.tsx`:

| # | Setup | Expected message |
|---|--------|-------------------|
| 7.1 | Trace + **Continuous** checked | Continuous is only valid in load mode. |
| 7.2 | Trace + any of **Users** / **Orders** / **Interval** / **Reject** set | users/orders/interval/reject are only valid in load mode. |
| 7.3 | Load + **Suite** non-empty or **Scenarios** non-empty | suite/scenarios are only valid in trace mode. |
| 7.4 | Reject outside [0, 1] | Reject rate must be between 0 and 1. |
| 7.5 | Users or orders &lt; 1 | Users must be >= 1 / Orders must be >= 1. |

Clear fields and confirm button re-enables.

---

## 9) Start Simulation, live console, cancel

| Step | Action | Pass criteria |
|------|--------|----------------|
| 8.1 | With valid form, **Start Simulation** | New row in **Recent Runs**; selection jumps to new id; **Starting…** then idle. |
| 8.2 | **Run Live Console** | Log lines stream / refresh for **running** run (~1s polling). |
| 8.3 | Select active run, **Stop Selected Run** | Cancel API called; status moves to cancelled/failed per backend. **Runner** role: expect permission error if backend enforces (UI still offers stop from table). |
| 8.4 | **Stop** from Recent Runs row | Same as cancel. |

---

## 10) Saved Profiles

| Step | Action | Pass criteria |
|------|--------|----------------|
| 9.1 | Fill form, **Save Current Form as Profile** | Profile appears in table; snapshot line shows `flow · timing · plan`. |
| 9.2 | **Load** on a profile | Form repopulates including suite/scenarios/checkboxes/numerics. |
| 9.3 | **Update Selected Profile** | Persisted changes after edit. |
| 9.4 | **Launch** | New run created without manually pressing Start Simulation. |
| 9.5 | **Delete** profile | Row removed from active profiles; profile appears under `/archives` → **Archived Profiles** with Restore action. |
| 9.6 | **Save as profile** (under command preview) | Scrolls to profiles section; focuses profile name input (`onSaveAsProfileShortcut`). |

---

## 11) Recent Runs table

| Step | Action | Pass criteria |
|------|--------|----------------|
| 10.1 | Row click / **View** | Navigates to `/runs/{id}`. |
| 10.2 | **Pagination** | Change page; offset updates; different slice of runs. |
| 10.3 | Columns **Launch** | Shows `trigger_source`, `trigger_label`, optional `profile_id` context. |
| 10.4 | **Delete** on completed run (as **admin/operator**) | Modal confirms; run removed from active list and appears in `/archives` Archived Runs with Restore action. |
| 10.5 | **Delete** disabled styling | Active runs: Delete button `disabled` when `isActiveStatus`. |

---

## 12) Run detail `/runs/[id]`

| Step | Action | Pass criteria |
|------|--------|----------------|
| 11.1 | **Overview** tab | Header, status, links back. |
| 11.2 | **Story** / **Report** | Markdown renders when artifact paths exist. |
| 11.3 | **Traffic** (events) | Paginated fetch; total count. |
| 11.4 | **Console** | Log tail loads. |
| 11.5 | **Execution** | Snapshot panel when available. |
| 11.6 | **Execution** tab | Snapshot panel; **Replay Exact Run** when `onReplay` wired (`replayRun` → new run id). |

---

## 13) Flow Planner & Command Guide

| Step | Action | Pass criteria |
|------|--------|----------------|
| 12.1 | Expand section | Tabs: Flow Matrix, Commands, Flags, Plan, Rules, Failures, Architecture, Guide. |
| 12.2 | Switch tabs | Embedded content changes (markdown from repo copies in `runs/page.tsx`). |

---

## 14) Other routes (smoke per role)

Use [SIMULATOR_GUIDE.md](../SIMULATOR_GUIDE.md) **Operator GUI** for screen semantics.

| Route | Minimal test |
|-------|----------------|
| `/overview` | Cards/charts load; latest run hero; link to run detail. |
| `/config` | List/edit simulation plans; email panel if present; permission `simulation_plans` / config APIs. |
| `/schedules` | Create draft schedule, preview, pause/resume, manual trigger (as permitted). |
| `/archives` | Browse archived runs/profiles/schedules/integration mappings; restore from archive actions. |
| `/retention` | Policies visible; **operator** read-only vs **admin** `retention` update. |
| `/admin/users` | **Admin** only: user CRUD. |
| `/admin/system` | **Admin**: system settings (e.g. allowed timezones). |

---

## 15) Trace scenarios — how to cover “all” from the GUI

The GUI does not run “all scenarios” as one click; it sends `suite` and/or repeated `--scenario` values.

| Strategy | Steps |
|----------|--------|
| **A — By suite** | For flow `doctor` (or `full` / `audit`), set **Suite** to each of `core`, `payments`, `menus`, `store`, `doctor`, `full`, `audit` in separate runs (clear multi-scenario between runs). |
| **B — By scenario pick list** | Flow `doctor` (trace), clear **Suite**, in **Scenarios** multi-select choose subsets; run. Repeat until every name in `available_scenarios` has appeared in at least one run’s command (exhaustive = one run per scenario minimum). |
| **C — Single run, many scenarios** | Multi-select many scenarios; preview shows multiple `--scenario`; one trace execution runs them in resolver order (see `resolve_trace_scenarios` in code). |

Cross-check preview against [SIMULATOR_CAPABILITIES.md](SIMULATOR_CAPABILITIES.md) **Trace suites** section for suite membership.

---

## 16) Automated / API regression (optional)

- `tests/test_web_api.py` — API-level regression for run create, flows, etc.
- Playwright or Cypress is **not** required by this repo for the checklist above; add separately if you want full browser automation.

---

## 17) Gaps (GUI vs backend)

| Backend capability | In GUI? |
|--------------------|---------|
| `extra_args` | **No** — test via API or CLI only. |
| `--no-enforce-websocket-gates` explicit | **No** — absence of checkbox = default from env/plan at process start; UI only sends enforce when checked. |

When product adds fields, extend this doc and `RunLaunchPanel` together.
