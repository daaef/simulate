# Changelog: Plan-Default Actor Selection

## High-level (what changed for the user / system)

The simulator now has an unambiguous, explicit signal for "plan default" (= randomise this field) vs "a specific value was chosen." Previously, "plan default" was represented by an empty/absent value, which was indistinguishable from a stale `.env` entry — causing the simulator to silently reuse a prior run's store or phone even when the user wanted randomisation. All actor selection data now flows exclusively from `sim_actors.json`; `.env` values for `STORE_ID` and `USER_PHONE_NUMBER` are completely ignored during selection. Consecutive run launches using "Plan default" now cycle through all stores and phones in the plan before repeating (shuffle-without-replacement), so the same store/phone is never used twice in a row unless only one exists.

**Observable differences:**
- Selecting "Plan default" in the Store or Phone dropdown on the Run Launcher now guarantees different actors across runs until the pool is exhausted.
- Selecting a specific store/phone (even one that matches `defaults.store_id`) always uses that exact value — never treated as a randomise signal.
- The command preview shows `--plan-default-store` / `--plan-default-phone` instead of no flag when plan default is active.

---

## Low-level (exactly what was changed and why)

### `api/app/runs/models.py`
- **Added** `store_is_plan_default: Optional[bool] = None` and `phone_is_plan_default: Optional[bool] = None` to `RunCreateRequest`.
- **Why:** The API model must carry the explicit intent so the command-builder can distinguish plan-default from explicit-but-absent.

### `web/src/lib/api.ts`
- **Added** `store_is_plan_default?: boolean` and `phone_is_plan_default?: boolean` to the `RunCreateRequest` TypeScript type.
- **Why:** TypeScript type must mirror the Python model for the frontend to send the flags.

### `web/src/components/runs/LaunchActorSelect.tsx`
- **Changed** `onChange` prop type from `(value: string) => void` to `(value: string, isPlanDefault: boolean) => void`.
- **Changed** `handleSelectChange`: when `ACTOR_SELECT_DEFAULT` is chosen, calls `onChange("", true)`; for any other selection, calls `onChange(value, false)`. Text input onChange also calls with `false`.
- **Why:** The component is the only place that knows which dropdown option was selected; it must propagate the boolean rather than leaving callers to infer from an empty string.

### `web/src/components/runs/RunLaunchPanel.tsx`
- **Changed** `LaunchActorSelect` `onChange` handlers for store and phone to accept `(value, isPlanDefault)` and write both the value and the boolean flag to the form state.
- **Why:** The form state (`RunCreateRequest`) must carry `store_is_plan_default` / `phone_is_plan_default` so both the command preview and the API submission include it.

### `web/src/lib/resolve-launch-actors.ts`
- **Added** `isStorePlanDefault = form.store_is_plan_default === true` and `isPhonePlanDefault = form.phone_is_plan_default === true`.
- **Changed** store/phone resolution: plan-default flag is checked first (before the empty-string check). When true, `storeSource` / `phoneSource` is `"random_plan_pool"` regardless of the value in `form.store_id`.
- **Why:** A store that equals the plan default but was explicitly selected must show as `"form"` not `"random_plan_pool"`. The boolean flag makes this unambiguous.

### `web/src/lib/run-command-preview.ts`
- **Changed** store/phone flag emission: when `form.store_is_plan_default` is true, emits `--plan-default-store`; else emits `--store <value>` if set. Same pattern for phone.
- **Why:** The preview should reflect intent (randomise) rather than the absent `--store` flag, making it readable.

### `api/app/main.py`
- **Added** `from collections import deque` and `import random` to imports.
- **Added** module-level `_store_pools: dict[str, deque[str]]`, `_phone_pools: dict[str, deque[str]]`, `_actor_pool_lock: threading.Lock`.
- **Added** `_load_plan_actor_candidates(plan_name)` — reads `sim_actors.json` or a GUI plan JSON, returns `(store_ids, phones)`. Silently returns `([], [])` on any read error.
- **Added** `_pick_from_actor_pool(plan_name, pool_dict, candidates)` — pops from deque; refills with `random.sample` (Fisher-Yates) when empty. Lock is acquired by the caller.
- **Changed** `_build_command`: before building `--store`/`--phone` CLI args, checks `store_is_plan_default` / `phone_is_plan_default`. When true, loads plan candidates and picks under `_actor_pool_lock`, injecting a concrete resolved value as an explicit `--store`/`--phone` arg. The subprocess always receives a concrete actor value.
- **Why:** The no-repeat guarantee must be enforced server-side because each run is a fresh subprocess with no cross-run state. `.env` is never read for actor candidates.

### `config.py`
- **Changed** `apply_actor_selection` lines 387–398: replaced `has_manual_user_phone` (previously read `USER_PHONE_NUMBER` env global) with `SIM_PHONE_EXPLICIT`; replaced `has_manual_store_id` (previously read `STORE_ID` env global) with `SIM_STORE_EXPLICIT`.
- **Changed** `explicit_user_phone`: now `str(USER_PHONE_NUMBER or "").strip() if SIM_PHONE_EXPLICIT else ""`; removed `.env` global from the expression.
- **Changed** `explicit_store_id`: now `str(store_id or "").strip() if SIM_STORE_EXPLICIT else ""`; removed `STORE_ID` env global from the `or`-chain entirely.
- **Why:** This is the root bug fix. When "Plan default" is selected (no `--store` flag), `SIM_STORE_EXPLICIT=False` and randomisation always proceeds regardless of any stale `.env` `STORE_ID` value.
