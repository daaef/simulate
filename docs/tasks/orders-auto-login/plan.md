# Plan: Orders Auto-Login & Cross-Store Lookup

**Created:** 2026-06-03  
**Status:** Awaiting implementation approval

---

## Context

The Orders page previously required the user to manually select a store and click "Sign In as a
Store" before they could look up any order. This login step fetched a Fainzy token and pinned all
searches to that specific store (`subentityId`).

Two problems this solves:
1. **Friction** — users had to perform a manual action before doing the thing they actually came
   to do (look up an order).
2. **Scope** — searches by reference ID only matched orders belonging to the signed-in store; a
   search for `#164235` from Store A would fail silently if the order belonged to Store B.

---

## Goal

1. The Orders page fetches a valid Fainzy token automatically on every page load — no user
   interaction required.
2. Order lookups by numeric ID and reference string search across **all** stores (no
   `subentityId` filter).
3. A new environment variable `SIMULATOR_PRODUCT` (default: `rds`) controls which product the
   token is issued for. In production this is set as a GitHub Secret.

---

## Key Concepts

| Term | Plain-English Meaning |
|---|---|
| Product token | A credential Fainzy issues per product (e.g. `rds`, `dashboard`). Different products may have different access levels. |
| `subentity_id` | A numeric ID that represents a single store. Passing it in a query tells the API "only return orders from this store." |
| `localStorage` | A small storage area in the browser that persists data between page reloads. Used to hold the current session token. |
| Auto-login | Fetching credentials in the background without a visible login form. |
| Cross-store search | Querying orders without a store filter — the API returns matches from any store the token can access. |

---

## Approach

### Step 1 — Backend: `SIMULATOR_PRODUCT` env var + new endpoint

**File:** `api/app/orders/service.py`

- Add `import os` at the top of the file.
- Read `SIMULATOR_PRODUCT = os.getenv("SIMULATOR_PRODUCT", "rds")` at module level.
- Change the hardcoded `product=rds` in `fetch_lastmile_token()` to `product={SIMULATOR_PRODUCT}`.
- Add a new `auto_login()` function that calls `fetch_lastmile_token()` and returns `{"token": <token>}`.

**File:** `api/app/orders/routes.py`

- Add a new `GET /api/v1/orders/auto-login` route that calls `service.auto_login()` and returns
  `{"token": "..."}`. Requires `orders:read` permission (same as all other orders endpoints).

### Step 2 — Docker & env files

**Files:** `docker-compose.yml`, `docker-compose.prod.yml`, `.env.prod.example`,
`simulate_project_work_review.md`

- Add `SIMULATOR_PRODUCT` with default `rds` in the dev compose.
- Add `SIMULATOR_PRODUCT` with default `rds` in the prod compose (not required — just optional).
- Document in `.env.prod.example` and the work review template.

### Step 3 — Frontend: `autoLoginForOrders()` in `api.ts`

**File:** `web/src/lib/api.ts`

- Add `autoLoginForOrders()`: calls `GET /api/v1/orders/auto-login`, constructs a minimal
  `OrdersStoreSession` object with `storeId: ""`, `storeName: ""`, `subentityId: null`, and the
  returned token. Stores it in localStorage (so `withOrdersToken()` keeps working without changes).

### Step 4 — Frontend: Simplify `orders/page.tsx`

**File:** `web/src/app/(app)/orders/page.tsx`

- Remove `StoreLoginForm` component and all state/handlers tied to it:
  `storesPayload`, `loadingStores`, `storesError`, `loadStores()`, `handleLogin()`,
  `handleSignOut()`, imports of `fetchOrdersStores`, `loginAsStore`, `OrdersStoreOption`,
  `OrdersStoresResponse`.
- Add `autoLoginLoading` and `autoLoginError` state.
- In `useEffect` on mount: call `autoLoginForOrders()` and set session. Re-auth errors also
  trigger `autoLoginForOrders()` instead of clearing session.
- Remove sign-out button from the page header.
- Show a "Connecting…" message while auto-login is in progress; show an error with a Retry button
  if it fails; show the order lookup tabs once a session is acquired.

---

## Cross-Store Search — Why No Extra Code Is Needed

`fetchFainzyOrder()` in `api.ts` reads `session?.subentityId` and only adds the `subentity_id`
query param if it is not null:

```ts
if (session?.subentityId != null) params.set("subentity_id", String(session.subentityId));
```

Auto-login sets `subentityId: null`. So `subentity_id` is never sent to the backend. The backend's
`fetch_by_reference()` and `fetch_by_numeric_id()` in `service.py` already handle a missing
`subentity_id` by not filtering — no code change required there.

---

## Verification

| Check | How to verify |
|---|---|
| Auto-login fires on page load | Open `/orders` in the browser, open DevTools → Network tab. Confirm a `GET /api/v1/orders/auto-login` call completes with 200 before any lookup. |
| Order lookup works without manual sign-in | Enter an order ID or reference in the lookup box immediately after page load — no login step should appear. |
| Cross-store reference search | Enter a reference ID that belongs to a different store than the default. Confirm it is found. |
| `SIMULATOR_PRODUCT` env var is respected | Set `SIMULATOR_PRODUCT=dashboard` in `.env`, restart, check that the auto-login call to Fainzy uses `product=dashboard` in its URL. |
| Auth error triggers re-auth | From the backend, temporarily make the auto-login endpoint return 502. Confirm an error message + Retry button appears. |

---

## Risks Remaining

- **Token write scope:** If `SIMULATOR_PRODUCT` is set to a read-only product (e.g. `dashboard`),
  status updates (`PATCH /api/v1/orders/status`) may be rejected by Fainzy with a 401/403.
  Currently mitigated by defaulting to `rds`. Document this in the env file.
- **Pagination on cross-store search:** Without `subentity_id`, reference searches page through
  up to 10 pages of all-store results. For high-volume systems this may be slow. Monitor in
  production; if needed, raise the page cap or add a specific API lookup by reference.
- **StoreLoginForm removal:** The `StoreLoginForm` component and related helpers (`loginAsStore`,
  `fetchOrdersStores`) will remain in `api.ts` (not deleted) to avoid breaking any other potential
  callsites. They are simply no longer called from `orders/page.tsx`.
