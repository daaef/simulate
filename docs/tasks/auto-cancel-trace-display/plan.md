# Implementation Plan: Backend Auto-Cancel, Real Store Mode, Live Trace Display

## Context

The Fainzy Simulator runs scripted simulations against a live server. Three improvements are being made:

1. **Backend auto-cancel is now a built-in guarantee** — every run proves that the server cleans up untouched orders.
2. **Real Store Mode** — a new checkbox lets you run the simulator with a real human acting as the store from their app.
3. **Live trace display** — the console stream switches from internal debug labels to human-readable narrative lines.

---

## Goals

| # | Goal | Done when |
|---|------|-----------|
| 1 | `backend_auto_cancel` runs in all trace suites + load mode, always with a 2-min window | Running `doctor` or `load` includes a backend auto-cancel check |
| 2 | "Wait for real store" checkbox appears in the UI; when checked, simulator waits for a real store instead of acting as one | Checking the box and running a trace scenario makes the simulator pause at each store decision point |
| 3 | Console output uses `[scenario] actor: action … result` format throughout | Running any trace scenario emits readable lines instead of `[green]trace:[/]` labels |

---

## Concepts

| Term | What it means here |
|------|--------------------|
| `asyncio.create_task` | Starts a background coroutine that runs in parallel with the main scenario logic — used for the backend auto-cancel watcher |
| `auto_cancel_wait_seconds` | The observation window (in seconds) the simulator waits to see if the backend cancels an order. Lives in `TimingProfile` in `scenarios.py`. |
| `SIM_WAIT_FOR_STORE_ACTION` | New config flag: when True, the simulator does NOT call store APIs; it waits for a real store to act |
| `_sim_log(scenario, actor, action, result)` | New helper in `trace_runner.py` that emits structured, human-readable console lines |
| Poll + WebSocket | Two ways to detect order status: WebSocket = server pushes instantly, polling = simulator asks every N seconds. The watcher uses WebSocket first, polling as fallback. |

---

## Approach — Step by Step

### Sub-task 01: Backend auto-cancel — universal timing

File: `scenarios.py`

- Set `auto_cancel_wait_seconds` to **120.0** for BOTH `fast` and `realistic` profiles (was 30s for fast)
- Add `backend_auto_cancel` to all `TRACE_SUITES` entries that don't already have it: `doctor`, `audit`, `core`, `store`, `payments`, `menus`
- Do NOT add `auto_cancel` to other suites — that one requires payment withholding and is complex enough to keep in `full` only

### Sub-task 02: Backend auto-cancel — load mode

File: `store_sim.py` or a new `auto_cancel_probe.py`

- In load mode, after all orders are placed and settled, run one dedicated "orphan order" probe: place one additional order, withhold all actions, and watch 120s for backend cancellation
- Record the outcome in the run recorder (verdict: `passed` if cancelled, `unsupported` if not observed)

### Sub-task 03: Real Store Mode — config + CLI

Files: `config.py`, `__main__.py`

- Add `SIM_WAIT_FOR_STORE_ACTION: bool = False` to `config.py`
- Add `--wait-for-store-action` flag to CLI in `__main__.py` (sets `config.SIM_WAIT_FOR_STORE_ACTION = True`)
- Add timeout: `SIM_STORE_ACTION_TIMEOUT_SECONDS: float = 600.0` (10 minutes, configurable)

### Sub-task 04: Real Store Mode — trace runner behavior

File: `trace_runner.py`

- In `_fulfill_placed_order`: when `SIM_WAIT_FOR_STORE_ACTION` is True, replace the `store_sim.patch_status("payment_processing")` call with `_wait_for_store_to_act()` — a polling loop that watches for the order to leave `pending` via the real store
- In `_fulfill_placed_order`: after payment, replace `store_sim.patch_status("ready")` with a wait for the real store to mark ready
- Timeout behavior: if the real store doesn't act within `SIM_STORE_ACTION_TIMEOUT_SECONDS`, mark the scenario as `blocked` with a clear note ("waiting for real store action — timed out")
- `backend_auto_cancel` and `auto_cancel` scenarios are unaffected in real-store mode (they already withhold store action by design)

### Sub-task 05: Real Store Mode — UI checkbox + API plumbing

Files:
- `web/src/lib/run-launcher-config.ts` — add `wait_for_store_action` field
- `web/src/components/runs/RunLaunchPanel.tsx` — add checkbox (unchecked by default, trace-mode only)
- `web/src/lib/api.ts` — add field to `RunCreateRequest`
- `api/app/runs/models.py` — add field and pass to CLI arg builder

### Sub-task 06: Live trace display

File: `trace_runner.py`

- Add `_sim_log(scenario: str, actor: str, message: str)` helper at the top of the file:
  ```python
  def _sim_log(scenario: str, actor: str, message: str) -> None:
      console.print(f"[{scenario}] {actor}: {message}")
  ```
- Replace all `console.print(...)` calls in `trace_runner.py` with `_sim_log(scenario, actor, message)` calls
- Format rules:
  - Use the scenario name as the prefix: `[store-accept]`, `[backend-auto-cancel]`, `[bootstrap]`
  - Actor is one of: `user`, `store`, `robot`, `payment`, `websocket`, `backend`, `trace`
  - Message follows `action … result` pattern: e.g. `placing order (₦2,500) … order #12345 created`

---

## Verification

| Check | How |
|-------|-----|
| backend_auto_cancel runs in doctor | Run `python -m simulate --flow doctor` and confirm `backend_auto_cancel` appears in the scenario list |
| 120s window on fast timing | Run doctor, observe the auto-cancel observe window is 120s not 30s |
| Real store mode waits | Run with `--wait-for-store-action`, confirm simulator logs "waiting for real store to act" and pauses |
| Live trace format | Run any scenario, confirm console output shows `[scenario] actor: action … result` |
| No regressions | Run `full` trace from end to end |

---

## Files Changed (summary)

| File | Change |
|------|--------|
| `scenarios.py` | fast profile `auto_cancel_wait_seconds` 30→120; `backend_auto_cancel` added to all suites |
| `config.py` | Add `SIM_WAIT_FOR_STORE_ACTION`, `SIM_STORE_ACTION_TIMEOUT_SECONDS` |
| `__main__.py` | Add `--wait-for-store-action` CLI flag |
| `trace_runner.py` | Add `_sim_log()`; replace `console.print()`; add `_wait_for_store_to_act()` |
| `api/app/runs/models.py` | Add `wait_for_store_action` to run request model + CLI builder |
| `web/src/lib/api.ts` | Add field to `RunCreateRequest` |
| `web/src/components/runs/RunLaunchPanel.tsx` | Add checkbox |
| `web/src/lib/run-launcher-config.ts` | Add field |
