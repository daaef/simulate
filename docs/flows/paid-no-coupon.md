# Flow: `paid-no-coupon`

## Intent

Use this flow to validate the standard returning-user paid order path without coupon application.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["returning_paid_no_coupon"],
  "payment_mode": "stripe",
  "payment_case": "paid_no_coupon",
  "coupon_id": null
}
```

## Operator behavior

- Runs `returning_paid_no_coupon` in trace mode.
- Uses Stripe-backed paid path and explicitly disables coupon by default.

## Launch examples

- GUI: Runs -> Flow `paid-no-coupon`.
- CLI: `python3 -m simulate paid-no-coupon --plan sim_actors.json --timing fast`

## Required inputs

- Valid Stripe test key and compatible backend webhook/account setup.
- Returning-user credentials in plan scope.

## Expected artifacts

- Full payment progression (`pending` -> `payment_processing` -> backend progression).
- Timing and status evidence across user/store/robot lifecycle.

## Common failure signals

- Missing `STRIPE_SECRET_KEY` for stripe-required scenarios.
- Payment confirmation timeout or webhook progression failure.
