# Plan: Plan-Default Actor Selection

## Implementation steps

### Step 1 — `api/app/runs/models.py`: add plan-default flags (trivial)
Add `store_is_plan_default: Optional[bool] = None` and `phone_is_plan_default: Optional[bool] = None` to `RunCreateRequest`.  
**AC:** Python `RunCreateRequest` accepts both new fields; existing requests without them still deserialise correctly.

### Step 2 — `web/src/lib/api.ts`: add plan-default flags to TypeScript type (trivial)
Add `store_is_plan_default?: boolean` and `phone_is_plan_default?: boolean` to the `RunCreateRequest` type.  
**AC:** TypeScript type-checks pass; no existing callers break.

### Step 3 — `web/src/components/runs/LaunchActorSelect.tsx`: emit plan-default signal (low)
Change `onChange` prop signature to `(value: string, isPlanDefault: boolean) => void`. When `ACTOR_SELECT_DEFAULT` is chosen, call `onChange("", true)`. For any other selection (specific actor or "Other"), call `onChange(value, false)`.  
**AC:** Selecting "Plan default" in the dropdown fires `isPlanDefault=true`; selecting any specific store/phone fires `isPlanDefault=false`.

### Step 4 — `web/src/components/runs/RunLaunchPanel.tsx`: wire plan-default flags into form state (low)
Update the two `LaunchActorSelect` `onChange` handlers to also set `store_is_plan_default` / `phone_is_plan_default` on the form. Store handler: `onChange={(store_id, isPlanDefault) => onFormChange((prev) => ({ ...prev, store_id, store_is_plan_default: isPlanDefault }))}`. Phone handler: same pattern.  
**AC:** `form.store_is_plan_default` is `true` exactly when "Plan default" is the active dropdown selection; `false` otherwise.

### Step 5 — `web/src/lib/resolve-launch-actors.ts`: use boolean flags (low)
Replace the `explicitStore = String(form.store_id ?? "").trim()` truthiness check with `const isStorePlanDefault = form.store_is_plan_default === true`. Same for phone. Drive `storeSource` / `phoneSource` from the flag, not from empty-string detection.  
**AC:** A store/phone that equals the plan default value but was explicitly selected resolves with `storeSource = "form"`, not `"random_plan_pool"`.

### Step 6 — `web/src/lib/run-command-preview.ts`: emit `--plan-default-store` / `--plan-default-phone` (trivial)
Replace `if (form.store_id && form.store_id.trim()) parts.push("--store", form.store_id.trim())` with: when `form.store_is_plan_default`, push `--plan-default-store`; else when `form.store_id`, push `--store form.store_id`. Same for phone.  
**AC:** Preview shows `--plan-default-store` when plan default is selected, `--store <value>` when explicit.

### Step 7 — `api/app/main.py`: shuffle-without-replacement pool + resolution (medium)
Add at module level:
```python
import threading
from collections import deque
_store_pools: dict[str, deque[str]] = {}
_phone_pools: dict[str, deque[str]] = {}
_actor_pool_lock = threading.Lock()
```
Add helper `_pick_from_actor_pool(plan_key, pool_dict, candidates)` — pops left from deque; if empty, refills from `random.sample(candidates, len(candidates))` (Fisher-Yates via `sample`) and pops again.  
Add `_load_plan_actor_candidates(plan_name)` — reads the plan JSON using the existing `_read_simulation_plan_file` path resolution (`sim_actors.json` → `_default_sim_actors_plan_path()`; others → `_simulation_plan_path()`). Returns `(store_ids: list[str], phones: list[str])`.  
In `_build_command`: before appending `--store`/`--phone`, check `request.store_is_plan_default` / `request.phone_is_plan_default`. If true, call `_pick_from_actor_pool` to resolve a concrete value and push `--store <resolved>` / `--phone <resolved>`. If false and the field has a value, push the existing explicit flag.  
**AC:** Two consecutive run launches with plan-default store get different store IDs (when plan has ≥2 stores). After all stores are exhausted, the sequence restarts from a new shuffle. `.env` is never consulted.

### Step 8 — `config.py:apply_actor_selection`: remove env-global fallbacks (low)
Change `has_manual_store_id = bool(str(store_id or STORE_ID or "").strip()) and not SIM_STORE_AUTO_SELECTED` to `has_manual_store_id = SIM_STORE_EXPLICIT`. Change `has_manual_user_phone = bool(str(USER_PHONE_NUMBER or "").strip()) and not SIM_PHONE_AUTO_SELECTED` to `has_manual_user_phone = SIM_PHONE_EXPLICIT`. Remove `STORE_ID` and `USER_PHONE_NUMBER` from the `or`-chain in `explicit_store_id` / `explicit_user_phone` — the only source of a concrete value is `store_id` / `user_phone` args passed in (which come from CLI).  
**AC:** With `SIM_STORE_EXPLICIT=False`, `apply_actor_selection` always randomises from plan actors regardless of what `STORE_ID` is set to in `.env`.

---

## Untested path disclosure
- The pool deque is reset on API server restart — tested only implicitly; no automated test covers the deque cycling.
- Direct CLI usage (`python3 -m simulate`) does not benefit from the pool (no persistent state between runs); it always randomises via `random.choice`. This is acceptable for CLI use.

## Regression checklist
| Changed component | Callers to verify |
|---|---|
| `apply_actor_selection` (config.py) | `load_sim_actors` → `__main__._apply_args`, `__main__._run_load_mode`, `trace_runner` |
| `LaunchActorSelect.onChange` | `RunLaunchPanel` (both store and phone handlers) |
| `resolveLaunchActors` | `RunLaunchPanel` (scope display), `FlowPlannerGuide` |
| `buildRunCommandPreview` | `RunLaunchPanel` (preview display), `run-command-preview.test.ts` |
| `_build_command` (main.py) | `POST /api/v1/runs`, schedule triggers, profile launches, replay |

---

## Definition of Done
- [ ] App runs without new warnings or errors
- [ ] Every AC in the plan is verified (observed in app or test output)
- [ ] Regression checklist cleared — all listed callers manually verified
- [ ] Dead code audit complete — `STORE_ID`/`USER_PHONE_NUMBER` env fallback removed from `has_manual_*` logic
- [ ] No new `any` types or unsafe assertions without inline justification
- [ ] No new dependencies without justification in solution doc
- [ ] Cross-file consistency verified — `store_is_plan_default` flag propagated consistently at all layers
- [ ] Performance baseline recorded: N/A (no rendering, query, or socket path affected)
