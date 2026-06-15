# Solution: is_default flag + read-only editor treatment

**Proposed approach:**
1. Add `"is_default": True` to `_default_sim_actors_plan_payload()` in `main.py`.
2. Add `is_default?: boolean` to the `SimulationPlan` TS type in `api.ts`.
3. In `config/page.tsx`, derive `isDefaultPlan = selectedPlan?.is_default === true` and:
   - Disable the textarea and plan name input.
   - Replace "Save Plan" / "Delete Selected" with a single "Create from this" button that calls `startNewPlan()` — which already populates the editor with the selected plan's content and clears `selectedPlanId` so the next save creates a new plan.
   - Show a muted read-only label above the editor.

**Alternatives rejected:**
- *New "Clone" API endpoint* — unnecessary; `createSimulationPlan()` + `startNewPlan()` already compose to produce the correct result without a round-trip.
- *Hide the default plan from the list* — removes visibility; operators need to inspect the default actors.

**Performance impact:** Neutral — one extra boolean field in the plan list payload (~2 bytes per plan).

**Performance delta:** N/A — no rendering path or query changed.

**Trade-offs:** None material. Backend guard remains, frontend now matches backend intent.

**Dead code audit:** `PLAN_TEMPLATE` constant in `config/page.tsx` becomes the fallback only when no plan is selected and no editor content exists — still needed.
