from __future__ import annotations

from typing import Any, Optional
from urllib import error as urllib_error

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["orders"])
ORDER_LOOKUP_NOT_FOUND_DETAIL = (
    "No matching order found for the selected store. "
    "Choose the store that owns this order and try again."
)


class OrderStatusUpdate(BaseModel):
    order_id: int
    status: str


class StoreLoginRequest(BaseModel):
    store_id: str


def _fainzy_error(exc: urllib_error.HTTPError, *, context: str = "orders") -> HTTPException:
    try:
        body = exc.read().decode(errors="replace")
    except Exception:
        body = ""
    body_lower = body.lower()
    if exc.code in {401, 403} and context == "store_login":
        return HTTPException(
            status_code=exc.code,
            detail="Store login was rejected by Fainzy. Please retry or choose another configured store.",
        )
    if exc.code in {401, 403}:
        return HTTPException(
            status_code=exc.code,
            detail="Fainzy token was rejected. Please sign in again.",
        )
    if exc.code == 400 and "valid token" in body_lower:
        return HTTPException(
            status_code=401,
            detail="Fainzy token was rejected. Please sign in again.",
        )
    if exc.code == 404:
        return HTTPException(status_code=404, detail=ORDER_LOOKUP_NOT_FOUND_DETAIL)
    return HTTPException(status_code=502, detail=f"Fainzy API {exc.code}: {body[:300]}")


@router.get("/api/v1/orders/auto-login")
def auto_login(
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    try:
        return service.auto_login()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/v1/orders/config")
def get_config(
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    try:
        return service.get_store_config()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/orders/stores")
def list_stores(
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    try:
        return service.list_stores()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/v1/orders/store-login")
def login_store(
    body: StoreLoginRequest,
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    try:
        payload = service.login_store(body.store_id)
    except urllib_error.HTTPError as exc:
        raise _fainzy_error(exc, context="store_login") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "session": {
            "storeId": payload["store_id"],
            "storeName": payload["store_name"],
            "token": payload["token"],
            "subentityId": payload["subentity_id"],
        },
        "store": payload.get("subentity") or {},
    }


@router.get("/api/v1/orders/lookup")
def lookup_order(
    query: Optional[str] = Query(default=None),
    order_id: Optional[int] = Query(default=None),
    ref: Optional[str] = Query(default=None),
    subentity_id: Optional[int] = Query(default=None),
    x_fainzy_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy token — please sign in again.")

    if query is not None and query.strip():
        try:
            order = service.fetch_by_query(query, token=token, subentity_id=subentity_id)
        except urllib_error.HTTPError as exc:
            raise _fainzy_error(exc) from exc
    elif order_id is not None:
        try:
            order = service.fetch_by_numeric_id(order_id, token=token)
        except urllib_error.HTTPError as exc:
            raise _fainzy_error(exc) from exc
    elif ref:
        try:
            order = service.fetch_by_reference(ref, token=token, subentity_id=subentity_id)
        except urllib_error.HTTPError as exc:
            raise _fainzy_error(exc) from exc
    else:
        raise HTTPException(status_code=400, detail="Provide order_id or ref.")

    if order is None:
        raise HTTPException(status_code=404, detail=ORDER_LOOKUP_NOT_FOUND_DETAIL)
    return {"order": order}


@router.patch("/api/v1/orders/status")
def update_order_status(
    body: OrderStatusUpdate,
    x_fainzy_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "update")),
) -> dict[str, Any]:
    token = (x_fainzy_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy token — please sign in again.")
    try:
        result = service.update_status(body.order_id, body.status, token=token)
    except urllib_error.HTTPError as exc:
        raise _fainzy_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "result": result}
