"""Stripe sandbox payment support for the simulator."""

from __future__ import annotations

import base64
from typing import Any

import httpx
from rich.console import Console

import config
from reporting import RunRecorder
from transport import RequestError, api_data, request_json

console = Console()


def _payment_intent_id(client_secret: str) -> str:
    if "_secret_" not in client_secret:
        raise RuntimeError(f"Invalid Stripe client_secret shape: {client_secret[:12]}...")
    return client_secret.split("_secret_", 1)[0]


def _basic_auth_header(secret_key: str) -> str:
    token = base64.b64encode(f"{secret_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


async def create_payment_intent(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_ref: str,
    order_db_id: int,
    amount: float,
    recorder: RunRecorder,
    scenario: str,
    step: str,
) -> dict[str, Any]:
    if amount <= 0:
        raise RuntimeError(
            "SIM_PAYMENT_MODE=stripe requires a positive order total. "
            "Use SIM_PAYMENT_MODE=free for zero-total coupon orders."
        )

    body: dict[str, Any] = {
        "currency": config.STORE_CURRENCY,
        "amount": round(amount),
        "order_id": order_ref,
        "payment_method_types": "card",
        "subentity_id": config.SUBENTITY_ID,
        "save_card": config.SIM_SAVE_CARD,
    }
    if config.SIM_COUPON_ID is not None:
        body["coupon"] = config.SIM_COUPON_ID

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor="user",
            action="create_payment_intent",
            category="payment",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            method="POST",
            url=f"{config.LASTMILE_BASE_URL}/v1/core/create/payment-intent/",
            endpoint="/v1/core/create/payment-intent/",
            json_body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {user_token}",
            },
            auth_header_name="Authorization",
            auth_token=user_token,
            auth_source=token_source,
            auth_scheme="Token",
            details={
                "amount": round(amount),
                "currency": config.STORE_CURRENCY,
                "payment_method": config.STRIPE_TEST_PAYMENT_METHOD,
            },
        )
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="payment_intent_http_error",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message="HTTP error creating payment intent",
        )
        raise

    payload = api_data(result.payload)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Payment intent response had invalid shape: {payload}")
    if not payload.get("client_secret"):
        raise RuntimeError(f"Payment intent response lacked client_secret: {payload}")
    return payload


async def confirm_payment_intent(
    client: httpx.AsyncClient,
    *,
    intent_data: dict[str, Any],
    order_ref: str,
    order_db_id: int,
    recorder: RunRecorder,
    scenario: str,
    step: str,
) -> bool:
    client_secret = str(intent_data["client_secret"])
    payment_intent_id = _payment_intent_id(client_secret)
    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor="user",
            action="confirm_stripe_payment",
            category="payment",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            method="POST",
            url=f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm",
            endpoint=f"/v1/payment_intents/{payment_intent_id}/confirm",
            data_body={"payment_method": config.STRIPE_TEST_PAYMENT_METHOD},
            headers={"Authorization": _basic_auth_header(config.STRIPE_SECRET_KEY)},
            auth_header_name="Authorization",
            auth_token=config.STRIPE_SECRET_KEY,
            auth_source="stripe_secret_key",
            auth_scheme="Basic",
            details={"payment_method": config.STRIPE_TEST_PAYMENT_METHOD},
        )
    except RequestError as exc:
        recorder.record_issue(
            severity="error",
            code="stripe_confirm_http_error",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message="Stripe confirm returned an error response",
        )
        return False

    payload = result.payload if isinstance(result.payload, dict) else {}
    status = str(payload.get("status") or "")
    ok = status in {"succeeded", "processing", "requires_capture"}
    if not ok:
        recorder.record_issue(
            severity="error",
            code="stripe_payment_not_successful",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=result.event["id"],
            message=f"Stripe payment ended with status {status or 'unknown'}",
            details={"stripe_status": status},
        )
    return ok


async def pay_order(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_ref: str,
    order_db_id: int,
    amount: float,
    recorder: RunRecorder,
    scenario: str,
    step: str,
) -> bool:
    try:
        intent_data = await create_payment_intent(
            client,
            user_token=user_token,
            token_source=token_source,
            order_ref=order_ref,
            order_db_id=order_db_id,
            amount=amount,
            recorder=recorder,
            scenario=scenario,
            step=f"{step}_create_intent",
        )
    except Exception as exc:
        recorder.record_issue(
            severity="error",
            code="payment_intent_failed",
            actor="user",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            message=f"Payment intent creation failed: {exc}",
        )
        return False
    return await confirm_payment_intent(
        client,
        intent_data=intent_data,
        order_ref=order_ref,
        order_db_id=order_db_id,
        recorder=recorder,
        scenario=scenario,
        step=f"{step}_confirm_intent",
    )
