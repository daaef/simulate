"""Post-order user actions from the real app sessions."""

from __future__ import annotations

from typing import Any

import httpx
from rich.console import Console

import config
from reporting import RunRecorder
from transport import HttpResult, RequestError, request_json

console = Console()


def receipt_endpoint(order_db_id: int) -> str:
    return f"/v1/core/generate-receipt/{order_db_id}/"


def reorder_params(order_db_id: int) -> dict[str, str]:
    return {"order_id": str(order_db_id)}


def build_review_payload(
    *,
    order_db_id: int,
    subentity: dict[str, Any],
    rating: int,
    comment: str,
) -> dict[str, Any]:
    subentity_id = subentity.get("id") or config.SUBENTITY_ID
    return {
        "subentity_id": str(subentity_id),
        "comment": comment,
        "rating": rating,
        "order": order_db_id,
        "subentity_metadata": subentity,
    }


async def _safe_action(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    actor: str,
    action: str,
    method: str,
    endpoint: str,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    scenario: str,
    step: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> HttpResult | None:
    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor=actor,
            action=action,
            category="post_order",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            method=method,
            url=f"{config.LASTMILE_BASE_URL}{endpoint}",
            endpoint=endpoint,
            params=params,
            json_body=json_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {user_token}",
            },
            auth_header_name="Authorization",
            auth_token=user_token,
            auth_source=token_source,
            auth_scheme="Token",
            track_order=False,
        )
        console.print(
            f"[green]post_order:[/] {action} completed for order {order_ref}."
        )
        return result
    except RequestError as exc:
        console.print(
            f"[yellow]post_order:[/] {action} failed for order {order_ref}: {exc}"
        )
        recorder.record_issue(
            severity="warning",
            code=f"{action}_failed",
            actor=actor,
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"Post-order action {action} failed for order {order_db_id}",
        )
    return None


async def generate_receipt(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    scenario: str,
) -> HttpResult | None:
    return await _safe_action(
        client,
        recorder=recorder,
        actor="user",
        action="generate_receipt",
        method="GET",
        endpoint=receipt_endpoint(order_db_id),
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        scenario=scenario,
        step="generate_receipt",
    )


async def submit_review(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    subentity: dict[str, Any],
    scenario: str,
    rating: int | None = None,
    comment: str | None = None,
) -> HttpResult | None:
    body = build_review_payload(
        order_db_id=order_db_id,
        subentity=subentity,
        rating=rating if rating is not None else config.SIM_REVIEW_RATING,
        comment=comment if comment is not None else config.SIM_REVIEW_COMMENT,
    )
    return await _safe_action(
        client,
        recorder=recorder,
        actor="user",
        action="submit_review",
        method="POST",
        endpoint="/v1/core/reviews/",
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        scenario=scenario,
        step="submit_review",
        json_body=body,
    )


async def fetch_reorder(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    scenario: str,
) -> HttpResult | None:
    return await _safe_action(
        client,
        recorder=recorder,
        actor="user",
        action="fetch_reorder",
        method="GET",
        endpoint="/v1/core/reorder/",
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        scenario=scenario,
        step="fetch_reorder",
        params=reorder_params(order_db_id),
    )


async def run_post_order_actions(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    subentity: dict[str, Any],
    scenario: str,
) -> None:
    if not config.SIM_RUN_POST_ORDER_ACTIONS:
        console.print(
            f"[dim]post_order:[/] Skipping receipt/review/reorder for order {order_ref}."
        )
        recorder.record_event(
            actor="user",
            action="post_order_actions_skipped",
            category="post_order",
            scenario=scenario,
            order_db_id=order_db_id,
            order_ref=order_ref,
            details={"reason": "SIM_RUN_POST_ORDER_ACTIONS=false"},
            track_order=False,
        )
        return
    console.print(f"[cyan]post_order:[/] Generating receipt for order {order_ref} ...")
    await generate_receipt(
        client,
        recorder=recorder,
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        scenario=scenario,
    )
    console.print(
        f"[cyan]post_order:[/] Submitting review for order {order_ref} "
        f"(rating={config.SIM_REVIEW_RATING}) ..."
    )
    await submit_review(
        client,
        recorder=recorder,
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        subentity=subentity,
        scenario=scenario,
    )
    console.print(f"[cyan]post_order:[/] Fetching reorder data for order {order_ref} ...")
    await fetch_reorder(
        client,
        recorder=recorder,
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        scenario=scenario,
    )
