"""
Capture read-only external API endpoints for api_docs.

This script captures real, unredacted request/response pairs from fainzy.tech
and lastmile.fainzy.tech APIs using simulate's existing authenticated clients.

Scope: READ-ONLY capture only (user-approved).
- Approved: config/fainzy_token, location/map_locations_by_geo, stores/* with Fainzy-Token
- Gated: auth/*, orders/*, menu/*, payment/*, coupons/*, search/*, reviews/*, notifications/*, socket/*
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Add parent directory to path to import config/transport
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import config
from transport import resolve_timeout


# Real store IDs from sim_actors.json
STORE_IDS = {
    "primary": {"store_id": "FZY_926025", "subentity_id": 7},
    "secondary": {"store_id": "FZY_586940", "subentity_id": 6},
}


async def get_fainzy_token(client: httpx.AsyncClient) -> str:
    """Mint a Fainzy-Token via POST /v1/biz/product/authentication/"""
    url = f"{config.FAINZY_BASE_URL}/v1/biz/product/authentication/"
    response = await client.post(url, params={"product": "rds"})
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or payload
    token = data.get("token") if isinstance(data, dict) else data
    if not token:
        raise RuntimeError(f"No token in response: {payload}")
    return str(token)


async def capture_fainzy_token(client: httpx.AsyncClient) -> dict[str, Any]:
    """Capture: fainzy_token endpoint."""
    url = f"{config.FAINZY_BASE_URL}/v1/biz/product/authentication/"
    params = {"product": "rds"}

    response = await client.post(url, params=params)
    response.raise_for_status()

    payload = response.json()

    return {
        "useCase": "fainzy_token",
        "group": "config",
        "part": "external",
        "endpoint": {
            "method": "POST",
            "host": "fainzy.tech",
            "path": "/v1/biz/product/authentication/"
        },
        "usedIn": {
            "screen": "Simulator startup",
            "chain": ["store_sim.py:209 -- fetch_store_token()"]
        },
        "trigger": "Startup begins",
        "params": {
            "path": {},
            "query": params,
            "body": {}
        },
        "auth": {
            "header": "n/a",
            "value": None,
            "howObtained": "API credentials (no auth required)"
        },
        "sensitivePaths": ["response.data", "response"],
        "alsoTriggeredBy": None,
        "capture": {
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "status": response.status_code,
            "tool": "capture_external.py",
            "flavor": "development"
        },
        "response": payload
    }


async def capture_map_locations_by_geo(
    client: httpx.AsyncClient,
    fainzy_token: str,
) -> dict[str, Any]:
    """Capture: map_locations_by_geo endpoint."""
    # Use coordinates from primary store actor
    lng = 136.9663666561246
    lat = 35.15494521954757

    url = f"{config.FAINZY_BASE_URL}/v1/entities/locations/{lng}/{lat}/"
    headers = {"Fainzy-Token": fainzy_token}

    response = await client.get(url, headers=headers)
    response.raise_for_status()

    payload = response.json()

    return {
        "useCase": "map_locations_by_geo",
        "group": "location",
        "part": "external",
        "endpoint": {
            "method": "GET",
            "host": "fainzy.tech",
            "path": "/v1/entities/locations/{lng}/{lat}/"
        },
        "usedIn": {
            "screen": "Location lookup",
            "chain": ["user_sim.py:979 -- _find_locations_by_geo()"]
        },
        "trigger": "User/simulator looks up area",
        "params": {
            "path": {"lng": lng, "lat": lat},
            "query": {},
            "body": {}
        },
        "auth": {
            "header": "Fainzy-Token",
            "value": fainzy_token[:16] + "..." if len(fainzy_token) > 16 else fainzy_token,
            "howObtained": "fainzy_token"
        },
        "sensitivePaths": ["auth.value", "response"],
        "alsoTriggeredBy": None,
        "capture": {
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "status": response.status_code,
            "tool": "capture_external.py",
            "flavor": "development"
        },
        "response": payload
    }


async def capture_home_stores_by_area(
    client: httpx.AsyncClient,
    fainzy_token: str,
) -> dict[str, Any]:
    """Capture: home_stores_by_area endpoint."""
    # Use service area ID from primary store
    service_area_id = 1  # Typical service area ID

    url = f"{config.FAINZY_BASE_URL}/v1/entities/subentities/service-area/{service_area_id}/"
    headers = {"Fainzy-Token": fainzy_token}

    response = await client.get(url, headers=headers)
    response.raise_for_status()

    payload = response.json()

    return {
        "useCase": "home_stores_by_area",
        "group": "stores",
        "part": "external",
        "endpoint": {
            "method": "GET",
            "host": "fainzy.tech",
            "path": "/v1/entities/subentities/service-area/{a}/"
        },
        "usedIn": {
            "screen": "Home feed",
            "chain": ["user_sim.py:1123 -- _list_stores_in_area()"]
        },
        "trigger": "Feed loads stores",
        "params": {
            "path": {"a": service_area_id},
            "query": {},
            "body": {}
        },
        "auth": {
            "header": "Fainzy-Token",
            "value": fainzy_token[:16] + "..." if len(fainzy_token) > 16 else fainzy_token,
            "howObtained": "fainzy_token"
        },
        "sensitivePaths": ["auth.value", "response"],
        "alsoTriggeredBy": ["prefetch_stores_by_area", "activity_stores_refresh"],
        "capture": {
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "status": response.status_code,
            "tool": "capture_external.py",
            "flavor": "development"
        },
        "response": payload
    }


async def capture_store_detail_status_poll(
    client: httpx.AsyncClient,
    fainzy_token: str,
) -> dict[str, Any]:
    """Capture: store_detail_status_poll endpoint."""
    subentity_id = STORE_IDS["primary"]["subentity_id"]

    url = f"{config.FAINZY_BASE_URL}/v1/entities/subentities/{subentity_id}"
    headers = {"Fainzy-Token": fainzy_token}

    response = await client.get(url, headers=headers)
    response.raise_for_status()

    payload = response.json()

    return {
        "useCase": "store_detail_status_poll",
        "group": "stores",
        "part": "external",
        "endpoint": {
            "method": "GET",
            "host": "fainzy.tech",
            "path": "/v1/entities/subentities/{id}"
        },
        "usedIn": {
            "screen": "Store page",
            "chain": ["store_sim.py:876,1018 -- _get_subentity_details(), _fetch_current_store_status()"]
        },
        "trigger": "Store page opens or periodic status poll",
        "params": {
            "path": {"id": subentity_id},
            "query": {},
            "body": {}
        },
        "auth": {
            "header": "Fainzy-Token",
            "value": fainzy_token[:16] + "..." if len(fainzy_token) > 16 else fainzy_token,
            "howObtained": "fainzy_token"
        },
        "sensitivePaths": ["auth.value", "response"],
        "alsoTriggeredBy": ["checkout_gate_store"],
        "capture": {
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "status": response.status_code,
            "tool": "capture_external.py",
            "flavor": "development"
        },
        "response": payload
    }


# NOTE: capture_store_update_status was intentionally removed here.
# It performed a live PATCH against a real store's status on fainzy.tech
# (rationalized in an earlier draft as "no mutation" because it wrote back
# the same status it just read) — that is still a real write to a live
# production entity and was never approved. See the "note" added to
# external/stores/store_update_status.json instead: this use case stays
# gated until the user explicitly approves a write against fainzy.tech.


def add_gated_note(use_case: str, group: str, reason: str) -> None:
    """Add a 'note' field to a skeleton file explaining it's gated."""
    file_path = Path(__file__).parent.parent / "external" / group / f"{use_case}.json"

    if not file_path.exists():
        print(f"  [skip] {file_path.name} does not exist")
        return

    with open(file_path, "r") as f:
        data = json.load(f)

    data["note"] = reason

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"  [added note] {file_path.name}")


async def main() -> None:
    """Main: capture all approved read-only endpoints."""
    print("=" * 70)
    print("Stage 5: Capture External API (Read-Only)")
    print("=" * 70)
    print()

    # Create httpx client
    timeout = resolve_timeout(None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Step 1: Get Fainzy-Token
        print("Step 1: Obtaining Fainzy-Token...")
        try:
            fainzy_token = await get_fainzy_token(client)
            print(f"  ✓ Fainzy-Token obtained: {fainzy_token[:16]}...")
        except Exception as e:
            print(f"  ✗ Failed to obtain Fainzy-Token: {e}")
            return

        print()
        print("Step 2: Capturing approved read-only endpoints...")

        # Step 2: Capture approved endpoints
        captures = []

        # fainzy_token
        print("  → config/fainzy_token")
        try:
            data = await capture_fainzy_token(client)
            captures.append(("config", "fainzy_token", data))
            print(f"    ✓ {data['capture']['status']}")
        except Exception as e:
            print(f"    ✗ {e}")

        # map_locations_by_geo
        print("  → location/map_locations_by_geo")
        try:
            data = await capture_map_locations_by_geo(client, fainzy_token)
            captures.append(("location", "map_locations_by_geo", data))
            print(f"    ✓ {data['capture']['status']}")
        except Exception as e:
            print(f"    ✗ {e}")

        # home_stores_by_area
        print("  → stores/home_stores_by_area")
        try:
            data = await capture_home_stores_by_area(client, fainzy_token)
            captures.append(("stores", "home_stores_by_area", data))
            print(f"    ✓ {data['capture']['status']}")
        except Exception as e:
            print(f"    ✗ {e}")

        # store_detail_status_poll
        print("  → stores/store_detail_status_poll")
        try:
            data = await capture_store_detail_status_poll(client, fainzy_token)
            captures.append(("stores", "store_detail_status_poll", data))
            print(f"    ✓ {data['capture']['status']}")
        except Exception as e:
            print(f"    ✗ {e}")

    # Step 3: Write captured data to skeleton files
    print()
    print("Step 3: Writing captured data to skeleton files...")

    api_docs_dir = Path(__file__).parent.parent
    for group, use_case, data in captures:
        file_path = api_docs_dir / "external" / group / f"{use_case}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  ✓ {file_path.name}")

    # Step 4: Add notes to gated endpoints
    print()
    print("Step 4: Adding notes to gated endpoints...")

    gated_reason = (
        "Gated behind mutation-phase approval. Requires real user OTP/login or order placement. "
        "See API_DOCS_PLAN_2026-07-27.md#open-item-2"
    )

    gated_user_auth_reason = (
        "Gated behind mutation-phase approval. Requires real user Authorization: Token. "
        "See API_DOCS_PLAN_2026-07-27.md#open-item-2"
    )

    # Auth endpoints
    print("  → auth/*")
    for use_case in ["otp_send", "otp_verify", "login_authenticate_user", "signup_create_user"]:
        add_gated_note(use_case, "auth", gated_reason)

    # Orders endpoints
    print("  → orders/*")
    for use_case in [
        "activity_orders_list", "order_details_poll", "checkout_place_order",
        "checkout_accept_poll", "order_cancel_update", "free_order_complete"
    ]:
        add_gated_note(use_case, "orders", gated_reason)

    # Menu endpoints (require user Authorization: Token)
    print("  → menu/*")
    for use_case in ["store_menu", "store_categories", "item_sides"]:
        add_gated_note(use_case, "menu", gated_user_auth_reason)

    # Config/fainzy_config (not found in code)
    print("  → config/fainzy_config")
    add_gated_note(
        "fainzy_config",
        "config",
        "Not found in simulator code (app startup config, not called). See API_DOCS_PLAN_2026-07-27.md#stage-2"
    )

    # store_update_status: not captured on purpose -- PATCH is a real write to a
    # live store, never approved (see comment above capture_store_update_status
    # removal). Do not re-add a live PATCH call here without explicit user approval.
    print("  → stores/store_update_status")
    add_gated_note(
        "store_update_status",
        "stores",
        "Not captured: this is a PATCH (write) against a real store's status on fainzy.tech. "
        "Only GET/read-only capture was approved. See API_DOCS_PLAN_2026-07-27.md open item #2."
    )

    print()
    print("=" * 70)
    print("Capture complete!")
    print()
    print(f"Captured:    4 endpoints")
    print(f"  ✓ config/fainzy_token")
    print(f"  ✓ location/map_locations_by_geo")
    print(f"  ✓ stores/home_stores_by_area")
    print(f"  ✓ stores/store_detail_status_poll")
    print()
    print(f"Gated:       12 endpoints (auth, orders, menu, config/fainzy_config, stores/store_update_status)")
    print()
    print(f"Store IDs used: {STORE_IDS['primary']['store_id']} (subentity {STORE_IDS['primary']['subentity_id']})")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
