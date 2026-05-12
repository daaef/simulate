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
from interaction_catalog import (
    LEGACY_AVAILABLE_STATUSES,
    MENU_AVAILABLE,
    menu_action_block_reason,
    menu_is_user_addable,
)
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


def _new_user_email(phone_number: str) -> str:
    if config.SIM_NEW_USER_EMAIL:
        return config.SIM_NEW_USER_EMAIL
    safe = "".join(ch.lower() for ch in phone_number if ch.isalnum())
    if not safe:
        safe = uuid.uuid4().hex[:12]
    return f"sim-{safe}@example.test"


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


async def _create_last_mile_user(
    client: httpx.AsyncClient,
    *,
    phone_number: str,
    recorder: RunRecorder | None,
    scenario: str | None,
) -> UserSession:
    body = {
        "first_name": config.SIM_NEW_USER_FIRST_NAME,
        "last_name": config.SIM_NEW_USER_LAST_NAME,
        "password": config.SIM_NEW_USER_PASSWORD,
        "email": _new_user_email(phone_number),
        "phone_number": phone_number,
    }
    payload = await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="create_user_account",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/users/create/",
        endpoint="/v1/auth/users/create/",
        scenario=scenario,
        step="auth_create_user_account",
        json_body=body,
    )
    data = api_data(payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"User create response had an invalid shape: {payload}")

    token = data.get("token")
    user = data.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not token:
        raise RuntimeError(f"User create response did not contain a token: {payload}")
    if not user_id:
        raise RuntimeError(f"User create response did not contain user.id: {payload}")

    _persist_user_token(token=str(token), user_id=int(user_id))
    if recorder is not None:
        recorder.record_event(
            actor="user",
            action="new_user_account_created",
            category="ui_flow",
            scenario=scenario,
            step="auth_create_user_account",
            details={
                "phone_setup_complete_before_create": False,
                "requires_location_selection": True,
            },
            track_order=False,
        )
    return UserSession(
        token=str(token),
        user_id=int(user_id),
        user=user,
        token_source="user_new_account_create",
    )


async def bootstrap_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    phone: str | None = None,
    scenario: str | None = None,
) -> UserSession:
    effective_phone = phone or config.USER_PHONE_NUMBER

    if config.USER_LASTMILE_TOKEN and not phone and scenario != "new_user_setup":
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
                session = UserSession(
                    token=config.USER_LASTMILE_TOKEN,
                    user_id=config.USER_ID,
                    user={"id": config.USER_ID},
                    token_source="user_cached_token",
                )
                # Fetch complete profile to ensure we have name and phone
                try:
                    profile = await fetch_user_profile(
                        client, token=session.token, recorder=recorder, scenario=scenario
                    )
                    if profile:
                        session.user.update(profile)
                except Exception as exc:
                    console.print(f"[yellow]user:[/] Profile fetch failed for cached token: {exc}")
                
                return session
            except HttpApiError as exc:
                if exc.status_code in {401, 403}:
                    console.print(
                        "[yellow]user:[/] Cached user token was rejected; refreshing via OTP."
                    )
                    _clear_cached_user_token()
                else:
                    raise

    if not effective_phone:
        raise RuntimeError(
            "Either USER_LASTMILE_TOKEN or USER_PHONE_NUMBER must be set in .env"
        )

    console.print(f"[dim]user:[/] Requesting OTP for {effective_phone} ...")
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
        json_body={"phone_number": effective_phone},
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
        json_body={"phone_number": effective_phone, "otp": str(otp)},
    )
    verify_data = api_data(verify_payload)
    if not isinstance(verify_data, dict):
        raise RuntimeError(f"OTP verify response had an invalid shape: {verify_payload}")
    if verify_data.get("setup_complete") is not True:
        console.print("[dim]user:[/] Creating new LastMile user account ...")
        return await _create_last_mile_user(
            client,
            phone_number=effective_phone,
            recorder=recorder,
            scenario=scenario,
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
        json_body={"phone_number": effective_phone},
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

async def fetch_user_profile(
    client: httpx.AsyncClient,
    *,
    token: str,
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    """Fetch the complete user profile from the backend."""
    payload = await _auth_request(
        client,
        recorder=recorder,
        actor="user",
        action="fetch_user_profile",
        method="GET",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/users/auth/",
        endpoint="/v1/auth/users/auth/",
        scenario=scenario,
        step="auth_fetch_user_profile",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {token}",
        },
        auth_header_name="Authorization",
        auth_token=token,
        auth_source="user_cached_token",
        auth_scheme="Token",
    )
    data = api_data(payload)
    if isinstance(data, dict):
        return data.get("user") or data
    return {}


@dataclass(frozen=True)
class UserFixtures:
    user_id: int
    store: dict[str, Any]
    location: dict[str, Any]
    menu_items: list[dict[str, Any]]
    currency: str
    user: dict[str, Any] | None = None


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

def _user_addable_menu_items(
    menu_items: list[dict[str, Any]],
    *,
    store: dict[str, Any],
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
    step: str = "vet_menu_items",
) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for item in menu_items:
        if not isinstance(item, dict):
            continue

        reason = menu_action_block_reason(item, store=store)
        if reason is None:
            usable.append(item)
        else:
            blocked.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "price": item.get("price"),
                    "discount_price": item.get("discount_price"),
                    "reason": reason,
                }
            )

    if recorder is not None:
        recorder.record_event(
            actor="user",
            action="vet_menu_items_before_cart",
            category="ui_gate",
            scenario=scenario,
            step=step,
            details={
                "store_id": store.get("id"),
                "store_status": store.get("status"),
                "usable_count": len(usable),
                "blocked_count": len(blocked),
                "blocked_preview": blocked[:20],
            },
            track_order=False,
        )

    return usable

def _real_cart_selection(
    menu_items: list[dict[str, Any]],
    *,
    store: dict[str, Any],
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> tuple[list[dict[str, Any]], float]:
    vetted = _user_addable_menu_items(
        menu_items,
        store=store,
        recorder=recorder,
        scenario=scenario,
        step="select_cart_items",
    )

    if not vetted:
        raise RuntimeError(
            "No user-addable menu items available. The user app cannot add sold_out, "
            "unavailable, legacy-status, closed-store, missing-id, or invalid-price items to cart."
        )

    count = random.randint(1, min(4, len(vetted)))
    chosen = random.sample(vetted, count)
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

def _require_non_empty(value: Any, *, name: str) -> None:
    if value is None:
        raise RuntimeError(f"{name} is required before making this request.")
    if isinstance(value, str) and not value.strip():
        raise RuntimeError(f"{name} is required before making this request.")
    if isinstance(value, (list, dict)) and not value:
        raise RuntimeError(f"{name} is required before making this request.")


def _validate_order_request_context(
    *,
    user_token: str,
    token_source: str,
    fixtures: UserFixtures,
    payload: dict[str, Any],
) -> None:
    _require_non_empty(user_token, name="user_token")
    _require_non_empty(token_source, name="token_source")
    _require_non_empty(fixtures.user_id, name="fixtures.user_id")
    _require_non_empty(fixtures.store, name="fixtures.store")
    _require_non_empty(fixtures.location, name="fixtures.location")
    _require_non_empty(payload.get("order_id"), name="payload.order_id")
    _require_non_empty(payload.get("restaurant"), name="payload.restaurant")
    _require_non_empty(payload.get("location"), name="payload.location")
    _require_non_empty(payload.get("menu"), name="payload.menu")

    store_id = fixtures.store.get("id")
    location_id = fixtures.location.get("id")
    _require_non_empty(store_id, name="fixtures.store.id")
    _require_non_empty(location_id, name="fixtures.location.id")

    total_price = payload.get("total_price")
    try:
        if float(total_price) <= 0:
            raise RuntimeError("payload.total_price must be greater than 0 before placing an order.")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("payload.total_price must be numeric before placing an order.") from exc

    for index, item in enumerate(payload["menu"]):
        if not isinstance(item, dict):
            raise RuntimeError(f"payload.menu[{index}] must be an object.")
        _require_non_empty(item.get("menuId"), name=f"payload.menu[{index}].menuId")
        _require_non_empty(item.get("quantity"), name=f"payload.menu[{index}].quantity")
        _require_non_empty(item.get("price"), name=f"payload.menu[{index}].price")

        menu = item.get("menu")
        if not isinstance(menu, dict):
            raise RuntimeError(f"payload.menu[{index}].menu must be an object.")

        if menu.get("status") != MENU_AVAILABLE:
            raise RuntimeError(
                f"payload.menu[{index}] cannot be ordered because status={menu.get('status')!r}."
            )

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
    lat: float | None = None,
    lng: float | None = None,
    subentity_id: int | None = None,
) -> UserFixtures:
    effective_lat = lat if lat is not None else config.SIM_LAT
    effective_lng = lng if lng is not None else config.SIM_LNG
    effective_subentity_id = subentity_id or config.SUBENTITY_ID

    if effective_lat is None or effective_lng is None:
        raise RuntimeError(
            "SIM_LAT and SIM_LNG are required so the simulator can fetch a real "
            "delivery location from /v1/entities/locations/<lng>/<lat>/."
        )

    store = _normalise_store(subentity or {"id": effective_subentity_id})

    menu_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/core/subentities/{effective_subentity_id}/menu",
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="load_store_menu",
        endpoint=f"/v1/core/subentities/{effective_subentity_id}/menu",
    )
    if not isinstance(menu_data, list):
        raise RuntimeError(f"Menu response had an invalid shape: {menu_data}")

    usable_menu = _user_addable_menu_items(
        [item for item in menu_data if isinstance(item, dict)],
        store=store,
        recorder=recorder,
        step="load_store_menu",
    )
    legacy_available = [
        item.get("id")
        for item in menu_data
        if isinstance(item, dict) and item.get("status") in LEGACY_AVAILABLE_STATUSES
    ]
    if recorder is not None and legacy_available:
        recorder.record_issue(
            severity="warning",
            code="legacy_menu_status_contract_risk",
            actor="backend",
            step="load_store_menu",
            message=(
                "Menu payload contains legacy status '1'. Store app counts it as "
                "available, but user app requires status 'available'."
            ),
            details={"menu_ids": legacy_available[:20]},
        )
    if not usable_menu:
        raise RuntimeError(
            f"No available priced menu items found for subentity_id={effective_subentity_id}."
        )

    location_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/entities/locations/{effective_lng}/{effective_lat}/",
        params={"search_radius": str(config.SIM_LOCATION_RADIUS)},
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="load_delivery_locations",
        endpoint=f"/v1/entities/locations/{effective_lng}/{effective_lat}/",
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

    location_required = (
        session.token_source == "user_new_account_create" or config.LOCATION_ID is None
    )
    if recorder is not None:
        recorder.record_event(
            actor="user",
            action="location_selection_gate",
            category="ui_flow",
            step="location_selection_gate",
            details={
                "is_new_user": session.token_source == "user_new_account_create",
                "saved_location_missing": config.LOCATION_ID is None,
                "region_selection_allowed": location_required,
                "radius_km": config.SIM_LOCATION_RADIUS,
            },
            track_order=False,
        )

    location = None
    location_selection_recorded = False
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
        if recorder is not None:
            recorder.record_event(
                actor="user",
                action="select_delivery_location",
                category="ui_flow",
                step="select_delivery_location",
                details={
                    "location_id": config.LOCATION_ID,
                    "reason": "new_user_or_missing_saved_location"
                    if location_required
                    else "bootstrap_default",
                },
                track_order=False,
            )
            location_selection_recorded = True

    if recorder is not None and location_required and not location_selection_recorded:
        recorder.record_event(
            actor="user",
            action="select_delivery_location",
            category="ui_flow",
            step="select_delivery_location",
            details={
                "location_id": location.get("id") if isinstance(location, dict) else None,
                "reason": "new_user_or_missing_saved_location",
            },
            track_order=False,
        )

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
        user=session.user,
    )


# ---------------------------------------------------------------------------
# Realistic store discovery
# ---------------------------------------------------------------------------

async def discover_stores_for_area(
    client: httpx.AsyncClient,
    *,
    store_token: str,
    lat: float,
    lng: float,
    recorder: RunRecorder | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, int | None]:
    """Discover open stores near (lat, lng) via the service-area API.

    Returns (open_stores, delivery_location, service_area_id).
    open_stores is a list of subentity dicts with status==1.
    delivery_location is the first active location found, or None.
    """
    location_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/entities/locations/{lng}/{lat}/",
        params={"search_radius": str(config.SIM_LOCATION_RADIUS)},
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="discover_locations",
        endpoint=f"/v1/entities/locations/{lng}/{lat}/",
    )
    if not isinstance(location_data, list) or not location_data:
        return [], None, None

    active_locs = _active_locations(
        [item for item in location_data if isinstance(item, dict)]
    )
    if not active_locs:
        return [], None, None

    delivery_location = active_locs[0]
    service_area_id = delivery_location.get("service_area")
    if not service_area_id:
        return [], delivery_location, None

    stores_data = await _seed_get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/entities/subentities/service-area/{service_area_id}/",
        token=store_token,
        auth_scheme="",
        auth_header_name="Fainzy-Token",
        recorder=recorder,
        action="discover_stores",
        endpoint=f"/v1/entities/subentities/service-area/{service_area_id}/",
    )
    if not isinstance(stores_data, list):
        return [], delivery_location, int(service_area_id)

    open_stores = []
    for entry in stores_data:
        sub = entry.get("subentity", entry) if isinstance(entry, dict) else entry
        if isinstance(sub, dict) and sub.get("status") == 1:
            open_stores.append(sub)

    return open_stores, delivery_location, int(service_area_id)


async def _discover_and_build_fixtures(
    client: httpx.AsyncClient,
    *,
    user_session: UserSession,
    store_sessions: list,  # list[store_sim.StoreSession]
    recorder: RunRecorder,
    worker_id: int,
) -> UserFixtures | None:
    """Per-order discovery: pick a random store GPS, call service-area API,
    choose an open store, fetch its menu, and return fresh UserFixtures."""
    import store_sim as _store_sim

    shuffled = list(store_sessions)
    random.shuffle(shuffled)

    for ss in shuffled:
        if ss.gps_lat is None or ss.gps_lng is None:
            continue
        if ss.gps_lat == 0.0 and ss.gps_lng == 0.0:
            continue

        console.print(
            f"[dim]user[{worker_id}]:[/] Discovering stores near "
            f"({ss.gps_lat:.4f}, {ss.gps_lng:.4f}) ..."
        )

        open_stores, delivery_location, service_area_id = await discover_stores_for_area(
            client,
            store_token=ss.last_mile_token,
            lat=ss.gps_lat,
            lng=ss.gps_lng,
            recorder=recorder,
        )

        if not open_stores:
            console.print(
                f"[yellow]user[{worker_id}]:[/] No open stores found near "
                f"({ss.gps_lat:.4f}, {ss.gps_lng:.4f}), trying next ..."
            )
            continue

        if delivery_location is None:
            console.print(
                f"[yellow]user[{worker_id}]:[/] No delivery location found, trying next ..."
            )
            continue

        # Constrain to stores we actually have a session for so the
        # store listener can accept the order.
        logged_in_ids = {s.store_id for s in store_sessions}
        reachable = [s for s in open_stores if s.get("id") in logged_in_ids]
        if not reachable:
            console.print(
                f"[yellow]user[{worker_id}]:[/] Discovered {len(open_stores)} open store(s) "
                f"but none match logged-in sessions {logged_in_ids}, trying next ..."
            )
            continue

        chosen_store = random.choice(reachable)
        chosen_id = chosen_store.get("id")
        normalized_store = _normalise_store(chosen_store)

        console.print(
            f"[green]user[{worker_id}]:[/] Discovered {len(open_stores)} open store(s) "
            f"in service_area={service_area_id}. Chose store {chosen_store.get('name')!r} "
            f"(subentity_id={chosen_id})"
        )

        menu_data = await _seed_get_json(
            client,
            f"{config.FAINZY_BASE_URL}/v1/core/subentities/{chosen_id}/menu",
            token=ss.last_mile_token,
            auth_scheme="",
            auth_header_name="Fainzy-Token",
            recorder=recorder,
            action="load_store_menu",
            endpoint=f"/v1/core/subentities/{chosen_id}/menu",
        )
        if not isinstance(menu_data, list):
            console.print(
                f"[yellow]user[{worker_id}]:[/] Menu fetch for store {chosen_id} failed, "
                "trying next ..."
            )
            continue

        usable_menu = _user_addable_menu_items(
            [item for item in menu_data if isinstance(item, dict)],
            store=normalized_store,
            recorder=recorder,
            step="load_store_menu",
        )
        legacy_available = [
            item.get("id")
            for item in menu_data
            if isinstance(item, dict) and item.get("status") in LEGACY_AVAILABLE_STATUSES
        ]
        if legacy_available:
            recorder.record_issue(
                severity="warning",
                code="legacy_menu_status_contract_risk",
                actor="backend",
                scenario="load",
                step="load_store_menu",
                message=(
                    "Menu payload contains legacy status '1'. Store app counts it "
                    "as available, but user app requires status 'available'."
                ),
                details={"menu_ids": legacy_available[:20], "store_id": chosen_id},
            )
        if not usable_menu:
            console.print(
                f"[yellow]user[{worker_id}]:[/] No available menu items for store "
                f"{chosen_id}, trying next ..."
            )
            continue

        store = _normalise_store(chosen_store)
        currency = str(store.get("currency") or config.STORE_CURRENCY).lower()

        return UserFixtures(
            user_id=user_session.user_id,
            store=store,
            location=delivery_location,
            menu_items=usable_menu,
            currency=currency,
        )

    console.print(
        f"[red]user[{worker_id}]:[/] Could not discover any open store with menu."
    )
    return None


def generate_order_payload(
    fixtures: UserFixtures,
    *,
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    menu_items, total_price = _real_cart_selection(
        fixtures.menu_items,
        store=fixtures.store,
        recorder=recorder,
        scenario=scenario,
    )

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
        self.recorder.record_websocket(
            source=f"user_orders_{self.user_id}",
            raw=raw,
            payload=payload,
            nested=nested,
            order_db_id=order_db_id,
            order_ref=str(data.get("order_id")) if data.get("order_id") else None,
            status=str(status),
        )


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
    payload = generate_order_payload(
        fixtures,
        recorder=recorder,
        scenario=scenario,
    )   
    _validate_order_request_context(
        user_token=user_token,
        token_source=token_source,
        fixtures=fixtures,
        payload=payload,
    )
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

    coupon_label = config.SIM_COUPON_ID if config.SIM_COUPON_ID is not None else "none"
    console.print(
        f"[cyan]user:[/] Completing free order {order_ref} "
        f"(db_id={order_db_id}, amount={config.SIM_FREE_ORDER_AMOUNT:g}, "
        f"{config.STORE_CURRENCY}, coupon={coupon_label}) ..."
    )
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
        console.print(f"[green]user:[/] Free order confirmed for {order_ref}.")
        return True
    except RequestError as exc:
        console.print(f"[red]user:[/] Free order failed for {order_ref}: {exc}")
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
    store_sessions: list | None = None,
    user_session: UserSession | None = None,
) -> None:
    async with httpx.AsyncClient() as client:
        while True:
            if work_queue is not None:
                try:
                    work_queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

            # Per-order discovery when store_sessions are available.
            effective_fixtures = fixtures
            if store_sessions and user_session is not None:
                discovered = await _discover_and_build_fixtures(
                    client,
                    user_session=user_session,
                    store_sessions=store_sessions,
                    recorder=recorder,
                    worker_id=worker_id,
                )
                if discovered is not None:
                    effective_fixtures = discovered
                else:
                    console.print(
                        f"[yellow]user[{worker_id}]:[/] Discovery failed; "
                        "falling back to bootstrap fixtures."
                    )

            order = await place_order(
                client,
                user_token=user_token,
                token_source=token_source,
                worker_id=worker_id,
                fixtures=effective_fixtures,
                recorder=recorder,
                scenario="load",
                step="place_order",
            )
            if order is not None:
                status_queue = watcher.subscribe(order["order_db_id"])
                try:
                    completed = await handle_order_payment(
                        client,
                        user_token=user_token,
                        token_source=token_source,
                        order=order,
                        recorder=recorder,
                        status_queue=status_queue,
                    )
                    if completed and config.SIM_RUN_POST_ORDER_ACTIONS:
                        import post_order_actions

                        await post_order_actions.run_post_order_actions(
                            client,
                            recorder=recorder,
                            user_token=user_token,
                            token_source=token_source,
                            order_db_id=int(order["order_db_id"]),
                            order_ref=str(order["order_ref"]),
                            subentity=effective_fixtures.store,
                            scenario="load",
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
    store_sessions: list | None = None,
) -> None:
    """Run the user simulation.

    If *session* and *fixtures* are provided the bootstrap phase is skipped
    (useful when __main__ pre-bootstraps to sequence store/robot startup).
    *store_sessions* enables per-order realistic discovery when provided.
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
                _worker(
                    session.token, session.token_source, i + 1, fixtures,
                    recorder, watcher, work_queue,
                    store_sessions=store_sessions,
                    user_session=session,
                )
            )
            for i in range(config.N_USERS)
        ]
        await asyncio.gather(*workers)
    finally:
        await watcher.stop()
