# Flow Guides

This index maps every GUI `Flow` option to its operator guide. These guides document intent, default preset behavior, required inputs, launch examples, expected outputs, and failure triage for each flow.

## Flow list

| Flow | Default mode | Primary intent |
| --- | --- | --- |
| [load](load.md) | `load` | Multi-worker concurrency and churn testing |
| [menus](menus.md) | `trace` | Menu and catalog validation suite |
| [new-user](new-user.md) | `trace` | First-time user onboarding and setup path |
| [paid-no-coupon](paid-no-coupon.md) | `trace` | Paid returning-user order without coupon |
| [paid-coupon](paid-coupon.md) | `trace` | Paid returning-user order with coupon |
| [free-coupon](free-coupon.md) | `trace` | Free order path via coupon |
| [store-setup](store-setup.md) | `trace` | Store setup bootstrap and readiness |
| [store-accept](store-accept.md) | `trace` | Store acceptance path for paid order |
| [store-reject](store-reject.md) | `trace` | Store rejection path |
| [robot-complete](robot-complete.md) | `trace` | Robot lifecycle through completion |
| [payments](payments.md) | `trace` | Payment-focused scenario suite |
| [audit](audit.md) | `trace` | Audit and evidence-oriented verification suite |
| [doctor](doctor.md) | `trace` | Daily end-to-end platform health check |
| [full](full.md) | `trace` | Broadest end-to-end regression suite |
| [receipt-review](receipt-review.md) | `trace` | Post-order receipt, review, and reorder flow |
| [store-dashboard](store-dashboard.md) | `trace` | Store dashboard probes and stats endpoints |

## Related docs

- Canonical operator behavior: [SIMULATOR_GUIDE.md](../../SIMULATOR_GUIDE.md)
- Quickstart: [README.md](../../README.md)
- System architecture: [ARCHITECTURE.md](../../ARCHITECTURE.md)
