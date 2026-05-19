# Flow: `store-reject`

## Intent

Use this flow to validate the store rejection branch before payment completion.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["store_reject"]
}
```

## Operator behavior

- Runs `store_reject` scenario in trace mode.
- Confirms rejection status handling and downstream cancellation semantics.

## Launch examples

- GUI: Runs -> Flow `store-reject`.
- CLI: `python3 -m simulate store-reject --plan sim_actors.json --timing fast`

## Required inputs

- Valid user/store identities from selected plan.
- Order placement path reachable before rejection step.

## Expected artifacts

- Clear rejection event sequence in run artifacts.
- Evidence that order does not proceed into paid completion path.

## Common failure signals

- Store patch failures on rejection status.
- Unexpected transition into payment/completion state.
