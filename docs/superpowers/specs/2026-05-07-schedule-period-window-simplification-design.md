# Schedule Period + Window Simplification Design

Date: 2026-05-07
Status: Draft for review
Scope: Scheduling UX and scheduling semantics for both Simple and Campaign schedules

## 1. Goal

Make scheduling understandable for all users by replacing cadence-heavy mental models with a plain-language flow:

1. When does it start?
2. What period should it repeat on?
3. When should it stop?
4. How many runs should happen within each period?

This model must work consistently for both `simple` and `campaign` schedules.

## 2. User-Facing Design

### 2.1 Primary Scheduling Controls (default view)

All schedules (simple and campaign) use the same primary controls:

- `Start at` (`anchor_start_at`, datetime in selected timezone)
- `Period` (`hourly`, `daily`, `weekly`, `monthly`)
- `Stop rule`
  - `Never`
  - `End at` (datetime)
  - `Duration` (e.g., 5 hours)
- `Runs per period` (integer >= 1)

Advanced controls remain behind an `Advanced` toggle (existing blackout dates, optional strict windows, timezone details if not shown by default).

### 2.2 Simple vs Campaign

- `Simple schedule`: one run profile is launched for each scheduled run timestamp.
- `Campaign schedule`: campaign step chain is launched for each scheduled run timestamp.

Scheduling controls are identical; only execution payload differs.

## 3. Scheduling Semantics (Contract)

## 3.1 Core Definitions

- `Period window`: the logical bucket where runs are distributed.
  - `hourly`: current hour window
  - `daily`: current day window
  - `weekly`: full week window
  - `monthly`: full month window
- `Anchor`: first datetime (`anchor_start_at`) that defines recurrence alignment.
- `Runs per period`: desired count of run timestamps in each period window.

## 3.2 Distribution Rule

When `runs_per_period = 1`:
- One run per period at the aligned anchor time.

When `runs_per_period > 1`:
- Runs are auto-distributed evenly across the entire period window.
- For weekly/monthly, distribution is across the whole week/month window (explicit user decision), not constrained to a single day window.

## 3.3 Stop Rule Precedence

Apply in this order:

1. Build candidate timestamps for period window.
2. Remove timestamps before `anchor_start_at`.
3. Apply stop rule:
   - `Never`: keep all future candidates.
   - `End at`: drop candidates after `end_at`.
   - `Duration`: derive `end_at = anchor_start_at + duration`, then apply same filter.
4. If optional blackout logic is enabled, remove candidates on blackout dates.

## 3.4 Feasibility Handling

If the requested `runs_per_period` cannot fit into a valid window after constraints:

- Scheduler computes feasible timestamps only.
- UI and API preview show:
  - requested runs
  - feasible runs
  - reason for reduction
- Save remains allowed (non-fatal) unless feasible runs become zero for all future windows.

## 4. UX Behavior and Preview

Before submit, always show:

- Mode: `Automatic`
- Next run datetime
- Current period run plan (all scheduled timestamps in current period)
- Effective stop point
- Requested vs feasible runs count
- Any warnings (window compression, stop-rule clipping, blackout removal)

This preview is source-of-truth for operator confidence before creating or updating schedules.

## 5. API / Data Shape Changes

Introduce scheduling fields independent of simple/campaign payload:

- `anchor_start_at` (ISO datetime, required)
- `period` (`hourly` | `daily` | `weekly` | `monthly`, required)
- `stop_rule` (`never` | `end_at` | `duration`, required)
- `end_at` (required when `stop_rule=end_at`)
- `duration_seconds` (required when `stop_rule=duration`)
- `runs_per_period` (int >=1, default 1)

Execution model fields remain:

- simple: `profile_id`
- campaign: `campaign_steps`

Preview/Explainability response fields:

- `next_run_at`
- `current_period_runs[]`
- `requested_runs_per_period`
- `feasible_runs_per_period`
- `schedule_warnings[]`

## 6. Worked Examples

### Example A: Daily fixed time

Input:
- Start at: `2026-05-08T10:00:00+01:00`
- Period: `daily`
- Stop rule: `never`
- Runs per period: `1`

Result:
- One run every day at `10:00` local time.

### Example B: Daily, 5 runs per day

Input:
- Start at: `2026-05-08T08:00:00+01:00`
- Period: `daily`
- Stop rule: `never`
- Runs per period: `5`

Result:
- Five evenly spaced run times across each day window.

### Example C: Start in 10 minutes, run for 5 hours

Input:
- Start at: `now + 10 minutes`
- Period: `daily`
- Stop rule: `duration`
- Duration: `5 hours`
- Runs per period: `5`

Result:
- Five timestamps evenly distributed inside the 5-hour effective range.
- No runs scheduled after derived `end_at`.

## 7. Failure/Edge Rules

- If `end_at <= anchor_start_at`, reject request.
- If `duration_seconds <= 0`, reject request.
- If computed future feasible windows = 0, reject as non-actionable.
- DST transitions: all planning in schedule timezone; persist UTC timestamps.
- Past times in current period are skipped; only future timestamps are materialized.

## 8. Rollout and Compatibility

- Existing schedules continue to run under legacy semantics until edited.
- Edited/new schedules use new period-window contract.
- API versioning or compatibility flag may be required if legacy clients post old cadence payloads.

## 9. Acceptance Criteria

1. Users can configure "start + period + stop + runs per period" without understanding internal cadence math.
2. Weekly/monthly multi-run distribution spans full week/month window.
3. Preview clearly shows exact planned runs and warnings before submit.
4. Simple and campaign schedules share one scheduling contract.
5. Operators can express all requested examples without custom/manual workaround.
