# Ideas backlog — GUI and functional

Opportunities and directions for the simulator **web UI** and **runtime/product** behavior. Nothing here is committed work; treat as a brainstorm list for prioritization.

---

## A) GUI — Runs and launch

| Idea | Why it might help |
|------|---------------------|
| **Curated preset profiles** | Seed or ship 3–6 named profiles (daily doctor, `core` trace, bounded load smoke, gates-on doctor) so operators launch consistent checks without rebuilding the form. Pair with schedules. |
| **`extra_args` in advanced UI** | Optional collapsible field or tokenized input for power users; today API/CLI only ([GUI_TESTING.md](GUI_TESTING.md) gap). |
| **Explicit “no enforce websocket gates”** | When gates default on in env, UI could send a negative flag for one-off runs; today only “enforce when checked” is mirrored in the command builder. |
| **Run cost / duration hints** | Next to flow or suite, show typical duration or “long run” badge from last N runs’ `finished_at - started_at`. |
| **Dry-run validate** | Button that calls a lightweight API to validate plan + flags without queuing a run (fast feedback for strict plan / coupon / Stripe config). |
| **Compare two runs** | Side-by-side diff of two `execution_snapshot` or summary metrics from the same flow/plan. |
| **Launch from Overview** | One-click “repeat last doctor” or “open Runs with form prefilled” from Latest Run hero. |
| **Profile folders / tags** | Group profiles by team or environment (`prod-like`, `staging`, `menu-only`). |
| **Keyboard shortcuts** | e.g. `S` start (when valid), `/` focus command preview, `Esc` collapse panels. |
| **Accessibility pass** | Scenario multi-select, tables, and modals through screen reader + focus order audit. |

---

## B) GUI — Run detail and artifacts

| Idea | Why it might help |
|------|---------------------|
| **Event search / filter** | In Traffic tab: filter `events.json` by actor, scenario, severity, HTTP path. |
| **Download bundle** | Zip `events.json` + `report.md` + `story.md` + log in one click for tickets. |
| **Shareable read-only link** | Time-limited signed URL to run detail for vendors without full app accounts. |
| **Critical findings panel on detail** | Same filter as Overview “Critical Findings” but scoped to this run with deep links into Traffic rows. |
| **Timeline scrubber** | Visual merge of log timestamps and HTTP milestones (when metrics API richer). |

---

## C) GUI — Overview, health, and posture

| Idea | Why it might help |
|------|---------------------|
| **SLO strip** | “Last successful doctor within 24h” with green/amber/red against an explicit policy target. |
| **Drill-down from charts** | Click flow distribution slice → prefiltered Runs list. |
| **Incident mode** | Compact dashboard: active runs, last failure, websocket 502 count, link to `check_lastmile_ws` doc. |

---

## D) GUI — Config, schedules, admin

| Idea | Why it might help |
|------|---------------------|
| **Plan JSON lint in browser** | Schema-aware editor with inline errors before save (monaco + JSON schema from backend). |
| **Schedule templates** | “Daily 08:00 doctor” wizard with preview of next N fires (reuse schedule preview API). |
| **Audit log for admin actions** | Who changed retention, deleted runs, changed system timezones. |
| **Role simulator** | Admin UI to “view as role” read-only to verify permission matrix ([GUI_TESTING.md](GUI_TESTING.md)). |

---

## E) Functional — Simulator runtime and fidelity

| Idea | Why it might help |
|------|---------------------|
| **Named checkpoint assertions** | First-class “expect order status X before PATCH Y” library shared by trace and reporting. |
| **Synthetic negative inject** | Separate tool class (not passive observer) for malformed client / double-subscribe tests called out in architecture discussions. |
| **Per-scenario timeout multipliers** | `auto_cancel` vs `doctor` need different ceilings; one global timeout is coarse. |
| **Stripe / webhook sub-probes** | Optional trace segment that only validates webhook path without full order (where product supports it). |
| **Menu mutation dry-run** | Plan flag: “report what would be created” without POSTing fixtures. |
| **Parallel trace stores** | Optional fan-out across plan `stores[]` for same suite (expensive; behind flag). |

---

## F) Functional — API, retention, and ops

| Idea | Why it might help |
|------|---------------------|
| **Run labels / freeform tags** | User-defined tags on runs for search (`#menu`, `#incident-4412`). |
| **Webhook on run terminal** | Notify external pager on `failed`/`succeeded` with signed payload. |
| **Retention simulation** | “What would be purged under current policy?” without deleting. |
| **Export runs table CSV** | For auditors: filter by date + flow + status → download. |
| **Rate limits on launch** | Per-user or global cap to avoid accidental load storms from GUI. |

---

## G) Testing and quality

| Idea | Why it might help |
|------|---------------------|
| **Playwright smoke** | Small suite: login → start `doctor` fast → wait terminal → open detail tab; runs in CI against compose stack. |
| **Contract test for `/api/v1/flows`** | Assert `capabilities` keys match backend `flow_capabilities()` shape so UI never silently degrades. |
| **Golden command snapshots** | Jest tests for `commandPreview` builder strings for representative forms. |

---

## How to use this doc

- **Promote** an idea by moving it to an issue or implementation tracker with acceptance criteria.
- **Reject** explicitly (strike through or delete) when decided against to avoid re-litigation.
- **Link** shipped work back here so the list stays honest.

If you adopt **preset profiles**, consider a short subsection in [SIMULATOR_GUIDE.md](../SIMULATOR_GUIDE.md) describing the blessed names and when to use each.
