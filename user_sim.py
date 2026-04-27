"""
User actor.

Responsibilities:
  1. Place orders from the user side.
  2. Observe store or backend status changes from the user side.
  3. Complete payment or cancel the order when a scenario requires it.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from rich.console import Console

import config
import sim_queue as q
import seed
import stripe_sim
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


async def place_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    worker_id: int,
    fixtures: seed.SimulationFixtures,
    recorder: RunRecorder,
    scenario: str = "load",
    step: str = "place_order",
    enqueue: bool = True,
) -> dict[str, Any] | None:
    payload = seed.generate_order_payload(fixtures)
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
        await q.terminal_orders_queue.put(
            {"order_db_id": None, "order_ref": order_ref, "status": "placement_failed"}
        )
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
        await q.terminal_orders_queue.put(
            {"order_db_id": None, "order_ref": order_ref, "status": "placement_failed"}
        )
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
    order = {
        "order_db_id": int(order_db_id),
        "order_ref": str(returned_ref),
        "order_total": float(order_total),
        "scenario": scenario,
    }
    if enqueue:
        await q.placed_orders_queue.put(order)
    return order


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


async def wait_for_status(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    expected_statuses: set[str],
    terminal_statuses: set[str] | None = None,
    scenario: str = "load",
    step: str,
    action: str,
    poll_interval: float,
    max_attempts: int,
    timeout_code: str,
    timeout_message: str,
) -> dict[str, Any] | None:
    terminal_statuses = terminal_statuses or {"rejected", "cancelled", "refunded"}
    for attempt in range(max_attempts):
        await asyncio.sleep(poll_interval)
        try:
            order = await fetch_order(
                client,
                user_token=user_token,
                token_source=token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                action=action,
                scenario=scenario,
                step=step,
                poll_attempt=attempt + 1,
            )
        except RequestError as exc:
            recorder.record_issue(
                severity="warning",
                code=f"{timeout_code}_poll_error",
                actor="user",
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
        actor="user",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        message=timeout_message,
    )
    return None


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
) -> bool:
    order_db_id = int(order["order_db_id"])
    order_ref = str(order["order_ref"])
    scenario = str(order.get("scenario") or "load")
    order_state = await wait_for_status(
        client,
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        recorder=recorder,
        expected_statuses={"payment_processing"},
        scenario=scenario,
        step="wait_for_store_decision",
        action="wait_for_store_decision",
        poll_interval=config.USER_DECISION_POLL_INTERVAL_SECONDS,
        max_attempts=config.USER_DECISION_POLL_MAX_ATTEMPTS,
        timeout_code="store_decision_timeout",
        timeout_message="Timed out waiting for store accept/reject decision",
    )
    if order_state is None:
        await q.terminal_orders_queue.put(
            {
                "order_db_id": order_db_id,
                "order_ref": order_ref,
                "status": "store_decision_timeout",
            }
        )
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

    status = str(order_state.get("status") or "")
    if status in {"rejected", "cancelled", "refunded"}:
        await q.terminal_orders_queue.put(
            {"order_db_id": order_db_id, "order_ref": order_ref, "status": status}
        )
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
        await q.terminal_orders_queue.put(
            {
                "order_db_id": order_db_id,
                "order_ref": order_ref,
                "status": "payment_failed",
            }
        )
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
    return True


async def _worker(
    user_token: str,
    token_source: str,
    worker_id: int,
    fixtures: seed.SimulationFixtures,
    recorder: RunRecorder,
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
                await handle_order_payment(
                    client,
                    user_token=user_token,
                    token_source=token_source,
                    order=order,
                    recorder=recorder,
                )

            if work_queue is not None:
                work_queue.task_done()
                if work_queue.empty():
                    return

            jitter = random.uniform(0.8, 1.2)
            await asyncio.sleep(config.ORDER_INTERVAL_SECONDS * jitter)


async def run(
    *,
    user_token: str,
    token_source: str,
    fixtures: seed.SimulationFixtures,
    recorder: RunRecorder,
) -> None:
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

    workers = [
        asyncio.create_task(
            _worker(user_token, token_source, i + 1, fixtures, recorder, work_queue)
        )
        for i in range(config.N_USERS)
    ]
    await asyncio.gather(*workers)
