# Flow: `audit`

## Intent

Use this flow for audit-oriented trace verification where evidence quality and coverage are prioritized.

## Preset defaults

```json
{
  "mode": "trace",
  "suite": "audit"
}
```

## Operator behavior

- Runs trace mode with the `audit` suite.
- Focuses on deterministic checks and report-ready findings.

## Launch examples

- GUI: Runs -> Flow `audit`.
- CLI: `python3 -m simulate audit --plan sim_actors.json --timing fast`

## Required inputs

- Stable plan fixtures and credentials.
- App/store endpoints reachable for suite probe set.

## Expected artifacts

- High-signal `report.md` and detailed `events.json` entries for review.
- Scenario-by-scenario pass/fail evidence with reasons.

## Common failure signals

- Probe contract mismatches or endpoint regressions.
- Missing preflight prerequisites leading to skipped/inconclusive checks.
