# Changelog — Rich Trace Log Diagnostics

**Date:** 2026-06-10  
**Plan:** [plan.md](plan.md)  
**Status:** done

---

## Layer 1 — High-level: what changed for users

Before this change, every line in the simulation console log was a short narrative sentence ("Store LastMile token acquired.", "payment succeeded ✓"). There was no way to know which HTTP verb was used, what endpoint was called, what the status code was, how long it took, or what a WebSocket gate was waiting for. When a gate failed, the log showed a single terse line with no diagnostic context.

After this change:

- Every auth HTTP call (OTP, store login, store profile, robot auth) now prints `METHOD /endpoint  →  HTTP_STATUS  (X ms)` immediately after the human-readable summary line.
- Every order-mutating HTTP call (place_order, store PATCH, robot PATCH) now prints the same detail line showing method, endpoint, status code, and latency.
- Every HTTP failure prints a bold-red `METHOD /endpoint  →  STATUS or reason  (X ms)  ✗` line showing exactly which call failed and why.
- WebSocket connections now log `connecting channel → wss://…` before the handshake and `connected channel → wss://…` after, for all three observer channels (store_orders, user_orders, store_stats), the store_sim internal watcher, the robot_sim internal watcher, and the user_sim internal watcher.
- WebSocket gates now announce before they wait: `waiting for status=X  channels=[…]  timeout=20s  order=N (#REF) …`
- When a gate passes: `✓ status=X  confirmed via store_orders  (1.8s)  order=N (#REF)`.
- When a gate fails: a four-line diagnostic block shows the step name, channel list, elapsed wait time, failure code, and the **last status actually seen** for that order (or "no events received" if none arrived).

---

## Layer 2 — Low-level: exactly what changed and why

### `simulate/websocket_observer.py`

**`WebsocketObserver.last_seen_status()` — new method, after `missing_sources()` (~line 156)**  
Before: no way to query the most recent order event from outside the class.  
After: `last_seen_status(order_db_id, sources=None)` iterates `_order_events` in reverse and returns the most recent entry matching `order_db_id` (and optionally filtered to the given source set), or `None`. Used by `_wait_for_ws_gate` to populate the failure diagnostic.  
Why: the failure block in `_wait_for_ws_gate` needed to show what the gate actually saw before timing out.

**`WebsocketObserver._listen()` — connecting + URL in connected lines (~line 377–388)**  
Before: `console.print(f"[blue]websocket:[/] connected {source}")` — no URL.  
After: adds `console.print(f"[dim]websocket:[/] connecting  {source}  →  {url}")` before opening the socket, and changes the connected line to `f"[blue]websocket:[/] connected   {source}  →  {url}"`.  
Why: users could not tell which server each channel connected to.

### `simulate/trace_runner.py`

**`_wait_for_ws_gate()` — enriched with pre-wait, success, and rich failure logs (~line 764–885)**  
Before: silent before the wait; after failure, a single `_sim_log` error line with just the failure code and step.  
After:
1. Resolves `effective_timeout` from param or config before starting.
2. Emits a pre-wait `_sim_log` line showing status, channels, timeout, and order identity.
3. Records `t_start = time.monotonic()` before calling `observer.wait_for_order_status()`.
4. On success: emits `✓ status=X  confirmed via {source}  (Xs)  order=N` with elapsed time.
5. On failure: computes elapsed, calls `observer.last_seen_status()`, then emits four `_sim_log` error lines (step, channels, waited + failure code, last seen). The bypass path (gates not enforced) also gains a warn log.  
Why: the failing gate in the user's log showed only `websocket_gate_timeout` — impossible to diagnose without knowing channels, wait time, or last seen status.

Note: Plan step 1 (`_http_log` helper) was merged into this step. The helper function was not created as a standalone since `_sim_log` already satisfies all formatting needs for trace_runner's own output. No dead code introduced.

### `simulate/store_sim.py`

**`_auth_request()` — HTTP detail print after success and on error (~line 120–170)**  
Before: `return result.payload` with no console output about the HTTP call.  
After: on success, prints `[dim]actor:[/] METHOD /endpoint  →  STATUS  (X ms)` before returning. On `RequestError`, prints `[bold red]actor:[/] METHOD /endpoint  →  STATUS_OR_REASON  (X ms)  ✗` before re-raising as `HttpApiError`.  
Why: calls to `fetch_store_token` and `bootstrap_auth` showed narrative summaries but no HTTP detail.

**`patch_status()` — capture result, replace status-only log with HTTP detail (~line 1111–1166)**  
Before: `await request_json(...)` (discarded result), then `console.print(f"[yellow]store_sim:[/] order=X -> status")`.  
After: `result = await request_json(...)`, then prints `[dim]actor:[/] PATCH /v1/core/orders/  →  STATUS  (X ms)  order=N  status=S`. On `RequestError`, prints the full error line before recording the issue.  
Why: store status transitions (accept/reject/ready) had no HTTP detail.

**`_StoreOrderWatcher._listen()` — URL in connected line (~line 382)**  
Before: `console.print(f"[blue]store_ws:[/] connected /ws/soc/store_{self.store_id}/")` — path only.  
After: `console.print(f"[blue]store_ws:[/] connected   store_orders  →  {url}")` — full URL.

### `simulate/user_sim.py`

**`_auth_request()` — same change as store_sim (~line 184–222)**  
Covers OTP send, OTP verify, token fetch, and cache validation calls.

**`place_order()` — HTTP detail lines on success and failure (~line 1477–1545)**  
Before: on error, `console.print(f"[red]user[{worker_id}]:[/] Error placing order: {exc}")` only. On success, only the "Order placed" summary.  
After: on error, prints the HTTP detail line (verb, endpoint, status, latency, order ref) before the error summary. On success, prints `[dim]user[N]:[/] POST /v1/core/orders/  →  STATUS  (X ms)  db_id=N  ref=#X` before the green success line.

**`_UserOrderWatcher._listen()` — URL in connected line (~line 1346)**  
Before: `console.print(f"[blue]user_ws:[/] connected /ws/soc/{self.user_id}/")`.  
After: `console.print(f"[blue]user_ws:[/] connected   user_orders  →  {url}")`.

### `simulate/robot_sim.py`

**`_auth_request()` — same change as store_sim (~line 117–155)**  
Covers robot store token acquisition.

**`patch_status()` — capture result, HTTP detail on success and error (~line 387–425)**  
Before: `await request_json(...)` (discarded), then `console.print(f"[magenta]robot_sim:[/] order=X -> status")`.  
After: `result = await request_json(...)`, then prints `[dim]robot:[/] PATCH /v1/core/orders/  →  STATUS  (X ms)  order=N  status=S`. On `RequestError`, prints the error detail before recording the issue.

**`_RobotOrderWatcher._listen()` — URL in connected line (~line 287)**  
Before: `console.print(f"[blue]robot_ws:[/] connected /ws/soc/store_{self.store_id}/")`.  
After: `console.print(f"[blue]robot_ws:[/] connected   robot_store_orders  →  {url}")`.
