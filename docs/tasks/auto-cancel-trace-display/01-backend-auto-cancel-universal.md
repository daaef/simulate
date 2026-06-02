# Sub-task 01: Backend auto-cancel — universal timing

## What this does
Makes backend_auto_cancel run in every trace suite (not just `full`) and sets the
observation window to 120 seconds for all timing profiles.

## Files
- `scenarios.py`

## Changes

### 1. `fast` profile: `auto_cancel_wait_seconds` 30 → 120

```python
# BEFORE
"fast": TimingProfile(
    ...
    auto_cancel_wait_seconds=30.0,
)

# AFTER
"fast": TimingProfile(
    ...
    auto_cancel_wait_seconds=120.0,
)
```

### 2. Add `backend_auto_cancel` to suites that lack it

Add `"backend_auto_cancel"` to: `core`, `payments`, `menus`, `store`, `audit`, `doctor`.

Place it last in each suite tuple (it's a terminal diagnostic, runs after the main scenarios).

## Done when
- `TRACE_SUITES["doctor"]` contains `"backend_auto_cancel"`
- `TRACE_SUITES["fast"].auto_cancel_wait_seconds == 120.0`
- Running `doctor` flow includes the scenario in its resolved list
