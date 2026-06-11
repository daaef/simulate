# Problem: Plan-Default Actor Selection — Ambiguity & No-Repeat

## Root cause
"Plan default" (randomize) is communicated by the *absence* of a value at every layer (empty string in the form, no `--store`/`--phone` CLI flag, `None` in the API model), which is indistinguishable from a leftover `STORE_ID`/`USER_PHONE_NUMBER` in `.env` — causing `config.py:apply_actor_selection` to treat plan-default intent as an explicit selection.

## Symptoms
1. User selects "Plan default" for store or phone in the UI → simulator does not randomize; reuses the previous run's store/phone (silently fixed to `.env` value).
2. User selects a specific store that happens to equal `defaults.store_id` in the plan → impossible to distinguish from "plan default" at the CLI layer; correct only by accident.
3. Consecutive run launches can land on the same store/phone because `random.choice()` has no no-repeat guarantee.

## Affected files / functions
| File | Location | Issue |
|------|----------|-------|
| `config.py` | `apply_actor_selection` L387–398 | `has_manual_store_id` reads `STORE_ID` global (stale env) → false explicit |
| `config.py` | `_select_actor_store`, `_select_actor_user` | `random.choice()` — can repeat |
| `api/app/runs/models.py` | `RunCreateRequest` | Missing `store_is_plan_default` / `phone_is_plan_default` |
| `api/app/main.py` | `_build_command`, `_launch_env_overrides_for_request` | No pool logic; no-repeat not guaranteed |
| `web/src/lib/api.ts` | `RunCreateRequest` type | Missing boolean flags |
| `web/src/lib/run-command-preview.ts` | `buildRunCommandPreview` | Does not emit plan-default hint |
| `web/src/lib/resolve-launch-actors.ts` | `resolveLaunchActors` | Infers plan-default from empty string instead of explicit flag |

## Blast radius
All run launches from the UI (manual, profile, schedule replay) that use "Plan default" for store or phone are affected. Direct CLI usage is affected only if `.env` has stale values.

## Constraints
- The `STORE_ID` / `USER_PHONE_NUMBER` env vars must still work for direct CLI usage with explicit values.
- No-repeat must cycle through ALL stores/phones before repeating — within the API server process lifetime (cross-run state).
- When a specific value is selected (even if it equals the plan default), it must be treated as explicit — no randomization.

## Edge cases
- Plan with only one store: pool cycles trivially (always the same store) — correct behaviour.
- Plan file missing or empty: pool is empty; fall through to `random.choice` safety net.
- Two simultaneous run launches: pool deque pops must be atomic/sequential (GIL protects CPython `deque.popleft` but explicit locking is safer).
