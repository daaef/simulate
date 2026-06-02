# Sub-task 06: Live trace display

## What this does
Replaces all `console.print()` calls in `trace_runner.py` with a structured
human-readable format: `[scenario] actor: action … result`

## Files
- `trace_runner.py`

## New helper

Add near the top of `trace_runner.py`, right after `console = Console()`:

```python
def _sim_log(scenario: str, actor: str, message: str) -> None:
    """Emit a structured, human-readable trace line."""
    console.print(f"[dim][{scenario}][/dim] [bold]{actor}:[/bold] {message}")
```

## Replacement rules

| Old pattern | New call |
|-------------|---------|
| `console.print(f"[green]trace:[/] Selected store {store_id}...")` | `_sim_log("bootstrap", "trace", f"selected store {store_id} …")` |
| `console.print(f"[cyan]user:[/] Checkout decision for order {order_ref}...")` | `_sim_log(scenario, "user", f"checkout — route={payment_mode}, case={payment_case} …")` |
| `console.print(f"[yellow]trace:[/] order={order_db_id} {phase_label} auto-cancel observe armed ...")` | `_sim_log(scenario, "backend", f"watching order {order_db_id} for auto-cancel ({total:.0f}s window) …")` |
| `console.print(f"[green]trace:[/] order={order_db_id} backend auto-cancel observed ...")` | `_sim_log(scenario, "backend", f"order {order_db_id} auto-cancelled by backend ✓")` |
| `console.print(f"[dim]trace:[/] order={order_db_id} cancel observe in {remaining_display:.0f}s ...")` | `_sim_log(scenario, "backend", f"still watching order {order_db_id} … {remaining_display:.0f}s remaining")` |

## Format guidelines

- `scenario` = the current scenario name (`"store_accept"`, `"backend_auto_cancel"`, `"bootstrap"`)
- `actor` = `user` / `store` / `robot` / `payment` / `backend` / `websocket` / `trace`
- `message` follows `action details … result` — the `…` separates what was attempted from what happened
- Keep each line ≤ 120 chars
- For milestone events (order created, payment succeeded, delivered), end with `✓`
- For waiting/polling lines, end with the remaining time or status

## Example output (store_accept scenario)

```
[bootstrap] trace: selected store FZY_926025 (Ask Me Restaurant) …
[store-accept] user: placing order (₦2,500, no coupon) … order #12345 created
[store-accept] store: waiting for pending on store feed …
[store-accept] store: accepting order #12345 … payment_processing
[store-accept] payment: Stripe test card charged … succeeded ✓
[store-accept] store: order processing — marking food ready … ready ✓
[store-accept] robot: picking up from store … enroute_pickup
[store-accept] robot: arrived at store … enroute_delivery
[store-accept] robot: arrived at user … completed ✓
[store-accept] websocket: confirmed all status transitions on user and store feeds ✓
```

## Done when
- Running any trace scenario shows the structured format in the console
- No raw `[green]trace:[/]` or `[cyan]user:[/]` labels remain in trace_runner.py output
- The web UI console stream tab shows the same readable lines in real-time
