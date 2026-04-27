"""
User actor — fully self-contained.

Owns:
  - User auth (OTP flow, cached token validation, .env persistence)
  - User seeding (store menu, delivery location)
  - Active websocket on /ws/soc/<user_id>/ for real-time order status
  - Order placement, payment, cancellation
"""

from __future__ import annotations

import asyncio
import json
import random
import string
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets
from rich.console import Console

import config
import stripe_sim
from reporting import RunRecorder
from transport import RequestError, api_data, build_auth_proof, request_json

console = Console()
ENV_PATH = Path(__file__).parent / ".env"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserSession:
    token: str
    user_id: int
    user: dict[str, Any]
    token_source: str


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


def _write_env_values(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        replaced = False
        for key, value in updates.items():
            prefix = f"{key}="
            if line.startswith(prefix):
                new_lines.append(f"{key}={value}")
                seen.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _persist_user_token(*, token: str, user_id: int) -> None:
    config.USER_LASTMILE_TOKEN = token
    config.USER_ID = user_id
    _write_env_values(
        {
            "USER_LASTMILE_TOKEN": token,
            "USER_ID": str(user_id),
        }
    )


def _clear_cached_user_token() -> None:
    config.USER_LASTMILE_TOKEN = ""
    config.USER_ID = None
    _write_env_values(
        {
            "USER_LASTMILE_TOKEN": "",
            "USER_ID": "",
        }
    )


def _otp_response(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {"data": "[redacted]"}
    return "[redacted]"


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


async def _validate_cached_user_token(
    client: httpx.AsyncClient,
    *,
    token: str,
    user_id: int,
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> bool:
    await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="validate_cached_user_token",
        method="GET",
        url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
        endpoint="/v1/core/orders/",
        scenario=scenario,
        step="auth_validate_cached_user_token",
        params={"user": str(user_id)},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {token}",
        },
        auth_header_name="Authorization",
        auth_token=token,
        auth_source="user_cached_token",
        auth_scheme="Token",
    )
    return True


async def bootstrap_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> UserSession:
    if config.USER_LASTMILE_TOKEN:
        if config.USER_ID is None:
            console.print(
                "[yellow]user:[/] USER_LASTMILE_TOKEN was set without USER_ID; "
                "ignoring cache and refreshing via OTP."
            )
        else:
            console.print("[dim]user:[/] Validating cached USER_LASTMILE_TOKEN ...")
            try:
                await _validate_cached_user_token(
                    client,
                    token=config.USER_LASTMILE_TOKEN,
                    user_id=config.USER_ID,
                    recorder=recorder,
                    scenario=scenario,
                )
                console.print(
                    f"[green]user:[/] Reusing cached user token for user_id={config.USER_ID}."
                )
                return UserSession(
                    token=config.USER_LASTMILE_TOKEN,
                    user_id=config.USER_ID,
                    user={"id": config.USER_ID},
                    token_source="user_cached_token",
                )
            except HttpApiError as exc:
                if exc.status_code in {401, 403}:
                    console.print(
                        "[yellow]user:[/] Cached user token was rejected; refreshing via OTP."
                    )
                    _clear_cached_user_token()
                else:
                    raise

    if not config.USER_PHONE_NUMBER:
        raise RuntimeError(
            "Either USER_LASTMILE_TOKEN or USER_PHONE_NUMBER must be set in .env"
        )

    console.print(f"[dim]user:[/] Requesting OTP for {config.USER_PHONE_NUMBER} ...")
    otp_payload = await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="request_user_otp",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/otp/send/",
        endpoint="/v1/auth/otp/send/",
        scenario=scenario,
        step="auth_request_user_otp",
        json_body={"phone_number": config.USER_PHONE_NUMBER},
        response_transform=_otp_response,
    )
    otp = api_data(otp_payload)
    if not otp:
        raise RuntimeError(f"OTP response did not contain data: {otp_payload}")

    console.print("[dim]user:[/] Verifying OTP ...")
    verify_payload = await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="verify_user_otp",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/otp/verify/",
        endpoint="/v1/auth/otp/verify/",
        scenario=scenario,
        step="auth_verify_user_otp",
        json_body={"phone_number": config.USER_PHONE_NUMBER, "otp": str(otp)},
    )
    verify_data = api_data(verify_payload)
    if not isinstance(verify_data, dict):
        raise RuntimeError(f"OTP verify response had an invalid shape: {verify_payload}")
    if verify_data.get("setup_complete") is not True:
        raise RuntimeError(
            "The configured phone number is not setup_complete=true. "
            "Use an already-registered test user before running the simulation."
        )
    if verify_data.get("is_active") is False:
        raise RuntimeError("The configured user is inactive; reactivate it before simulation.")

    console.print("[dim]user:[/] Fetching user LastMile token ...")
    auth_payload = await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="fetch_user_token",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/users/auth/",
        endpoint="/v1/auth/users/auth/",
        scenario=scenario,
        step="auth_fetch_user_token",
        json_body={"phone_number": config.USER_PHONE_NUMBER},
    )
    auth_data = api_data(auth_payload)
    if not isinstance(auth_data, dict):
        raise RuntimeError(f"User auth response had an invalid shape: {auth_payload}")

    token = auth_data.get("token")
    user = auth_data.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not token:
        raise RuntimeError(f"User auth response did not contain a token: {auth_payload}")
    if not user_id:
        raise RuntimeError(f"User auth response did not contain user.id: {auth_payload}")

    _persist_user_token(token=str(token), user_id=int(user_id))
    console.print(f"[green]user:[/] User token acquired for user_id={user_id}.")
    return UserSession(
        token=str(token),
        user_id=int(user_id),
        user=user,
        token_source="user_otp_auth",
    )


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserFixtures:
    user_id: int
    store: dict[str, Any]
    location: dict[str, Any]
    menu_items: list[dict[str, Any]]
    currency: str


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _line_price(menu: dict[str, Any]) -> float:
    discount_price = _as_float(menu.get("discount_price"))
    price = _as_float(menu.get("price"))
    if discount_price is not None and discount_price > 0:
        return discount_price
    if price is not None and price > 0:
        return price
    raise RuntimeError(f"Menu item has no usable price: {menu}")


def _real_cart_selection(menu_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    count = random.randint(1, min(4, len(menu_items)))
    chosen = random.sample(menu_items, count)
    items = []
    total = 0.0
    for menu in chosen:
        qty = random.randint(1, 3)
        price = _line_price(menu)
        line_total = price * qty
        total += line_total
        items.append(
            {
                "id": str(uuid.uuid1()),
                "menuId": menu["id"],
                "menu": menu,
                "quantity": qty,
                "price": price,
                "sides": [],
            }
        )
    return items, round(total, 2)


def _random_order_id() -> str:
    digits = "".join(random.choices(string.digits, k=6))
    return f"#{digits}"


def _normalise_store(store: dict[str, Any]) -> dict[str, Any]:
    store_id = store.get("id") or config.SUBENTITY_ID
    if not store_id:
        raise RuntimeError(f"Store fixture has no id: {store}")

    return {
        **store,
        "id": store_id,
        "name": store.get("name") or "Fainzy Test Store",
        "branch": store.get("branch") or "",
        "status": store.get("status", 1),
        "currency": str(store.get("currency") or config.STORE_CURRENCY).lower(),
    }


def _active_locations(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in locations if item.get("is_active") is not False]


async def _seed_get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    token: str,
    auth_scheme: str = "Token",
    auth_header_name: str = "Authorization",
    recorder: RunRecorder | None = None,
    action: str,
    endpoint: str,
) -> Any:
    headers = {
        "Content-Type": "application/json",
        auth_header_name: f"{auth_scheme} {token}" if auth_scheme else token,
    }
    if recorder is None:
        resp = await client.get(url, params=params, headers=headers, timeout=30.0)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:500]}"
            ) from exc
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor="user",
            action=action,
            category="fixture",
            step=action,
            method="GET",
            url=url,
            endpoint=endpoint,
            params=params,
            headers=headers,
            auth_header_name=auth_header_name,
            auth_token=token,
            auth_source="user_fixture_lookup",
            auth_scheme=auth_scheme,
            track_order=False,
        )
    except RequestError as exc:
        if exc.result is not None:
            raise RuntimeError(
                f"HTTP {exc.result.response.status_code} from {url}: "
                f"{exc.result.response.text[:500]}"
            ) from exc
        raise RuntimeError(f"Error calling {url}: {exc}") from exc
    return api_data(result.payload)


async def bootstrap_fixtures(
    client: httpx.AsyncClient,
    *,
    session: UserSession,
    store_token: str,
    subentity: dict[str, Any] | None = None,
    recorder: RunRecorder | None = None,
) -> UserFixtures:
    if config.SIM_LAT is None or config.SIM_LNG is None:
        raise RuntimeError(
            "SIM_LAT and SIM_LNG are required so the simulator can fetch a real "
            "delivery location from /v1/entities/locations/<lng>/<lat>/."
        )

    menu_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/core/subentities/{config.SUBENTITY_ID}/menu",
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="load_store_menu",
        endpoint=f"/v1/core/subentities/{config.SUBENTITY_ID}/menu",
    )
    if not isinstance(menu_data, list):
        raise RuntimeError(f"Menu response had an invalid shape: {menu_data}")

    usable_menu = [
        item
        for item in menu_data
        if isinstance(item, dict)
        and item.get("id")
        and item.get("status") == "available"
        and _as_float(item.get("price")) is not None
    ]
    if not usable_menu:
        raise RuntimeError(
            f"No available priced menu items found for subentity_id={config.SUBENTITY_ID}."
        )

    location_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/entities/locations/{config.SIM_LNG}/{config.SIM_LAT}/",
        params={"search_radius": str(config.SIM_LOCATION_RADIUS)},
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="load_delivery_locations",
        endpoint=f"/v1/entities/locations/{config.SIM_LNG}/{config.SIM_LAT}/",
    )
    if not isinstance(location_data, list):
        raise RuntimeError(f"Location response had an invalid shape: {location_data}")

    active_locations = _active_locations(
        [item for item in location_data if isinstance(item, dict)]
    )
    if not active_locations:
        raise RuntimeError(
            "No active delivery locations were returned. Adjust SIM_LAT/SIM_LNG "
            "or SIM_LOCATION_RADIUS."
        )

    location = None
    if config.LOCATION_ID is not None:
        location = next(
            (item for item in active_locations if item.get("id") == config.LOCATION_ID),
            None,
        )
        if location is None:
            raise RuntimeError(
                f"LOCATION_ID={config.LOCATION_ID} was not returned for the configured "
                "SIM_LAT/SIM_LNG search."
            )
    else:
        location = active_locations[0]
        config.LOCATION_ID = int(location["id"])

    store = _normalise_store(subentity or {"id": config.SUBENTITY_ID})
    currency = str(store.get("currency") or config.STORE_CURRENCY).lower()
    config.STORE_CURRENCY = currency

    console.print(
        "[green]user:[/] Loaded fixtures "
        f"store={store['id']} location={location['id']} menu_items={len(usable_menu)}"
    )
    return UserFixtures(
        user_id=session.user_id,
        store=store,
        location=location,
        menu_items=usable_menu,
        currency=currency,
    )


def generate_order_payload(fixtures: UserFixtures) -> dict[str, Any]:
    menu_items, total_price = _real_cart_selection(fixtures.menu_items)

    return {
        "order_id": _random_order_id(),
        "restaurant": fixtures.store,
        "location": fixtures.location,
        "menu": menu_items,
        "total_price": total_price,
        "status": "pending",
        "user": fixtures.user_id,
    }


# ---------------------------------------------------------------------------
# Active websocket listener
# ---------------------------------------------------------------------------

def _websocket_root() -> str:
    parsed = urlparse(config.LASTMILE_BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


class _UserOrderWatcher:
    """Connects to /ws/soc/<user_id>/ and dispatches status changes."""

    def __init__(self, user_id: int, recorder: RunRecorder) -> None:
        self.user_id = user_id
        self.recorder = recorder
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

    async def _listen(self) -> None:
        root = _websocket_root()
        url = f"{root}/ws/soc/{self.user_id}/"
        while True:
            try:
                async with websockets.connect(
                    url,
                    subprotocols=["websocket"],
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    console.print(f"[blue]user_ws:[/] connected /ws/soc/{self.user_id}/")
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
        if order_db_id is None or status is None:
            return

        try:
            order_db_id = int(order_db_id)
        except (TypeError, ValueError):
            return

        q = self._status_queues.get(order_db_id)
        if q is not None:
            q.put_nowait(str(status))


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


async def place_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    worker_id: int,
    fixtures: UserFixtures,
    recorder: RunRecorder,
    scenario: str = "load",
    step: str = "place_order",
) -> dict[str, Any] | None:
    payload = generate_order_payload(fixtures)
    order_ref = payload["order_id"]
    order_total = payload["total_price"]

    console.print(
        f"[cyan]user[{worker_id}]:[/] Placing order {order_ref}  "
        f"({len(payload['menu'])} items, {config.STORE_CURRENCY} {order_total:,.0f})"
    )

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor="user",
            action="place_order",
            category="status",
            scenario=scenario,
            step=step,
            method="POST",
            url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
            endpoint="/v1/core/orders/",
            json_body=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {user_token}",
            },
            auth_header_name="Authorization",
            auth_token=user_token,
            auth_source=token_source,
            auth_scheme="Token",
            response_order_info=_order_identity,
            expect_websocket=True,
            details={
                "worker_id": worker_id,
                "items": len(payload["menu"]),
                "total": order_total,
                "currency": config.STORE_CURRENCY,
            },
        )
    except RequestError as exc:
        response_text = ""
        if exc.result is not None:
            response_text = exc.result.response.text[:1000]
        console.print(f"[red]user[{worker_id}]:[/] Error placing order: {exc}")
        recorder.record_issue(
            severity="error",
            code="place_order_http_error",
            actor="user",
            scenario=scenario,
            step=step,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"Failed to place order {order_ref}",
            details={"response": response_text},
        )
        return None

    raw = _order_payload(result.payload)
    order_db_id = raw.get("id")
    returned_ref = raw.get("order_id") or order_ref
    if not order_db_id:
        console.print(f"[red]user[{worker_id}]:[/] No order id in response: {raw}")
        recorder.record_issue(
            severity="error",
            code="place_order_missing_id",
            actor="user",
            scenario=scenario,
            step=step,
            order_ref=order_ref,
            related_event_id=result.event["id"],
            message="Order placement response did not contain an order id",
            details={"response": raw},
        )
        return None

    console.print(
        f"[green]user[{worker_id}]:[/] Order placed — db_id={order_db_id}  ref={returned_ref}"
    )
    return {
        "order_db_id": int(order_db_id),
        "order_ref": str(returned_ref),
        "order_total": float(order_total),
        "scenario": scenario,
    }


async def fetch_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str | None,
    recorder: RunRecorder,
    action: str,
    scenario: str = "load",
    step: str,
    poll_attempt: int | None = None,
) -> dict[str, Any]:
    result = await request_json(
        client,
        recorder=recorder,
        actor="user",
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
            "Authorization": f"Token {user_token}",
        },
        auth_header_name="Authorization",
        auth_token=user_token,
        auth_source=token_source,
        auth_scheme="Token",
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


async def cancel_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    scenario: str,
    step: str,
) -> bool:
    try:
        await request_json(
            client,
            recorder=recorder,
            actor="user",
            action="cancel_order",
            category="status",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            expected_status="cancelled",
            method="PATCH",
            url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
            endpoint="/v1/core/orders/",
            params={"order_id": str(order_db_id)},
            json_body={"status": "cancelled"},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {user_token}",
            },
            auth_header_name="Authorization",
            auth_token=user_token,
            auth_source=token_source,
            auth_scheme="Token",
            response_order_info=_order_identity,
            expect_websocket=True,
        )
        return True
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="cancel_order_http_error",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"HTTP error cancelling order {order_db_id}",
        )
        return False


async def complete_free_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_ref: str,
    order_db_id: int,
    recorder: RunRecorder,
    scenario: str,
    step: str,
) -> bool:
    if config.SIM_FREE_ORDER_AMOUNT > 0:
        raise RuntimeError(
            "SIM_PAYMENT_MODE=free cannot send a positive amount. "
            "Use SIM_FREE_ORDER_AMOUNT=0 and SIM_COUPON_ID if the backend requires a coupon."
        )

    body: dict[str, Any] = {
        "amount": config.SIM_FREE_ORDER_AMOUNT,
        "order_id": order_ref,
        "currency": config.STORE_CURRENCY,
        "subentity_id": config.SUBENTITY_ID,
    }
    if config.SIM_COUPON_ID is not None:
        body["coupon"] = config.SIM_COUPON_ID

    try:
        await request_json(
            client,
            recorder=recorder,
            actor="user",
            action="complete_free_order",
            category="payment",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            expected_status="order_processing",
            method="POST",
            url=f"{config.LASTMILE_BASE_URL}/v1/core/order/free/",
            endpoint="/v1/core/order/free/",
            json_body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {user_token}",
            },
            auth_header_name="Authorization",
            auth_token=user_token,
            auth_source=token_source,
            auth_scheme="Token",
        )
        return True
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="free_order_http_error",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"HTTP error while confirming free order {order_ref}",
        )
        return False


async def handle_order_payment(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order: dict[str, Any],
    recorder: RunRecorder,
    status_queue: asyncio.Queue[str],
) -> bool:
    order_db_id = int(order["order_db_id"])
    order_ref = str(order["order_ref"])
    scenario = str(order.get("scenario") or "load")

    timeout = config.USER_DECISION_POLL_INTERVAL_SECONDS * config.USER_DECISION_POLL_MAX_ATTEMPTS
    status = await wait_for_status_ws(
        status_queue,
        expected_statuses={"payment_processing"},
        timeout_seconds=timeout,
    )
    if status is None:
        recorder.record_event(
            actor="user",
            action="store_decision_timeout",
            category="terminal",
            scenario=scenario,
            step="wait_for_store_decision",
            ok=False,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status="store_decision_timeout",
        )
        return False

    if status in {"rejected", "cancelled", "refunded"}:
        recorder.record_event(
            actor="user",
            action="observed_terminal_before_payment",
            category="terminal",
            scenario=scenario,
            step="wait_for_store_decision",
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status=status,
        )
        return False

    if config.SIM_PAYMENT_MODE == "stripe":
        paid = await stripe_sim.pay_order(
            client,
            user_token=user_token,
            token_source=token_source,
            order_ref=order_ref,
            order_db_id=order_db_id,
            amount=float(order["order_total"]),
            recorder=recorder,
            scenario=scenario,
            step="complete_payment",
        )
    elif config.SIM_PAYMENT_MODE == "free":
        paid = await complete_free_order(
            client,
            user_token=user_token,
            token_source=token_source,
            order_ref=order_ref,
            order_db_id=order_db_id,
            recorder=recorder,
            scenario=scenario,
            step="complete_free_order",
        )
    else:
        raise RuntimeError(f"Unsupported SIM_PAYMENT_MODE={config.SIM_PAYMENT_MODE!r}")

    if not paid:
        recorder.record_event(
            actor="user",
            action="payment_failed",
            category="terminal",
            scenario=scenario,
            step="complete_payment",
            ok=False,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status="payment_failed",
        )
        return False

    # Wait for terminal status after payment
    terminal_timeout = config.ORDER_PROCESSING_POLL_INTERVAL_SECONDS * config.ORDER_PROCESSING_POLL_MAX_ATTEMPTS
    terminal_status = await wait_for_status_ws(
        status_queue,
        expected_statuses={"completed"},
        terminal_statuses={"rejected", "cancelled", "refunded"},
        timeout_seconds=terminal_timeout,
    )
    recorder.record_event(
        actor="user",
        action="order_terminal",
        category="terminal",
        scenario=scenario,
        step="wait_for_terminal",
        order_db_id=order_db_id,
        order_ref=order_ref,
        observed_status=terminal_status or "terminal_timeout",
    )
    return terminal_status == "completed"


# ---------------------------------------------------------------------------
# Workers and run entrypoint
# ---------------------------------------------------------------------------

async def _worker(
    user_token: str,
    token_source: str,
    worker_id: int,
    fixtures: UserFixtures,
    recorder: RunRecorder,
    watcher: _UserOrderWatcher,
    work_queue: asyncio.Queue[int] | None = None,
) -> None:
    async with httpx.AsyncClient() as client:
        while True:
            if work_queue is not None:
                try:
                    work_queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

            order = await place_order(
                client,
                user_token=user_token,
                token_source=token_source,
                worker_id=worker_id,
                fixtures=fixtures,
                recorder=recorder,
                scenario="load",
                step="place_order",
            )
            if order is not None:
                status_queue = watcher.subscribe(order["order_db_id"])
                try:
                    await handle_order_payment(
                        client,
                        user_token=user_token,
                        token_source=token_source,
                        order=order,
                        recorder=recorder,
                        status_queue=status_queue,
                    )
                finally:
                    watcher.unsubscribe(order["order_db_id"])

            if work_queue is not None:
                work_queue.task_done()
                if work_queue.empty():
                    return

            jitter = random.uniform(0.8, 1.2)
            await asyncio.sleep(config.ORDER_INTERVAL_SECONDS * jitter)


async def run(
    *,
    recorder: RunRecorder,
    session: UserSession | None = None,
    fixtures: UserFixtures | None = None,
) -> None:
    """Run the user simulation.

    If *session* and *fixtures* are provided the bootstrap phase is skipped
    (useful when __main__ pre-bootstraps to sequence store/robot startup).
    """
    if session is None or fixtures is None:
        console.print("[cyan]user_sim:[/] Bootstrapping auth ...")
        async with httpx.AsyncClient() as bootstrap_client:
            session = await bootstrap_auth(bootstrap_client, recorder)
            import store_sim
            store_session = await store_sim.bootstrap_auth(bootstrap_client, recorder)
            fixtures = await bootstrap_fixtures(
                bootstrap_client,
                session=session,
                store_token=store_session.last_mile_token,
                subentity=store_session.subentity,
                recorder=recorder,
            )

    watcher = _UserOrderWatcher(session.user_id, recorder)
    await watcher.start()

    console.print(
        f"[bold cyan]user_sim:[/] Starting {config.N_USERS} user worker(s), "
        f"interval={config.ORDER_INTERVAL_SECONDS}s, "
        f"{'continuous' if config.SIM_CONTINUOUS else f'orders={config.SIM_ORDERS}'}"
    )
    work_queue: asyncio.Queue[int] | None = None
    if not config.SIM_CONTINUOUS:
        work_queue = asyncio.Queue()
        for i in range(config.SIM_ORDERS):
            work_queue.put_nowait(i + 1)

    try:
        workers = [
            asyncio.create_task(
                _worker(session.token, session.token_source, i + 1, fixtures, recorder, watcher, work_queue)
            )
            for i in range(config.N_USERS)
        ]
        await asyncio.gather(*workers)
    finally:
        await watcher.stop()
