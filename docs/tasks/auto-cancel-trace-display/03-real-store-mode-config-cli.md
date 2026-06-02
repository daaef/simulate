# Sub-task 03: Real Store Mode — config + CLI

## What this does
Adds the flag that enables "wait for real store to act" mode.

## Files
- `config.py`
- `__main__.py`

## Changes

### config.py — add two new variables
```python
SIM_WAIT_FOR_STORE_ACTION: bool = _bool("SIM_WAIT_FOR_STORE_ACTION", False)
SIM_STORE_ACTION_TIMEOUT_SECONDS: float = _float("SIM_STORE_ACTION_TIMEOUT_SECONDS", 600.0)
```

Place near the other `SIM_` boolean flags (around line 81).

### __main__.py — add CLI flag
```python
parser.add_argument(
    "--wait-for-store-action",
    action="store_true",
    default=False,
    help=(
        "Do not simulate store actions. Wait for a real store operator to act "
        "from their app for each order in this run."
    ),
)
```
After parsing:
```python
if args.wait_for_store_action:
    config.SIM_WAIT_FOR_STORE_ACTION = True
```

## Done when
- `python -m simulate --wait-for-store-action ...` sets `config.SIM_WAIT_FOR_STORE_ACTION = True`
- No runtime behavior change yet (that's sub-task 04)
