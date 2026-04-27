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


async def bootstrap_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> StoreSession:
    if not config.STORE_ID:
        raise RuntimeError("STORE_ID is required so fixtures can use a real store profile.")

    last_mile_token, token_source = await fetch_store_token(
        client,
        recorder=recorder,
        scenario=scenario,
    )

    console.print(f"[dim]store:[/] Fetching store profile for store_id={config.STORE_ID} ...")
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
        json_body={"store_id": config.STORE_ID},
        headers={
            "Content-Type": "application/json",
            "Store-Request": str(config.STORE_ID),
        },
    )
    data = api_data(payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Store login response had an invalid shape: {payload}")

    subentity = data.get("subentity")
    if not isinstance(subentity, dict) or not subentity.get("id"):
        raise RuntimeError(f"Store login response did not contain subentity.id: {payload}")

    config.SUBENTITY_ID = int(subentity["id"])
    if subentity.get("currency"):
        config.STORE_CURRENCY = str(subentity["currency"]).lower()

    console.print(
        f"[green]store:[/] Store profile acquired for subentity_id={config.SUBENTITY_ID}."
    )
    return StoreSession(
        last_mile_token=last_mile_token,
        fainzy_token=data.get("token"),
        subentity=subentity,
        store_id=config.SUBENTITY_ID,
        token_source=token_source,
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
