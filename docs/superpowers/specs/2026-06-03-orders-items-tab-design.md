# Orders Update Tab Design

## Summary

Refine the Orders page so both modes show a readable raw order JSON pane, while the second tab becomes a direct order-status update workflow. The store is already selected at page sign-in, so the second tab should not repeat store details.

The current second tab shows unwanted `Store` and `Items Ordered` detail cards before the status update controls. Those blocks should be removed.

## Goal

Make the Orders page easier to inspect and faster to use:

- Add a raw order JSON view on the right side of both tabs after lookup.
- Rename `Items & Store` to `Update Status`.
- Remove the separate store summary panel from this tab.
- In the second tab, after lookup, show only ordered item names and total price.
- In the second tab, place the status select and `Update Status` button directly below the item/total summary.
- Keep the second tab focused on updating order status, not browsing full store/order details.

## Non-Goals

- Do not change store sign-in, token storage, lookup, or update API contracts.
- Do not introduce per-item status updates. Fainzy status updates are order-level.
- Do not remove the existing `Order Summary` mode; only add the raw JSON pane to it.
- Do not add new environment variables or cross-project changes.

## Shared JSON Viewer

After a successful lookup in either tab:

- Show the existing tab content on the left.
- Show a readable raw JSON representation of the fetched order on the right.
- Format the JSON with indentation for scanning.
- The JSON viewer is read-only.
- On narrow screens, stack the JSON viewer below the main tab content.

## Second Tab UX

The tab label should be `Update Status`.

After a successful lookup, the second tab should show a simple vertical workflow:

1. `Order` section:
   - List every ordered item name.
   - Show the order total price.
   - Do not show item quantity or item-level price in this tab.
   - Do not show store name/branch in this tab.
   - Avoid extra cards around the result content; keep it direct.

2. `Update` section:
   - Reuse the existing lifecycle status select.
   - Button text should be `Update Status`.
   - Place the select and button together on one row when space allows.
   - Put the update section below item names and total price.
   - Disable the button when the selected status equals the current order status or an update is in progress.
   - Keep success and error feedback near the controls.

## Responsive Behavior

- Desktop/tablet: main tab content on the left, JSON viewer on the right.
- Second tab left side: item names and total first, status controls directly below on a compact row.
- Mobile/narrow widths: main tab content first, then JSON viewer below; status select and button stack if needed.
- Controls must not overlap or resize awkwardly when item names are long.

## Data Flow

Reuse the existing `OrderItemsTab` state and API helpers:

- `LookupInput` fetches the order.
- `order.menu` provides item names.
- `order.total_price` and `order.is_free` provide the total price display.
- `order.status` initializes the selected status.
- `updateFainzyOrderStatus(order.id, selectedStatus)` mutates the order.
- Existing auth error handling clears the stored session on 401/403.

## Testing

Use focused checks for this UI-only change:

- TypeScript check: `cd web && npx tsc --noEmit`.
- Existing web test suite if practical: `cd web && npm test`.
- Manual browser check on `/orders`:
  - Sign in.
  - Open `Order Summary`, look up a known live order, and confirm JSON appears on the right.
  - Open `Update Status`.
  - Look up a known live order.
  - Confirm item names and total price render without store panel or item-level prices.
  - Confirm status select and `Update Status` appear directly below item names and total price.
  - Confirm raw JSON appears on the right on desktop and below the main content on narrow width.
