# Bounded Load Smoke Fix Explainer

This document explains what was broken in bounded load smoke, why it happened, and how the fix works.

## Problem statement

Two operator-facing problems existed:

1. Launch/runtime mismatch in load mode:
   - The launch command/header could show `--users 2 --orders 3 --interval 2.0`
   - But effective runtime could fall back to plan defaults (`users=1`, `orders=1`, `interval=30`)
2. `bounded-load-smoke` did not guarantee a successful accepted/completed order.
   - A run could end with only rejected/cancelled outcomes depending on stochastic load behavior.

## Root cause

The load runner reloaded actor/plan defaults after argument application, which allowed plan defaults to override explicit launch values.

- Argument application set load knobs from CLI/profile.
- Later, load-mode bootstrap reapplied plan defaults again.
- Effective worker settings drifted from launch intent.

Separately, bounded load smoke relied on probabilistic reject behavior only, with no deterministic accepted-order baseline gate.

## Solution design

## 1) Precedence correction

Load mode now uses already-loaded actor state from argument/bootstrap phase instead of reloading and reapplying plan defaults.

- Result: effective runtime values stay aligned with launch values for `users/orders/interval/reject`.

## 2) Phased bounded-load policy

`bounded-load-smoke` stays in `flow=load`, but now runs in two phases:

1. Baseline phase:
   - Rejects are forced off.
   - Run must produce at least one completed order (`baseline_min_completed=1`).
2. Tail phase:
   - Reject/cancel pressure is restored for remaining attempts.

If baseline is not met within the bounded guardrail (`baseline_max_attempts`), run fails with:

- `accepted_baseline_not_met`

## 3) Phase evidence in artifacts

Run artifacts now include phase transitions and summaries:

- `bounded_load_phase_baseline`
- `bounded_load_phase_tail`
- `bounded_load_phase_summary`
- `bounded_load_attempt_guard_reached` (when applicable)

This gives auditable proof that baseline completed before reject/cancel tail behavior.

## Before/after examples

## Before

Command:

```bash
python3 -u -m simulate load --plan sim_actors.json --timing fast --mode load --users 2 --orders 3 --interval 2.0 --reject 0.1
```

Possible runtime:

- banner: `users=2, orders=3, interval=2.0`
- worker runtime: `users=1, orders=1, interval=30.0`
- completed orders: `0`

## After

Catalog bounded profile command now includes bounded policy flags:

```bash
python3 -u -m simulate load --plan sim_actors.json --timing fast --mode load --users 2 --orders 3 --interval 2.0 --reject 0.35 \
  --bounded-load-smoke-policy \
  --bounded-baseline-min-completed 1 \
  --bounded-baseline-max-attempts 3 \
  --bounded-tail-reject-rate 0.35 \
  --bounded-tail-cancel-rate 0.15
```

Expected behavior:

- baseline phase guarantees `completed >= 1`
- tail phase can produce reject/cancel outcomes
- if baseline fails within max attempts, explicit failure `accepted_baseline_not_met`

## Operator interpretation guide

- `Critical Findings = 0` does not mean all business outcomes are successful.
- For bounded smoke, check:
  - completed baseline met (`>=1`)
  - tail outcomes (reject/cancel) as optional pressure checks
  - phase events in `events.json` for auditability

Success model for bounded smoke:

- simulator success + baseline accepted/completed met
- reject/cancel in tail are expected and not automatically “platform down”

## Troubleshooting matrix

| Symptom | Likely cause | Verification |
|---|---|---|
| Launch shows 2/3/2.0 but runtime behaves like 1/1/30 | precedence drift | check `events.json` config snapshot and user worker startup line |
| Bounded run fails with `accepted_baseline_not_met` | no completed order within baseline max attempts | inspect `bounded_load_phase_summary` details and store/user terminal statuses |
| No tail rejects/cancels seen | low tail rates or low remaining attempts | review `bounded-tail-*` flags and total bounded orders |
| Run has rejects only | baseline policy not enabled | verify command contains `--bounded-load-smoke-policy` |

## Regression protection

Automated coverage added/updated:

- catalog seed/command tests assert bounded policy flags are present in the seeded profile command
- bounded policy transition tests validate baseline -> tail switch and reject-rate restoration
- bounded guard summary tests validate not-met baseline state/attempt tracking
- docs updated to codify new bounded smoke contract and precedence behavior
