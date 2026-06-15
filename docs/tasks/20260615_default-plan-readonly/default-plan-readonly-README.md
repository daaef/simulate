# Default Plan Read-Only Treatment

> Completed: 2026-06-15  
> Files changed: `api/app/main.py`, `web/src/lib/api.ts`, `web/src/app/(app)/config/page.tsx`  
> Checklist items fixed: 1 (accessibility — read-only notice DOM order + `aria-describedby`)

---

## What happened (Layman)

The simulator has a master settings file called the "default plan" — think of it like a factory-reset template for your simulation. Previously, the Config page let you accidentally try to save changes to it or delete it, which just caused a confusing error. Now the page recognises the default plan and shows it as read-only (you can look but not edit). There's a single "Create from this plan" button instead of Save/Delete: clicking it makes a fresh editable copy that you can rename and customise freely without touching the original.

---

## How it works (Pseudocode)

1. The server sends the list of plans; for the default plan it also includes a flag: `is_default = true`.
2. The page checks: is the currently selected plan the one with `is_default = true`?
3. If yes — show a "read-only" notice at the top of the editor panel, lock the name field and the JSON editor so they cannot be typed in, and show only a "Create from this plan" button.
4. If the operator clicks "Create from this plan" — copy the default plan's content into a new unsaved draft, set the name to `"<default name> (Copy)"`, and make the editor editable again.
5. The operator can now rename and save the copy as a new plan; the original default is untouched.
6. If the selected plan is not the default — show the normal Save and Delete buttons.

---

## The implementation (Code-level)

**Changed files:**
- [api/app/main.py:5566](api/app/main.py#L5566) — adds `"is_default": True` to the default plan payload
- [web/src/lib/api.ts:534](web/src/lib/api.ts#L534) — adds `is_default?: boolean` to `SimulationPlan` type
- [web/src/app/(app)/config/page.tsx:172](web/src/app/(app)/config/page.tsx#L172) — derives `isDefaultPlan`; read-only inputs; swapped action buttons; `aria-describedby`

**Key changes:**

```python
# main.py — Before
return {
    "id": DEFAULT_SIM_ACTORS_PLAN_ID,
    "name": name,
    "path": "sim_actors.json",
    "content": content,
}

# main.py — After
return {
    "id": DEFAULT_SIM_ACTORS_PLAN_ID,
    "name": name,
    "path": "sim_actors.json",
    "content": content,
    "is_default": True,      # <-- signal to the frontend
}
```

```ts
// api.ts — Before
export type SimulationPlan = {
  id: string; name: string; path: string; content: SimulationPlanContent;
};

// api.ts — After
export type SimulationPlan = {
  id: string; name: string; path: string; content: SimulationPlanContent;
  is_default?: boolean;   // optional: absent on user-created plans
};
```

```tsx
// config/page.tsx — derived flag (boolean derivation pattern)
const isDefaultPlan = selectedPlan?.is_default === true;

// Action buttons — conditional render pattern
{isDefaultPlan ? (
  <button type="button" onClick={startNewPlan}>Create from this plan</button>
) : (
  <div className="grid two">
    <button …>Save Plan / Create Plan</button>
    <button …>Delete Selected</button>
  </div>
)}
```

**Accessibility fix (Phase 3):** Read-only notice moved above the name input; both the name `<input>` and the `<textarea>` receive `aria-describedby="plan-readonly-notice"` so screen readers announce the read-only context before the user interacts with the field.

---

## Why this way (Advanced)

**Backend as source of truth (SRP).** The backend already enforced the constraint via `_raise_if_reserved_simulation_plan_id` — the frontend was just unaware of it. Adding `is_default` to the payload makes the server the single authority: the UI does not need to match on plan id strings or path patterns, which would be fragile if the default plan id ever changes.

**Optional field, not a boolean enum.** `is_default?: boolean` is absent on user-created plans rather than `is_default: false`. This keeps the payload minimal and means existing API consumers are unaffected. `undefined === true` is `false` in JavaScript, so the guard `selectedPlan?.is_default === true` is safe with no nullish coalescing needed.

**`startNewPlan()` reuse.** The existing function already does exactly what "Create from this" needs: copies the current editor value into a new draft and clears `selectedPlanId`. Re-using it means zero new state, zero new async paths, and zero new API calls. A dedicated "clone" endpoint was rejected on this basis.

**`is_default` does not leak into plan content.** The field is injected at the API wrapper layer (`_default_sim_actors_plan_payload`), not into the JSON file on disk. The `content` key holds only what `sim_actors.json` contains. If a user clones the default and saves it, `is_default` is not present in the saved file — `_write_simulation_plan` writes `request.content` only.

**WCAG 2.2 SC 1.3.1 (Info and Relationships).** The "read-only" relationship must be programmatically determinable. The `readonly` HTML attribute maps to `aria-readonly="true"` implicitly, which satisfies the attribute requirement. The `aria-describedby` association additionally ensures the advisory text ("Default plan — read-only") is announced in the input's accessible description — not just visually proximate.

---

## Verification

- [ ] Open `/config` → Plans tab. The default `sim_actors` plan appears first.
- [ ] Click "Load" on the default plan — name input and JSON textarea are not editable (cursor shows as text, not caret).
- [ ] Only "Create from this plan" button is visible; Save/Delete are absent.
- [ ] Click "Create from this plan" — editor becomes editable, name is set to `"<name> (Copy)"`, `selectedPlanId` is cleared (button label reads "Create Plan").
- [ ] Save the copy — new plan appears in the list; default plan is unchanged.
- [ ] Load any non-default plan — Save Plan and Delete Selected buttons reappear.
- [ ] Run `cd web && pnpm run build` — no type errors.
