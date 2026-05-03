# Complete Order Flow Simulator

## Overview

`simulate` supports two execution styles plus friendly presets:

| Mode | Purpose |
|---|---|
| `load` | Randomised multi-actor traffic simulation for churn, failure hunting, and live platform smoke tests |
| `trace` | Deterministic proof-oriented scenarios for `completed`, `rejected`, `cancelled`, and optional `auto_cancel` |

| Friendly preset | Purpose |
|---|---|
| `doctor` | Daily production health check: app probes, store setup/dashboard, menu gates, payments, store actions, robot completion, receipt/review/reorder |
| `full` | Broadest suite including new-user setup and coupon scenarios |
| `receipt-review` | Completed order plus receipt, review, and reorder probes |
| `store-dashboard` | Store orders, statistics, and top-customer probes |

Each simulator is **fully self-contained** — it owns its own auth, data seeding, and
active websocket connection. There are no shared queues between simulators.

| Component | Responsibility |
|---|---|
| `__main__` | CLI parsing, config validation, launches sims, passive websocket observer, report writing |
| `user_sim` | User auth (OTP/cached token), menu/location seeding, active WS `/ws/soc/<user_id>/`, order placement, payment, cancellation |
| `store_sim` | Store auth (product auth + store login), active WS `/ws/soc/store_<id>/`, accept/reject, payment wait, mark ready |
| `robot_sim` | Store token acquisition (independent), active WS `/ws/soc/store_<id>/`, delivery lifecycle to completed |
| `trace_runner` | Deterministic scenarios; bootstraps own auth/fixtures, uses polling for verification |
| `websocket_observer` | Passive user/store/stats socket observation for report validation |
| `transport` | Masked request/response proof, auth proof, latency capture |
| `reporting` | `events.json`, `report.md`, and `story.md` artifacts |
| `run_plan` | JSON run-plan parsing and validation for operator input |
| `app_probes` | Real-app API probes outside the core order mutation |
| `post_order_actions` | Receipt, review, and reorder probes after completed orders |
| `health` | Daily doctor summary, latency, bottleneck, websocket, and issue metrics |

REST remains the control-plane source of truth. Each sim listens on an active websocket for real-time order status changes that drive behaviour. The passive `WebsocketObserver` runs alongside for reporting validation.

Before app-like order scenarios run, the simulator performs the same prerequisite gate the apps do. User auth creates a profile when OTP says `setup_complete=false`; store auth checks `setup`; and store/menu preflight creates or repairs missing store setup, categories, and menu items when `SIM_AUTO_PROVISION_FIXTURES=true`. Targeted negative checks can disable this flag to prove the backend reports missing prerequisites instead of repairing them.

## Status Ownership

| Owner | Status/action | Endpoint |
|---|---|---|
| User | `pending` order creation | `POST /v1/core/orders/` |
| Store | `payment_processing` or `rejected` | `PATCH /v1/core/orders/?order_id=<id>` |
| User | `cancelled` while still pending | `PATCH /v1/core/orders/?order_id=<id>` |
| Backend | `order_processing` | Stripe webhook or free-order confirmation |
| Store | `ready` | `PATCH /v1/core/orders/?order_id=<id>` |
| Robot | `enroute_pickup` to `completed` | `PATCH /v1/core/orders/?order_id=<id>` |

The simulator never patches `order_processing`; it waits for the backend to prove payment completion.

## Trace Mode

Supported scenarios:

| Scenario | Intent |
|---|---|
| `completed` | Full happy path from order placement through robot completion |
| `rejected` | Store rejects before payment |
| `cancelled` | Customer cancels while the order is still pending |
| `auto_cancel` | Diagnostic check for backend timeout cancellation without store action |
| `app_bootstrap` | Probe config, product auth, pricing, saved cards, coupons, active user orders |
| `store_dashboard` | Probe store orders, store statistics, and top customers |
| `receipt_review_reorder` | Full completed order plus receipt generation, review submission, and reorder fetch |

Timing profiles:

| Profile | Intent |
|---|---|
| `fast` | Minimal artificial delays for proof runs and CI-like validation |
| `realistic` | Human-like store and robot timing |

## Auth And Token Reuse

Each simulator handles its own authentication inside its `run()` entrypoint (or `bootstrap_auth()` for trace mode).

**User auth** (`user_sim`):
1. If `USER_LASTMILE_TOKEN` and `USER_ID` exist, validates via `GET /v1/core/orders/?user=<USER_ID>`.
2. If validation succeeds, reuses the cached token.
3. If rejected (`401/403`), clears cache, runs OTP flow, persists fresh token + user_id to `.env`.

**Store auth** (`store_sim`):
- Reuses `STORE_LASTMILE_TOKEN` from `.env`, or fetches via product-auth endpoint.
- Fetches store profile via `/v1/entities/store/login` and sets `SUBENTITY_ID`.

**Robot auth** (`robot_sim`):
- Independently acquires the same store token (env or product-auth).
- No shared token provider — each sim authenticates on its own.

Auth proof (masked header, scheme, source, fingerprint) is recorded in every case.

## Websocket Validation

The observer connects before scenario or load actors start:

| Stream | URL |
|---|---|
| User orders | `/ws/soc/<user_id>/` |
| Store orders | `/ws/soc/store_<store_id>/` |
| Store stats | `/ws/soc/store_statistics_<store_id>/` |

Messages are decoded the same way the Flutter apps consume them: outer JSON first, then `payload["message"]` if it contains nested JSON. Every expected status change is matched against websocket traffic by order id/reference and status, with latency attached to the originating event. Missing or late messages are recorded as findings.

## Run Artifacts

Each run writes:

```text
simulate/runs/<timestamp>/
  events.json
  report.md
  story.md
```

Artifact roles:

| File | Contents |
|---|---|
| `events.json` | Full source-of-truth ledger for auth, fixture lookup, HTTP traffic, websocket traffic, delays, status proofs, and issues |
| `report.md` | Technical proof document with scenario verdicts, websocket assertions, developer findings, and full per-step trace |
| `story.md` | Layman-friendly explanation of what happened and what went wrong |

`report.md` starts with a daily doctor summary before the technical trace:

| Section | Contents |
|---|---|
| Daily Doctor Summary | Verdict, duration, scenario/order/API/websocket/issue counts |
| Graphical Summary | Plain-text bars for quick scanning in any markdown viewer |
| Bottlenecks | Slowest endpoints grouped by method/path with average, p95, and max latency |
| Scenario Verdicts | Expected vs actual result per scenario |
| Websocket Assertions | Expected status messages matched to observed socket traffic |
| Technical Trace | Full per-event proof with auth fingerprints, payload previews, and latency |

## JSON Run Plan

The public input is a JSON file. `sim_actors.json` remains valid, and richer plans can add GPS to each user:

```json
{
  "defaults": {
    "user_phone": "+2348166675609",
    "store_id": "FZY_586940",
    "location_radius": 1,
    "coupon_id": null
  },
  "users": [
    {
      "phone": "+2349077777740",
      "role": "returning",
      "lat": 35.15494521954757,
      "lng": 136.9663666561246,
      "orders": 3
    }
  ],
  "stores": [
    {
      "store_id": "FZY_586940",
      "subentity_id": 6,
      "currency": "jpy",
      "lat": 35.15494521954757,
      "lng": 136.9663666561246
    }
  ]
}
```

Use `--strict-plan` when operators want the simulator to reject users without GPS coordinates or stores without IDs.

## CLI

Examples:

```bash
python3 -m simulate --mode load --orders 1 --reject 0
python3 -m simulate --mode load --continuous --users 5 --interval 20 --reject 0.2
python3 -m simulate --mode trace --suite core --timing fast
python3 -m simulate --mode trace --scenario completed --scenario cancelled --timing realistic
python3 -m simulate doctor --plan sim_actors.json --timing fast
python3 -m simulate receipt-review --plan sim_actors.json --post-order-actions
python3 -m simulate store-dashboard --plan sim_actors.json
```

## Required Environment

```env
USER_PHONE_NUMBER=+819012345678
USER_LASTMILE_TOKEN=
USER_ID=

STORE_ID=1
STORE_LASTMILE_TOKEN=

SUBENTITY_ID=1
LOCATION_ID=
STORE_CURRENCY=jpy

SIM_LAT=
SIM_LNG=
SIM_LOCATION_RADIUS=1

SIM_RUN_MODE=load
SIM_TRACE_SUITE=core
SIM_TRACE_SCENARIOS=
SIM_TIMING_PROFILE=fast

SIM_PAYMENT_MODE=stripe
SIM_PAYMENT_CASE=paid_no_coupon
SIM_RUN_APP_PROBES=true
SIM_RUN_STORE_DASHBOARD_PROBES=true
SIM_RUN_POST_ORDER_ACTIONS=false
SIM_STRICT_PLAN=false
SIM_APP_AUTOPILOT=true
SIM_AUTO_SELECT_STORE=true
SIM_AUTO_SELECT_COUPON=true
SIM_REVIEW_RATING=4
SIM_REVIEW_COMMENT=Simulator review
STRIPE_SECRET_KEY=
STRIPE_TEST_PAYMENT_METHOD=pm_card_visa
SIM_SAVE_CARD=false
SIM_FREE_ORDER_AMOUNT=0
SIM_COUPON_ID=

LASTMILE_BASE_URL=https://lastmile.fainzy.tech
FAINZY_BASE_URL=https://fainzy.tech

N_USERS=1
SIM_ORDERS=1
SIM_CONTINUOUS=false
ORDER_INTERVAL_SECONDS=30
REJECT_RATE=0.1

USER_DECISION_POLL_INTERVAL_SECONDS=5
USER_DECISION_POLL_MAX_ATTEMPTS=60
ORDER_PROCESSING_POLL_INTERVAL_SECONDS=5
ORDER_PROCESSING_POLL_MAX_ATTEMPTS=60
SIM_WEBSOCKET_CONNECT_GRACE_SECONDS=1
SIM_WEBSOCKET_DRAIN_SECONDS=3
SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS=20
```

`SIM_LAT` and `SIM_LNG` are user delivery coordinates for `/v1/entities/locations/<lng>/<lat>/`. Store coordinates from the run plan are store metadata only and must not overwrite delivery-location search coordinates.

`SIM_APP_AUTOPILOT=true` is the default operator mode. It lets doctor/trace flows behave like the apps: when no store is explicit, startup can try planned stores until one serves the selected user/location, and coupon scenarios can fetch/select a valid coupon automatically.

## Verification

Static verification:

```bash
PYTHONPYCACHEPREFIX=/tmp/fainzy-pycache python3 -m py_compile simulate/*.py
python3 -m unittest discover -s simulate/tests
python3 -m simulate --help
```

Live examples after `.env` is configured:

```bash
python3 -m simulate --mode trace --suite core --timing fast
python3 -m simulate --mode load --orders 1 --reject 0
python3 -m simulate --mode load --orders 1 --reject 1
STRIPE_TEST_PAYMENT_METHOD=pm_card_chargeDeclined python3 -m simulate --mode load --orders 1 --reject 0
python3 -m simulate doctor --plan sim_actors.json --timing fast
```
