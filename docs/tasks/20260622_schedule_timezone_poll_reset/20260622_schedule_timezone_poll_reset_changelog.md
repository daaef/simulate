# Changelog — Schedule timezone poll-reset fix (2026-06-22)

## Layer 1 — High-level
The schedule create/edit form no longer loses user input to the 15-second background refresh. Previously, selecting a timezone (e.g. `Asia/Tokyo`) in the edit form reverted to the machine default (`Africa/Lagos`) within ~10s because the poll re-seeded the field on every cycle. Now, while the form is open, polling refreshes only the schedule list, summary, and timezone policy — every form field the user is editing is left untouched. When the form is closed, default seeding behaves exactly as before. Affected: the schedules create and edit flows.

## Layer 2 — Low-level
File: `web/src/app/(app)/schedules/page.tsx`

1. **`showFormRef` added (~line 208).** Before: only `loadInFlightRef` existed. Now: a `useRef(false)` mirrors the form-open state so the once-registered `setInterval` closure can read the *current* open/closed status instead of its stale captured `showForm`. Chosen per solution.md — a state-variable guard would always read the stale `false`.

2. **Ref-sync effect added (before the polling effect, ~line 308).** Before: nothing kept a ref in sync. Now: `useEffect(() => { showFormRef.current = showForm; }, [showForm])` updates the ref on every `showForm` change.

3. **`load()` seeding block gated (~lines 288–303).** Before: `setProfileId`/`setStepProfileId`/`setTimezone` ran on every `load()` call, including silent polls — `setTimezone(next)` ran unconditionally and overwrote edits. Now: the entire seeding block runs only when `!showFormRef.current` (form closed). Internal logic (allowlist fallback, `defaultScheduleTimezone()`) is unchanged.

## Plan step mapping
- Plan step 1 → change 1. Plan step 2 → change 2. Plan step 3 → change 3. No steps skipped.

## Verification
- `npx tsc --noEmit` → exit 0 (no type errors).
- No `lint` script in the project; ESLint v9 has no flat config present — skipped, not applicable.
- Manual behavioral verification (edit tz, wait ≥2 poll cycles) pending user confirmation in-app.
