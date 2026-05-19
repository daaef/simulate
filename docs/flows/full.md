# Flow: `full`

## Intent

Use this flow for the broadest trace regression sweep when you want maximal scenario coverage.

## Preset defaults

```json
{
  "mode": "trace",
  "suite": "full"
}
```

## Operator behavior

- Runs trace mode with the `full` suite.
- Covers the widest set of scenarios and therefore generally has the longest duration.

## Launch examples

- GUI: Runs -> Flow `full`.
- CLI: `python3 -m simulate full --plan sim_actors.json --timing realistic`

## Required inputs

- Fully prepared plan and dependencies to avoid noisy, non-actionable failures.
- Time budget for broad regression execution.

## Expected artifacts

- Comprehensive scenario ledger with broad pass/fail distribution.
- Rich set of findings useful for release-readiness decisions.

## Common failure signals

- Any gap across auth, menu, payment, store, robot, or probe layers can fail this run.
- Longer runs may expose intermittent timing or websocket instability.
