# Plan: Recent Orders Tab

## Context
The simulate orders page has two lookup-style tabs (Order Summary, Update Status) that require knowing an order ID upfront. This feature adds a third tab — **Recent Orders** — that loads the full order list for the authenticated store and lets the operator click any row to inspect and update it.

## Goal
A "Recent Orders" tab that:
- Fetches all orders via `GET /v1/core/orders/?filter_params=all`
- Displays them in a sortable table (Order ID, Status, Customer, Amount, Date)
- On row click: opens the existing split layout (structured detail left, searchable raw JSON right) with inline status update
- No pagination — return and render everything the API gives back

## Approach
1. **Backend** — add `list_orders(token)` to `service.py` and expose it as `GET /api/v1/orders/list` in `routes.py`
2. **Frontend tab** — add `Tab = "recent"` variant; fetch on tab activation or manual refresh; render orders table
3. **Row detail** — reuse existing `OrderResultLayout` + `OrderJsonViewer`; inline `LookupInput` is replaced by clicking a row
4. **JSON search** — add a filter input to `OrderJsonViewer` that collapses/highlights non-matching lines

## Verification
- Tab loads and shows all orders when session is active
- Clicking a row opens correct order detail
- Status update from detail view reflects immediately in the table row
- JSON search filters output in real time
- Refresh button re-fetches without reloading the page

## Sub-tasks
- [01-backend-list-endpoint.md](01-backend-list-endpoint.md)
- [02-recent-orders-tab.md](02-recent-orders-tab.md)
- [03-json-search.md](03-json-search.md)
