# Changelog: Default plan read-only treatment

## Layer 1 — What changed for the user

The default `sim_actors` plan in Config → Plans is now read-only. Operators can inspect it but cannot edit or delete it. A "Create from this plan" button replaces the Save/Delete controls when the default is loaded, producing a named copy pre-filled with the default's content. All other user-created plans are unaffected.

## Layer 2 — What was changed and why

### `api/app/main.py:5566–5572` — `_default_sim_actors_plan_payload()`
- Before: returned `id`, `name`, `path`, `content`.
- After: adds `"is_default": True` to the payload.
- Why: gives the frontend a stable signal without requiring it to pattern-match on the plan id or path string.

### `web/src/lib/api.ts:534–539` — `SimulationPlan` type
- Before: `{ id, name, path, content }`.
- After: adds `is_default?: boolean`.
- Why: typed signal consumed by the config page; optional so existing user-created plans remain valid.

### `web/src/app/(app)/config/page.tsx:167–171` — `isDefaultPlan` derivation
- Before: no concept of a default plan in component state.
- After: `const isDefaultPlan = selectedPlan?.is_default === true` derived from `selectedPlan`.
- Why: single source of truth for all conditional rendering in the editor panel.

### `web/src/app/(app)/config/page.tsx` — editor panel
- Before: name input, textarea, and Save/Delete buttons rendered identically for all plans.
- After:
  - Name input and textarea gain `readOnly={isDefaultPlan}`.
  - `aria-invalid` and JSON validation messages suppressed when read-only (no edits possible).
  - A muted "Default plan — read-only" label appears above the textarea when `isDefaultPlan`.
  - Action buttons branch: default plan shows a single "Create from this plan" button (calls `startNewPlan()`); all other plans show the original Save/Delete pair.
- Why: matches UI affordances to backend constraints; removes confusing 400 errors from save/delete attempts on the reserved plan.
