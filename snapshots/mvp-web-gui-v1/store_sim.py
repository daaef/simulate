"""
Store actor — fully self-contained.

Owns:
  - Store auth (product auth endpoint, store login, profile fetch)
  - Active websocket on /ws/soc/store_<store_id>/ for real-time order status
  - Accept/reject orders, wait for payment, mark ready
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets
from rich.console import Console

import config
from interaction_catalog import MENU_STATUSES, WORKING_DAYS
from reporting import RunRecorder
from transport import RequestError, api_data, build_auth_proof, request_json

console = Console()
ENV_PATH = Path(__file__).parent / ".env"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StoreSession:
    last_mile_token: str
    fainzy_token: str | None
    subentity: dict[str, Any]
    store_id: int  # subentity_id — used for websocket channel
    token_source: str
    store_login_id: str = ""  # original store_id used for login (e.g. "FZY_586940")
    gps_lat: float | None = None
    gps_lng: float | None = None


class HttpApiError(RuntimeError):
    def __init__(
        self,
        *,
        url: str,
        status_code: int,
        response_text: str,
        related_event_id: int | None = None,
    ) -> None:
        super().__init__(f"HTTP {status_code} from {url}: {response_text[:500]}")
        self.url = url
        self.status_code = status_code
        self.response_text = response_text
        self.related_event_id = related_event_id


def _token(payload: dict[str, Any]) -> str | None:
    data = api_data(payload)
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("token") or payload.get("token")
    return payload.get("token")


async def _auth_request(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder | None,
    actor: str,
    action: str,
    method: str,
    url: str,
    endpoint: str,
    scenario: str | None = None,
    step: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    auth_header_name: str | None = None,
    auth_token: str | None = None,
    auth_source: str | None = None,
    auth_scheme: str | None = None,
    response_transform=None,
    track_order: bool = False,
) -> Any:
    if recorder is None:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=30.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HttpApiError(
                url=url,
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            ) from exc
        return response.json()

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor=actor,
            action=action,
            category="auth",
            scenario=scenario,
            step=step,
            method=method,
            url=url,
            endpoint=endpoint,
            params=params,
            json_body=json_body,
            headers=headers,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            auth_source=auth_source,
            auth_scheme=auth_scheme,
            response_transform=response_transform,
            track_order=track_order,
        )
    except RequestError as exc:
        if exc.result is not None:
            raise HttpApiError(
                url=url,
                status_code=exc.result.response.status_code,
                response_text=exc.result.response.text,
                related_event_id=exc.event["id"] if exc.event else None,
            ) from exc
        raise HttpApiError(
            url=url,
            status_code=0,
            response_text=str(exc),
            related_event_id=exc.event["id"] if exc.event else None,
        ) from exc
    return result.payload


async def fetch_store_token(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> tuple[str, str]:
    if config.STORE_LASTMILE_TOKEN:
        console.print("[dim]store:[/] Using pre-set STORE_LASTMILE_TOKEN from .env")
        if recorder is not None:
            recorder.record_event(
                actor="store",
                action="reuse_store_env_token",
                category="auth",
                scenario=scenario,
                step="auth_reuse_store_env_token",
                auth=build_auth_proof(
                    header_name="Fainzy-Token",
                    token=config.STORE_LASTMILE_TOKEN,
                    source="store_env_token",
                ),
                details={"mode": "env"},
                track_order=False,
            )
        return config.STORE_LASTMILE_TOKEN, "store_env_token"

    if not config.STORE_ID:
        raise RuntimeError(
            "Either STORE_LASTMILE_TOKEN or STORE_ID must be set in .env"
        )

    console.print("[dim]store:[/] Fetching store LastMile/Fainzy-Token ...")
    payload = await _auth_request(
        client,
        recorder=recorder,
        actor="store",
        action="fetch_store_token",
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/biz/product/authentication/",
        endpoint="/v1/biz/product/authentication/",
        scenario=scenario,
        step="auth_fetch_store_token",
        params={"product": "rds"},
    )
    token = _token(payload)
    if not token:
        raise RuntimeError(f"Store auth response did not contain a token: {payload}")

    console.print("[green]store:[/] Store LastMile token acquired.")
    return str(token), "store_product_auth"


def _extract_gps(subentity: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return (lat, lng) from subentity.gps_coordinates.coordinates [lng, lat]."""
    gps = subentity.get("gps_coordinates") or subentity.get("gps_cordinates") or {}
    coords = gps.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lng, lat = coords[0], coords[1]
        return float(lat), float(lng)
    return None, None


def provisioning_preflight_enabled() -> bool:
    return (
        config.SIM_AUTO_PROVISION_FIXTURES
        or config.SIM_MUTATE_STORE_SETUP
        or config.SIM_MUTATE_MENU_SETUP
    )


def store_setup_provisioning_enabled() -> bool:
    return config.SIM_AUTO_PROVISION_FIXTURES or config.SIM_MUTATE_STORE_SETUP


def menu_provisioning_enabled() -> bool:
    return config.SIM_AUTO_PROVISION_FIXTURES or config.SIM_MUTATE_MENU_SETUP


def store_status_toggling_enabled() -> bool:
    return config.SIM_AUTO_TOGGLE_STORE_STATUS and provisioning_preflight_enabled()


async def bootstrap_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    store_id: str | None = None,
    scenario: str | None = None,
) -> StoreSession:
    effective_store_id = store_id or config.STORE_ID
    if not effective_store_id:
        raise RuntimeError("STORE_ID is required so fixtures can use a real store profile.")

    last_mile_token, token_source = await fetch_store_token(
        client,
        recorder=recorder,
        scenario=scenario,
    )

    console.print(f"[dim]store:[/] Fetching store profile for store_id={effective_store_id} ...")
    payload = await _auth_request(
        client,
        recorder=recorder,
        actor="store",
        action="fetch_store_profile",
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/entities/store/login",
        endpoint="/v1/entities/store/login",
        scenario=scenario,
        step="auth_fetch_store_profile",
        json_body={"store_id": effective_store_id},
        headers={
            "Content-Type": "application/json",
            "Store-Request": str(effective_store_id),
        },
    )
    data = api_data(payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Store login response had an invalid shape: {payload}")

    subentity = data.get("subentity")
    if not isinstance(subentity, dict) or not subentity.get("id"):
        raise RuntimeError(f"Store login response did not contain subentity.id: {payload}")

    sub_id = int(subentity["id"])
    config.SUBENTITY_ID = sub_id
    if subentity.get("currency"):
        config.STORE_CURRENCY = str(subentity["currency"]).lower()

    gps_lat, gps_lng = _extract_gps(subentity)

    console.print(
        f"[green]store:[/] Store profile acquired for {effective_store_id} "
        f"(subentity_id={sub_id}, lat={gps_lat}, lng={gps_lng})."
    )
    return StoreSession(
        last_mile_token=last_mile_token,
        fainzy_token=data.get("token"),
        subentity=subentity,
        store_id=sub_id,
        token_source=token_source,
        store_login_id=effective_store_id,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
    )


# ---------------------------------------------------------------------------
# Active websocket listener
# ---------------------------------------------------------------------------

def _websocket_root() -> str:
    parsed = urlparse(config.LASTMILE_BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


class _StoreOrderWatcher:
    """Connects to /ws/soc/store_<id>/ and dispatches order status changes."""

    def __init__(self, store_id: int, recorder: RunRecorder) -> None:
        self.store_id = store_id
        self.recorder = recorder
        self._pending_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._status_queues: dict[int, asyncio.Queue[str]] = {}
        self._task: asyncio.Task | None = None

    def subscribe(self, order_db_id: int) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._status_queues[order_db_id] = q
        return q

    def unsubscribe(self, order_db_id: int) -> None:
        self._status_queues.pop(order_db_id, None)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def get_pending_order(self) -> dict[str, Any]:
        return await self._pending_queue.get()

    async def _listen(self) -> None:
        root = _websocket_root()
        url = f"{root}/ws/soc/store_{self.store_id}/"
        while True:
            try:
                async with websockets.connect(
                    url,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    console.print(f"[blue]store_ws:[/] connected /ws/soc/store_{self.store_id}/")
                    async for raw in ws:
                        self._dispatch(str(raw))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)

    def _dispatch(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        nested = None
        if isinstance(payload, dict):
            msg = payload.get("message")
            if isinstance(msg, str):
                try:
                    nested = json.loads(msg)
                except json.JSONDecodeError:
                    nested = None
            elif isinstance(msg, dict):
                nested = msg

        data = nested if nested is not None else payload
        if not isinstance(data, dict):
            return

        order_db_id = data.get("id")
        status = data.get("status")
        order_ref = data.get("order_id")
        if order_db_id is None or status is None:
            return

        try:
            order_db_id = int(order_db_id)
        except (TypeError, ValueError):
            return

        status = str(status)
        self.recorder.record_websocket(
            source=f"store_orders_{self.store_id}",
            raw=raw,
            payload=payload,
            nested=nested,
            order_db_id=order_db_id,
            order_ref=str(order_ref) if order_ref else None,
            status=status,
        )

        # If this is a new pending order, enqueue it for _handle_order
        if status == "pending":
            self._pending_queue.put_nowait({
                "order_db_id": order_db_id,
                "order_ref": str(order_ref) if order_ref else "",
                "status": status,
            })

        # Dispatch to any subscriber waiting on this order's status
        q = self._status_queues.get(order_db_id)
        if q is not None:
            q.put_nowait(status)


# ---------------------------------------------------------------------------
# Order operations
# ---------------------------------------------------------------------------

def _order_payload(payload: Any) -> dict[str, Any]:
    raw = api_data(payload)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"Order response had invalid shape: {payload}")
    return raw


def _order_identity(payload: Any) -> tuple[int | None, str | None, str | None]:
    raw = api_data(payload)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return None, None, None
    order_db_id = raw.get("id")
    order_ref = raw.get("order_id")
    status = raw.get("status")
    try:
        order_db_id = int(order_db_id) if order_db_id is not None else None
    except (TypeError, ValueError):
        order_db_id = None
    return order_db_id, str(order_ref) if order_ref is not None else None, str(status) if status else None


def _store_api_token(session: StoreSession) -> tuple[str, str]:
    if session.fainzy_token:
        return str(session.fainzy_token), "store_fainzy_login_token"
    return session.last_mile_token, session.token_source


def _menu_identity(payload: Any) -> tuple[int | None, str | None, str | None]:
    raw = api_data(payload)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return None, None, None
    menu_id = raw.get("id")
    try:
        menu_id = int(menu_id) if menu_id is not None else None
    except (TypeError, ValueError):
        menu_id = None
    status = raw.get("status")
    return menu_id, None, str(status) if status is not None else None


def _menu_to_server(menu: dict[str, Any], *, status: str | None = None) -> dict[str, Any]:
    images = []
    for image in menu.get("images") or []:
        if isinstance(image, dict) and image.get("id") is not None:
            images.append({"id": image["id"]})

    data: dict[str, Any] = {
        "category": menu.get("category"),
        "subentity": menu.get("subentity"),
        "name": menu.get("name"),
        "price": menu.get("price"),
        "description": menu.get("description"),
        "currency_symbol": menu.get("currency_symbol"),
        "ingredients": menu.get("ingredients") or "",
        "discount": menu.get("discount") or 0,
        "discount_price": menu.get("discount_price"),
        "status": status if status is not None else menu.get("status"),
    }
    if images:
        data["images"] = images
    if menu.get("sides"):
        data["sides"] = menu["sides"]
    return data


def build_menu_create_payload(
    *,
    session: StoreSession,
    category_id: int,
    status: str,
) -> dict[str, Any]:
    return {
        "category": category_id,
        "subentity": session.store_id,
        "name": config.SIM_MENU_NAME,
        "price": config.SIM_MENU_PRICE,
        "description": config.SIM_MENU_DESCRIPTION,
        "currency_symbol": None,
        "ingredients": config.SIM_MENU_INGREDIENTS,
        "discount": config.SIM_MENU_DISCOUNT,
        "discount_price": config.SIM_MENU_DISCOUNT_PRICE,
        "status": status,
    }


def build_store_setup_payload(session: StoreSession) -> dict[str, Any]:
    subentity = session.subentity
    location = _store_location_source(subentity)
    location_lat, location_lng = _extract_location_gps(location)
    lat = (
        session.gps_lat
        if session.gps_lat is not None
        else location_lat
        if location_lat is not None
        else config.SIM_LAT
    )
    lng = (
        session.gps_lng
        if session.gps_lng is not None
        else location_lng
        if location_lng is not None
        else config.SIM_LNG
    )
    lat = 0.0 if lat is None else lat
    lng = 0.0 if lng is None else lng
    payload: dict[str, Any] = {
        "id": session.store_id,
        "name": subentity.get("name") or config.SIM_STORE_SETUP_NAME,
        "branch": subentity.get("branch") or config.SIM_STORE_SETUP_BRANCH,
        "description": subentity.get("description")
        or config.SIM_STORE_SETUP_DESCRIPTION,
        "opening_days": subentity.get("opening_days") or ",".join(WORKING_DAYS),
        "start_time": subentity.get("start_time") or config.SIM_STORE_SETUP_START_TIME,
        "closing_time": subentity.get("closing_time")
        or config.SIM_STORE_SETUP_CLOSING_TIME,
        "setup": True,
        "mobile_number": subentity.get("mobile_number")
        or config.SIM_STORE_SETUP_MOBILE,
        "notification_id": subentity.get("notification_id") or "",
        "currency": str(subentity.get("currency") or config.STORE_CURRENCY).lower(),
        "rating": subentity.get("rating") or 0.0,
        "status": _first_present(subentity.get("status"), config.SIM_STORE_SETUP_STATUS),
        "location": [
            {
                "name": _first_present(
                    location.get("name"),
                    subentity.get("name"),
                    config.SIM_STORE_SETUP_NAME,
                ),
                "country": _first_present(location.get("country"), config.SIM_STORE_SETUP_COUNTRY),
                "post_code": _first_present(location.get("post_code"), ""),
                "state": _first_present(location.get("state"), config.SIM_STORE_SETUP_STATE),
                "city": _first_present(location.get("city"), config.SIM_STORE_SETUP_CITY),
                "ward": _first_present(location.get("ward"), ""),
                "village": _first_present(location.get("village"), ""),
                "location_type": _first_present(location.get("location_type"), "pick_up"),
                "gps_coordinates": {
                    "latitude": str(lat),
                    "longitude": str(lng),
                },
                "address_details": _first_present(
                    location.get("address_details"),
                    location.get("name"),
                    config.SIM_STORE_SETUP_ADDRESS,
                ),
            }
        ],
    }
    if subentity.get("image"):
        payload["image"] = subentity["image"]
    if subentity.get("carousel_uploads"):
        payload["carousel_uploads"] = subentity["carousel_uploads"]
    return payload


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return values[-1] if values else None


def _store_location_source(subentity: dict[str, Any]) -> dict[str, Any]:
    for key in ("location", "locations"):
        value = subentity.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if isinstance(value, dict):
            return value
    for key in ("location_details", "address"):
        value = subentity.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_location_gps(location: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = location.get("gps_coordinates") or location.get("gps_cordinates") or {}
    if not isinstance(gps, dict):
        return None, None
    if gps.get("latitude") is not None and gps.get("longitude") is not None:
        return float(gps["latitude"]), float(gps["longitude"])
    coords = gps.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lng, lat = coords[0], coords[1]
        return float(lat), float(lng)
    return None, None


async def fetch_categories(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    recorder: RunRecorder,
    scenario: str,
    step: str = "fetch_categories",
) -> list[dict[str, Any]]:
    api_token, token_source = _store_api_token(session)
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action="fetch_categories",
        category="fixture",
        scenario=scenario,
        step=step,
        method="GET",
        url=f"{config.FAINZY_BASE_URL}/v1/core/subentities/{session.store_id}/categories",
        endpoint=f"/v1/core/subentities/{session.store_id}/categories",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


async def fetch_menus(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    recorder: RunRecorder,
    scenario: str,
    category_id: int | None = None,
    step: str = "fetch_menus",
) -> list[dict[str, Any]]:
    api_token, token_source = _store_api_token(session)
    params = {"categoryId": str(category_id)} if category_id is not None else None
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action="fetch_menus",
        category="fixture",
        scenario=scenario,
        step=step,
        method="GET",
        url=f"{config.FAINZY_BASE_URL}/v1/core/subentities/{session.store_id}/menu",
        endpoint=f"/v1/core/subentities/{session.store_id}/menu",
        params=params,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


async def create_category(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    name: str,
    recorder: RunRecorder,
    scenario: str,
    step: str = "create_category",
) -> dict[str, Any]:
    api_token, token_source = _store_api_token(session)
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action="create_category",
        category="store_setup",
        scenario=scenario,
        step=step,
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/core/subentities/{session.store_id}/categories",
        endpoint=f"/v1/core/subentities/{session.store_id}/categories",
        json_body={"name": name},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Category create response had invalid shape: {result.payload}")
    return data


async def create_menu(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    category_id: int,
    status: str,
    recorder: RunRecorder,
    scenario: str,
    step: str = "create_menu",
) -> dict[str, Any]:
    if status not in MENU_STATUSES:
        raise RuntimeError(f"Unsupported menu status {status!r}")
    api_token, token_source = _store_api_token(session)
    body = build_menu_create_payload(
        session=session,
        category_id=category_id,
        status=status,
    )
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action="create_menu",
        category="store_setup",
        scenario=scenario,
        step=step,
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/core/subentities/{session.store_id}/menu",
        endpoint=f"/v1/core/subentities/{session.store_id}/menu",
        json_body=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Menu create response had invalid shape: {result.payload}")
    return data


async def update_menu_status(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    menu: dict[str, Any],
    status: str,
    recorder: RunRecorder,
    scenario: str,
    step: str = "update_menu_status",
) -> dict[str, Any]:
    if status not in MENU_STATUSES:
        raise RuntimeError(f"Unsupported menu status {status!r}")
    menu_id = menu.get("id")
    if menu_id is None:
        raise RuntimeError(f"Menu has no id: {menu}")
    api_token, token_source = _store_api_token(session)
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action="update_menu_status",
        category="store_setup",
        scenario=scenario,
        step=step,
        method="PATCH",
        url=f"{config.FAINZY_BASE_URL}/v1/core/subentities/{session.store_id}/menu/{menu_id}",
        endpoint=f"/v1/core/subentities/{session.store_id}/menu/{menu_id}",
        json_body=_menu_to_server(menu, status=status),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Menu update response had invalid shape: {result.payload}")
    return data


async def _submit_store_profile_patch(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    recorder: RunRecorder,
    scenario: str,
    action: str,
    step: str,
) -> dict[str, Any] | None:
    api_token, token_source = _store_api_token(session)
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action=action,
        category="store_setup",
        scenario=scenario,
        step=step,
        method="PATCH",
        url=f"{config.FAINZY_BASE_URL}/v1/entities/subentities/{session.store_id}",
        endpoint=f"/v1/entities/subentities/{session.store_id}",
        json_body=build_store_setup_payload(session),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    if not isinstance(data, dict):
        return None
    session.subentity.update(data)
    return data


async def ensure_store_setup(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    recorder: RunRecorder,
    scenario: str,
) -> bool:
    setup_complete = session.subentity.get("setup") is True
    recorder.record_event(
        actor="store",
        action="store_setup_gate",
        category="ui_flow",
        scenario=scenario,
        step="store_setup_gate",
        details={
            "setup": session.subentity.get("setup"),
            "menu_actions_allowed": setup_complete or store_setup_provisioning_enabled(),
            "order_actions_allowed": setup_complete or store_setup_provisioning_enabled(),
            "auto_provision_enabled": config.SIM_AUTO_PROVISION_FIXTURES,
            "store_setup_mutation_enabled": config.SIM_MUTATE_STORE_SETUP,
            "store_update_mutation_enabled": config.SIM_AUTO_PROVISION_FIXTURES,
        },
        track_order=False,
    )
    if setup_complete:
        if config.SIM_AUTO_PROVISION_FIXTURES:
            console.print(
                f"[dim]store:[/] Store setup is already complete; submitting store update for subentity_id={session.store_id} ..."
            )
            data = await _submit_store_profile_patch(
                client,
                session=session,
                recorder=recorder,
                scenario=scenario,
                action="submit_store_update",
                step="submit_store_update",
            )
            if isinstance(data, dict):
                console.print(
                    f"[green]store:[/] Store profile update completed for subentity_id={session.store_id}."
                )
                return True
            console.print(
                f"[yellow]store:[/] Store profile update response had an unexpected shape for subentity_id={session.store_id}."
            )
            return False
        console.print(
            f"[dim]store:[/] Store setup already complete for subentity_id={session.store_id}."
        )
        return True
    if not store_setup_provisioning_enabled():
        console.print(
            "[yellow]store:[/] Store setup is false and automatic provisioning is disabled."
        )
        recorder.record_issue(
            severity="error",
            code="store_setup_required",
            actor="store",
            scenario=scenario,
            step="store_setup_gate",
            message=(
                "Store setup is false and automatic provisioning is disabled; "
                "set SIM_AUTO_PROVISION_FIXTURES=true or SIM_MUTATE_STORE_SETUP=true "
                "to PATCH the store profile through the setup flow."
            ),
        )
        return False

    console.print(
        f"[dim]store:[/] Store setup is false; submitting store setup for subentity_id={session.store_id} ..."
    )
    data = await _submit_store_profile_patch(
        client,
        session=session,
        recorder=recorder,
        scenario=scenario,
        action="submit_store_setup",
        step="submit_store_setup",
    )
    if isinstance(data, dict):
        if data.get("setup") is True:
            console.print(
                f"[green]store:[/] Store setup completed for subentity_id={session.store_id}."
            )
            return True
        console.print(
            f"[yellow]store:[/] Store setup response did not confirm setup=true for subentity_id={session.store_id}."
        )
        return False
    console.print(
        f"[yellow]store:[/] Store setup response had an unexpected shape for subentity_id={session.store_id}."
    )
    return False


def _status_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _patch_store_status(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    status: int,
    recorder: RunRecorder,
    scenario: str,
    action: str,
    step: str,
) -> dict[str, Any]:
    api_token, token_source = _store_api_token(session)
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action=action,
        category="store_status",
        scenario=scenario,
        step=step,
        method="PATCH",
        url=f"{config.FAINZY_BASE_URL}/v1/entities/subentities/{session.store_id}",
        endpoint=f"/v1/entities/subentities/{session.store_id}",
        json_body={"status": status},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {api_token}",
        },
        auth_header_name="Authorization",
        auth_token=api_token,
        auth_source=token_source,
        auth_scheme="Token",
        track_order=False,
    )
    data = api_data(result.payload)
    if isinstance(data, dict):
        session.subentity.update(data)
        return data
    raise RuntimeError(f"Store status update response had invalid shape: {result.payload}")


async def open_store_for_simulation(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    recorder: RunRecorder,
    scenario: str,
) -> int | None:
    original_status = _status_int(session.subentity.get("status"))
    recorder.record_event(
        actor="store",
        action="store_status_gate",
        category="ui_flow",
        scenario=scenario,
        step="store_status_gate",
        details={
            "status": original_status,
            "open_status": config.SIM_STORE_OPEN_STATUS,
            "closed_status": config.SIM_STORE_CLOSED_STATUS,
            "auto_toggle_enabled": config.SIM_AUTO_TOGGLE_STORE_STATUS,
        },
        track_order=False,
    )
    if not store_status_toggling_enabled():
        console.print("[dim]store:[/] Store status auto-toggle is disabled.")
        return None
    if original_status == config.SIM_STORE_OPEN_STATUS:
        console.print(
            f"[dim]store:[/] Store already open for subentity_id={session.store_id}."
        )
        return None

    console.print(
        f"[dim]store:[/] Opening store for simulation "
        f"(subentity_id={session.store_id}, previous_status={original_status}) ..."
    )
    await _patch_store_status(
        client,
        session=session,
        status=config.SIM_STORE_OPEN_STATUS,
        recorder=recorder,
        scenario=scenario,
        action="open_store_for_simulation",
        step="open_store_status",
    )
    console.print(
        f"[green]store:[/] Store opened for simulation "
        f"(subentity_id={session.store_id})."
    )
    return original_status


async def restore_store_status(
    client: httpx.AsyncClient,
    *,
    session: StoreSession,
    original_status: int | None,
    recorder: RunRecorder,
    scenario: str,
) -> bool:
    if original_status is None:
        return False
    current_status = _status_int(session.subentity.get("status"))
    if current_status == original_status:
        return False
    console.print(
        f"[dim]store:[/] Restoring store status "
        f"(subentity_id={session.store_id}, status={original_status}) ..."
    )
    await _patch_store_status(
        client,
        session=session,
        status=original_status,
        recorder=recorder,
        scenario=scenario,
        action="restore_store_status",
        step="restore_store_status",
    )
    console.print(
        f"[green]store:[/] Store status restored "
        f"(subentity_id={session.store_id}, status={original_status})."
    )
    return True


async def patch_status(
    client: httpx.AsyncClient,
    *,
    order_db_id: int,
    order_ref: str,
    status: str,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    actor: str = "store",
    action: str = "patch_status",
) -> bool:
    try:
        await request_json(
            client,
            recorder=recorder,
            actor=actor,
            action=action,
            category="status",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            expected_status=status,
            method="PATCH",
            url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
            endpoint="/v1/core/orders/",
            params={"order_id": str(order_db_id)},
            json_body={"status": status},
            headers={
                "Content-Type": "application/json",
                "Fainzy-Token": store_token,
            },
            auth_header_name="Fainzy-Token",
            auth_token=store_token,
            auth_source=token_source,
            response_order_info=_order_identity,
            expect_websocket=True,
        )
        console.print(f"[yellow]store_sim:[/] order={order_db_id} -> {status}")
        return True
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="store_patch_http_error",
            actor=actor,
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"HTTP error patching order {order_db_id} to {status}",
        )
        return False


async def fetch_order(
    client: httpx.AsyncClient,
    *,
    store_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str | None,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    action: str,
    poll_attempt: int | None = None,
) -> dict[str, Any]:
    result = await request_json(
        client,
        recorder=recorder,
        actor="store",
        action=action,
        category="verification",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        method="GET",
        url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
        endpoint="/v1/core/orders/",
        params={"order_id": str(order_db_id)},
        headers={
            "Content-Type": "application/json",
            "Fainzy-Token": store_token,
        },
        auth_header_name="Fainzy-Token",
        auth_token=store_token,
        auth_source=token_source,
        response_order_info=_order_identity,
        poll_attempt=poll_attempt,
    )
    return _order_payload(result.payload)


async def wait_for_status_ws(
    status_queue: asyncio.Queue[str],
    *,
    expected_statuses: set[str],
    terminal_statuses: set[str] | None = None,
    timeout_seconds: float,
) -> str | None:
    terminal_statuses = terminal_statuses or {"rejected", "cancelled", "refunded"}
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            status = await asyncio.wait_for(status_queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if status in expected_statuses:
            return status
        if status in terminal_statuses:
            return status


async def _handle_order(
    client: httpx.AsyncClient,
    *,
    order_db_id: int,
    order_ref: str,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
    watcher: _StoreOrderWatcher,
) -> None:
    scenario = "load"

    status_queue = watcher.subscribe(order_db_id)
    try:
        await asyncio.sleep(random.uniform(3, 12))

        if random.random() < config.REJECT_RATE:
            console.print(
                f"[red]store_sim:[/] Rejecting order={order_db_id} (reject_rate={config.REJECT_RATE})"
            )
            if not await patch_status(
                client,
                order_db_id=order_db_id,
                order_ref=order_ref,
                status="rejected",
                store_token=store_token,
                token_source=token_source,
                recorder=recorder,
                scenario=scenario,
                step="reject_order",
            ):
                return
            recorder.record_event(
                actor="store",
                action="rejected_order",
                category="terminal",
                scenario=scenario,
                step="reject_order",
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status="rejected",
            )
            return

        if not await patch_status(
            client,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status="payment_processing",
            store_token=store_token,
            token_source=token_source,
            recorder=recorder,
            scenario=scenario,
            step="accept_order",
        ):
            return

        # Wait for order_processing via websocket
        timeout = config.ORDER_PROCESSING_POLL_INTERVAL_SECONDS * config.ORDER_PROCESSING_POLL_MAX_ATTEMPTS
        status = await wait_for_status_ws(
            status_queue,
            expected_statuses={"order_processing"},
            timeout_seconds=timeout,
        )
        if status is None:
            recorder.record_event(
                actor="store",
                action="order_processing_timeout",
                category="terminal",
                scenario=scenario,
                step="wait_for_order_processing",
                ok=False,
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status="order_processing_timeout",
            )
            return

        if status in {"rejected", "cancelled", "refunded"}:
            recorder.record_event(
                actor="store",
                action="observed_terminal_during_processing_wait",
                category="terminal",
                scenario=scenario,
                step="wait_for_order_processing",
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status=status,
            )
            return

        prep_time = random.uniform(20, 90)
        console.print(
            f"[yellow]store_sim:[/] Preparing order={order_db_id} (~{prep_time:.0f}s) ..."
        )
        await asyncio.sleep(prep_time)

        if not await patch_status(
            client,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status="ready",
            store_token=store_token,
            token_source=token_source,
            recorder=recorder,
            scenario=scenario,
            step="mark_ready",
        ):
            recorder.record_event(
                actor="store",
                action="ready_failed",
                category="terminal",
                scenario=scenario,
                step="mark_ready",
                ok=False,
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status="ready_failed",
            )
            return

        console.print(f"[green]store_sim:[/] order={order_db_id} marked ready")
    finally:
        watcher.unsubscribe(order_db_id)


# ---------------------------------------------------------------------------
# Run entrypoint
# ---------------------------------------------------------------------------

async def run(*, recorder: RunRecorder, session: StoreSession | None = None) -> None:
    if session is None:
        console.print("[cyan]store_sim:[/] Bootstrapping auth ...")
        async with httpx.AsyncClient() as bootstrap_client:
            session = await bootstrap_auth(bootstrap_client, recorder)

    watcher = _StoreOrderWatcher(session.store_id, recorder)
    await watcher.start()

    console.print("[bold yellow]store_sim:[/] Listening for orders via websocket ...")
    tasks: set[asyncio.Task] = set()

    def _finish_task(task: asyncio.Task) -> None:
        tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            recorder.record_issue(
                severity="error",
                code="store_task_exception",
                actor="store",
                scenario="load",
                message=f"Store order task failed: {exc}",
            )

    async with httpx.AsyncClient() as client:
        try:
            while True:
                order = await watcher.get_pending_order()
                task = asyncio.create_task(
                    _handle_order(
                        client,
                        order_db_id=int(order["order_db_id"]),
                        order_ref=str(order["order_ref"]),
                        store_token=session.last_mile_token,
                        token_source=session.token_source,
                        recorder=recorder,
                        watcher=watcher,
                    )
                )
                tasks.add(task)
                task.add_done_callback(_finish_task)
        finally:
            await watcher.stop()
            pending = list(tasks)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
