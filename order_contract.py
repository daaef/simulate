"""Run-level order lifecycle contract enforcement."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from reporting import RunRecorder
import store_sim
import user_sim

TERMINAL_ORDER_STATUSES = frozenset({"completed", "rejected", "cancelled"})


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_terminal(status: Any) -> bool:
    return _normalized_status(status) in TERMINAL_ORDER_STATUSES


def _allowed_non_terminal_reason(order: dict[str, Any], current_status: str) -> str | None:
    """Return the explicit reason a non-terminal order may remain open."""
    if current_status != "pending":
        return None
    statuses = order.get("statuses") if isinstance(order, dict) else None
    if not isinstance(statuses, list):
        return None
    if any(
        isinstance(item, dict) and str(item.get("scenario") or "") == "place_order"
        for item in statuses
    ):
        return "place_order_pending_seed"
    return None


def _order_identity_ids(order: dict[str, Any]) -> tuple[int | None, int | None]:
    identity = order.get("identity") if isinstance(order, dict) else None
    if not isinstance(identity, dict):
        return None, None
    user = identity.get("user") if isinstance(identity.get("user"), dict) else {}
    store = identity.get("store") if isinstance(identity.get("store"), dict) else {}
    user_id = user.get("id")
    store_id = store.get("subentity_id")
    try:
        parsed_user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        parsed_user_id = None
    try:
        parsed_store_id = int(store_id) if store_id is not None else None
    except (TypeError, ValueError):
        parsed_store_id = None
    return parsed_user_id, parsed_store_id


async def _fetch_order_state(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    order_db_id: int,
    order_ref: str,
    scenario: str,
    step: str,
    user_session: user_sim.UserSession | None,
    store_session: store_sim.StoreSession | None,
) -> str | None:
    if user_session is not None:
        try:
            payload = await user_sim.fetch_order(
                client,
                user_token=user_session.token,
                token_source=user_session.token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                action="cleanup_fetch_order_user",
                scenario=scenario,
                step=step,
            )
            return str(payload.get("status") or "").strip().lower() or None
        except Exception as exc:
            recorder.record_issue(
                severity="warning",
                code="order_contract_fetch_user_failed",
                actor="user",
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                message=f"User-side cleanup fetch failed for order {order_db_id}: {exc}",
            )
    if store_session is not None:
        try:
            payload = await store_sim.fetch_order(
                client,
                store_token=store_session.last_mile_token,
                token_source=store_session.token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                scenario=scenario,
                step=step,
                action="cleanup_fetch_order_store",
            )
            return str(payload.get("status") or "").strip().lower() or None
        except Exception as exc:
            recorder.record_issue(
                severity="warning",
                code="order_contract_fetch_store_failed",
                actor="store",
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                message=f"Store-side cleanup fetch failed for order {order_db_id}: {exc}",
            )
    return None


async def enforce_order_closure(
    *,
    recorder: RunRecorder,
    user_sessions_by_id: dict[int, user_sim.UserSession],
    store_sessions_by_subentity_id: dict[int, store_sim.StoreSession],
    scenario: str = "simulation_cleanup",
    settle_attempts: int = 3,
    settle_interval_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    """Ensure every created order reaches a strict terminal status."""
    unresolved: list[dict[str, Any]] = []
    all_orders = sorted(
        (
            order
            for order in recorder.orders.values()
            if isinstance(order, dict) and order.get("order_db_id") is not None
        ),
        key=lambda item: int(item["order_db_id"]),
    )
    if not all_orders:
        return unresolved

    recorder.record_event(
        actor="contract",
        action="order_contract_guard_started",
        category="contract",
        scenario=scenario,
        step="order_contract_start",
        details={
            "orders_seen": len(all_orders),
            "terminal_statuses": sorted(TERMINAL_ORDER_STATUSES),
            "settle_attempts": settle_attempts,
            "settle_interval_seconds": settle_interval_seconds,
        },
        track_order=False,
    )

    async with httpx.AsyncClient() as client:
        fallback_user_session = next(iter(user_sessions_by_id.values()), None)
        fallback_store_session = next(iter(store_sessions_by_subentity_id.values()), None)
        for order in all_orders:
            order_db_id = int(order["order_db_id"])
            order_ref = str(order.get("order_ref") or f"#{order_db_id}")
            current_status = _normalized_status(order.get("final_status"))
            user_id, store_id = _order_identity_ids(order)
            user_session = user_sessions_by_id.get(user_id) if user_id is not None else None
            store_session = (
                store_sessions_by_subentity_id.get(store_id)
                if store_id is not None
                else None
            )
            user_session = user_session or fallback_user_session
            store_session = store_session or fallback_store_session

            if _is_terminal(current_status):
                continue

            allowed_reason = _allowed_non_terminal_reason(order, current_status)
            if allowed_reason is not None:
                recorder.record_event(
                    actor="contract",
                    action="order_contract_non_terminal_allowed",
                    category="contract",
                    scenario=scenario,
                    step="order_contract_allow_open_order",
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    observed_status=current_status,
                    details={
                        "reason": allowed_reason,
                        "user_id": user_id,
                        "store_subentity_id": store_id,
                    },
                )
                continue

            recorder.record_issue(
                severity="warning",
                code="order_contract_non_terminal_detected",
                actor="contract",
                scenario=scenario,
                step="order_contract_detect_open_order",
                order_db_id=order_db_id,
                order_ref=order_ref,
                message=(
                    f"Order {order_db_id} ended run in non-terminal state "
                    f"({current_status or 'unknown'}); applying cleanup."
                ),
                details={
                    "user_id": user_id,
                    "store_subentity_id": store_id,
                },
            )

            observed = current_status or None
            for attempt in range(1, max(1, int(settle_attempts)) + 1):
                observed = await _fetch_order_state(
                    client,
                    recorder=recorder,
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    scenario=scenario,
                    step=f"order_contract_natural_settle_{attempt}",
                    user_session=user_session,
                    store_session=store_session,
                )
                if _is_terminal(observed):
                    recorder.record_event(
                        actor="contract",
                        action="order_contract_natural_settle_resolved",
                        category="contract",
                        scenario=scenario,
                        step=f"order_contract_natural_settle_{attempt}",
                        order_db_id=order_db_id,
                        order_ref=order_ref,
                        observed_status=observed,
                        details={"attempt": attempt},
                    )
                    break
                if attempt < max(1, int(settle_attempts)):
                    await asyncio.sleep(max(0.1, float(settle_interval_seconds)))

            if _is_terminal(observed):
                continue

            cancel_attempted = False
            if user_session is not None:
                cancel_attempted = True
                await user_sim.cancel_order(
                    client,
                    user_token=user_session.token,
                    token_source=user_session.token_source,
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    recorder=recorder,
                    scenario=scenario,
                    step="order_contract_cleanup_cancel",
                )
                observed = await _fetch_order_state(
                    client,
                    recorder=recorder,
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    scenario=scenario,
                    step="order_contract_post_cancel_check",
                    user_session=user_session,
                    store_session=store_session,
                )
                if _is_terminal(observed):
                    recorder.record_event(
                        actor="contract",
                        action="order_contract_cleanup_resolved",
                        category="contract",
                        scenario=scenario,
                        step="order_contract_post_cancel_check",
                        order_db_id=order_db_id,
                        order_ref=order_ref,
                        observed_status=observed,
                        details={"cleanup_action": "cancel"},
                    )
                    continue

            reject_attempted = False
            if store_session is not None:
                reject_attempted = True
                await store_sim.patch_status(
                    client,
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    status="rejected",
                    store_token=store_session.last_mile_token,
                    token_source=store_session.token_source,
                    recorder=recorder,
                    scenario=scenario,
                    step="order_contract_cleanup_reject",
                    actor="store",
                    action="cleanup_reject_order",
                )
                observed = await _fetch_order_state(
                    client,
                    recorder=recorder,
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    scenario=scenario,
                    step="order_contract_post_reject_check",
                    user_session=user_session,
                    store_session=store_session,
                )
                if _is_terminal(observed):
                    recorder.record_event(
                        actor="contract",
                        action="order_contract_cleanup_resolved",
                        category="contract",
                        scenario=scenario,
                        step="order_contract_post_reject_check",
                        order_db_id=order_db_id,
                        order_ref=order_ref,
                        observed_status=observed,
                        details={"cleanup_action": "reject"},
                    )
                    continue

            unresolved_state = _normalized_status(observed) or current_status or "unknown"
            unresolved.append(
                {
                    "order_db_id": order_db_id,
                    "order_ref": order_ref,
                    "status": unresolved_state,
                    "user_id": user_id,
                    "store_subentity_id": store_id,
                    "cancel_attempted": cancel_attempted,
                    "reject_attempted": reject_attempted,
                }
            )
            recorder.record_issue(
                severity="error",
                code="order_contract_unresolved",
                actor="contract",
                scenario=scenario,
                step="order_contract_unresolved",
                order_db_id=order_db_id,
                order_ref=order_ref,
                message=(
                    f"Order {order_db_id} remained non-terminal after cleanup "
                    f"({unresolved_state})."
                ),
                details=unresolved[-1],
            )

    recorder.record_event(
        actor="contract",
        action="order_contract_guard_finished",
        category="contract",
        scenario=scenario,
        step="order_contract_finish",
        details={
            "orders_seen": len(all_orders),
            "unresolved_orders": len(unresolved),
            "terminal_statuses": sorted(TERMINAL_ORDER_STATUSES),
        },
        track_order=False,
    )
    return unresolved
