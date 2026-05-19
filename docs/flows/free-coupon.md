# Flow: `free-coupon`

## Intent

Use this flow to validate coupon-driven free-order behavior for returning users.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["returning_free_with_coupon"],
  "payment_mode": "free",
  "payment_case": "free_with_coupon",
  "free_order_amount": 0.0,
  "coupon_required": true
}
```

## Operator behavior

- Runs `returning_free_with_coupon` in trace mode.
- Uses free payment path with coupon requirement and zero-amount expectation.

## Launch examples

- GUI: Runs -> Flow `free-coupon`.
- CLI: `python3 -m simulate free-coupon --plan sim_actors.json --timing fast`

## Required inputs

- Coupon that can reduce the order to free in the selected context.
- Plan/store fixtures that support coupon validation path.

## Expected artifacts

- Evidence that order proceeds through free-payment branch.
- Explicit proof of coupon gating and terminal order status.

## Common failure signals

- Coupon not applicable or not found.
- Free amount mismatch (`SIM_FREE_ORDER_AMOUNT` not aligned with expected free flow).
