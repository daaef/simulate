"""
Deterministic trace-mode orchestration.

Bootstraps its own auth and fixtures via user_sim / store_sim modules,
then drives each scenario step-by-step using polling for verification.
"""

from __future__ import annotations

import asyncio

import httpx
from rich.console import Console

import config
import app_probes
from interaction_catalog import (
    MENU_AVAILABLE,
    MENU_SOLD_OUT,
    MENU_UNAVAILABLE,
    menu_action_block_reason,
)
import robot_sim
import post_order_actions
from reporting import RunRecorder
from scenarios import TimingProfile, resolve_timing_profile, resolve_trace_scenarios
import store_sim
import stripe_sim
from transport import traced_sleep
import user_sim
from websocket_observer import WebsocketObserver

console = Console()

FIXTURE_REQUIRED_SCENARIOS = {
    "completed",
    "rejected",
    "cancelled",
    "auto_cancel",
    "new_user_setup",
    "returning_paid_no_coupon",
    "returning_paid_with_coupon",
    "returning_free_with_coupon",
    "menu_available",
    "menu_unavailable",
    "menu_sold_out",
    "menu_store_closed",
    "store_accept",
    "store_reject",
    "robot_complete",
    "app_bootstrap",
    "receipt_review_reorder",
}


def _trace_requires_fixtures(scenarios: list[str]) -> bool:
    return any(name in FIXTURE_REQUIRED_SCENARIOS for name in scenarios)


def _trace_store_candidates() -> list[str | None]:
    actors = getattr(config, "SIM_ACTORS", {}) or {}
    actor_store_ids: list[str] = []
    for store in actors.get("stores", []):
        if not isinstance(store, dict):
            continue
        store_id = store.get("store_id")
        if store_id and str(store_id) not in actor_store_ids:
            actor_store_ids.append(str(store_id))

    if not actor_store_ids:
        raise RuntimeError(
            "No stores were found in the selected plan. "
            "All trace runs now require store selection from plan stores only."
        )

    if config.SIM_STORE_EXPLICIT:
        explicit_store = config.STORE_ID or ""
        if explicit_store not in actor_store_ids:
            raise RuntimeError(
                f"Explicit store {explicit_store!r} is not present in the selected plan stores."
            )
        return [explicit_store]

    return actor_store_ids


async def _bootstrap_store_auth(
    client: httpx.AsyncClient,
    recorder: RunRecorder,
    *,
    store_id: str | None,
) -> store_sim.StoreSession:
    if store_id is None:
        return await store_sim.bootstrap_auth(client, recorder)
    try:
        return await store_sim.bootstrap_auth(client, recorder, store_id=store_id)
    except TypeError as exc:
        if "store_id" not in str(exc):
            raise
        return await store_sim.bootstrap_auth(client, recorder)


async def _bootstrap_trace_store_context(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    recorder: RunRecorder,
    resolved: list[str],
) -> tuple[store_sim.StoreSession, user_sim.UserFixtures | None, bool, int | None]:
    requires_fixtures = _trace_requires_fixtures(resolved)
    should_preflight = "store_first_setup" in resolved or (
        store_sim.provisioning_preflight_enabled() and requires_fixtures
    )
    last_error: RuntimeError | None = None
    candidates = _trace_store_candidates()

    for candidate in candidates:
        store_session: store_sim.StoreSession | None = None
        original_store_status: int | None = None
        try:
            store_session = await _bootstrap_store_auth(
                client,
                recorder,
                store_id=candidate,
            )
            setup_ran = False
            if should_preflight:
                original_store_status = await _run_store_first_setup(
                    client,
                    store_session=store_session,
                    recorder=recorder,
                )
                setup_ran = True

            fixtures = None
            if requires_fixtures:
                fixtures = await user_sim.bootstrap_fixtures(
                    client,
                    session=user_session,
                    store_token=store_session.last_mile_token,
                    subentity=store_session.subentity,
                    recorder=recorder,
                    subentity_id=store_session.store_id,
                )
                recorder.set_fixtures(fixtures)

            config.SUBENTITY_ID = store_session.store_id
            if store_session.store_login_id:
                config.STORE_ID = store_session.store_login_id
            recorder.record_event(
                actor="trace",
                action="auto_select_store",
                category="ui_flow",
                scenario="bootstrap",
                step="auto_select_store",
                details={
                    "candidate_count": len(candidates),
                    "requested_store_id": candidate,
                    "selected_store_id": store_session.store_login_id or candidate,
                    "subentity_id": store_session.store_id,
                    "explicit_store": config.SIM_STORE_EXPLICIT,
                },
                track_order=False,
            )
            console.print(
                f"[green]trace:[/] Selected store "
                f"{store_session.store_login_id or candidate or store_session.store_id} "
                f"(subentity_id={store_session.store_id})."
            )
            return store_session, fixtures, setup_ran, original_store_status
        except RuntimeError as exc:
            if store_session is not None and original_store_status is not None:
                try:
                    await store_sim.restore_store_status(
                        client,
                        session=store_session,
                        original_status=original_store_status,
                        recorder=recorder,
                        scenario="bootstrap_cleanup",
                    )
                except Exception as cleanup_exc:
                    recorder.record_issue(
                        severity="warning",
                        code="store_status_restore_failed",
                        actor="store",
                        scenario="bootstrap_cleanup",
                        step="restore_store_status",
                        message=(
                            "Store candidate cleanup could not restore status: "
                            f"{cleanup_exc}"
                        ),
                    )
            last_error = exc
            recorder.record_issue(
                severity="error" if config.SIM_STORE_EXPLICIT else "warning",
                code="store_candidate_unusable",
                actor="trace",
                scenario="bootstrap",
                step="auto_select_store",
                message=f"Store candidate {candidate or config.STORE_ID or 'default'} could not be used: {exc}",
            )
            if config.SIM_STORE_EXPLICIT:
                raise
            console.print(
                f"[yellow]trace:[/] Store {candidate or 'default'} could not be used: {exc}"
            )

    raise RuntimeError(
        "No usable store candidate could serve this simulation."
        + (f" Last error: {last_error}" if last_error else "")
    )


def _poll_interval(profile: TimingProfile, default_seconds: float) -> float:
    if profile.name == "fast":
        return min(default_seconds, 0.25)
    return default_seconds


def _poll_attempts(profile: TimingProfile, default_attempts: int) -> int:
    if profile.name == "fast":
        return max(default_attempts, 60)
    return default_attempts


async def _poll_for_status(
    client: httpx.AsyncClient,
    *,
    token: str,
    token_source: str,
    auth_header: str,
    auth_scheme: str,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    actor: str,
    expected_statuses: set[str],
    terminal_statuses: set[str] | None = None,
    scenario: str,
    step: str,
    action: str,
    poll_interval: float,
    max_attempts: int,
    timeout_code: str,
    timeout_message: str,
) -> dict | None:
    from transport import RequestError, api_data, request_json

    terminal_statuses = terminal_statuses or {"rejected", "cancelled", "refunded"}

    def _order_identity(payload):
        from transport import api_data as _ad
        raw = _ad(payload)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        if not isinstance(raw, dict):
            return None, None, None
        oid = raw.get("id")
        try:
            oid = int(oid) if oid is not None else None
        except (TypeError, ValueError):
            oid = None
        oref = raw.get("order_id")
        st = raw.get("status")
        return oid, str(oref) if oref is not None else None, str(st) if st else None

    for attempt in range(max_attempts):
        await asyncio.sleep(poll_interval)
        try:
            result = await request_json(
                client,
                recorder=recorder,
                actor=actor,
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
                    auth_header: f"{auth_scheme} {token}" if auth_scheme else token,
                },
                auth_header_name=auth_header,
                auth_token=token,
                auth_source=token_source,
                auth_scheme=auth_scheme if auth_scheme else None,
                response_order_info=_order_identity,
                poll_attempt=attempt + 1,
            )
        except RequestError as exc:
            recorder.record_issue(
                severity="warning",
                code=f"{timeout_code}_poll_error",
                actor=actor,
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                related_event_id=exc.event["id"] if exc.event else None,
                message=f"Poll attempt {attempt + 1} failed: {exc}",
            )
            continue

        raw = api_data(result.payload)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "")
        if status in expected_statuses:
            return raw
        if status in terminal_statuses:
            return raw

    recorder.record_issue(
        severity="error",
        code=timeout_code,
        actor=actor,
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        message=timeout_message,
    )
    return None


async def _verify_receive_code(
    client: httpx.AsyncClient,
    *,
    user_token: str,
    token_source: str,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    scenario: str,
) -> None:
    order = await user_sim.fetch_order(
        client,
        user_token=user_token,
        token_source=token_source,
        order_db_id=order_db_id,
        order_ref=order_ref,
        recorder=recorder,
        action="verify_receive_code",
        scenario=scenario,
        step="verify_receive_code",
    )
    code = str(order.get("code") or "")
    if code:
        recorder.record_event(
            actor="user",
            action="receive_code_available",
            category="ui_proof",
            scenario=scenario,
            step="verify_receive_code",
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status=str(order.get("status") or ""),
            details={"code_length": len(code)},
        )
        return
    recorder.record_issue(
        severity="error",
        code="receive_code_missing",
        actor="user",
        scenario=scenario,
        step="verify_receive_code",
        order_db_id=order_db_id,
        order_ref=order_ref,
        message="Order did not expose a receive code at robot_arrived_for_delivery.",
    )


def _finish_checked(
    recorder: RunRecorder,
    scenario: str,
    *,
    actual_final_status: str | None,
    order_db_id: int | None = None,
    order_ref: str | None = None,
    note: str | None = None,
) -> None:
    expected = (recorder.scenarios.get(scenario) or {}).get("expected_final_status")
    verdict = "passed" if expected is None or actual_final_status == expected else "blocked"
    recorder.finish_scenario(
        scenario,
        verdict=verdict,
        actual_final_status=actual_final_status,
        order_db_id=order_db_id,
        order_ref=order_ref,
        note=note,
    )


def _save_payment_config() -> tuple[str, int | None, float, str, dict | None]:
    return (
        config.SIM_PAYMENT_MODE,
        config.SIM_COUPON_ID,
        config.SIM_FREE_ORDER_AMOUNT,
        config.SIM_PAYMENT_CASE,
        config.SIM_SELECTED_COUPON,
    )


def _restore_payment_config(saved: tuple[str, int | None, float, str, dict | None]) -> None:
    (
        config.SIM_PAYMENT_MODE,
        config.SIM_COUPON_ID,
        config.SIM_FREE_ORDER_AMOUNT,
        config.SIM_PAYMENT_CASE,
        config.SIM_SELECTED_COUPON,
    ) = saved


def _fixture_order_estimate(fixtures: user_sim.UserFixtures) -> float | None:
    totals: list[float] = []
    for item in fixtures.menu_items:
        if not isinstance(item, dict):
            continue
        discount_price = item.get("discount_price")
        price = item.get("price")
        try:
            value = float(discount_price) if discount_price not in {None, "", 0, 0.0} else float(price)
        except (TypeError, ValueError):
            continue
        if value > 0:
            totals.append(value)
    return min(totals) if totals else None


async def _ensure_coupon_for_scenario(
    client: httpx.AsyncClient,
    *,
    scenario: str,
    user_session: user_sim.UserSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
) -> bool:
    if scenario not in {"returning_paid_with_coupon", "returning_free_with_coupon"}:
        config.SIM_SELECTED_COUPON = None
        return True
    if config.SIM_COUPON_ID is not None:
        return True
    if not config.SIM_AUTO_SELECT_COUPON:
        return False

    order_total = _fixture_order_estimate(fixtures)
    coupons = await app_probes.fetch_user_coupons(
        client,
        recorder=recorder,
        user_token=user_session.token,
        token_source=user_session.token_source,
        scenario=scenario,
    )
    selected = app_probes.select_coupon(
        coupons,
        order_total=order_total,
        prefer_covering=scenario == "returning_free_with_coupon",
    )
    if selected is None:
        recorder.record_issue(
            severity="error",
            code="coupon_unavailable",
            actor="user",
            scenario=scenario,
            step="checkout_coupon",
            message="No valid coupon was returned for this coupon flow.",
        )
        return False

    config.SIM_COUPON_ID = int(selected["id"])
    config.SIM_SELECTED_COUPON = selected
    recorder.record_event(
        actor="user",
        action="select_coupon",
        category="ui_flow",
        scenario=scenario,
        step="checkout_coupon",
        details={
            "coupon_id": config.SIM_COUPON_ID,
            "coupon_code": selected.get("code"),
            "order_total_estimate": order_total,
            "auto_selected": True,
        },
        track_order=False,
    )
    console.print(
        f"[green]user:[/] Selected coupon {selected.get('code') or config.SIM_COUPON_ID} "
        f"for {scenario}."
    )
    return True


def _payment_mode_for_order(order_total: float) -> str:
    if config.SIM_PAYMENT_MODE == "free":
        return "free"
    if (
        config.SIM_PAYMENT_CASE in {"paid_with_coupon", "free_with_coupon"}
        and config.SIM_COUPON_ID is not None
        and isinstance(config.SIM_SELECTED_COUPON, dict)
        and app_probes.coupon_discount_amount(config.SIM_SELECTED_COUPON, order_total)
        >= order_total
    ):
        return "free"
    return config.SIM_PAYMENT_MODE


def _print_checkout_decision(
    *,
    order_ref: str,
    payment_mode: str,
    payment_case: str,
    coupon_id: int | None,
    save_card: bool,
) -> None:
    coupon_label = coupon_id if coupon_id is not None else "none"
    console.print(
        f"[cyan]user:[/] Checkout decision for order {order_ref}: "
        f"route={payment_mode}, case={payment_case}, coupon={coupon_label}, "
        f"save_card={str(save_card).lower()}"
    )


def _gate_failure_code(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("websocket_gate_source_unavailable:"):
        return "websocket_gate_source_unavailable"
    if message.startswith("websocket_gate_timeout:"):
        return "websocket_gate_timeout"
    return "websocket_gate_failed"


async def _wait_for_ws_gate(
    observer: WebsocketObserver,
    *,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    order_db_id: int,
    order_ref: str,
    expected_status: str,
    sources: set[str],
    phase: str,
) -> bool:
    try:
        event = await observer.wait_for_order_status(
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=expected_status,
            sources=sources,
        )
    except RuntimeError as exc:
        if not config.SIM_ENFORCE_WEBSOCKET_GATES:
            recorder.record_issue(
                severity="warning",
                code=_gate_failure_code(exc),
                actor="websocket",
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                message=(
                    f"Websocket gate bypassed for status={expected_status}: {exc}"
                ),
                details={"sources": sorted(sources), "enforced": False},
            )
            recorder.record_event(
                actor="websocket",
                action="websocket_gate_bypassed",
                category="websocket_gate",
                scenario=scenario,
                step=step,
                order_db_id=order_db_id,
                order_ref=order_ref,
                observed_status=expected_status,
                details={
                    "sources": sorted(sources),
                    "reason": str(exc),
                    "enforced": False,
                },
            )
            return True
        recorder.record_issue(
            severity="error",
            code=_gate_failure_code(exc),
            actor="websocket",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            message=(
                f"Websocket gate failed for status={expected_status}: {exc}"
            ),
            details={"sources": sorted(sources), "enforced": True},
        )
        _finish_checked(
            recorder,
            scenario,
            actual_final_status=_gate_failure_code(exc),
            order_db_id=order_db_id,
            order_ref=order_ref,
            note=f"Websocket gate failed at step={step}",
        )
        return False

    recorder.record_event(
        actor="websocket",
        action=(
            "websocket_gate_precondition_ok"
            if phase == "precondition"
            else "websocket_gate_result_ok"
        ),
        category="websocket_gate",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        observed_status=expected_status,
        details={
            "source": event.get("source"),
            "sources": sorted(sources),
        },
    )
    return True


async def _run_completed(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
    scenario: str = "completed",
) -> None:
    recorder.start_scenario(scenario, expected_final_status="completed")
    order = await user_sim.place_order(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        worker_id=1,
        fixtures=fixtures,
        recorder=recorder,
        scenario=scenario,
        step="place_order",
    )
    if order is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
            note="Order could not be created.",
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_pending_before_store_decision",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="pending",
        sources={"store_orders"},
        phase="precondition",
    ):
        return

    recorder.record_event(
        actor="store",
        action="pending_order_actions_available",
        category="ui_gate",
        scenario=scenario,
        step="pending_order_actions",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        observed_status="pending",
        details={"allowed": ["accept", "reject"], "ready_allowed": False},
    )

    await traced_sleep(
        timing.store_decision_delay.pick(),
        recorder=recorder,
        actor="store",
        action="simulate_store_decision_delay",
        scenario=scenario,
        step="accept_order_delay",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )
    accepted = await store_sim.patch_status(
        client,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        status="payment_processing",
        store_token=store_session.last_mile_token,
        token_source=store_session.token_source,
        recorder=recorder,
        scenario=scenario,
        step="accept_order",
    )
    if not accepted:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="accept_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_payment_processing_before_checkout",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="payment_processing",
        sources={"user_orders", "store_orders"},
        phase="result",
    ):
        return

    recorder.record_event(
        actor="store",
        action="ready_blocked_before_payment",
        category="ui_gate",
        scenario=scenario,
        step="payment_processing_gate",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        observed_status="payment_processing",
        details={"ready_allowed": False},
    )

    payment_mode = _payment_mode_for_order(float(order["order_total"]))
    recorder.record_event(
        actor="user",
        action="select_checkout_payment_case",
        category="ui_flow",
        scenario=scenario,
        step="checkout_payment_case",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        details={
            "payment_mode": payment_mode,
            "payment_case": config.SIM_PAYMENT_CASE,
            "coupon_id": config.SIM_COUPON_ID,
            "save_card": config.SIM_SAVE_CARD,
            "stripe_expected": payment_mode == "stripe",
            "free_order_expected": payment_mode == "free",
        },
    )
    _print_checkout_decision(
        order_ref=order["order_ref"],
        payment_mode=payment_mode,
        payment_case=config.SIM_PAYMENT_CASE,
        coupon_id=config.SIM_COUPON_ID,
        save_card=config.SIM_SAVE_CARD,
    )

    if payment_mode == "stripe":
        paid = await stripe_sim.pay_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_ref=order["order_ref"],
            order_db_id=order["order_db_id"],
            amount=float(order["order_total"]),
            recorder=recorder,
            scenario=scenario,
            step="complete_payment",
        )
    else:
        paid = await user_sim.complete_free_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_ref=order["order_ref"],
            order_db_id=order["order_db_id"],
            recorder=recorder,
            scenario=scenario,
            step="complete_free_order",
        )
    if not paid:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="payment_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_order_processing_before_ready",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="order_processing",
        sources={"store_orders", "user_orders"},
        phase="result",
    ):
        return

    recorder.record_event(
        actor="store",
        action="ready_allowed_after_payment",
        category="ui_gate",
        scenario=scenario,
        step="order_processing_gate",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        observed_status="order_processing",
        details={"ready_allowed": True},
    )

    await traced_sleep(
        timing.store_prep_delay.pick(),
        recorder=recorder,
        actor="store",
        action="simulate_store_prep_delay",
        scenario=scenario,
        step="mark_ready_delay",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )
    ready = await store_sim.patch_status(
        client,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        status="ready",
        store_token=store_session.last_mile_token,
        token_source=store_session.token_source,
        recorder=recorder,
        scenario=scenario,
        step="mark_ready",
    )
    if not ready:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="ready_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return
    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_ready_before_robot_lifecycle",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="ready",
        sources={"store_orders"},
        phase="result",
    ):
        return

    previous_status = "ready"
    for status, _ in robot_sim.ROBOT_LIFECYCLE:
        if not await _wait_for_ws_gate(
            observer,
            recorder=recorder,
            scenario=scenario,
            step=f"wait_{previous_status}_before_{status}_api",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            expected_status=previous_status,
            sources={"store_orders"},
            phase="precondition",
        ):
            return
        await traced_sleep(
            timing.robot_delay(status),
            recorder=recorder,
            actor="robot",
            action=f"simulate_{status}_delay",
            scenario=scenario,
            step=f"{status}_delay",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        success = await robot_sim.patch_status(
            client,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            status=status,
            store_token=store_session.last_mile_token,
            token_source=store_session.token_source,
            recorder=recorder,
            scenario=scenario,
            step=f"robot_{status}",
        )
        if not success:
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="robot_status_failed",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
            )
            return
        if not await _wait_for_ws_gate(
            observer,
            recorder=recorder,
            scenario=scenario,
            step=f"wait_{status}_before_next_action",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            expected_status=status,
            sources={"store_orders"},
            phase="result",
        ):
            return
        previous_status = status
        if status == "robot_arrived_for_delivery":
            await _verify_receive_code(
                client,
                user_token=user_session.token,
                token_source=user_session.token_source,
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                recorder=recorder,
                scenario=scenario,
            )

    final_state = await _poll_for_status(
        client,
        token=user_session.token,
        token_source=user_session.token_source,
        auth_header="Authorization",
        auth_scheme="Token",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        actor="user",
        expected_statuses={"completed"},
        scenario=scenario,
        step="verify_completed",
        action="verify_completed",
        poll_interval=_poll_interval(timing, 1.0),
        max_attempts=_poll_attempts(timing, 30),
        timeout_code="trace_completed_timeout",
        timeout_message="Order never reached completed in trace mode.",
    )
    actual_final_status = (
        str(final_state.get("status") or "completed_timeout")
        if final_state
        else "completed_timeout"
    )
    if actual_final_status == "completed" and config.SIM_RUN_POST_ORDER_ACTIONS:
        await post_order_actions.run_post_order_actions(
            client,
            recorder=recorder,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            subentity=fixtures.store,
            scenario=scenario,
        )
    _finish_checked(
        recorder,
        scenario,
        actual_final_status=actual_final_status,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )


async def _run_rejected(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
    scenario: str = "rejected",
) -> None:
    recorder.start_scenario(scenario, expected_final_status="rejected")
    order = await user_sim.place_order(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        worker_id=1,
        fixtures=fixtures,
        recorder=recorder,
        scenario=scenario,
        step="place_order",
    )
    if order is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_pending_before_reject",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="pending",
        sources={"store_orders"},
        phase="precondition",
    ):
        return

    recorder.record_event(
        actor="store",
        action="pending_order_actions_available",
        category="ui_gate",
        scenario=scenario,
        step="pending_order_actions",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        observed_status="pending",
        details={"allowed": ["accept", "reject"], "ready_allowed": False},
    )

    await traced_sleep(
        timing.store_decision_delay.pick(),
        recorder=recorder,
        actor="store",
        action="simulate_store_decision_delay",
        scenario=scenario,
        step="reject_order_delay",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )
    rejected = await store_sim.patch_status(
        client,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        status="rejected",
        store_token=store_session.last_mile_token,
        token_source=store_session.token_source,
        recorder=recorder,
        scenario=scenario,
        step="reject_order",
    )
    if not rejected:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="reject_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_rejected_terminal",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="rejected",
        sources={"user_orders", "store_orders"},
        phase="result",
    ):
        return
    final_state = await _poll_for_status(
        client,
        token=user_session.token,
        token_source=user_session.token_source,
        auth_header="Authorization",
        auth_scheme="Token",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        actor="user",
        expected_statuses={"rejected"},
        scenario=scenario,
        step="verify_rejected",
        action="verify_rejected",
        poll_interval=_poll_interval(timing, 1.0),
        max_attempts=_poll_attempts(timing, 20),
        timeout_code="trace_rejected_timeout",
        timeout_message="Order never reached rejected in trace mode.",
    )
    _finish_checked(
        recorder,
        scenario,
        actual_final_status=str(final_state.get("status") or "rejected_timeout")
        if final_state
        else "rejected_timeout",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )


async def _run_cancelled(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
) -> None:
    scenario = "cancelled"
    recorder.start_scenario(scenario, expected_final_status="cancelled")
    order = await user_sim.place_order(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        worker_id=1,
        fixtures=fixtures,
        recorder=recorder,
        scenario=scenario,
        step="place_order",
    )
    if order is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_pending_before_cancel",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="pending",
        sources={"user_orders"},
        phase="precondition",
    ):
        return

    cancelled = await user_sim.cancel_order(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        scenario=scenario,
        step="cancel_order",
    )
    if not cancelled:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="cancel_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_cancelled_terminal",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="cancelled",
        sources={"user_orders", "store_orders"},
        phase="result",
    ):
        return

    final_state = await _poll_for_status(
        client,
        token=user_session.token,
        token_source=user_session.token_source,
        auth_header="Authorization",
        auth_scheme="Token",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        actor="user",
        expected_statuses={"cancelled"},
        scenario=scenario,
        step="verify_cancelled_user_view",
        action="verify_cancelled_user_view",
        poll_interval=_poll_interval(timing, 1.0),
        max_attempts=_poll_attempts(timing, 20),
        timeout_code="trace_cancelled_timeout",
        timeout_message="Order never reached cancelled in trace mode.",
    )
    if final_state is not None and str(final_state.get("status") or "") == "cancelled":
        await _poll_for_status(
            client,
            token=store_session.last_mile_token,
            token_source=store_session.token_source,
            auth_header="Fainzy-Token",
            auth_scheme="",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            recorder=recorder,
            actor="store",
            expected_statuses={"cancelled"},
            scenario=scenario,
            step="observe_cancelled_store_view",
            action="observe_cancelled_store_view",
            poll_interval=_poll_interval(timing, 1.0),
            max_attempts=_poll_attempts(timing, 10),
            timeout_code="trace_cancelled_store_timeout",
            timeout_message="Store side never observed cancelled in trace mode.",
        )

    _finish_checked(
        recorder,
        scenario,
        actual_final_status=str(final_state.get("status") or "cancelled_timeout")
        if final_state
        else "cancelled_timeout",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )


async def _run_auto_cancel(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
) -> None:
    scenario = "auto_cancel"
    recorder.start_scenario(
        scenario,
        expected_final_status="cancelled",
        note="Diagnostic scenario: the store intentionally does nothing.",
    )
    order = await user_sim.place_order(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        worker_id=1,
        fixtures=fixtures,
        recorder=recorder,
        scenario=scenario,
        step="place_order",
    )
    if order is None:
        recorder.finish_scenario(
            scenario,
            verdict="unsupported",
            actual_final_status="placement_failed",
            note="Order could not be created.",
        )
        return

    recorder.record_event(
        actor="store",
        action="withhold_store_action",
        category="scenario",
        scenario=scenario,
        step="withhold_store_action",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        details={"reason": "Waiting to see whether backend auto-cancels pending orders."},
        track_order=False,
    )

    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_backend_auto_cancel",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="cancelled",
        sources={"user_orders", "store_orders"},
        phase="result",
    ):
        return
    _finish_checked(
        recorder,
        scenario,
        actual_final_status="cancelled",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        note="Backend auto-cancelled the untouched order.",
    )


def _run_new_user_setup(
    *,
    user_session: user_sim.UserSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
) -> None:
    scenario = "new_user_setup"
    recorder.start_scenario(scenario, expected_final_status="location_ready")
    recorder.record_event(
        actor="user",
        action="submit_account_fields",
        category="ui_flow",
        scenario=scenario,
        step="setup_account",
        details={
            "first_name": bool(config.SIM_NEW_USER_FIRST_NAME),
            "last_name": bool(config.SIM_NEW_USER_LAST_NAME),
            "email": bool(config.SIM_NEW_USER_EMAIL)
            or bool(user_session.user.get("email")),
            "password_visibility_toggle": True,
        },
        track_order=False,
    )
    recorder.record_event(
        actor="user",
        action="select_delivery_location",
        category="ui_flow",
        scenario=scenario,
        step="location_selection",
        details={
            "location_id": fixtures.location.get("id"),
            "location_name": fixtures.location.get("name"),
            "radius_km": config.SIM_LOCATION_RADIUS,
        },
        track_order=False,
    )
    if user_session.token_source != "user_new_account_create":
        recorder.record_issue(
            severity="error",
            code="new_user_not_created",
            actor="user",
            scenario=scenario,
            step="setup_account",
            message=(
                "The phone number was already setup_complete=true, so this did "
                "not prove the new-user account creation path."
            ),
        )
        _finish_checked(recorder, scenario, actual_final_status="account_already_setup")
        return
    _finish_checked(recorder, scenario, actual_final_status="location_ready")


def _run_menu_status_probe(
    *,
    status: str,
    store_is_open: bool,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
) -> None:
    if not store_is_open:
        scenario = "menu_store_closed"
        expected = "add_to_cart_blocked"
    else:
        scenario = {
            MENU_AVAILABLE: "menu_available",
            MENU_UNAVAILABLE: "menu_unavailable",
            MENU_SOLD_OUT: "menu_sold_out",
        }[status]
        expected = (
            "add_to_cart_allowed"
            if status == MENU_AVAILABLE
            else "add_to_cart_blocked"
        )

    recorder.start_scenario(scenario, expected_final_status=expected)

    sample = fixtures.menu_items[0] if fixtures.menu_items else {}

    # Create a simulated menu object that matches the scenario being tested.
    menu = dict(sample)
    menu["status"] = status

    # Create a simulated store object that matches the scenario being tested.
    store = dict(fixtures.store)
    store["status"] = 1 if store_is_open else 0

    recorder.record_event(
        actor="user",
        action="tap_menu_item",
        category="ui_flow",
        scenario=scenario,
        step="open_menu_detail",
        details={
            "menu_id": menu.get("id"),
            "menu_status": menu.get("status"),
            "store_is_open": store_is_open,
            "store_status": store.get("status"),
            "category_tabs_available": True,
            "side_extras_checkboxes_available": bool(menu.get("sides")),
        },
        track_order=False,
    )

    blocked_reason = menu_action_block_reason(menu, store=store)
    can_add = blocked_reason is None

    expected_block = scenario in {
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
    }

    if can_add:
        recorder.record_event(
            actor="user",
            action="tap_add_to_cart",
            category="ui_gate",
            scenario=scenario,
            step="add_to_cart_gate",
            ok=True,
            status="allowed",
            details={
                "allowed": True,
                "menu_id": menu.get("id"),
                "menu_status": menu.get("status"),
                "store_status": store.get("status"),
                "expected_block": expected_block,
            },
            track_order=False,
        )
    else:
        recorder.record_event(
            actor="user",
            action="tap_add_to_cart",
            category="ui_gate",
            scenario=scenario,
            step="add_to_cart_gate",
            ok=True,
            status="blocked_expected" if expected_block else "blocked_unexpected",
            details={
                "allowed": False,
                "blocked_reason": blocked_reason,
                "expected_block": expected_block,
                "menu_id": menu.get("id"),
                "menu_status": menu.get("status"),
                "store_status": store.get("status"),
                "user_message": "This store can't take orders"
                if blocked_reason == "store_closed"
                else "This Item is sold out",
            },
            track_order=False,
        )

    actual = "add_to_cart_allowed" if can_add else "add_to_cart_blocked"

    if expected_block and not can_add:
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status=actual,
            note=f"Add-to-cart correctly blocked: {blocked_reason}",
        )
        return

    if not expected_block and can_add:
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status=actual,
            note="Add-to-cart correctly allowed.",
        )
        return

    recorder.record_issue(
        severity="error",
        code="menu_gate_unexpected_result",
        actor="user",
        scenario=scenario,
        step="add_to_cart_gate",
        message=(
            f"Menu gate result was unexpected. "
            f"expected_block={expected_block}, can_add={can_add}, reason={blocked_reason}"
        ),
        details={
            "menu_id": menu.get("id"),
            "menu_status": menu.get("status"),
            "store_status": store.get("status"),
        },
    )
    recorder.finish_scenario(
        scenario,
        verdict="blocked",
        actual_final_status=actual,
        note=f"Unexpected menu gate result: {blocked_reason}",
    )

async def _run_store_first_setup(
    client: httpx.AsyncClient,
    *,
    store_session: store_sim.StoreSession,
    recorder: RunRecorder,
    scenario: str = "store_first_setup",
) -> int | None:
    recorder.start_scenario(scenario, expected_final_status="setup_complete")
    setup_ok = await store_sim.ensure_store_setup(
        client,
        session=store_session,
        recorder=recorder,
        scenario=scenario,
    )
    if not setup_ok:
        _finish_checked(recorder, scenario, actual_final_status="setup_required")
        return None

    original_store_status = await store_sim.open_store_for_simulation(
        client,
        session=store_session,
        recorder=recorder,
        scenario=scenario,
    )

    categories = await store_sim.fetch_categories(
        client,
        session=store_session,
        recorder=recorder,
        scenario=scenario,
    )
    menus = await store_sim.fetch_menus(
        client,
        session=store_session,
        recorder=recorder,
        scenario=scenario,
    )
    menu_mutation_enabled = store_sim.menu_provisioning_enabled()
    if menu_mutation_enabled and not categories:
        category = await store_sim.create_category(
            client,
            session=store_session,
            name=config.SIM_MENU_CATEGORY_NAME,
            recorder=recorder,
            scenario=scenario,
        )
        categories = [category]
    if menu_mutation_enabled and categories and not menus:
        category_id = int(categories[0]["id"])
        menu = await store_sim.create_menu(
            client,
            session=store_session,
            category_id=category_id,
            status=MENU_AVAILABLE,
            recorder=recorder,
            scenario=scenario,
        )
        menus = [menu]
    if menu_mutation_enabled and menus:
        updated = await store_sim.update_menu_status(
            client,
            session=store_session,
            menu=menus[0],
            status=MENU_AVAILABLE,
            recorder=recorder,
            scenario=scenario,
        )
        menus[0] = updated

    recorder.record_event(
        actor="store",
        action="store_setup_inventory_ready",
        category="ui_flow",
        scenario=scenario,
        step="menu_inventory_check",
        details={
            "categories": len(categories),
            "menus": len(menus),
            "auto_provision_enabled": config.SIM_AUTO_PROVISION_FIXTURES,
            "menu_mutation_enabled": config.SIM_MUTATE_MENU_SETUP,
            "menu_provisioning_enabled": menu_mutation_enabled,
        },
        track_order=False,
    )
    if not categories or not menus:
        recorder.record_issue(
            severity="warning",
            code="store_menu_inventory_missing",
            actor="store",
            scenario=scenario,
            step="menu_inventory_check",
            message=(
                "Store setup is complete, but category/menu creation was not "
                "proven because no existing inventory was found and provisioning is off."
            ),
        )
    _finish_checked(recorder, scenario, actual_final_status="setup_complete")
    return original_store_status


async def _run_app_bootstrap(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
) -> None:
    scenario = "app_bootstrap"
    recorder.start_scenario(scenario, expected_final_status="probes_completed")
    await app_probes.run_user_app_probes(
        client,
        recorder=recorder,
        user_id=user_session.user_id,
        user_token=user_session.token,
        user=user_session.user,
        token_source=user_session.token_source,
        currency=fixtures.currency,
        scenario=scenario,
    )
    _finish_checked(recorder, scenario, actual_final_status="probes_completed")


async def _run_store_dashboard(
    client: httpx.AsyncClient,
    *,
    store_session: store_sim.StoreSession,
    recorder: RunRecorder,
) -> None:
    scenario = "store_dashboard"
    recorder.start_scenario(scenario, expected_final_status="probes_completed")
    await app_probes.run_store_dashboard_probes(
        client,
        recorder=recorder,
        subentity_id=store_session.store_id,
        store_token=store_session.last_mile_token,
        token_source=store_session.token_source,
        scenario=scenario,
    )
    _finish_checked(recorder, scenario, actual_final_status="probes_completed")


async def _run_payment_scenario(
    client: httpx.AsyncClient,
    *,
    scenario: str,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
) -> None:
    saved = _save_payment_config()
    try:
        if scenario == "returning_paid_no_coupon":
            config.SIM_PAYMENT_MODE = "stripe"
            config.SIM_PAYMENT_CASE = "paid_no_coupon"
            config.SIM_COUPON_ID = None
            config.SIM_SELECTED_COUPON = None
        elif scenario == "returning_paid_with_coupon":
            config.SIM_PAYMENT_MODE = "stripe"
            config.SIM_PAYMENT_CASE = "paid_with_coupon"
            coupon_ready = await _ensure_coupon_for_scenario(
                client,
                scenario=scenario,
                user_session=user_session,
                fixtures=fixtures,
                recorder=recorder,
            )
            if not coupon_ready:
                recorder.start_scenario(scenario, expected_final_status="completed")
                _finish_checked(recorder, scenario, actual_final_status="coupon_missing")
                return
            if config.SIM_COUPON_ID is None:
                recorder.start_scenario(scenario, expected_final_status="completed")
                recorder.record_issue(
                    severity="error",
                    code="coupon_required",
                    actor="user",
                    scenario=scenario,
                    step="checkout_coupon",
                    message="SIM_COUPON_ID is required for paid coupon checkout.",
                )
                _finish_checked(recorder, scenario, actual_final_status="coupon_missing")
                return
        elif scenario == "returning_free_with_coupon":
            config.SIM_PAYMENT_MODE = "free"
            config.SIM_PAYMENT_CASE = "free_with_coupon"
            config.SIM_FREE_ORDER_AMOUNT = 0.0
            coupon_ready = await _ensure_coupon_for_scenario(
                client,
                scenario=scenario,
                user_session=user_session,
                fixtures=fixtures,
                recorder=recorder,
            )
            if not coupon_ready:
                recorder.start_scenario(scenario, expected_final_status="completed")
                _finish_checked(recorder, scenario, actual_final_status="coupon_missing")
                return
            if config.SIM_COUPON_ID is None:
                recorder.start_scenario(scenario, expected_final_status="completed")
                recorder.record_issue(
                    severity="error",
                    code="coupon_required",
                    actor="user",
                    scenario=scenario,
                    step="checkout_coupon",
                    message="SIM_COUPON_ID is required for free coupon checkout.",
                )
                _finish_checked(recorder, scenario, actual_final_status="coupon_missing")
                return
        await _run_completed(
            client,
            user_session=user_session,
            store_session=store_session,
            fixtures=fixtures,
            recorder=recorder,
            timing=timing,
            observer=observer,
            scenario=scenario,
        )
    finally:
        _restore_payment_config(saved)


async def run(
    *,
    recorder: RunRecorder,
    suite: str | None,
    scenarios: list[str] | None,
    timing_profile: str,
) -> None:
    timing = resolve_timing_profile(timing_profile)
    resolved = resolve_trace_scenarios(suite=suite, scenarios=scenarios)
    console.print(
        f"[bold cyan]trace:[/] Running trace mode scenarios: {', '.join(resolved)} "
        f"(timing={timing.name})"
    )
    actors = getattr(config, "SIM_ACTORS", {}) or {}
    actor_users = actors.get("users", [])
    if not actor_users:
        raise RuntimeError(
            "No users were found in the selected plan. Trace runs require users defined in plan users[]."
        )
    allowed_phones = {str(user.get("phone")) for user in actor_users if isinstance(user, dict) and user.get("phone")}
    configured_phone = str(getattr(config, "USER_PHONE_NUMBER", "") or "").strip()
    if configured_phone and allowed_phones and configured_phone not in allowed_phones:
        raise RuntimeError(
            f"Configured phone {configured_phone!r} is not present in selected plan users[]."
        )

    console.print("[cyan]trace:[/] Bootstrapping auth for trace sims ...")
    bootstrap_scenario = "new_user_setup" if "new_user_setup" in resolved else None
    async with httpx.AsyncClient() as bootstrap_client:
        user_session = await user_sim.bootstrap_auth(
            bootstrap_client,
            recorder,
            scenario=bootstrap_scenario,
        )
        user_phone = (
            user_session.user.get("phone_number")
            or user_session.user.get("phone")
            or getattr(config, "USER_PHONE_NUMBER", "")
        )
        recorder.set_user_identity(
            user_id=user_session.user_id,
            phone=str(user_phone) if user_phone else None,
            raw_user=user_session.user,
        )
        (
            store_session,
            fixtures,
            store_setup_ran_before_fixtures,
            original_store_status,
        ) = (
            await _bootstrap_trace_store_context(
                bootstrap_client,
                user_session=user_session,
                recorder=recorder,
                resolved=resolved,
            )
        )
        recorder.set_store_identity(
            subentity_id=store_session.store_id,
            login_id=store_session.store_login_id or config.STORE_ID,
            raw_store=store_session.subentity,
        )

    order_scenarios = {
        "completed",
        "rejected",
        "cancelled",
        "auto_cancel",
        "returning_paid_no_coupon",
        "returning_paid_with_coupon",
        "returning_free_with_coupon",
        "store_accept",
        "store_reject",
        "robot_complete",
        "receipt_review_reorder",
    }
    observer = (
        WebsocketObserver(
            recorder=recorder,
            user_id=user_session.user_id,
            store_id=store_session.store_id,
        )
        if any(name in order_scenarios for name in resolved)
        else None
    )
    async with httpx.AsyncClient() as client:
        if observer is not None:
            await observer.start()
        try:
            for name in resolved:
                if name == "app_bootstrap":
                    await _run_app_bootstrap(
                        client,
                        user_session=user_session,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name == "completed":
                    await _run_completed(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                    )
                elif name == "rejected":
                    await _run_rejected(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                    )
                elif name == "cancelled":
                    await _run_cancelled(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                    )
                elif name == "auto_cancel":
                    await _run_auto_cancel(
                        client,
                        user_session=user_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                    )
                elif name == "new_user_setup":
                    _run_new_user_setup(
                        user_session=user_session,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name in {
                    "returning_paid_no_coupon",
                    "returning_paid_with_coupon",
                    "returning_free_with_coupon",
                }:
                    await _run_payment_scenario(
                        client,
                        scenario=name,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                    )
                elif name == "menu_available":
                    _run_menu_status_probe(
                        status=MENU_AVAILABLE,
                        store_is_open=True,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name == "menu_unavailable":
                    _run_menu_status_probe(
                        status=MENU_UNAVAILABLE,
                        store_is_open=True,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name == "menu_sold_out":
                    _run_menu_status_probe(
                        status=MENU_SOLD_OUT,
                        store_is_open=True,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name == "menu_store_closed":
                    _run_menu_status_probe(
                        status=MENU_AVAILABLE,
                        store_is_open=False,
                        fixtures=fixtures,
                        recorder=recorder,
                    )
                elif name == "store_first_setup":
                    if not store_setup_ran_before_fixtures:
                        await _run_store_first_setup(
                            client,
                            store_session=store_session,
                            recorder=recorder,
                        )
                elif name == "store_dashboard":
                    await _run_store_dashboard(
                        client,
                        store_session=store_session,
                        recorder=recorder,
                    )
                elif name == "store_accept":
                    await _run_completed(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                        scenario="store_accept",
                    )
                elif name == "store_reject":
                    await _run_rejected(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                        scenario="store_reject",
                    )
                elif name == "robot_complete":
                    await _run_completed(
                        client,
                        user_session=user_session,
                        store_session=store_session,
                        fixtures=fixtures,
                        recorder=recorder,
                        timing=timing,
                        observer=observer,
                        scenario="robot_complete",
                    )
                elif name == "receipt_review_reorder":
                    saved = config.SIM_RUN_POST_ORDER_ACTIONS
                    config.SIM_RUN_POST_ORDER_ACTIONS = True
                    try:
                        await _run_completed(
                            client,
                            user_session=user_session,
                            store_session=store_session,
                            fixtures=fixtures,
                            recorder=recorder,
                            timing=timing,
                            observer=observer,
                            scenario="receipt_review_reorder",
                        )
                    finally:
                        config.SIM_RUN_POST_ORDER_ACTIONS = saved
        finally:
            if observer is not None:
                await observer.stop()
                recorder.set_websocket_coverage(observer.coverage_summary())
            await store_sim.restore_store_status(
                client,
                session=store_session,
                original_status=original_store_status,
                recorder=recorder,
                scenario="simulation_cleanup",
            )
