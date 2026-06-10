# WebSocket Failure Visibility

> Completed: 2026-06-10  
> Files changed: `simulate/trace_runner.py`, `simulate/websocket_observer.py`, `simulate/__main__.py`  
> Checklist items fixed: 0 (no pre-existing quality issues in touched lines)

---

## What happened (Layman)

When the simulation runs its tests, it checks that real-time messages (called
"websocket events") arrived from the server at each important step — like when
an order is created, accepted, or cancelled. If these messages are missing, the
run fails. Before this fix, the failure message only said "missing websocket
evidence" with no detail about *which* order failed or *which* step was
missing. The run log looked fine right up until the very last line, where it
suddenly said it failed — like a race with no visible crash. Now, the console
prints exactly which order and which step failed, both at the moment it happens
and again as a summary at the end.

---

## How it works (Pseudocode)

1. During the run, when the simulator waits for a websocket message confirming
   an order reached a specific status (the "gate"):
   - If the message arrives → continue normally.
   - If the message never arrives within the time limit AND enforcement is on →
     record an error issue in the run file **and** print it to the console
     immediately (new).

2. At the end of the run, the validator loops over every order and checks that
   a websocket message exists for every important status (pending, final status,
   etc.):
   - If a status has no matching websocket message → record an issue in the run
     file **and** print the order ID + missing status to the console (new).

3. When the run is about to fail because of these websocket gaps:
   - Collect all error-level issues from the run file.
   - Print them as a numbered list to the console (new).
   - Then raise the failure error.

---

## The implementation (Code-level)

**Changed files:**
- [trace_runner.py:816](../../trace_runner.py#L816) — `_wait_for_ws_gate`: added `_sim_log` on enforced gate failure
- [websocket_observer.py:679](../../websocket_observer.py#L679) — `validate_websocket_events`: `console.print` per lifecycle proof gap
- [__main__.py:1005](../../__main__.py#L1005) — consolidated error summary before raising

**Key change — trace_runner.py (gate failure log):**
```python
# Before: silent failure (issue recorded to file only)
recorder.record_issue(severity="error", ...)
_finish_checked(recorder, scenario, ...)
return False

# After: gate failure is also printed to console
recorder.record_issue(severity="error", ...)
_sim_log(
    scenario,
    "websocket",
    f"GATE FAILED order={order_db_id} ({order_ref}) "
    f"expected={expected_status} step={step}: {_gate_failure_code(exc)}",
    level="error",
)
_finish_checked(recorder, scenario, ...)
return False
```

**Key change — websocket_observer.py (lifecycle proof print):**
```python
# Before: issue recorded, nothing printed
recorder.record_issue(severity=issue_severity, code=code, ...)
if strict:
    blocking_failures += 1

# After: issue recorded AND printed
recorder.record_issue(severity=issue_severity, code=code, ...)
ref_label = f" ({order_ref})" if order_ref else ""
console.print(
    f"[bold red]lifecycle proof:[/] order {order_db_id}{ref_label} "
    f"status={required_status} — no websocket evidence [{code}]"
)
if strict:
    blocking_failures += 1
```

**Key change — __main__.py (failure summary):**
```python
# Before: immediate raise with generic message
if int(websocket_validation.get("blocking_failures", 0)) > 0:
    raise RuntimeError("websocket_lifecycle_proof_failed: ...")

# After: print every blocking error, then raise
if int(websocket_validation.get("blocking_failures", 0)) > 0:
    error_issues = [i for i in recorder.issues if i.get("severity") == "error"]
    if error_issues:
        console.print(f"\n[bold red]Run failed — {len(error_issues)} blocking error(s):[/]")
        for issue in error_issues:
            order_label = issue.get("order_db_id") or issue.get("order_ref") or "-"
            scenario_label = issue.get("scenario") or "-"
            console.print(
                f"  [red]✗[/] order={order_label} scenario={scenario_label} "
                f"[{issue.get('code')}] {issue.get('message')}"
            )
    raise RuntimeError("websocket_lifecycle_proof_failed: ...")
```

---

## Why this way (Advanced)

**Separation of concerns — recording vs. reporting:** The existing
`recorder.record_issue` call correctly persists failures to `events.json` and
`report.md`. These fixes add console output *alongside* the existing storage
calls — they do not replace or duplicate the storage. The invariant "all
failures are in the run file" is preserved; the fix only adds the missing
"all failures are also visible in the run log" invariant.

**Why not change `record_issue` itself to print?** `record_issue` is a general
utility called from dozens of places including warnings, precondition
degradations, and informational notices. Adding a print inside it would flood
the console with non-critical noise. The print is intentionally placed only in
the two specific paths that produce *blocking* failures: the enforced WS gate
and the strict lifecycle proof check.

**Why a summary in `__main__.py` as well?** The per-event prints happen mid-run
and can be hundreds of lines above the final failure line. In CI environments
the tail of the log is what gets read. The summary block immediately before the
error line makes triage instant without requiring a scroll.

**`_sim_log` vs `console.print` directly:** `_sim_log` is used in
`trace_runner.py` because it formats output consistently with the rest of the
trace (scenario prefix, colour by level). In `websocket_observer.py` the
function is not available (different module), so `console.print` is used
directly — consistent with the existing `console.print` calls already in that
file (e.g. the `websocket: connected` message).

**Alternatives considered:**
- *Add a `verbose` flag to `validate_websocket_events`*: over-engineered; the
  lifecycle proof failures are always actionable and never noise.
- *Log inside `recorder.record_issue`*: rejected — see above.
- *Emit a structured JSON failure summary file*: useful long-term but out of
  scope for this task. The run already writes `events.json` which contains all
  issues; this fix makes the console self-sufficient without changing the file
  format.

---

## Verification

- [ ] Run `python3 -m simulate full --plan sim_actors.json --timing fast --mode trace --suite full --scenario completed --scenario rejected --scenario cancelled --scenario auto_cancel --enforce-websocket-gates --post-order-actions` against a live environment.
- [ ] When the `cancelled` scenario's WS gate fails, confirm a red `[cancelled] websocket: GATE FAILED order=... expected=pending step=wait_pending_before_cancel: websocket_gate_timeout` line appears in the console at that point in the run, not just at the end.
- [ ] When the run ends with `websocket_lifecycle_proof_failed`, confirm a `Run failed — N blocking error(s):` block listing each `order=... scenario=... [code] message` appears immediately before `Simulation failed:`.
- [ ] Confirm the `events.json` and `report.md` still contain all issues (existing behaviour unchanged).
- [ ] Run a passing suite (e.g. `--suite core` on a healthy environment) and confirm no extra console noise appears.
