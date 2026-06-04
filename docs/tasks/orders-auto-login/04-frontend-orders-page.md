# Sub-task 04 — Frontend: Simplify orders/page.tsx

**Status:** Done

## What we're doing

Removing the StoreLoginForm gate from the Orders page and replacing it with a silent auto-login
on mount.

## File to change

- `web/src/app/(app)/orders/page.tsx`

## Done when

1. `StoreLoginForm` component is removed from the file (no longer rendered and definition removed).
2. State removed: `storesPayload`, `loadingStores`, `storesError`.
3. Functions removed: `loadStores()`, `handleLogin()`, `handleSignOut()`.
4. Imports removed from `api.ts`: `fetchOrdersStores`, `loginAsStore`, `OrdersStoreOption`,
   `OrdersStoresResponse`.
5. `autoLoginForOrders` is imported from `../../../lib/api`.
6. `useEffect` on mount calls `autoLoginForOrders()` and sets session state.
7. `handleAuthError` calls `autoLoginForOrders()` instead of just clearing the session.
8. Page renders a "Connecting to orders service…" spinner/message while `session` is null and no
   error has occurred.
9. Page renders an error message + Retry button if auto-login fails.
10. Sign-out button is removed from the page header.
11. The `!session` guard that previously showed `StoreLoginForm` now shows the loading/error state
    only; the tabs render as soon as a session exists.
