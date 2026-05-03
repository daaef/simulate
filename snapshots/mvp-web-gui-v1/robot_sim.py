"""
Robot actor — fully self-contained.

Owns:
  - Store token acquisition (same mechanism as store_sim, independent call)
  - Active websocket on /ws/soc/store_<store_id>/ for discovering ready orders
  - Delivery lifecycle (status progression to completed)
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets
from rich.console import Console

import config
from reporting import RunRecorder
from transport import RequestError, api_data, build_auth_proof, request_json

console = Console()

ROBOT_LIFECYCLE = [
    ("enroute_pickup", (20, 60)),
    ("robot_arrived_for_pickup", (5, 20)),
    ("enroute_delivery", (30, 120)),
    ("robot_arrived_for_delivery", (5, 20)),
    ("completed", (2, 8)),
]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RobotSession:
    store_token: str
    store_id: int  # subentity_id — used for websocket channel
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


async def bootstrap_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    store_token: str | None = None,
    subentity_id: int | None = None,
    scenario: str | None = None,
) -> RobotSession:
    # When explicit store_token + subentity_id are provided (multi-store mode),
    # skip the product auth and just return a session for that store.
    if store_token and subentity_id:
        console.print(
            f"[dim]robot:[/] Using provided store token for subentity_id={subentity_id}"
        )
        return RobotSession(
            store_token=store_token,
            store_id=subentity_id,
            token_source="robot_store_provided",
        )

    if config.STORE_LASTMILE_TOKEN:
        console.print("[dim]robot:[/] Using pre-set STORE_LASTMILE_TOKEN from .env")
        if recorder is not None:
            recorder.record_event(
                actor="robot",
                action="reuse_store_env_token",
                category="auth",
                scenario=scenario,
                step="auth_reuse_store_env_token",
                auth=build_auth_proof(
                    header_name="Fainzy-Token",
                    token=config.STORE_LASTMILE_TOKEN,
                    source="robot_store_env_token",
                ),
                details={"mode": "env"},
                track_order=False,
            )
        if not config.SUBENTITY_ID:
            raise RuntimeError(
                "SUBENTITY_ID must be set before robot can start. "
                "Store auth must run first."
            )
        return RobotSession(
            store_token=config.STORE_LASTMILE_TOKEN,
            store_id=config.SUBENTITY_ID,
            token_source="robot_store_env_token",
        )

    if not config.STORE_ID:
        raise RuntimeError(
            "Either STORE_LASTMILE_TOKEN or STORE_ID must be set in .env"
        )

    console.print("[dim]robot:[/] Fetching store LastMile/Fainzy-Token ...")
    payload = await _auth_request(
        client,
        recorder=recorder,
        actor="robot",
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
        raise RuntimeError(f"Robot store auth response did not contain a token: {payload}")

    console.print("[green]robot:[/] Store token acquired.")
    if not config.SUBENTITY_ID:
        raise RuntimeError(
            "SUBENTITY_ID must be set before robot can start. "
            "Store auth must run first."
        )
    return RobotSession(
        store_token=str(token),
        store_id=config.SUBENTITY_ID,
        token_source="robot_store_product_auth",
    )


# ---------------------------------------------------------------------------
# Active websocket listener
# ---------------------------------------------------------------------------

def _websocket_root() -> str:
    parsed = urlparse(config.LASTMILE_BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


class _RobotOrderWatcher:
    """Connects to /ws/soc/store_<id>/ and discovers ready orders."""

    def __init__(self, store_id: int, recorder: RunRecorder) -> None:
        self.store_id = store_id
        self.recorder = recorder
        self._ready_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

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

    async def get_ready_order(self) -> dict[str, Any]:
        return await self._ready_queue.get()

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
                    console.print(f"[blue]robot_ws:[/] connected /ws/soc/store_{self.store_id}/")
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

        self.recorder.record_websocket(
            source=f"robot_store_orders_{self.store_id}",
            raw=raw,
            payload=payload,
            nested=nested,
            order_db_id=order_db_id,
            order_ref=str(order_ref) if order_ref else None,
            status=str(status),
        )

        if str(status) == "ready":
            self._ready_queue.put_nowait({
                "order_db_id": order_db_id,
                "order_ref": str(order_ref) if order_ref else "",
            })


# ---------------------------------------------------------------------------
# Order operations
# ---------------------------------------------------------------------------

def _order_identity(payload: object) -> tuple[int | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None
    raw = payload.get("data", payload)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return None, None, None
    order_db_id = raw.get("id")
    try:
        order_db_id = int(order_db_id) if order_db_id is not None else None
    except (TypeError, ValueError):
        order_db_id = None
    order_ref = raw.get("order_id")
    status = raw.get("status")
    return order_db_id, str(order_ref) if order_ref is not None else None, str(status) if status else None


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
) -> bool:
    try:
        await request_json(
            client,
            recorder=recorder,
            actor="robot",
            action="patch_status",
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
        console.print(f"[magenta]robot_sim:[/] order={order_db_id} -> {status}")
        return True
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="robot_patch_http_error",
            actor="robot",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"HTTP error patching order {order_db_id} to {status}",
        )
        return False


async def _deliver_order(
    client: httpx.AsyncClient,
    *,
    order: dict,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
) -> None:
    order_db_id = int(order["order_db_id"])
    order_ref = str(order["order_ref"])
    scenario = "load"
    console.print(f"[magenta]robot_sim:[/] Starting delivery for order={order_db_id}")
    for status, (lo, hi) in ROBOT_LIFECYCLE:
        delay = random.uniform(lo, hi)
        console.print(
            f"[dim]robot_sim:[/] order={order_db_id} waiting {delay:.0f}s before -> {status}"
        )
        await asyncio.sleep(delay)
        success = await patch_status(
            client,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=status,
            store_token=store_token,
            token_source=token_source,
            recorder=recorder,
            scenario=scenario,
            step=f"robot_{status}",
        )
        if not success:
            recorder.record_event(
                actor="robot",
                action="delivery_aborted",
                category="terminal",
                scenario=scenario,
                step=f"robot_{status}",
                ok=False,
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status="robot_status_failed",
                details={"failed_status": status},
            )
            return

    recorder.record_event(
        actor="robot",
        action="completed_order",
        category="terminal",
        scenario=scenario,
        step="robot_completed",
        order_db_id=order_db_id,
        order_ref=order_ref,
        observed_status="completed",
    )
    console.print(f"[bold green]robot_sim:[/] order={order_db_id} COMPLETED")


# ---------------------------------------------------------------------------
# Run entrypoint
# ---------------------------------------------------------------------------

async def _run_single(*, recorder: RunRecorder, session: RobotSession) -> None:
    """Run a single robot listener for one store."""
    watcher = _RobotOrderWatcher(session.store_id, recorder)
    await watcher.start()

    console.print(
        f"[bold magenta]robot_sim:[/] Listening for ready orders on "
        f"store_{session.store_id} ..."
    )
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
                code="robot_task_exception",
                actor="robot",
                scenario="load",
                message=f"Robot delivery task failed: {exc}",
            )

    async with httpx.AsyncClient() as client:
        try:
            while True:
                order = await watcher.get_ready_order()
                task = asyncio.create_task(
                    _deliver_order(
                        client,
                        order=order,
                        store_token=session.store_token,
                        token_source=session.token_source,
                        recorder=recorder,
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


async def run(
    *,
    recorder: RunRecorder,
    session: RobotSession | None = None,
    sessions: list[RobotSession] | None = None,
) -> None:
    """Run robot delivery listeners.

    If *sessions* (plural) is provided, launches one listener per store.
    Otherwise falls back to *session* (single) or bootstraps from config.
    """
    if sessions:
        await asyncio.gather(
            *[_run_single(recorder=recorder, session=s) for s in sessions]
        )
        return

    if session is None:
        console.print("[cyan]robot_sim:[/] Bootstrapping auth ...")
        async with httpx.AsyncClient() as bootstrap_client:
            session = await bootstrap_auth(bootstrap_client, recorder)

    await _run_single(recorder=recorder, session=session)
