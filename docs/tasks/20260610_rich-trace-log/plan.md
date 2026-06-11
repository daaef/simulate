# Plan — Rich Trace Log Diagnostics

## Implementation Steps

### Step 1 — Add `_http_log` helper to `trace_runner.py`  *(trivial)*
**File:** `simulate/trace_runner.py`  
Add a small helper below `_sim_log` that accepts scenario, actor, method, endpoint, http_status, latency_ms, and an optional note (e.g., `db_id=X ref=#Y`), then calls `_sim_log` with a formatted `METHOD /endpoint → HTTP_STATUS (Xms) [note]` message.  
**AC:** Helper exists and is callable; `_sim_log` output matches the format in solution.md.

---

### Step 2 — Enrich `_wait_for_ws_gate` with pre-wait, success, and rich failure logs  *(low)*
**File:** `simulate/trace_runner.py` lines 751–870  
- Before calling `observer.wait_for_order_status()`: emit `_sim_log(scenario, "websocket", f"waiting for status={expected_status} on {sorted(sources)} timeout={timeout}s order={order_db_id} ({order_ref}) …")`.  
- On success: emit `_sim_log(scenario, "websocket", f"✓ status={expected_status} confirmed via {event.get('source')} ({elapsed:.1f}s) order={order_db_id} ({order_ref})", level="success")`.  
- On failure: replace the single-line error with a multi-line block (use Rich panel or indented lines) showing step, channels, wait duration, and last-seen event for that order pulled from `observer.last_seen_status(order_db_id)` (see step 3).  
**AC:** Running a failing `completed` scenario prints channels, wait time, and last-seen status before the gate error is reported.

---

### Step 3 — Add `last_seen_status()` to `WebsocketObserver`  *(low)*
**File:** `simulate/websocket_observer.py`  
Add a method `last_seen_status(order_db_id: int) -> dict | None` that returns the most recent `_order_events` entry matching that order_db_id, or `None` if no events were received.  
Also make `wait_for_order_status()` track elapsed time so it can be returned in the `RuntimeError` message or a companion attribute.  
**AC:** `last_seen_status(2353)` returns `{"status": "payment_processing", "source": "store_orders", ...}` when called after the gate timeout for order 2353.

---

### Step 4 — Add URL to WebSocket connection console lines  *(trivial)*
**File:** `simulate/websocket_observer.py` lines ~373  
Change `console.print(f"[blue]websocket:[/] connected {source}")` to `console.print(f"[blue]websocket:[/] connected {source}  →  {url}")` and add a matching "connecting …" line before the socket is opened.  
**AC:** Log shows `websocket: connected store_orders  →  wss://lastmile.fainzy.tech/ws/soc/store_7/`.

---

### Step 5 — Emit HTTP detail lines from store_sim action functions  *(low)*
**File:** `simulate/store_sim.py`  
After each `request_json()` call that has a user-facing console.print before it, call `_http_log` (imported from trace_runner, or re-implemented as a standalone inline call). Target calls: `bootstrap_auth`, `get_store_profile`, `ensure_store_setup`, `accept_order`, `reject_order`, `mark_ready`.  
Keep existing human-readable "Fetching …" / "Store profile acquired …" lines; the HTTP detail line follows on the next line.  
**AC:** Log shows `store: GET /api/subentities/FZY_926025/  →  200 OK  (143 ms)` immediately after the human-readable store profile line.

---

### Step 6 — Emit HTTP detail lines from user_sim and robot_sim  *(low)*
**Files:** `simulate/user_sim.py`, `simulate/robot_sim.py`  
Same pattern: after each `request_json()` call in place_order, get_user_token, delivery status updates, emit the HTTP detail line.  
**AC:** Log shows `user: POST /api/orders/  →  201 Created  (88 ms)  db_id=2348  ref=#323885` on the line after "Placing order #323885".

---

### Step 7 — Emit HTTP error detail on RequestError  *(low)*
**File:** `simulate/trace_runner.py` and each sim module where `RequestError` is caught  
In the `except RequestError` blocks (or wherever the sim modules currently log HTTP failures), emit a `_sim_log` error line: `METHOD /endpoint  →  HTTP_STATUS or REASON  (Xms)  ✗`.  
**AC:** A simulated 503 from accept_order shows `store: POST /api/orders/2348/accept/  →  503  (5012 ms)  ✗` in red.

---

### Step 8 — Update `docs/tasks/README.md`  *(trivial)*
Add a row for this task.  
**AC:** README table has a row with slug `20260610_rich-trace-log`, status `done`, summary "Rich HTTP + WebSocket diagnostic output in trace/load console logs".

---

## Untested path disclosure

- Load mode HTTP detail lines (step 5–6 changes will print in trace mode only; load mode uses `SIM_RUN_MODE`-gated paths — this must be guarded so load mode workers don't flood stdout).
- WS `websocket_gate_source_unavailable` path (step 2) — not covered by any scenario that reliably kills a WS source; will be visually verified by inspection of the code path.

## Regression checklist

| Changed function | Direct callers to verify |
|-----------------|-------------------------|
| `_wait_for_ws_gate()` | all gate call sites in trace_runner.py (~8 sites) |
| `WebsocketObserver.wait_for_order_status()` | `_wait_for_ws_gate`, `__main__.py` load gate enforcement |
| `WebsocketObserver._listen()` | `start()` |
| `store_sim` action functions | `trace_runner.py` scenario functions |
| `user_sim.place_order` | `trace_runner.py` order placement |
| `robot_sim` status update | `trace_runner.py` robot lifecycle |

## Definition of Done

- [ ] App runs without new warnings or errors
- [ ] Every AC in the plan is verified (observed in app or test output)
- [ ] Regression checklist cleared — all listed callers manually verified
- [ ] Dead code audit complete — orphaned code removed or explicitly deferred with a note
- [ ] No new `any` types or unsafe assertions without inline justification
- [ ] No new dependencies without justification in solution doc
- [ ] Cross-file consistency verified — similar patterns elsewhere are consistent or intentionally different
- [ ] Performance baseline recorded and delta noted (if fix touches rendering, queries, or socket traffic)
