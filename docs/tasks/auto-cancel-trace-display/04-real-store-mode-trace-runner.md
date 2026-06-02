# Sub-task 04: Real Store Mode — trace runner behavior

## What this does
When `SIM_WAIT_FOR_STORE_ACTION` is True, replaces every `store_sim.patch_status()` call
in `trace_runner.py` with a polling wait for the real store to act.

## Files
- `trace_runner.py`

## New helper function

Add `_wait_for_store_to_act()` in trace_runner.py:

```python
async def _wait_for_store_to_act(
    client: httpx.AsyncClient,
    *,
    order_db_id: int,
    order_ref: str,
    user_session: user_sim.UserSession,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    current_status: str,
    expected_next_statuses: set[str],
    terminal_statuses: set[str] | None = None,
    timeout_seconds: float | None = None,
) -> str | None:
    """
    Poll until the real store changes the order away from current_status.
    Returns the new status, or None on timeout.
    """
    timeout = timeout_seconds or config.SIM_STORE_ACTION_TIMEOUT_SECONDS
    deadline = time.monotonic() + timeout
    _sim_log(scenario, "store", f"waiting for real store action on order {order_ref} (status={current_status}) …")

    while time.monotonic() < deadline:
        await asyncio.sleep(5.0)
        try:
            order = await user_sim.fetch_order(
                client,
                user_token=user_session.token,
                token_source=user_session.token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                action="wait_for_store_action_poll",
                scenario=scenario,
                step=step,
            )
        except Exception:
            continue
        status = str(order.get("status") or "").strip().lower()
        if status != current_status:
            _sim_log(scenario, "store", f"real store acted — order {order_ref} is now {status}")
            return status

    recorder.record_issue(
        severity="warning",
        code="real_store_action_timeout",
        actor="store",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        message=f"Timed out waiting for real store to act (waited {timeout:.0f}s, status stayed {current_status})",
    )
    return None
```

## Where to hook it in

In `_fulfill_placed_order()`:

**Before store accept (around line 871):**
```python
if config.SIM_WAIT_FOR_STORE_ACTION:
    new_status = await _wait_for_store_to_act(
        client,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        user_session=user_session,
        recorder=recorder,
        scenario=scenario,
        step="wait_real_store_accept",
        current_status="pending",
        expected_next_statuses={"payment_processing", "rejected"},
    )
    if new_status is None:
        _finish_checked(recorder, scenario, actual_final_status="store_action_timeout", ...)
        return "store_action_timeout"
    if new_status == "rejected":
        ...  # handle real rejection
    # continue with payment if accepted
else:
    accepted = await store_sim.patch_status(...)
```

**Before store marks ready (around line 1015):**
```python
if config.SIM_WAIT_FOR_STORE_ACTION:
    new_status = await _wait_for_store_to_act(
        ..., current_status="order_processing", expected_next_statuses={"ready"}
    )
    ...
else:
    ready = await store_sim.patch_status(..., status="ready", ...)
```

## Done when
- Running with `--wait-for-store-action` and a trace scenario: the simulator logs "waiting for real store action" and pauses polling every 5s
- If the real store accepts from their app, the simulator resumes with payment and robot
- If 10 minutes pass with no action, the scenario is marked `blocked` with a clear note
