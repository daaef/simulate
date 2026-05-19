# Flow: `robot-complete`

## Intent

Use this flow to validate robot delivery lifecycle transitions through terminal completion.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["robot_complete"],
  "payment_mode": "stripe",
  "payment_case": "paid_no_coupon",
  "coupon_id": null
}
```

## Operator behavior

- Runs `robot_complete` scenario in trace mode.
- Verifies statuses from ready/enroute stages to completed terminal state.

## Launch examples

- GUI: Runs -> Flow `robot-complete`.
- CLI: `python3 -m simulate robot-complete --plan sim_actors.json --timing realistic`

## Required inputs

- Successful paid path up to store ready stage.
- Robot simulator connectivity and status patch capability.

## Expected artifacts

- Robot lifecycle status evidence with timing.
- Terminal completion proof suitable for end-to-end validation.

## Common failure signals

- Order never reaches ready state before robot actions.
- Robot status patch errors or websocket event gaps.
