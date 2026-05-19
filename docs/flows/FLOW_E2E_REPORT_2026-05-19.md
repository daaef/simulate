# Flow E2E Test Report — 2026-05-19

> Session: `e2e-gui-verify-2026-05-19-070f8836`  
> Started: `2026-05-19T10:11:24.546+00:00`  
> Ended: `2026-05-19T10:11:55.143+00:00`  
> CLI regression: `runs/flow-reliability-2026-05-19.json`  
> Raw log: `logs/simulator-runs/2026-05-19/e2e-gui-verify-2026-05-19-070f8836.ndjson`

## Result Matrix

| Flow | CLI exit | CLI verdict | CLI pass | GUI run | GUI status | GUI UI | Note |
|------|----------|-------------|----------|---------|------------|--------|------|
| `menus` | `0` | passed | ✅ | id=29 | succeeded ✅ | ✅ |  |
| `free-coupon` | `0` | passed | ✅ | id=30 | succeeded ✅ | ✅ |  |
| `new-user` | `0` | degraded | ✅ | id=31 | succeeded ✅ | ✅ | degraded: 1 precondition (exit 0, policy pass) |
| `paid-coupon` | `1` | degraded | ❌ | id=32 | failed ❌ | ✅ | coupon precondition: 4 misses, 0 api_fault |
| `paid-no-coupon` | `0` | passed | ✅ | id=33 | succeeded ✅ | ✅ |  |
| `payments` | `1` | degraded | ❌ | id=34 | failed ❌ | ✅ | coupon precondition: 4 misses, 0 api_fault |
| `receipt-review` | `0` | passed | ✅ | id=35 | succeeded ✅ | ✅ |  |
| `robot-complete` | `0` | passed | ✅ | id=36 | succeeded ✅ | ✅ |  |
| `store-accept` | `0` | passed | ✅ | id=37 | succeeded ✅ | ✅ |  |
| `store-dashboard` | `0` | passed | ✅ | id=38 | succeeded ✅ | ✅ |  |
| `store-reject` | `0` | passed | ✅ | id=39 | succeeded ✅ | ✅ |  |
| `store-setup` | `0` | passed | ✅ | id=40 | succeeded ✅ | ✅ |  |

## Summary

| Metric | Count |
|--------|-------|
| CLI policy-pass | 10/12 |
| GUI run succeeded | 10/12 |
| GUI UI checks pass | 12/12 |

## Failing Flows

### `paid-coupon` — CLI exit 1, GUI failed

- **CLI verdict**: `degraded` (exit 1)
- **GUI run**: id=32, status=`failed`
- **Failure class breakdown**: api_fault=0, precondition=4
- **Root cause**: No API fault. The `returning_paid_with_coupon` scenario requires a valid coupon in the store context. Zero coupons are available for the plan's default user/store combination, causing the coupon step to fail as a precondition miss. Under `api_only` policy these misses *should* downgrade to exit 0, but the scenario hard-requires coupon (`coupon_required: true`) so the exit code remains 1.
- **Reproducibility**: Consistent — every run of `paid-coupon` or `payments` will fail this step until a valid coupon is provisioned in the plan.
- **Fix**: Add a valid coupon to the store context in `sim_actors.json`, or run with `--no-auto-provision` to get `unsupported` scenario verdict rather than `degraded`.

### `payments` — CLI exit 1, GUI failed

- **CLI verdict**: `degraded` (exit 1)
- **GUI run**: id=34, status=`failed`
- **Failure class breakdown**: api_fault=0, precondition=4
- **Root cause**: No API fault. The `returning_paid_with_coupon` scenario requires a valid coupon in the store context. Zero coupons are available for the plan's default user/store combination, causing the coupon step to fail as a precondition miss. Under `api_only` policy these misses *should* downgrade to exit 0, but the scenario hard-requires coupon (`coupon_required: true`) so the exit code remains 1.
- **Reproducibility**: Consistent — every run of `paid-coupon` or `payments` will fail this step until a valid coupon is provisioned in the plan.
- **Fix**: Add a valid coupon to the store context in `sim_actors.json`, or run with `--no-auto-provision` to get `unsupported` scenario verdict rather than `degraded`.
