# Flow: `store-dashboard`

## Intent

Use this flow to validate store dashboard data surfaces such as orders, statistics, and top-customer endpoints.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["store_dashboard"]
}
```

## Operator behavior

- Runs `store_dashboard` scenario in trace mode.
- Focuses on store observability APIs rather than full ordering lifecycle completion.

## Launch examples

- GUI: Runs -> Flow `store-dashboard`.
- CLI: `python3 -m simulate store-dashboard --plan sim_actors.json --timing fast`

## Required inputs

- Valid store auth and subentity mapping in plan.
- Dashboard endpoints enabled for the selected environment.

## Expected artifacts

- Dashboard probe call evidence with pass/fail outcomes.
- Findings around stats/orders/top-customer query health.

## Common failure signals

- Store token/login failures.
- Store dashboard endpoint contract or availability errors.
