# Solution — Rich Trace Log Diagnostics

## Proposed approach

Extend the **existing `_sim_log` path in trace mode** and the console.print calls in store_sim/robot_sim/user_sim to surface HTTP verb + endpoint + status code + latency at every call site. For WebSocket, add three new log lines: (1) a pre-wait "waiting for…" announcement, (2) a post-success "✓ confirmed on channel" line, and (3) a rich failure block that lists the events that DID arrive for that order before the timeout.

All changes are purely additive to console output — no recorder schema changes, no output file changes.

### HTTP call lines

Every existing high-level message ("Fetching store profile …", "Placing order …", "Processing payment …") gains an inline suffix:
```
[scenario] store: GET /api/subentities/FZY_926025/  →  200 OK  (143 ms)
[scenario] user: POST /api/orders/  →  201 Created  (88 ms)  db_id=2348  ref=#323885
[scenario] payment: POST /api/stripe/confirm/  →  200 OK  (234 ms)
```
HTTP errors show the full request + response status:
```
[scenario] store: POST /api/orders/2348/accept/  →  503 Service Unavailable  (5012 ms)  ✗
```

The `request_json()` wrapper already receives `method`, `endpoint`, `http_status`, and `latency_ms`. The cleanest implementation is a thin helper that formats and emits this line immediately after `request_json()` returns (or raises), called from each sim module's own action function rather than from inside transport.py (keeps transport generic).

### WebSocket connection lines

```
websocket: connecting  user_orders  →  wss://lastmile.fainzy.tech/ws/soc/11/
websocket: ✓ connected  store_orders  →  wss://…/ws/soc/store_7/  (0.3 s)
```

### WS gate: pre-wait announcement

```
[scenario] websocket: waiting for status=order_processing  on [store_orders, user_orders]  timeout=20 s  order=2353 (#954460) …
```

### WS gate: success confirmation

```
[scenario] websocket: ✓ status=order_processing  confirmed via store_orders  (1.8 s)  order=2353 (#954460)
```

### WS gate: failure — rich diagnostic block

```
[scenario] websocket: ✗ GATE FAILED  status=order_processing  order=2353 (#954460)
          step     : wait_order_processing_before_ready
          channels : store_orders, user_orders
          waited   : 20.0 s  (timeout)
          last seen: no events received for this order on these channels
```
Or when some events arrived:
```
          last seen: payment_processing (store_orders, t+0.3 s)  — expected order_processing
```

`websocket_gate_source_unavailable` variant:
```
          reason   : channel failed — store_orders, user_orders both down
```

## Alternatives rejected

- **Emitting HTTP details from inside `transport.request_json()`** — rejected because it would force a `scenario` + console reference into a generic transport layer that currently knows nothing about the UI, and would print in load mode too (undesirable noise for concurrent workers).
- **Changing the recorder schema** — rejected; the data is already recorded. Adding it a second time creates duplication maintenance.

## Performance impact

Neutral — these are console writes on a non-hot-path. Trace mode is single-threaded sequential. Load mode changes are gated behind the existing `SIM_RUN_MODE == "load"` branch.

## Performance delta

N/A — no rendering, queries, or socket traffic changed. Pure console output.

## Trade-offs

Trace mode logs become more verbose (~2-4× more lines). This is intentional; trace mode is a diagnostic tool.

## Dead code audit

No dead code introduced or created by this change. No existing code is removed.
