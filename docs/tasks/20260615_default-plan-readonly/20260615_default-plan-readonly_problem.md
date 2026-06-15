# Problem: Default plan is editable/deletable in the UI

**Root cause:** `SimulationPlan` carries no `is_default` flag, so the config UI renders the same Save/Delete controls for the `sim-actors` default plan as for any user-created plan.

**Symptoms:**
- Loading the default plan and clicking "Save Plan" returns a 400 from the backend (`_raise_if_reserved_simulation_plan_id`), but the error message is cryptic.
- "Delete Selected" similarly fails with a 400 and leaves the user confused.
- No affordance to create a copy from the default — only a generic "New" button that ignores the default's content unless the user manually loads it first.

**Affected files / functions:**
- `api/app/main.py:5557` — `_default_sim_actors_plan_payload()` omits `is_default`
- `web/src/lib/api.ts:534` — `SimulationPlan` type has no `is_default` field
- `web/src/app/(app)/config/page.tsx:462–473` — editor action buttons don't branch on default plan

**Blast radius:** Config page `/config` only. The runs page uses `SimulationPlan` for plan selection but does not expose edit/delete.

**Constraints:**
- Backend protection (`_raise_if_reserved_simulation_plan_id`) must stay — defence in depth.
- No new API endpoints needed; `startNewPlan()` already handles the copy flow correctly.
