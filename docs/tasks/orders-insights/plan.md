# Plan: Orders Insights — Stores & Customers (simulate project)

## Context

The simulate project is a FastAPI backend at `/Users/mars/FAINZY/simulate`.
It currently has an `orders` module (`api/app/orders/`) with routes and a service that proxies
to the Fainzy and LastMile APIs.

This plan adds four new capabilities scoped to the orders domain:

1. **List & search stores** — proxy `GET https://fainzy.tech/v1/entities/subentities`
2. **Store stats** — compute per-store order count, revenue, avg order value, status breakdown
3. **Customer stats** — compute per-customer order count, total spend, last order date (ranked)
4. **Customer search** — filter the customer stats list by name

This mirrors the UI work already done in the dashboard project and provides the backend
endpoints that the dashboard (or any client) can call.

---

## Auth tokens — two distinct tokens

| Token | Where it comes from | Used for |
|---|---|---|
| **LastMile token** (`x-fainzy-token` header) | `GET /api/v1/orders/auto-login` | Orders (LastMile API) — already in use |
| **Fainzy auth token** (`x-fainzy-auth-token` header) | Client passes its own session token | Subentities (Fainzy base API) |

The subentities endpoint (`https://fainzy.tech/v1/entities/subentities`) requires
`Authorization: Token <fainzy_auth_token>` — this is the client's regular Fainzy account token,
**not** the LastMile product token. The new subentities routes accept it as `x-fainzy-auth-token`.

---

## Files to create / change

| File | Action |
|---|---|
| `api/app/subentities/` | **New module** — service + routes for store listing/search |
| `api/app/subentities/__init__.py` | Empty init |
| `api/app/subentities/service.py` | `fetch_subentities`, `search_subentities` |
| `api/app/subentities/routes.py` | `GET /api/v1/subentities`, `GET /api/v1/subentities/search` |
| `api/app/orders/service.py` | Add `fetch_all_orders`, `compute_store_stats`, `compute_customer_stats` |
| `api/app/orders/routes.py` | Add `GET /api/v1/orders/store-stats`, `GET /api/v1/orders/customer-stats`, `GET /api/v1/orders/customers/search` |
| `api/app/main.py` | Import and `include_router` for the new subentities router |

---

## Sub-task 01 — `subentities` module

### `api/app/subentities/service.py`

```python
_SUBENTITIES_PATH = "/v1/entities/subentities"

def _fainzy_auth_get(path: str, *, fainzy_token: str) -> Any:
    """GET to Fainzy base URL using Authorization: Token header."""
    url = f"{_FAINZY_BASE_URL}{path}"
    req = urllib_request.Request(
        url,
        headers={**_JSON_HEADERS, "Authorization": f"Token {fainzy_token}"},
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def fetch_subentities(*, fainzy_token: str) -> list[dict[str, Any]]:
    payload = _fainzy_auth_get(_SUBENTITIES_PATH, fainzy_token=fainzy_token)
    # Response shape: { "data": { "data": [...] } } or { "data": [...] }
    outer = payload.get("data", payload)
    if isinstance(outer, dict):
        items = outer.get("data", outer.get("results", []))
    elif isinstance(outer, list):
        items = outer
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]

def search_subentities(query: str, *, fainzy_token: str) -> list[dict[str, Any]]:
    stores = fetch_subentities(fainzy_token=fainzy_token)
    if not query.strip():
        return stores
    term = query.strip().lower()
    return [
        s for s in stores
        if term in str(s.get("name", "")).lower()
        or term in str(s.get("branch", "")).lower()
    ]
```

Note: `_FAINZY_BASE_URL` and `_JSON_HEADERS` should be imported from `orders.service` or moved
to a shared `api/app/_http.py` utility. Either approach works — importing from orders.service
is the fastest path.

### `api/app/subentities/routes.py`

```python
@router.get("/api/v1/subentities")
def list_subentities(
    x_fainzy_auth_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_auth_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy auth token.")
    stores = service.fetch_subentities(fainzy_token=token)
    return {"data": stores}

@router.get("/api/v1/subentities/search")
def search_subentities(
    q: str = Query(default=""),
    x_fainzy_auth_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_auth_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy auth token.")
    stores = service.search_subentities(q, fainzy_token=token)
    return {"data": stores, "query": q}
```

### `main.py` change

```python
from .subentities.routes import router as subentities_router
# ...
app.include_router(subentities_router)
```

---

## Sub-task 02 — store stats & customer stats (orders module)

### New functions in `api/app/orders/service.py`

```python
def fetch_all_orders(*, token: str, subentity_id: int | None = None) -> list[dict[str, Any]]:
    """Fetch all pages of orders. Uses list pagination via next_url."""
    all_orders: list[dict[str, Any]] = []
    next_url: str | None = None
    while True:
        payload = list_orders_page(token=token, next_url=next_url)
        page = payload.get("data", [])
        if isinstance(page, list):
            all_orders.extend(page)
        elif isinstance(page, dict):
            items = page.get("data") or page.get("results") or []
            all_orders.extend(items if isinstance(items, list) else [])
        next_url = payload.get("next") or (
            page.get("next") if isinstance(page, dict) else None
        )
        if not next_url:
            break
    if subentity_id is not None:
        sid = str(subentity_id)
        all_orders = [
            o for o in all_orders
            if str(o.get("subentity_id") or o.get("subentity") or
                   (o.get("restaurant") or {}).get("id") or "") == sid
        ]
    return all_orders


def _order_amount(order: dict[str, Any]) -> float:
    for key in ("total_price", "amount", "grand_total", "total", "price"):
        val = order.get(key)
        try:
            f = float(val)
            if f == f:  # not NaN
                return f
        except (TypeError, ValueError):
            pass
    return 0.0


def _order_subentity_id(order: dict[str, Any]) -> str:
    return str(
        order.get("subentity_id") or
        order.get("subentity") or
        (order.get("restaurant") or {}).get("id") or ""
    ).strip()


def _order_status(order: dict[str, Any]) -> str:
    return str(order.get("status") or order.get("order_status") or "unknown").lower()


def _customer_key(order: dict[str, Any]) -> str:
    user = order.get("user") or {}
    return str(
        user.get("id") or
        order.get("customer_id") or
        user.get("email") or
        order.get("customer_name") or
        order.get("user_fullname") or
        user.get("full_name") or ""
    ).strip()


def _customer_name(order: dict[str, Any]) -> str:
    user = order.get("user") or {}
    name = (
        order.get("customer_name") or
        order.get("user_fullname") or
        user.get("full_name") or
        " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or
        user.get("name") or ""
    )
    return name.strip()


def compute_store_stats(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group orders by subentity and return per-store stats, sorted by order count desc."""
    buckets: dict[str, dict[str, Any]] = {}
    for order in orders:
        sid = _order_subentity_id(order)
        if not sid:
            continue
        if sid not in buckets:
            store_name = (
                (order.get("restaurant") or {}).get("name") or
                (order.get("subentity_metadata") or {}).get("name") or
                order.get("store_name") or sid
            )
            buckets[sid] = {
                "subentity_id": sid,
                "store_name": store_name,
                "order_count": 0,
                "revenue": 0.0,
                "status_breakdown": {
                    "completed": 0, "pending": 0, "missed": 0,
                    "cancelled": 0, "rejected": 0, "other": 0,
                },
            }
        b = buckets[sid]
        b["order_count"] += 1
        b["revenue"] += _order_amount(order)
        status = _order_status(order)
        if status in b["status_breakdown"]:
            b["status_breakdown"][status] += 1
        else:
            b["status_breakdown"]["other"] += 1

    result = []
    for b in buckets.values():
        count = b["order_count"]
        b["avg_order_value"] = b["revenue"] / count if count else 0.0
        result.append(b)

    return sorted(result, key=lambda x: x["order_count"], reverse=True)


def compute_customer_stats(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group orders by customer and return ranked stats, sorted by order count desc."""
    buckets: dict[str, dict[str, Any]] = {}
    for order in orders:
        key = _customer_key(order)
        if not key:
            continue
        name = _customer_name(order)
        if not name:
            continue
        if key not in buckets:
            buckets[key] = {
                "customer_key": key,
                "name": name,
                "order_count": 0,
                "total_spend": 0.0,
                "last_order_date": None,
            }
        b = buckets[key]
        b["order_count"] += 1
        b["total_spend"] += _order_amount(order)
        raw_date = order.get("created") or order.get("created_at") or order.get("ordered_at")
        if raw_date and (b["last_order_date"] is None or raw_date > b["last_order_date"]):
            b["last_order_date"] = raw_date

    return sorted(buckets.values(), key=lambda x: x["order_count"], reverse=True)
```

### New routes in `api/app/orders/routes.py`

```python
@router.get("/api/v1/orders/store-stats")
def get_store_stats(
    subentity_id: Optional[int] = Query(default=None),
    x_fainzy_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy token.")
    try:
        orders = service.fetch_all_orders(token=token, subentity_id=subentity_id)
    except urllib_error.HTTPError as exc:
        raise _fainzy_error(exc) from exc
    return {"data": service.compute_store_stats(orders)}


@router.get("/api/v1/orders/customer-stats")
def get_customer_stats(
    subentity_id: Optional[int] = Query(default=None),
    x_fainzy_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy token.")
    try:
        orders = service.fetch_all_orders(token=token, subentity_id=subentity_id)
    except urllib_error.HTTPError as exc:
        raise _fainzy_error(exc) from exc
    return {"data": service.compute_customer_stats(orders)}


@router.get("/api/v1/orders/customers/search")
def search_customers(
    q: str = Query(default=""),
    subentity_id: Optional[int] = Query(default=None),
    x_fainzy_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy token.")
    try:
        orders = service.fetch_all_orders(token=token, subentity_id=subentity_id)
    except urllib_error.HTTPError as exc:
        raise _fainzy_error(exc) from exc
    customers = service.compute_customer_stats(orders)
    if q.strip():
        term = q.strip().lower()
        customers = [c for c in customers if term in c["name"].lower()]
    return {"data": customers, "query": q}
```

---

## New endpoint summary

| Method | Path | Auth header | What it does |
|--------|------|-------------|---|
| `GET` | `/api/v1/subentities` | `x-fainzy-auth-token` | List all stores from Fainzy |
| `GET` | `/api/v1/subentities/search?q=` | `x-fainzy-auth-token` | Filter stores by name/branch |
| `GET` | `/api/v1/orders/store-stats` | `x-fainzy-token` | Per-store stats from all orders |
| `GET` | `/api/v1/orders/customer-stats` | `x-fainzy-token` | Ranked customer stats |
| `GET` | `/api/v1/orders/customers/search?q=` | `x-fainzy-token` | Search customers by name |

All routes require simulator session auth (`require_permission("orders", "read")`).

---

## Verification

1. `flask run` / `uvicorn` — server starts without import errors
2. `GET /api/v1/subentities` with valid `x-fainzy-auth-token` → returns store list
3. `GET /api/v1/subentities/search?q=main` → returns filtered stores
4. `GET /api/v1/orders/store-stats` with valid `x-fainzy-token` → returns per-store stats list
5. `GET /api/v1/orders/customer-stats` → returns ranked customer list
6. `GET /api/v1/orders/customers/search?q=john` → filters customers by name
7. All routes return 401 when auth headers are missing
