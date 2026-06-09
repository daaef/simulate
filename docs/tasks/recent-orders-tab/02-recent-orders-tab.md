# Sub-task 02 — Recent Orders tab

## What
Third tab on the orders page. Fetches all orders on activation, renders a table, clicking a row shows the split detail view with inline status update.

## How
- Extend `Tab` type to `"summary" | "items" | "recent"`
- Add `fetchAllFainzyOrders()` to `lib/api.ts` calling `GET /api/v1/orders/list`
- New `RecentOrdersTab` component: fetches on mount/refresh, stores `FainzyOrder[]`, renders table
- Row click sets `selectedOrder` state → renders existing `OrderResultLayout` below the table (or replaces it)
- Status update inside detail syncs back to the table row

## Done when
Tab renders full order list; clicking a row shows correct detail; status update reflects in row badge.
