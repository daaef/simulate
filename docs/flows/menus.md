# Flow: `menus`

## Intent

Use this flow to validate menu/catalog data availability and related ordering prerequisites via the `menus` trace suite.

## Preset defaults

```json
{
  "mode": "trace",
  "suite": "menus"
}
```

## Operator behavior

- Runs in trace mode using the `menus` suite unless you intentionally override.
- Before menu gate scenarios, the simulator creates a **new menu item** in the selected store (category created first if missing). The item name is `SIM_MENU_NAME` plus a UTC timestamp suffix.
- Requires store setup to be completable and menu provisioning enabled (`SIM_AUTO_PROVISION_FIXTURES` or `SIM_MUTATE_MENU_SETUP`; the menus flow enables menu mutation for this step when needed).
- Focuses on menu readiness and menu-dependent checks rather than high concurrency.

## Launch examples

- GUI: Runs -> Flow `menus`.
- CLI: `python3 -m simulate menus --plan sim_actors.json --timing fast`

## Required inputs

- Plan with valid store and user records.
- Store menu prerequisites available or auto-provisioning enabled.

## Expected artifacts

- Trace-oriented event ledger with suite and scenario resolution.
- Findings around missing categories/items or menu fetch failures.

## Common failure signals

- Missing store setup/menu entities when auto-provisioning is disabled.
- Auth/probe failures to menu-related APIs.
