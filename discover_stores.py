#!/usr/bin/env python3
"""
Store discovery script.

Logs into every store listed in sim_actors.json, extracts GPS coordinates
and subentity metadata from the profile response, and writes the enriched
data back to sim_actors.json.

Usage:
    python discover_stores.py            # enrich sim_actors.json in-place
    python discover_stores.py --dry-run  # print results without writing
    python discover_stores.py --open     # also open any closed stores
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

# -- bootstrap project config (reads .env) -----------------------------------
import config

console = Console()

ACTORS_PATH = Path(__file__).parent / "sim_actors.json"

FAINZY_BASE = config.FAINZY_BASE_URL
LASTMILE_BASE = config.LASTMILE_BASE_URL


# ---------------------------------------------------------------------------
# Lightweight auth helpers (mirrors store_sim logic, no recorder dependency)
# ---------------------------------------------------------------------------

async def _fetch_store_token(client: httpx.AsyncClient) -> str:
    """Get a Fainzy-Token via the product auth endpoint."""
    resp = await client.post(
        f"{FAINZY_BASE}/v1/biz/product/authentication/",
        params={"product": "rds"},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("token") or payload.get("token", "")
    return payload.get("token", "")


async def _fetch_store_profile(
    client: httpx.AsyncClient,
    store_id: str,
) -> dict:
    """POST /v1/entities/store/login with a given store_id, return raw data dict."""
    resp = await client.post(
        f"{FAINZY_BASE}/v1/entities/store/login",
        json={"store_id": store_id},
        headers={
            "Content-Type": "application/json",
            "Store-Request": store_id,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response for {store_id}: {payload}")
    return data


def _extract_gps(subentity: dict) -> tuple[float | None, float | None]:
    """Return (lat, lng) from subentity.gps_coordinates.coordinates [lng, lat]."""
    gps = subentity.get("gps_coordinates") or subentity.get("gps_cordinates") or {}
    coords = gps.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lng, lat = coords[0], coords[1]
        return float(lat), float(lng)
    return None, None


def _store_status_label(status: int | None) -> str:
    """Convert numeric status to human label. 1=open, 3=closed."""
    if status == 1:
        return "open"
    if status == 3:
        return "closed"
    if status is None:
        return "unknown"
    return f"status={status}"


async def _open_store(
    client: httpx.AsyncClient,
    subentity_id: int,
    fainzy_token: str,
) -> bool:
    """PATCH /v1/entities/subentities/{id} with {status: 1} to open the store."""
    resp = await client.patch(
        f"{FAINZY_BASE}/v1/entities/subentities/{subentity_id}",
        json={"status": 1},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {fainzy_token}",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Main discovery
# ---------------------------------------------------------------------------

async def discover_all(stores: list[dict], *, try_open: bool = False) -> list[dict]:
    """Authenticate each store and enrich with GPS + subentity metadata."""
    enriched: list[dict] = []

    async with httpx.AsyncClient() as client:
        # One shared Fainzy-Token for all store logins.
        console.print("[cyan]discover:[/] Fetching shared Fainzy-Token ...")
        token = await _fetch_store_token(client)
        if not token:
            console.print("[red]discover:[/] Could not obtain Fainzy-Token. Aborting.")
            sys.exit(1)
        console.print(f"[green]discover:[/] Fainzy-Token acquired (len={len(token)}).")

        for entry in stores:
            store_id = entry["store_id"]
            console.print(f"[cyan]discover:[/] Logging into {store_id} ...")
            try:
                data = await _fetch_store_profile(client, store_id)
                subentity = data.get("subentity", {})
                fainzy_token = data.get("token")
                sub_id = subentity.get("id")
                name = subentity.get("name", "?")
                branch = subentity.get("branch", "")
                currency = subentity.get("currency", "")
                status = subentity.get("status")
                lat, lng = _extract_gps(subentity)

                status_label = _store_status_label(status)
                console.print(
                    f"  [green]✓[/] {store_id} → subentity_id={sub_id}, "
                    f"name={name!r}, status={status_label}, lat={lat}, lng={lng}"
                )

                # Attempt to open closed stores if requested.
                if try_open and status != 1 and sub_id and fainzy_token:
                    console.print(
                        f"    [yellow]→ Store is {status_label}. Attempting to open ...[/yellow]"
                    )
                    try:
                        await _open_store(client, int(sub_id), fainzy_token)
                        status = 1
                        status_label = "open"
                        console.print(f"    [green]✓ Store opened successfully.[/green]")
                    except Exception as open_exc:
                        console.print(f"    [red]✗ Failed to open: {open_exc}[/red]")

                result = {
                    "store_id": store_id,
                    "subentity_id": sub_id,
                    "name": name,
                    "branch": branch,
                    "currency": currency,
                    "status": status,
                    "lat": lat,
                    "lng": lng,
                }
                enriched.append(result)
            except Exception as exc:
                console.print(f"  [red]✗[/] {store_id} → {exc}")
                enriched.append({
                    "store_id": store_id,
                    "error": str(exc),
                })

    return enriched


def _print_table(stores: list[dict]) -> None:
    table = Table(title="Discovered Store Profiles")
    table.add_column("Store ID", style="cyan")
    table.add_column("Sub ID", justify="right")
    table.add_column("Name")
    table.add_column("Branch")
    table.add_column("Currency")
    table.add_column("Status")
    table.add_column("Lat", justify="right")
    table.add_column("Lng", justify="right")

    for s in stores:
        if "error" in s:
            table.add_row(s["store_id"], "ERR", s.get("error", "")[:60], "", "", "", "", "")
        else:
            status = s.get("status")
            status_str = _store_status_label(status)
            status_style = "green" if status == 1 else "red" if status == 3 else "yellow"
            table.add_row(
                s["store_id"],
                str(s.get("subentity_id", "")),
                s.get("name", ""),
                s.get("branch", ""),
                s.get("currency", ""),
                f"[{status_style}]{status_str}[/{status_style}]",
                f"{s['lat']:.6f}" if s.get("lat") is not None else "—",
                f"{s['lng']:.6f}" if s.get("lng") is not None else "—",
            )
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover store GPS coordinates")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without writing back to sim_actors.json",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Attempt to open any closed stores (PATCH status=1)",
    )
    args = parser.parse_args()

    if not ACTORS_PATH.exists():
        console.print(f"[red]Error:[/] {ACTORS_PATH} not found.")
        sys.exit(1)

    actors = json.loads(ACTORS_PATH.read_text())
    stores = actors.get("stores", [])
    if not stores:
        console.print("[red]Error:[/] No stores in sim_actors.json.")
        sys.exit(1)

    console.print(f"[bold]Discovering {len(stores)} store(s) ...[/bold]")
    if args.open:
        console.print("[yellow]--open: Will attempt to open closed stores.[/yellow]")
    console.print()
    enriched = asyncio.run(discover_all(stores, try_open=args.open))

    _print_table(enriched)

    if args.dry_run:
        console.print("\n[yellow]Dry run — sim_actors.json not modified.[/yellow]")
        return

    # Write enriched stores back to sim_actors.json.
    actors["stores"] = enriched
    ACTORS_PATH.write_text(json.dumps(actors, indent=2) + "\n")
    console.print(f"\n[green]✓ Updated {ACTORS_PATH}[/green]")


if __name__ == "__main__":
    main()
