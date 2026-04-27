"""
Store actor.

Responsibilities:
  1. Accept or reject new orders.
  2. Verify when payment has moved the order into store preparation.
  3. Mark orders as ready for robot pickup.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from rich.console import Console

import config
import sim_queue as q
from reporting import RunRecorder
from transport import RequestError, api_data, request_json

console = Console()


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


async def wait_for_status(
    client: httpx.AsyncClient,
    *,
    store_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    action: str,
    expected_statuses: set[str],
    terminal_statuses: set[str] | None = None,
    poll_interval: float,
    max_attempts: int,
    timeout_code: str,
    timeout_message: str,
) -> dict[str, Any] | None:
    terminal_statuses = terminal_statuses or {"rejected", "cancelled", "refunded"}
    console.print(f"[yellow]store_sim:[/] Polling order={order_db_id} for {expected_statuses}")
    for attempt in range(max_attempts):
        await asyncio.sleep(poll_interval)
        try:
            order = await fetch_order(
                client,
                store_token=store_token,
                token_source=token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                scenario=scenario,
                step=step,
                action=action,
                poll_attempt=attempt + 1,
            )
        except RequestError as exc:
            recorder.record_issue(
                severity="warning",
                code=f"{timeout_code}_poll_error",
                actor="store",
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                related_event_id=exc.event["id"] if exc.event else None,
                message=f"Poll attempt {attempt + 1} failed: {exc}",
            )
            continue

        status = str(order.get("status") or "")
        if status in expected_statuses:
            return order
        if status in terminal_statuses:
            return order

    recorder.record_issue(
        severity="error",
        code=timeout_code,
        actor="store",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        message=timeout_message,
    )
    return None


async def _handle_order(
    client: httpx.AsyncClient,
    *,
    order_db_id: int,
    order_ref: str,
    order_total: float,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
) -> None:
    scenario = "load"
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
        await q.terminal_orders_queue.put(
            {"order_db_id": order_db_id, "order_ref": order_ref, "status": "rejected"}
        )
        recorder.record_event(
            actor="store",
            action="rejected_order",
            category="terminal",
            scenario=scenario,
            step="reject_order",
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status="rejected",
            details={"order_total": order_total},
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

    order_state = await wait_for_status(
        client,
        store_token=store_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        recorder=recorder,
        scenario=scenario,
        step="wait_for_order_processing",
        action="wait_for_order_processing",
        expected_statuses={"order_processing"},
        poll_interval=config.ORDER_PROCESSING_POLL_INTERVAL_SECONDS,
        max_attempts=config.ORDER_PROCESSING_POLL_MAX_ATTEMPTS,
        timeout_code="order_processing_timeout",
        timeout_message="Order never reached order_processing after payment",
    )
    if order_state is None:
        await q.terminal_orders_queue.put(
            {
                "order_db_id": order_db_id,
                "order_ref": order_ref,
                "status": "order_processing_timeout",
            }
        )
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

    status = str(order_state.get("status") or "")
    if status in {"rejected", "cancelled", "refunded"}:
        await q.terminal_orders_queue.put(
            {"order_db_id": order_db_id, "order_ref": order_ref, "status": status}
        )
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
        await q.terminal_orders_queue.put(
            {"order_db_id": order_db_id, "order_ref": order_ref, "status": "ready_failed"}
        )
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

    await q.ready_orders_queue.put(
        {
            "order_db_id": order_db_id,
            "order_ref": order_ref,
            "order_total": order_total,
            "scenario": scenario,
        }
    )
    console.print(f"[green]store_sim:[/] order={order_db_id} handed off to robot_sim")


async def run(
    *,
    store_token: str,
    token_source: str,
    recorder: RunRecorder,
) -> None:
    console.print("[bold yellow]store_sim:[/] Waiting for orders ...")
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
                order = await q.placed_orders_queue.get()
                task = asyncio.create_task(
                    _handle_order(
                        client,
                        order_db_id=int(order["order_db_id"]),
                        order_ref=str(order["order_ref"]),
                        order_total=float(order["order_total"]),
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
