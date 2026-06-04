# Sub-task 01 — Backend: SIMULATOR_PRODUCT + auto-login endpoint

**Status:** Done

## What we're doing

Making the backend aware of `SIMULATOR_PRODUCT` and exposing a new endpoint that returns a token
without requiring a store ID.

## Files to change

- `api/app/orders/service.py`
- `api/app/orders/routes.py`

## Done when

1. `os.getenv("SIMULATOR_PRODUCT", "rds")` is read at module level in `service.py`.
2. `fetch_lastmile_token()` uses the variable instead of the hardcoded string `"rds"`.
3. A new `auto_login()` function in `service.py` calls `fetch_lastmile_token()` and returns
   `{"token": <token>}`.
4. `GET /api/v1/orders/auto-login` exists in `routes.py`, requires `orders:read`, and returns
   `{"token": "..."}` on success or HTTP 502 on upstream error.
