# Sub-task 03 — Frontend: autoLoginForOrders() in api.ts

**Status:** Done

## What we're doing

Adding a new API function that calls the auto-login endpoint and saves the session token to
localStorage so all existing token-passing plumbing (`withOrdersToken`) continues to work.

## File to change

- `web/src/lib/api.ts`

## Done when

1. `autoLoginForOrders()` is exported from `api.ts`.
2. It calls `GET /api/v1/orders/auto-login`, receives `{ token: string }`.
3. It builds an `OrdersStoreSession` with `storeId: ""`, `storeName: ""`, `subentityId: null`, and
   the token.
4. It stores the session in localStorage via `ordersStorage()?.setItem(...)`.
5. It returns the session object.
6. Existing `loginAsStore()` function is kept (not deleted) to avoid breaking potential other
   callers.
