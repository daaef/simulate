# Solution: Explicit Plan-Default Flags + Server-Side Shuffle Pool

## Proposed approach

All store and phone candidate data comes exclusively from `sim_actors.json`. The `.env` file is never consulted for actor selection at any layer.

Introduce an explicit boolean flag at every layer of the stack so "plan default" is never inferred from absence-of-value:

1. **TypeScript `RunCreateRequest`** (`web/src/lib/api.ts`): add `store_is_plan_default?: boolean` and `phone_is_plan_default?: boolean`.
2. **Python `RunCreateRequest`** (`api/app/runs/models.py`): add `store_is_plan_default: Optional[bool] = None` and `phone_is_plan_default: Optional[bool] = None`.
3. **API server** (`api/app/main.py`): maintain per-plan shuffle-without-replacement deques (`_store_pools`, `_phone_pools`) at module level, guarded by a `threading.Lock`. Candidates are loaded by reading the plan JSON file (via the existing `_read_simulation_plan_file` path). When either plan-default flag is `True`, pop from the deque (refill + reshuffle when empty) and inject the resolved value as an explicit `--store`/`--phone` CLI arg. The subprocess always receives a concrete value.
4. **`run-command-preview.ts`**: when `store_is_plan_default` is true, emit `--plan-default-store` as a display hint (shows the user intent without knowing the resolved value in advance).
5. **`resolve-launch-actors.ts`**: use `form.store_is_plan_default` / `form.phone_is_plan_default` booleans instead of checking if the trimmed string is empty.
6. **`config.py:apply_actor_selection`**: remove all `.env`-global fallbacks from actor selection. `has_manual_store_id` becomes `SIM_STORE_EXPLICIT` only — if `--store` was not passed on the CLI, treat the field as plan-default (randomize). Same for phone. `STORE_ID` and `USER_PHONE_NUMBER` env globals are cleared before selection so stale `.env` values cannot leak in.

Because the API server resolves the pool value before subprocess launch, the subprocess always receives an explicit `--store`/`--phone`. No new CLI flags are needed for the API path. The `config.py` fix handles direct CLI use correctly.

## Alternatives rejected
- **Keep empty-string sentinel, clear `.env` before each launch**: fragile; requires side-effects on shared state; breaks concurrent launches.
- **Pass `--plan-default-store` as a new CLI flag and resolve the pool inside the subprocess**: would require subprocess-to-API round-trip state (no shared deque), making no-repeat across runs impossible without a persistence layer.

## Performance impact
Neutral. A `deque.popleft()` under a lock is O(1). Plan JSON is loaded once per run launch (already happens for validation); stores/phones are extracted from the already-loaded content with no extra I/O.

## Performance delta
Not applicable — no rendering, query, or socket path is touched.

## Trade-offs
- The pool deque is in-memory; an API server restart resets it. Acceptable because the guarantee is "no repeat within a continuous session," not "no repeat ever."
- Schedule-triggered runs also benefit if the profile's `store_is_plan_default` flag is set. Profiles stored without the flag use the legacy empty-string behaviour until re-saved.

## Dead code audit
- `SIM_STORE_AUTO_SELECTED` / `SIM_PHONE_AUTO_SELECTED` flags in `config.py`: remain as-is (they guard a different path — within-run sticky reuse of an already-selected actor).
- `ACTOR_SELECT_DEFAULT = ""` in `web/src/lib/plan-actor-options.ts`: stays as the dropdown value; the component maps it to `store_is_plan_default = true` when selected. No removal needed.
