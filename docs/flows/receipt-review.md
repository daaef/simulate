# Flow: `receipt-review`

## Intent

Use this flow to validate post-order receipt, review submission, reorder fetch, and second-order continuity.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["receipt_review_reorder"],
  "payment_mode": "stripe",
  "payment_case": "paid_no_coupon",
  "coupon_id": null,
  "post_order_actions": true
}
```

## Operator behavior

- Runs `receipt_review_reorder` scenario in trace mode.
- Enables post-order actions by default, including reorder-data driven follow-up order behavior.

## Launch examples

- GUI: Runs -> Flow `receipt-review`.
- CLI: `python3 -m simulate receipt-review --plan sim_actors.json --timing fast --post-order-actions`

## Required inputs

- Working paid-order completion path.
- Receipt/review/reorder endpoints reachable for the selected environment.

## Expected artifacts

- Evidence for receipt generation, review submission, reorder payload fetch, and continuation behavior.
- Detailed findings when post-order APIs diverge from expected contracts.

## Common failure signals

- Receipt or review endpoint failures despite completed order.
- Reorder payload mismatch preventing follow-up cart reconstruction.
