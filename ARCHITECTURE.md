# Complete Order Flow Simulator

## Overview

`simulate` now supports two execution styles:

| Mode | Purpose |
|---|---|
| `load` | Randomised multi-actor traffic simulation for churn, failure hunting, and live platform smoke tests |
| `trace` | Deterministic proof-oriented scenarios for `completed`, `rejected`, `cancelled`, and optional `auto_cancel` |

Shared components:

| Component | Responsibility |
|---|---|
| `auth` | User/store auth, cached-token validation, OTP fallback, token-source proof |
| `seed` | Real store/menu/location fixture lookup |
| `user_sim` | Order placement, user-side polling, payment, cancellation |
| `store_sim` | Store accept/reject, payment verification, mark ready |
| `robot_sim` | Robot-owned delivery statuses until completion |
| `trace_runner` | Deterministic end-to-end trace orchestration |
| `websocket_observer` | User/store/stats socket observation and validation |
| `transport` | Masked request/response proof, auth proof, latency capture |
| `reporting` | `events.json`, `report.md`, and `story.md` artifacts |

REST remains the control-plane source of truth. Websockets are observed in parallel and validated per status transition instead of only being counted.

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

The simulator treats the user LastMile token as a cached credential in `simulate/.env`.

1. If `USER_LASTMILE_TOKEN` and `USER_ID` exist, startup validates them with `GET /v1/core/orders/?user=<USER_ID>`.
2. If validation succeeds, the simulator reuses the cached token and records masked auth proof.
3. If the backend rejects the token with `401/403`, the simulator clears the cached token fields, runs the OTP flow, and writes the fresh token and user id back into `.env`.

Store auth can either reuse `STORE_LASTMILE_TOKEN` from `.env` or fetch a fresh one from the product-auth endpoint. In every case the recorder stores masked auth proof only: header name, scheme, source, fingerprint, and short preview.

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
