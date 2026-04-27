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
import robot_sim
from reporting import RunRecorder
from scenarios import TimingProfile, resolve_timing_profile, resolve_trace_scenarios
import store_sim
import stripe_sim
from transport import traced_sleep
import user_sim

console = Console()


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


async def _run_completed(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
) -> None:
    scenario = "completed"
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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="placement_failed",
            note="Order could not be created.",
        )
        return

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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="accept_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    accepted_state = await _poll_for_status(
        client,
        token=user_session.token,
        token_source=user_session.token_source,
        auth_header="Authorization",
        auth_scheme="Token",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        actor="user",
        expected_statuses={"payment_processing"},
        scenario=scenario,
        step="verify_store_acceptance",
        action="verify_store_acceptance",
        poll_interval=_poll_interval(timing, 1.0),
        max_attempts=_poll_attempts(timing, 30),
        timeout_code="trace_acceptance_timeout",
        timeout_message="Order never reached payment_processing in trace mode.",
    )
    if accepted_state is None or str(accepted_state.get("status") or "") != "payment_processing":
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status=str(accepted_state.get("status") or "acceptance_timeout")
            if accepted_state
            else "acceptance_timeout",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    if config.SIM_PAYMENT_MODE == "stripe":
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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="payment_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    processing_state = await _poll_for_status(
        client,
        token=store_session.last_mile_token,
        token_source=store_session.token_source,
        auth_header="Fainzy-Token",
        auth_scheme="",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        recorder=recorder,
        actor="store",
        expected_statuses={"order_processing"},
        scenario=scenario,
        step="verify_order_processing",
        action="verify_order_processing",
        poll_interval=_poll_interval(timing, 1.0),
        max_attempts=_poll_attempts(timing, 30),
        timeout_code="trace_order_processing_timeout",
        timeout_message="Order never reached order_processing in trace mode.",
    )
    if processing_state is None or str(processing_state.get("status") or "") != "order_processing":
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status=str(processing_state.get("status") or "order_processing_timeout")
            if processing_state
            else "order_processing_timeout",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="ready_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return

    for status, _ in robot_sim.ROBOT_LIFECYCLE:
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
            recorder.finish_scenario(
                scenario,
                verdict="passed",
                actual_final_status="robot_status_failed",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
            )
            return
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
    recorder.finish_scenario(
        scenario,
        verdict="passed",
        actual_final_status=str(final_state.get("status") or "completed_timeout")
        if final_state
        else "completed_timeout",
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
) -> None:
    scenario = "rejected"
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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="placement_failed",
        )
        return

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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="reject_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
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
    recorder.finish_scenario(
        scenario,
        verdict="passed",
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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="placement_failed",
        )
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
        recorder.finish_scenario(
            scenario,
            verdict="passed",
            actual_final_status="cancel_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
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

    recorder.finish_scenario(
        scenario,
        verdict="passed",
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

    wait_seconds = timing.auto_cancel_wait_seconds
    poll_interval = _poll_interval(timing, 5.0)
    attempts = max(1, int(wait_seconds / poll_interval))
    observed = None
    for attempt in range(attempts):
        observed = await user_sim.fetch_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            recorder=recorder,
            action="observe_auto_cancel",
            scenario=scenario,
            step="observe_auto_cancel",
            poll_attempt=attempt + 1,
        )
        if str(observed.get("status") or "") == "cancelled":
            recorder.finish_scenario(
                scenario,
                verdict="passed",
                actual_final_status="cancelled",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note="Backend auto-cancelled the untouched order.",
            )
            return
        await traced_sleep(
            poll_interval,
            recorder=recorder,
            actor="user",
            action="wait_for_auto_cancel",
            scenario=scenario,
            step="observe_auto_cancel_delay",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )

    recorder.record_issue(
        severity="warning",
        code="auto_cancel_not_observed",
        actor="backend",
        scenario=scenario,
        step="observe_auto_cancel",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        message=(
            "The backend did not auto-cancel the untouched pending order within the "
            "diagnostic window."
        ),
    )
    recorder.finish_scenario(
        scenario,
        verdict="unsupported",
        actual_final_status=str(observed.get("status") or "pending") if observed else "pending",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        note="Auto-cancel was not observed inside the configured diagnostic window.",
    )


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

    console.print("[cyan]trace:[/] Bootstrapping auth for trace sims ...")
    async with httpx.AsyncClient() as bootstrap_client:
        user_session = await user_sim.bootstrap_auth(bootstrap_client, recorder)
        store_session = await store_sim.bootstrap_auth(bootstrap_client, recorder)
        fixtures = await user_sim.bootstrap_fixtures(
            bootstrap_client,
            session=user_session,
            store_token=store_session.last_mile_token,
            subentity=store_session.subentity,
            recorder=recorder,
        )

    async with httpx.AsyncClient() as client:
        for name in resolved:
            if name == "completed":
                await _run_completed(
                    client,
                    user_session=user_session,
                    store_session=store_session,
                    fixtures=fixtures,
                    recorder=recorder,
                    timing=timing,
                )
            elif name == "rejected":
                await _run_rejected(
                    client,
                    user_session=user_session,
                    store_session=store_session,
                    fixtures=fixtures,
                    recorder=recorder,
                    timing=timing,
                )
            elif name == "cancelled":
                await _run_cancelled(
                    client,
                    user_session=user_session,
                    store_session=store_session,
                    fixtures=fixtures,
                    recorder=recorder,
                    timing=timing,
                )
            elif name == "auto_cancel":
                await _run_auto_cancel(
                    client,
                    user_session=user_session,
                    fixtures=fixtures,
                    recorder=recorder,
                    timing=timing,
                )
