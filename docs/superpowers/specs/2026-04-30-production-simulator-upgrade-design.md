# Production Simulator Upgrade Design

## Goal

Turn the current order simulator into a daily production doctor for the Fainzy ordering system. The simulator should be easy for non-programmers to run from a JSON file, realistic enough to mirror the user and store apps, and detailed enough for engineers to diagnose failures, latency, websocket gaps, and bottlenecks.

## Current System

The simulator already has useful foundations:

- `load` mode creates concurrent user/store/robot actors.
- `trace` mode proves deterministic scenarios such as completed, rejected, cancelled, payments, menu states, store setup, store accept/reject, and robot completion.
- `RunRecorder` writes event, technical, and story artifacts.
- HTTP calls are masked and timed.
- Websocket events are recorded and matched to expected order status transitions.

The missing pieces are not a rewrite problem. They are coverage, input, reporting, and usability gaps.

## Target Operator Experience

An operator should prepare one JSON file containing users, their GPS coordinates, and store IDs. They should run commands such as:

```bash
python3 -m simulate doctor --plan sim_actors.json
python3 -m simulate load --plan sim_actors.json --orders 50 --users 10
python3 -m simulate receipt-review --plan sim_actors.json
```

Each run produces a folder under `runs/` with:

- `events.json`: full machine-readable evidence.
- `report.md`: concise verdict first, then graphs/tables, then technical trace.
- `story.md`: plain-English journey.

## Real-App Coverage

The supplied app sessions show these surfaces that must be simulated or probed:

- App bootstrap: config and product authentication.
- User auth: OTP send, OTP verify, user create, cached-token validation.
- Location: GPS lookup, unserved-location request as a diagnostic probe, active delivery location selection.
- Discovery: active orders, service-area restaurants, categories, menus, menu sides.
- Checkout: pricing, saved cards, coupons, order creation, free order, Stripe payment intent.
- Live order: user/store/stats websockets and repeated status updates.
- Post-order: fetch details, generate receipt, submit review, reorder payload.
- Store: store login, setup patch, categories, menus, category creation, menu creation, status updates, orders by subentity, statistics, top customers.

## Architecture

Add focused modules around the existing actors:

- `run_plan.py`: public JSON input parser and validator.
- `app_probes.py`: non-order API probes used by user/store flows.
- `post_order_actions.py`: receipt, review, and reorder checks.
- `health.py`: aggregate metrics and report-ready summaries.

Existing actors stay responsible for auth and order behavior. New modules provide reusable probes so trace and load mode can share them.

## Safety

The simulator must be safe by default:

- Store setup and menu creation stay behind explicit mutation flags.
- Receipt, review, reorder, stats, cards, coupons, pricing, and config probes are non-destructive.
- All secrets and sensitive payload fields stay redacted.
- Probe failures should record issues without masking core order results.

## Reporting Design

`report.md` should start with:

- Overall verdict.
- Counts for scenarios, orders, API calls, websocket matches, warnings, errors.
- Slowest endpoints and latency percentiles.
- Bottleneck bars rendered as plain text.
- Top actionable failures.

Lower sections keep scenario verdicts, order lifecycle, websocket assertions, developer findings, full technical trace, and config/fixture details.

## Assumptions

- Captured backend errors are not treated as requirements to preserve failures; user asked us to assume APIs are being fixed.
- The simulator continues to run against live configured environments.
- Google Maps calls from the store setup session are documented but not run by default because they require external keys and are not part of the ordering backend.

## Approval Basis

The user explicitly requested a complete upgrade, sophisticated recommendations, and asked for clarification only if needed. This design proceeds without additional questions because the provided sessions and existing code give enough scope to implement.
