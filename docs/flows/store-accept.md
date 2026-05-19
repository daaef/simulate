# Flow: `store-accept`

## Intent

Use this flow to validate the store acceptance branch for a paid order.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["store_accept"],
  "payment_mode": "stripe",
  "payment_case": "paid_no_coupon",
  "coupon_id": null
}
```

## Operator behavior

- Runs `store_accept` scenario in trace mode.
- Verifies store-side transition into accepted processing path.

## Launch examples

- GUI: Runs -> Flow `store-accept`.
- CLI: `python3 -m simulate store-accept --plan sim_actors.json --timing fast`

## Required inputs

- Stripe-capable paid checkout setup.
- Store permissions to accept orders.

## Expected artifacts

- Acceptance status transitions and timing.
- Store and user evidence around post-accept progression.

## Common failure signals

- Store cannot patch order to accepted state.
- Payment processing progression fails after acceptance.
