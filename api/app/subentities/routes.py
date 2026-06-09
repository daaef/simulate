from __future__ import annotations

from typing import Any, Optional
from urllib import error as urllib_error

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..auth.policies import require_permission
from . import service

router = APIRouter(tags=["subentities"])


def _auth_error(exc: urllib_error.HTTPError) -> HTTPException:
    if exc.code in {401, 403}:
        return HTTPException(
            status_code=exc.code,
            detail="Fainzy auth token was rejected. Please sign in again.",
        )
    return HTTPException(status_code=502, detail=f"Fainzy API {exc.code}")


@router.get("/api/v1/subentities")
def list_subentities(
    x_fainzy_auth_token: Optional[str] = Header(default=None),
    current_user: dict = Depends(require_permission("orders", "read")),
) -> dict[str, Any]:
    token = (x_fainzy_auth_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No Fainzy auth token.")
    try:
        stores = service.fetch_subentities(fainzy_token=token)
    except urllib_error.HTTPError as exc:
        raise _auth_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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
    try:
        stores = service.search_subentities(q, fainzy_token=token)
    except urllib_error.HTTPError as exc:
        raise _auth_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": stores, "query": q}
