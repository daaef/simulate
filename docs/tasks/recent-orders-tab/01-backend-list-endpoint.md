# Sub-task 01 — Backend list endpoint

## What
Add `list_orders(token)` to `api/app/orders/service.py` and expose it as `GET /api/v1/orders/list` in `routes.py`.

## How
`service.py`: call `_get({"filter_params": "all"}, token=token)` and return `payload.get("data", [])`.

`routes.py`: new route reads the `Fainzy-Token` header (same pattern as `/lookup`), calls `list_orders`, returns the list.

## Done when
`GET /api/v1/orders/list` with a valid token returns a JSON array of order objects.
