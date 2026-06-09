from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urllib_error, parse as urllib_parse, request as urllib_request

_FAINZY_BASE_URL = "https://fainzy.tech"
_LASTMILE_BASE_URL = "https://lastmile.fainzy.tech"
SIMULATOR_PRODUCT: str = os.getenv("SIMULATOR_PRODUCT", "rds")
_ORDERS_PATH = "/v1/core/orders/"
_USER_AGENT = "Fainzy-Simulator/1.0"
_JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": _USER_AGENT,
}


def _fainzy_base() -> str:
    return _FAINZY_BASE_URL


def _lastmile_base() -> str:
    return _LASTMILE_BASE_URL


def _sim_actors_path() -> Path:
    return Path(__file__).resolve().parents[3] / "sim_actors.json"


def _load_actors() -> dict[str, Any]:
    path = _sim_actors_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _as_store_id(value: str) -> str:
    return value.strip().upper()


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _store_name(store: dict[str, Any], fallback: str) -> str:
    name = str(store.get("name") or store.get("branch") or "").strip()
    return name or fallback


def _extract_token(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        token = data.get("token")
        if token:
            return str(token)
    token = payload.get("token")
    return str(token) if token else None


def fetch_lastmile_token() -> str:
    product = SIMULATOR_PRODUCT or "rds"
    req = urllib_request.Request(
        f"{_fainzy_base()}/v1/biz/product/authentication/?product={product}",
        data=b"",
        method="POST",
        headers=_JSON_HEADERS,
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    token = _extract_token(payload if isinstance(payload, dict) else {})
    if not token:
        raise RuntimeError("Store product auth returned no LastMile token.")
    return token


def auto_login() -> dict[str, Any]:
    token = fetch_lastmile_token()
    return {"token": token}


def get_store_config() -> dict[str, Any]:
    actors = _load_actors()
    store_id = str(actors.get("defaults", {}).get("store_id", "")).strip()
    if not store_id:
        raise RuntimeError("No defaults.store_id found in sim_actors.json.")
    return {"store_id": store_id}


def list_stores() -> dict[str, Any]:
    actors = _load_actors()
    defaults = actors.get("defaults", {})
    default_store_id = str(defaults.get("store_id") or "").strip()
    stores: list[dict[str, Any]] = []
    for raw_store in actors.get("stores", []):
        if not isinstance(raw_store, dict):
            continue
        store_id = str(raw_store.get("store_id") or "").strip()
        if not store_id:
            continue
        store = {
            "store_id": store_id,
            "subentity_id": _as_int(raw_store.get("subentity_id")),
            "name": str(raw_store.get("name") or "").strip() or None,
            "branch": str(raw_store.get("branch") or "").strip() or None,
            "currency": str(raw_store.get("currency") or "").strip() or None,
            "status": _as_int(raw_store.get("status")),
            "is_default": store_id == default_store_id,
        }
        stores.append(store)
    return {"default_store_id": default_store_id or None, "stores": stores}


def login_store(store_id: str) -> dict[str, Any]:
    normalized = _as_store_id(store_id)
    if not normalized:
        raise ValueError("Store ID is required.")

    lastmile_token = fetch_lastmile_token()
    body = json.dumps({"store_id": normalized}).encode("utf-8")
    req = urllib_request.Request(
        f"{_fainzy_base()}/v1/entities/store/login",
        data=body,
        method="POST",
        headers={
            **_JSON_HEADERS,
            "Store-Request": normalized,
        },
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Store login response had an invalid shape.")
    store_profile_token = data.get("token")
    subentity = data.get("subentity")
    if not isinstance(subentity, dict):
        subentity = {}
    subentity_id = _as_int(subentity.get("id"))
    return {
        "store_id": normalized,
        "store_name": _store_name(subentity, normalized),
        "token": lastmile_token,
        "store_profile_token": str(store_profile_token) if store_profile_token else None,
        "subentity_id": subentity_id,
        "subentity": subentity,
    }


def _get(params: dict[str, str], *, token: str, timeout: int = 15) -> Any:
    url = f"{_lastmile_base()}{_ORDERS_PATH}?" + urllib_parse.urlencode(params)
    req = urllib_request.Request(
        url,
        headers={**_JSON_HEADERS, "Fainzy-Token": token},
    )
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _patch(params: dict[str, str], body: dict[str, Any], *, token: str) -> Any:
    url = f"{_lastmile_base()}{_ORDERS_PATH}?" + urllib_parse.urlencode(params)
    req = urllib_request.Request(
        url,
        data=json.dumps(body).encode(),
        method="PATCH",
        headers={**_JSON_HEADERS, "Fainzy-Token": token},
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_by_numeric_id(order_id: int, *, token: str) -> dict[str, Any] | None:
    try:
        payload = _get({"order_id": str(order_id)}, token=token)
    except urllib_error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    data = payload.get("data", [])
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def fetch_by_reference(ref: str, *, token: str, subentity_id: int | None = None) -> dict[str, Any] | None:
    normalized = ref.strip()
    if not normalized.startswith("#"):
        normalized = f"#{normalized}"
    params: dict[str, str] = {"reference_code": normalized}
    if subentity_id is not None:
        params["subentity_id"] = str(subentity_id)
    payload = _get(params, token=token)
    data = payload.get("data", [])
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def fetch_by_query(query: str, *, token: str, subentity_id: int | None = None) -> dict[str, Any] | None:
    value = query.strip()
    if not value:
        return None
    if value.isdigit():
        order = fetch_by_numeric_id(int(value), token=token)
        if order is not None:
            return order
        return fetch_by_reference(f"#{value}", token=token, subentity_id=subentity_id)
    return fetch_by_reference(value, token=token, subentity_id=subentity_id)


def list_orders_page(*, token: str, next_url: str | None = None) -> dict[str, Any]:
    """Fetch one page of orders. Returns {orders, next} where next is the raw next-page URL or None."""
    if next_url:
        parsed = urllib_parse.urlparse(next_url)
        params = dict(urllib_parse.parse_qsl(parsed.query))
    else:
        params = {"filter_params": "all"}
    payload = _get(params, token=token, timeout=45)
    data = payload.get("data", [])
    orders = data if isinstance(data, list) else []
    return {"orders": orders, "next": payload.get("next") or None}


def update_status(order_id: int, status: str, *, token: str) -> Any:
    return _patch({"order_id": str(order_id)}, {"status": status}, token=token)


def fetch_all_orders(*, token: str, subentity_id: int | None = None) -> list[dict[str, Any]]:
    all_orders: list[dict[str, Any]] = []
    next_url: str | None = None
    while True:
        result = list_orders_page(token=token, next_url=next_url)
        all_orders.extend(result.get("orders") or [])
        next_url = result.get("next")
        if not next_url:
            break
    if subentity_id is not None:
        sid = str(subentity_id)
        all_orders = [
            o for o in all_orders
            if str(
                o.get("subentity_id") or
                o.get("subentity") or
                (o.get("restaurant") or {}).get("id") or ""
            ).strip() == sid
        ]
    return all_orders


def _order_amount(order: dict[str, Any]) -> float:
    for key in ("total_price", "amount", "grand_total", "total", "price"):
        val = order.get(key)
        try:
            f = float(val)  # type: ignore[arg-type]
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
    return str(order.get("status") or order.get("order_status") or "unknown").strip().lower()


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
    parts = [user.get("first_name"), user.get("last_name")]
    return str(
        order.get("customer_name") or
        order.get("user_fullname") or
        user.get("full_name") or
        " ".join(p for p in parts if p) or
        user.get("name") or ""
    ).strip()


def compute_store_stats(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for order in orders:
        sid = _order_subentity_id(order)
        if not sid:
            continue
        if sid not in buckets:
            restaurant = order.get("restaurant") or {}
            subentity_meta = order.get("subentity_metadata") or {}
            store_name = (
                restaurant.get("name") or
                subentity_meta.get("name") or
                order.get("store_name") or
                sid
            )
            buckets[sid] = {
                "subentity_id": sid,
                "store_name": store_name,
                "order_count": 0,
                "revenue": 0.0,
                "status_breakdown": {
                    "completed": 0,
                    "pending": 0,
                    "missed": 0,
                    "cancelled": 0,
                    "rejected": 0,
                    "other": 0,
                },
            }
        b = buckets[sid]
        b["order_count"] += 1
        b["revenue"] += _order_amount(order)
        status = _order_status(order)
        breakdown = b["status_breakdown"]
        if status in breakdown:
            breakdown[status] += 1
        else:
            breakdown["other"] += 1

    result = []
    for b in buckets.values():
        count = b["order_count"]
        b["avg_order_value"] = b["revenue"] / count if count else 0.0
        result.append(b)

    return sorted(result, key=lambda x: x["order_count"], reverse=True)


def compute_customer_stats(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "name": name,
                "order_count": 0,
                "total_spend": 0.0,
                "last_order_date": None,
            }
        b = buckets[key]
        b["order_count"] += 1
        b["total_spend"] += _order_amount(order)
        raw_date = (
            order.get("created") or
            order.get("created_at") or
            order.get("ordered_at") or
            order.get("placed_at")
        )
        if raw_date and (b["last_order_date"] is None or raw_date > b["last_order_date"]):
            b["last_order_date"] = raw_date

    return sorted(buckets.values(), key=lambda x: x["order_count"], reverse=True)
