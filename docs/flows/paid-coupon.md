# Flow: `paid-coupon`

## Intent

Use this flow to validate paid returning-user checkout with required coupon application.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["returning_paid_with_coupon"],
  "payment_mode": "stripe",
  "payment_case": "paid_with_coupon",
  "coupon_required": true
}
```

## Operator behavior

- Runs `returning_paid_with_coupon` in trace mode.
- Enforces coupon requirement, then validates paid completion behavior.

## Launch examples

- GUI: Runs -> Flow `paid-coupon`.
- CLI: `python3 -m simulate paid-coupon --plan sim_actors.json --timing fast`

## Required inputs

- Coupon availability in selected plan/store context.
- Valid Stripe path for paid checkout.

## Expected artifacts

- Coupon selection/validation evidence before payment completion.
- Clear failure detail when coupon preconditions are missing.

## Common failure signals

- Coupon not found or invalid for selected store/user.
- Stripe or payment progression failures after coupon application.
