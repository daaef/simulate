from __future__ import annotations

import json
from typing import Any
from urllib import request as urllib_request

from ..orders.service import _FAINZY_BASE_URL, _JSON_HEADERS

_SUBENTITIES_PATH = "/v1/entities/subentities"


def _fainzy_auth_get(path: str, *, fainzy_token: str) -> Any:
    url = f"{_FAINZY_BASE_URL}{path}"
    req = urllib_request.Request(
        url,
        headers={**_JSON_HEADERS, "Authorization": f"Token {fainzy_token}"},
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_subentities(*, fainzy_token: str) -> list[dict[str, Any]]:
    payload = _fainzy_auth_get(_SUBENTITIES_PATH, fainzy_token=fainzy_token)
    outer = payload.get("data", payload)
    if isinstance(outer, dict):
        items = outer.get("data") or outer.get("results") or []
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
