# Flow: `payments`

## Intent

Use this flow to validate payment-related behavior using the `payments` trace suite.

## Preset defaults

```json
{
  "mode": "trace",
  "suite": "payments"
}
```

## Operator behavior

- Runs trace mode with the `payments` suite.
- Emphasizes checkout, payment progression, and payment-adjacent failure handling.

## Launch examples

- GUI: Runs -> Flow `payments`.
- CLI: `python3 -m simulate payments --plan sim_actors.json --timing fast`

## Required inputs

- Stripe/free payment config compatible with suite scenarios.
- Plan-level users/stores valid for payment test path.

## Expected artifacts

- Payment status progression evidence and latency findings.
- Clear failure details for auth, method, or webhook progression issues.

## Common failure signals

- Missing Stripe key or account mismatch with backend webhook environment.
- Payment method/coupon preconditions not satisfied.
