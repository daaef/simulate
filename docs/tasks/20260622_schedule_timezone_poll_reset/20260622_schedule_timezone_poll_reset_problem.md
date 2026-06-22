# Problem — Schedule timezone reverts while editing

## Root cause
The 15s polling `load()` unconditionally re-seeds the `timezone` form-input state from the machine default on every refresh, overwriting whatever the user selected in the open edit/create form.

## Symptoms
- Editing a schedule's timezone to `Asia/Tokyo` reverts to `Africa/Lagos` (machine default) within ~10s.
- Same class of silent overwrite applies to any form field `load()` seeds.

## Affected files / functions
- `web/src/app/(app)/schedules/page.tsx`
  - `load()` — lines 274–306; the offending block is 290–298 (`setTimezone(next)` runs every call).
  - Polling effect — lines 308–332: `setInterval(refresh, 15000)` + `focus`/`visibilitychange` triggers, all calling `load({ silent: true })`.
  - `timezone` state — line 185.
  - `startEditSchedule` — line 502 seeds the schedule's real tz, immediately clobbered by the next poll.
  - Form-open signal `showForm` — set true at 551 (edit) and 752 (create); set false on submit (478) / cancel (558).

## Blast radius
Single page component. `timezone` is consumed only by the form (`submit` payload line 453, `<select>` ~1010). No other screen or service reads this state.

## Constraints
- The 15s refresh of the schedule LIST / summary / timezone policy must keep working — only form-input seeding must stop during editing.
- A NEW (create) form still needs a valid default timezone that satisfies the allowlist policy.
- `defaultScheduleTimezone()` fallback-to-allowlist logic (line 296) must be preserved.

## Edge cases
- The `setInterval` is registered once (deps `[]`), so its `refresh` closure captures the **first-render** `load`, which sees stale `showForm`/`profileId`. A guard reading the state variable directly would always observe the stale `false` and never engage. The guard must read a **ref**.
- Post-submit `load()` runs right after `setShowForm(false)`; the ref may still read `true` for that one call — acceptable, since we do not want to reset a just-saved/closing form.
