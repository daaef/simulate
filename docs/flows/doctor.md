# Flow: `doctor`

## Intent

Use this as the daily operator health check for end-to-end platform readiness.

## Preset defaults

```json
{
  "mode": "trace",
  "suite": "doctor"
}
```

## Operator behavior

- Runs trace mode `doctor` suite with broad operational coverage.
- This is the preferred flow for “is the platform healthy now?” decisions.

## Launch examples

- GUI: Runs -> Flow `doctor`.
- CLI: `python3 -m simulate doctor --plan sim_actors.json --timing fast`

## Required inputs

- Stable plan with valid users/stores.
- External dependencies (auth/payment/websocket endpoints) reachable.

## Expected artifacts

- Clear run verdict with critical and operational findings.
- Coverage across app probes, ordering lifecycle, and realtime behavior.

## Common failure signals

- Auth/bootstrap failures, 5xx API failures, websocket gate failures (when enforced).
- Missing business prerequisites surfaced as operational findings.
