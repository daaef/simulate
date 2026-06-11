# Problem — Rich Trace Log Diagnostics

**Root cause:** Console output in trace mode (and load mode) is high-level narrative only. HTTP method/URL, WebSocket channel URLs, gate wait intent, and gate failure context are all silently swallowed into the recorder (events.jsonl) and never surfaced on screen.

## Symptoms

- HTTP calls print human-readable summaries ("Fetching store profile …") but never the verb, endpoint, HTTP status code, or latency — impossible to tell whether a slow or failing call is a GET vs POST, or which endpoint is misbehaving.
- WebSocket connections print `websocket: connected store_orders` with no URL, so it is unclear which server/path the socket connected to.
- WS gate waits start silently. There is no log line announcing "waiting for status=order_processing on [user_orders, store_orders] with timeout=20 s". When a timeout fires you don't know how long it waited.
- WS gate failures print only a code (`websocket_gate_timeout`) with no context about which events DID arrive for that order, what channels were being observed, what the last seen status was, or how much of the timeout elapsed.
- WS gate successes are completely silent. There is no confirmation that a gate passed, which channel delivered the event, or how fast it arrived.
- `store_sim: order=X -> status` and `robot_sim: order=X -> status` lines are orphaned from the HTTP call that drove the status change.
- Load mode has no per-order console progress at all.

## Affected files / functions

| File | Function / area | Lines |
|------|----------------|-------|
| `trace_runner.py` | `_wait_for_ws_gate()` | 751–870 |
| `trace_runner.py` | `_sim_log` callsites for HTTP actions | scattered |
| `websocket_observer.py` | `wait_for_order_status()` | 163–224 |
| `websocket_observer.py` | `_listen()` / connection lifecycle | 226–400 |
| `store_sim.py` | `console.print` bootstrap and status lines | 93–145, 1427–1501 |
| `robot_sim.py` | lifecycle status console output | delivery loop |
| `__main__.py` | load mode worker loop | 725–789 |

## Blast radius

Purely additive console output changes. No API contracts, no data shapes, no recorder events are changed. The recorder already captures all this data — the gap is only on-screen visibility.

## Constraints

- Must not change the recorder event schema.
- Must not affect `report.md`, `events.jsonl`, or `story.jsonl` output.
- Load mode: output must remain minimal enough not to drown concurrent workers — one summary line per order lifecycle event (not per poll).
- Trace mode: verbosity increase is acceptable; it is already a single-order trace.

## Edge cases

- Gate failure with `websocket_gate_source_unavailable` (not timeout) must show which sources failed vs which were expected.
- WS gate called with no previous events for the order (empty seen-events list) must still surface cleanly.
- HTTP errors (4xx/5xx, timeout, connection refused) must show the full request line, not just the action name.
