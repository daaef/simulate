# Sub-task 02: Backend auto-cancel — load mode probe

## What this does
Adds a single "orphan order probe" at the end of every load run: one order is placed,
all actions are withheld, and the simulator watches 120s for the backend to cancel it.

## Where this lives
Load mode is orchestrated in `store_sim.py` and driven by `__main__.py`.
The probe runs as a final step after all load orders settle.

## Approach
- After the load run completes (all concurrent users finish), run `_run_backend_auto_cancel()`
  from `trace_runner.py` using the same user/store session
- This reuses the existing `_run_backend_auto_cancel` function — no new logic needed
- Record the result in the same `RunRecorder`

## Done when
- Running `--flow load` logs a `backend_auto_cancel` probe step at the end
- The probe outcome (passed/unsupported/timeout) appears in the run report
