"""
Robot actor.

Responsibilities:
  1. Move ready orders through robot-owned statuses.
  2. Mark the order as completed when delivery finishes.
"""

from __future__ import annotations

import asyncio
import random

import httpx
from rich.console import Console

import config
import sim_queue as q
from reporting import RunRecorder
from transport import RequestError, request_json

console = Console()

ROBOT_LIFECYCLE = [
    ("enroute_pickup", (20, 60)),
    ("robot_arrived_for_pickup", (5, 20)),
    ("enroute_delivery", (30, 120)),
    ("robot_arrived_for_delivery", (5, 20)),
    ("completed", (2, 8)),
]


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
    scenario = str(order.get("scenario") or "load")
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
            await q.terminal_orders_queue.put(
                {
                    "order_db_id": order_db_id,
                    "order_ref": order_ref,
                    "status": "robot_status_failed",
                }
            )
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

    await q.terminal_orders_queue.put(
        {"order_db_id": order_db_id, "order_ref": order_ref, "status": "completed"}
    )
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


async def run(
    *,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
) -> None:
    console.print("[bold magenta]robot_sim:[/] Waiting for ready orders ...")
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
                order = await q.ready_orders_queue.get()
                task = asyncio.create_task(
                    _deliver_order(
                        client,
                        order=order,
                        store_token=store_token,
                        token_source=token_source,
                        recorder=recorder,
                    )
                )
                tasks.add(task)
                task.add_done_callback(_finish_task)
        finally:
            pending = list(tasks)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
