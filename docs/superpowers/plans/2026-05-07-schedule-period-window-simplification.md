# Implementation Plan: Schedule Period + Window Simplification

Date: 2026-05-07
Source Spec: `docs/superpowers/specs/2026-05-07-schedule-period-window-simplification-design.md`
Status: Ready for implementation

## 1) Outcome and Scope

Implement a single scheduling contract for both simple and campaign schedules:
- `start at` + `period` + `stop rule` + `runs per period`
- predictable distribution across period windows
- pre-submit preview showing exact expected behavior

In scope:
- schedule API model and persistence updates
- deterministic planner + explainability payload
- schedule form UX simplification with advanced toggle
- docs and tests

Out of scope:
- cron syntax support
- distributed scheduler architecture changes
- retention/alerts redesign beyond required schedule metadata integration

## 2) Technical Decisions (Locked)

1. Periods: `hourly`, `daily`, `weekly`, `monthly`.
2. Multi-run distribution:
- `runs_per_period > 1` is evenly spaced across whole period window.
- weekly/monthly use full week/full month windows.
3. Stop rules:
- `never`, `end_at`, `duration`.
4. Simple/campaign share schedule timing model; execution payload differs only by target (`profile_id` vs `campaign_steps`).
5. Preview is authoritative and required before submit.
6. Legacy schedules remain runnable until edited; edited/new schedules use new model.

## 3) Backend Implementation

### 3.1 Data Model and Migration

Files:
- `api/app/schedules/models.py`
- `api/app/main.py`

Add new schedule fields:
- `anchor_start_at` (ISO datetime)
- `period` (`hourly|daily|weekly|monthly`)
- `stop_rule` (`never|end_at|duration`)
- `end_at` (nullable datetime)
- `duration_seconds` (nullable int)
- `runs_per_period` (int, default 1)

Explainability fields persisted/returned:
- `next_run_at`
- `next_run_reason`
- `current_period_runs` (computed response field)
- `requested_runs_per_period`
- `feasible_runs_per_period`
- `schedule_warnings`

Migration strategy:
- add nullable columns for new fields
- keep existing cadence columns for compatibility period
- for legacy rows: mark internally as `legacy_semantics=true` and continue old behavior unless user edits

### 3.2 Validation Rules

Request validation gates:
1. `anchor_start_at` required for new-model schedules.
2. `period` required and enum constrained.
3. `runs_per_period >= 1`.
4. `stop_rule=end_at` requires `end_at` and `end_at > anchor_start_at`.
5. `stop_rule=duration` requires `duration_seconds > 0`.
6. reject invalid mixed input (both `end_at` and `duration_seconds` when not required).
7. timezone validity still enforced by current policy endpoint.

### 3.3 Scheduler Planner

Implement planner functions in `api/app/main.py`:
1. Build period window boundaries from schedule timezone and reference time.
2. Generate candidate timestamps aligned to `anchor_start_at`.
3. Evenly distribute N timestamps within period window when `runs_per_period > 1`.
4. Filter by stop rule (`never`, `end_at`, `duration`).
5. Filter blackout dates if configured.
6. Skip already-past timestamps in current period.
7. Return:
- `next_run_at`
- `current_period_runs[]`
- feasibility metadata
- warnings and reason code

Reason codes:
- `computed`
- `window_clipped`
- `blackout_skipped`
- `outside_stop_range`
- `no_future_run`

### 3.4 Trigger Loop Integration

Update due-check loop to consume planner output:
- schedule due if `next_run_at <= now` and status is active
- after trigger/skip/failure, recompute planner output and persist latest metadata
- preserve pause/resume/disable/delete/restore semantics

## 4) Frontend Implementation

Files:
- `web/src/lib/api.ts`
- `web/src/app/(app)/schedules/page.tsx`

### 4.1 Form Simplification

Default controls:
- Start at
- Period
- Stop rule (never/end_at/duration)
- Runs per period

Advanced toggle controls:
- blackout dates
- optional run window fields (if retained)
- timezone details (if not already visible)

### 4.2 Preview Panel (Required)

Before submit show:
- mode (automatic)
- next run timestamp
- current period run list
- effective end point
- requested vs feasible count
- warnings

Submission behavior:
- send new model fields
- for legacy schedules being edited, migrate payload into new model and show conversion summary

### 4.3 Schedule List

Show server payload directly:
- next trigger
- reason/warnings
- feasibility counts
- execution mode label if provided

## 5) API Compatibility Plan

1. Keep existing schedule endpoints unchanged (`/api/v1/schedules*`).
2. Accept both legacy and new payloads during transition window.
3. Response always includes normalized new-model explainability fields.
4. If legacy payload used, include `compat_mode: legacy` in response metadata.

## 6) Test Plan

### 6.1 Unit Tests (planner)

Add planner-focused tests for:
1. hourly/daily/weekly/monthly single-run alignment
2. even spacing for multi-run daily/weekly/monthly
3. start-in-future behavior
4. end_at clipping
5. duration clipping
6. blackout filtering
7. DST boundary stability
8. feasible < requested warning behavior

### 6.2 API Tests

Extend `tests/test_web_api.py` for:
1. create/update schedule with each stop rule
2. validation failures for invalid combinations
3. response includes preview/explainability fields
4. simple and campaign parity on schedule timing metadata
5. lifecycle endpoints keep expected state transitions

### 6.3 UI Tests

Add/extend tests for:
1. simplified form defaults
2. advanced toggle visibility
3. preview updates as inputs change
4. warning display for infeasible counts

## 7) Documentation Updates

Update in same patch:
- `README.md`
- `SIMULATOR_GUIDE.md`

Doc changes:
1. Replace cadence-heavy terminology with period-window model.
2. Add field reference and stop-rule matrix.
3. Add worked examples from spec.
4. Add troubleshooting keyed to reason/warning payloads.
5. Add compatibility note for legacy schedules.

## 8) Implementation Sequence

1. Backend schema + request/response model changes.
2. Planner implementation + due-loop integration.
3. API tests for validation/planner semantics.
4. Frontend form simplification + preview panel.
5. Frontend tests.
6. Docs update and final regression run.

## 9) Completion Criteria

Done when all are true:
1. Users can schedule via start/period/stop/runs without cadence interpretation.
2. Preview accurately matches backend-computed current period runs.
3. Weekly/monthly multi-run distribution spans entire week/month windows.
4. Simple and campaign schedules share the same timing contract.
5. Tests pass and docs reflect final behavior.
