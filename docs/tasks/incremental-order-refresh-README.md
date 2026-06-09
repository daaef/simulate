# Incremental Order Refresh

> Completed: 2026-06-09
> Files changed: `web/src/contexts/OrdersContext.tsx`, `web/src/app/(app)/orders/page.tsx`
> Checklist items fixed: 1 (interface return type precision)

---

## What happened (Layman)

Before this change, every time you clicked "Refresh" on the orders screen, the app threw away everything it already knew and re-downloaded the entire order history from scratch — every page of results, one after another. If the server was slow on any one of those pages, the whole thing would time out and show an error.

Now, clicking "Refresh" only asks for the first page of results (the most recent orders). The app then quietly updates the orders it already has on screen — new ones appear at the top, changed ones get their new status, and older orders stay where they were. This is the same idea as refreshing your email inbox: you only download new messages, not your entire mail history every time.

A full re-download still happens automatically when you first open the page. If you ever need to force a complete reload, that path still exists in the code for use elsewhere.

---

## How it works (Pseudocode)

1. User clicks "Refresh" button → call `softRefresh()`
2. If there is no active session, fall back to full login flow and stop
3. Mark the page as "refreshing" (button shows "Refreshing…", button disabled)
4. Ask the server for page 1 of orders only (no pagination cursor = first page)
5. Receive a list of the most recent orders from the server
6. **Merge** into the existing list:
   a. Collect the IDs of every order that came back on page 1
   b. Prepend the fresh orders to the front of the list
   c. Append every existing order whose ID was **not** in the fresh batch
   d. Result: fresh records overwrite stale, new records appear at the top, old records stay
7. Clear the "refreshing" marker; button returns to "Refresh"
8. If anything went wrong, show the error message; clear "refreshing" marker

---

## The implementation (Code-level)

### `web/src/contexts/OrdersContext.tsx`

**`mergeOrders` — module-level pure function (new)**
```ts
// Before: no merge — reload cleared everything
// After:
function mergeOrders(existing: FainzyOrder[], fresh: FainzyOrder[]): FainzyOrder[] {
  const freshIds = new Set(fresh.map((o) => o.id));
  return [...fresh, ...existing.filter((o) => !freshIds.has(o.id))];
}
```
Pattern: *Set-based dedup* — O(n) lookup instead of O(n²) nested loop.

**`softRefresh` — new `useCallback` in provider**
```ts
const softRefresh = useCallback(async (): Promise<void> => {
  if (!session) { void doLogin(); return; }
  abortRef.current = false;
  setLoadingMore(true);
  setError(null);
  try {
    const result = await fetchFainzyOrdersPage(undefined); // page 1 only
    if (!abortRef.current) {
      setOrders((prev) => mergeOrders(prev, result.orders));
    }
  } catch (err) {
    if (!abortRef.current) setError(formatErr(err));
  } finally {
    setLoadingMore(false);
  }
}, [session, doLogin]);
```
Reuses `fetchFainzyOrdersPage` (already imported) and the existing `abortRef` abort guard.
Uses the *functional updater* form of `setOrders` to avoid capturing stale state.

**Interface update (quality fix)**
```ts
// Before
softRefresh: () => void;
// After
softRefresh: () => Promise<void>;
```

### `web/src/app/(app)/orders/page.tsx:319,390`

```tsx
// Before
const { orders: allOrders, loading, loadingMore, error, reload, updateOrder } = useOrders();
// …
<button onClick={() => { reload(); setSelected(null); }} disabled={loading}>
  {loading ? "Loading…" : "Refresh"}
</button>

// After
const { orders: allOrders, loading, loadingMore, error, softRefresh, reload, updateOrder } = useOrders();
// …
<button onClick={() => { softRefresh(); setSelected(null); }} disabled={loading || loadingMore}>
  {loading ? "Loading…" : loadingMore ? "Refreshing…" : "Refresh"}
</button>
```

---

## Why this way (Advanced)

**Root cause:** The original `reload → fetchOrders` path always started a full paginated scan. Each `fetchFainzyOrdersPage` call carries a 45 s network timeout; with many pages, the cumulative wall-clock time easily exceeded nginx's upstream timeout, producing a 504.

**Design principle — Incremental computation (a form of SRP/cache coherence):** Rather than treating the client as a stateless view that always re-fetches ground truth, we treat the in-memory order list as a cache and the soft refresh as a *reconciliation* step. Only the delta (page 1) travels over the wire.

**Why page 1 is sufficient for reconciliation:** The LastMile API returns orders newest-first. Any order created or status-updated since the last fetch will appear within the first page. Orders on page N (older history) do not change status in the normal operational flow. The rare edge case — a very old order getting a late status update — is handled on next full reload or by the optimistic `updateOrder` call after a manual status change.

**Why `loadingMore` instead of a new `refreshing` state:** `loadingMore` was already wired to the "Loading more…" UI indicator in two places. Reusing it for soft refresh avoids an interface churn and keeps the existing UI affordances consistent. The button text change (`"Refreshing…"`) gives users sufficient feedback without a new boolean.

**Why `mergeOrders` is module-level, not inside the hook:** Pure functions with no closure dependencies belong outside the component tree. This makes them trivially testable, avoids re-creation on every render, and signals to future maintainers that the function has no side effects.

**Alternatives ruled out:**
- *Server-side `since` timestamp filter:* The LastMile API does not expose a `created_after` filter param, so the client cannot ask "give me only orders newer than X."
- *New `refreshing` state boolean:* Would require adding a 7th state variable and a new context key. `loadingMore` serves the same UX purpose.
- *Polling instead of manual refresh:* Would require a `setInterval` and conflict with the abort logic; out of scope and not requested.

**Future work this enables:** The `softRefresh` function can be called on a timer interval with no UX disruption — the `loadingMore` indicator is already non-blocking and the merge is non-destructive. Auto-refresh every 60 s is a one-line addition if needed.

---

## Verification

- [ ] `cd web && pnpm run build` completes without TypeScript errors
- [ ] Open the orders page → Recent Orders tab loads (full fetch, spinner visible)
- [ ] After load: click "Refresh" → button shows "Refreshing…" briefly, then returns to "Refresh"; order count stays the same or increases; no full-page loading state
- [ ] Trigger a status update on an order → click Refresh → the updated status persists (merge does not revert it from page-1 data)
- [ ] Simulate a slow first-page response: confirm button re-enables and error message appears, existing orders stay on screen
