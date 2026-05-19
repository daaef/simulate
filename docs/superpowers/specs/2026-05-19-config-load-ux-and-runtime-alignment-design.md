# Config Tabs, Default Plan Loading, and Load Runtime Alignment

**Date:** 2026-05-19  
**Status:** Approved for implementation

## Problem

1. **Config usability drift:** `/config` currently renders plans, email settings, and integration mappings in one long page, which increases operator scanning time and makes plan editing slower.
2. **Default plan load gap:** `sim_actors.json` appears in plan listings but cannot be loaded through the existing `GET /api/v1/simulation-plans/{id}` path because that path only resolves GUI plan files.
3. **New-plan behavior mismatch:** `New` currently resets to a hardcoded template instead of cloning the plan the operator just loaded.
4. **Load semantics ambiguity:** operators need deterministic behavior for `users=N` with and without `all_users`; current runtime fans out by authenticated user bundles and can produce non-obvious worker counts.
5. **Mode-specific UI noise:** load flows still expose trace-oriented settings in advanced sections, creating invalid-combination cognitive load.

## Approved decisions

1. **Hybrid implementation:** keep API contract mostly stable; apply targeted backend/runtime fixes plus frontend UX cleanup.
2. **Config tabs:** split `/config` into tabs: `Plans`, `Email`, `Integration mappings`.
3. **Default plan loading:** make root `sim_actors.json` loadable from Config like any other plan row.
4. **New clones current:** `New` creates a draft cloned from the currently loaded plan content (default or GUI-owned), not from static template-only defaults.
5. **Load-mode UX isolation:** when resolved mode is load, hide trace-only controls and hide mode override in launcher settings.
6. **Load pacing presets:** add load-only pacing preset selector (`slow=10s`, `normal=3s`, `fast=1s`) that writes `interval` with manual override retained.
7. **Runtime worker policy:**
   - `all_users=false` and `users=N`: reuse one selected/default user across all `N` workers.
   - `all_users=true` and `users=N`:
     - when `N <= plan users`, assign the first `N` users in plan order.
     - when `N > plan users`, assign users by strict deterministic round-robin, repeating from beginning.
8. **Timing separation:** trace `fast/realistic` remains independent from load pacing presets.
9. **Docs ownership:** `SIMULATOR_GUIDE.md` becomes canonical operator doc; `README.md` reduced to quickstart and links.
10. **Per-flow operator docs:** add one comprehensive doc per GUI-selectable flow under `docs/flows/`.

## UX contract

### Config page

- A tab bar controls content sections:
  - `Plans`: list, load, new, create/update/delete, JSON editor.
  - `Email`: notification toggles, recipients, triggers, test email.
  - `Integration mappings`: existing GitHub mapping and trigger panels.
- `Load` on any row (including default) must populate editor + plan name consistently.
- `New` always copies currently loaded JSON into editable draft, then clears selected persisted id.

### Runs launcher (load mode)

- If resolved mode is load:
  - hide `Suite`, `Scenarios`, and `Mode override` controls.
  - show only load-relevant controls (`users`, `orders`, `interval`, `reject`, `continuous`, `all_users`, etc.).
- Add pacing selector near load controls.
- Selecting pace writes interval value; editing interval manually preserves numeric override.
- Command preview must stay truthful to explicit values passed.

## Runtime contract

- Effective worker pool size is `N_USERS`.
- User assignment policy:
  - `all_users=false`: every worker uses same actor identity context for selected/default phone.
  - `all_users=true`:
    - if `N_USERS <= len(plan_users)`, use the first `N_USERS` users in plan order.
    - if `N_USERS > len(plan_users)`, precompute worker->user mapping by deterministic modulo indexing.
- This policy must be reproducible across identical runs.
- Existing constraints remain:
  - `users >= 1`
  - `orders >= 1` unless continuous
  - `reject` in `[0,1]`

## Backend/API shape

No breaking API redesign.

- Keep existing run-create payload fields (`users`, `orders`, `interval`, `reject`, `continuous`, `all_users`).
- Add targeted plan-loading support for default plan row in simulation-plan service path(s).
- Preserve run profiles, schedules, and integration-trigger launch compatibility.

## Files expected to change

### Frontend

- `web/src/app/(app)/config/page.tsx`
- `web/src/components/config/IntegrationMappingsPanel.tsx` (compose under tab shell)
- `web/src/components/runs/RunLaunchPanel.tsx`
- `web/src/app/(app)/runs/page.tsx` (if needed for launcher state wiring)
- `web/src/lib/run-launcher-config.ts` (help text/visibility metadata)
- `web/src/lib/resolve-launch-actors.ts` (if pace defaults or summary need updates)
- CSS in existing app styles as needed for tabs/pacing controls

### Backend/runtime

- `api/app/main.py` (simulation plan default load path behavior)
- `__main__.py` (load-mode worker assignment orchestration)
- `user_sim.py` (worker execution path, if assignment helper lives here)

### Tests

- `tests/test_web_api.py`
- `tests/test_simulate.py`
- `web/src/lib/*.test.ts` and/or component tests for launcher/config behavior

### Docs

- `SIMULATOR_GUIDE.md` (canonical operator behavior)
- `README.md` (quickstart + links only)
- `docs/flows/*.md` (one comprehensive operator guide per GUI flow)

## Testing strategy

1. Backend plan-loading tests for default `sim_actors` row behavior.
2. Frontend config tests for:
   - tab rendering/switching,
   - default-row load,
   - new-draft clone-from-loaded behavior.
3. Launcher tests for load-mode field visibility and pace preset mapping.
4. Runtime tests for worker/user assignment:
  - single-user reuse for `all_users=false`.
  - first-`N` selection for `all_users=true` when `N <= plan users`.
  - round-robin fill for `all_users=true` when `N` exceeds user count.
5. Regression tests for command preview and profile/schedule compatibility.
6. Docs coverage check: every flow from `/api/v1/flows` has a matching `docs/flows/<flow>.md`.

## Risks and mitigations

- **Risk:** changing user assignment may alter load behavior expectations in existing operators.  
  **Mitigation:** document exact policy and keep deterministic mapping; no randomization.
- **Risk:** UI hiding mode override could reduce advanced flexibility.  
  **Mitigation:** only hide for load preset flow where mode intent is explicit; keep payload compatibility.
- **Risk:** default plan load logic could collide with GUI-plan id semantics.  
  **Mitigation:** explicit branch for default sentinel id/path with dedicated tests.

## Acceptance criteria

- `sim_actors.json` can be loaded from Config without errors.
- Clicking `New` clones currently loaded plan content into draft editor.
- Config page is tabbed (`Plans`, `Email`, `Integration mappings`).
- Load flow shows no trace-specific controls or mode override in settings UI.
- Load pace preset exists and maps to `interval` with manual override retained.
- Runtime assignment follows approved policy for `all_users` true/false with `users=N`.
- `SIMULATOR_GUIDE.md` is canonical and `README.md` is reduced to quickstart + links.
- `docs/flows/` contains one comprehensive operator file for each GUI flow option.
