# Complete Order Flow Simulator

## Overview

`simulate` now supports two execution styles:

| Mode | Purpose |
|---|---|
| `load` | Randomised multi-actor traffic simulation for churn, failure hunting, and live platform smoke tests |
| `trace` | Deterministic proof-oriented scenarios for `completed`, `rejected`, `cancelled`, and optional `auto_cancel` |

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

REST remains the control-plane source of truth. Each sim listens on an active websocket for real-time order status changes that drive behaviour. The passive `WebsocketObserver` runs alongside for reporting validation.

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

## CLI

Examples:

```bash
python3 -m simulate --mode load --orders 1 --reject 0
python3 -m simulate --mode load --continuous --users 5 --interval 20 --reject 0.2
python3 -m simulate --mode trace --suite core --timing fast
python3 -m simulate --mode trace --scenario completed --scenario cancelled --timing realistic
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
```
