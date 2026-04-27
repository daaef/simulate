"""Fetches real order fixtures and builds order payloads from them."""

from __future__ import annotations

import random
import string
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from rich.console import Console

import auth
import config
from reporting import RunRecorder
from transport import RequestError, api_data, request_json

console = Console()


@dataclass(frozen=True)
class SimulationFixtures:
    user_id: int
    store: dict[str, Any]
    location: dict[str, Any]
    menu_items: list[dict[str, Any]]
    currency: str


def _random_order_id() -> str:
    digits = "".join(random.choices(string.digits, k=6))
    return f"#{digits}"


def _api_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    token: str,
    recorder: RunRecorder | None = None,
    action: str,
    endpoint: str,
) -> Any:
    if recorder is None:
        resp = await client.get(
            url,
            params=params,
            headers={"Content-Type": "application/json", "Fainzy-Token": token},
            timeout=30.0,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:500]}"
            ) from exc
        return _api_data(resp.json())

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor="seed",
            action=action,
            category="fixture",
            step=action,
            method="GET",
            url=url,
            endpoint=endpoint,
            params=params,
            headers={"Content-Type": "application/json", "Fainzy-Token": token},
            auth_header_name="Fainzy-Token",
            auth_token=token,
            auth_source="store_fixture_lookup",
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


def _normalise_store(store: dict[str, Any]) -> dict[str, Any]:
    store_id = store.get("id") or config.SUBENTITY_ID
    if not store_id:
        raise RuntimeError(f"Store fixture has no id: {store}")

    return {
        **store,
        "id": int(store_id),
        "name": store.get("name") or "Fainzy Test Store",
        "branch": store.get("branch") or "",
        "status": store.get("status", 1),
        "currency": str(store.get("currency") or config.STORE_CURRENCY).lower(),
    }


def _active_locations(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in locations if item.get("is_active") is not False]


async def load_fixtures(
    client: httpx.AsyncClient,
    *,
    user_session: auth.UserSession,
    store_session: auth.StoreSession,
    recorder: RunRecorder | None = None,
) -> SimulationFixtures:
    if config.SIM_LAT is None or config.SIM_LNG is None:
        raise RuntimeError(
            "SIM_LAT and SIM_LNG are required so the simulator can fetch a real "
            "delivery location from /v1/entities/locations/<lng>/<lat>/."
        )

    menu_data = await _get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/core/subentities/{config.SUBENTITY_ID}/menu",
        token=store_session.last_mile_token,
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

    location_data = await _get_json(
        client,
        f"{config.FAINZY_BASE_URL}/v1/entities/locations/{config.SIM_LNG}/{config.SIM_LAT}/",
        params={"search_radius": str(config.SIM_LOCATION_RADIUS)},
        token=store_session.last_mile_token,
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

    store = _normalise_store(store_session.subentity)
    currency = str(store.get("currency") or config.STORE_CURRENCY).lower()
    config.STORE_CURRENCY = currency

    console.print(
        "[green]seed:[/] Loaded real fixtures "
        f"store={store['id']} location={location['id']} menu_items={len(usable_menu)}"
    )
    return SimulationFixtures(
        user_id=user_session.user_id,
        store=store,
        location=location,
        menu_items=usable_menu,
        currency=currency,
    )


def generate_order_payload(fixtures: SimulationFixtures) -> dict[str, Any]:
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
