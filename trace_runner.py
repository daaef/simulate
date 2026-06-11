"""
Deterministic trace-mode orchestration.

Bootstraps its own auth and fixtures via user_sim / store_sim modules,
then drives each scenario step-by-step using polling for verification.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import random
import time
from typing import Any, Literal

import httpx
from rich.console import Console
from rich.panel import Panel

import config
import app_probes
import menu_catalog
from failure_policy import classify_http_status, classify_issue, is_api_only, is_hard_stop
from interaction_catalog import (
    MENU_AVAILABLE,
    MENU_SOLD_OUT,
    MENU_UNAVAILABLE,
    menu_action_block_reason,
)
import robot_sim
import post_order_actions
import order_contract
from reporting import RunRecorder
from scenarios import (
    TimingProfile,
    resolve_effective_timing_profile,
    resolve_timing_profile,
    resolve_trace_scenarios,
)
import store_sim
import stripe_sim
from transport import traced_sleep
import user_sim
from websocket_observer import REQUIRED_WEBSOCKET_SOURCES, WebsocketObserver

console = Console()


def _sim_log(
    scenario: str,
    actor: str,
    message: str,
    level: str = "info",
) -> None:
    """Emit a structured trace line.  level: info | success | warn | error."""
    if level == "success":
        actor_markup = f"[bold green]{actor}[/bold green]"
    elif level == "warn":
        actor_markup = f"[bold yellow]{actor}[/bold yellow]"
    elif level == "error":
        actor_markup = f"[bold red]{actor}[/bold red]"
    else:
        actor_markup = f"[bold]{actor}[/bold]"
    console.print(
        f"[dim][[/dim][cyan]{scenario}[/cyan][dim]][/dim] {actor_markup}: {message}"
    )


FIXTURE_REQUIRED_SCENARIOS = {
    "completed",
    "rejected",
    "cancelled",
    "backend_auto_cancel",
    "place_order",
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

MENU_FLOW_SCENARIOS = frozenset(
    {
        "menu_available",
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
    }
)


def _trace_requires_fixtures(scenarios: list[str]) -> bool:
    return any(name in FIXTURE_REQUIRED_SCENARIOS for name in scenarios)


def _is_menus_flow_run(resolved: list[str]) -> bool:
    return bool(resolved) and all(name in MENU_FLOW_SCENARIOS for name in resolved)


async def _provision_menus_flow_inventory(
    client: httpx.AsyncClient,
    *,
    store_session: store_sim.StoreSession,
    user_session: user_sim.UserSession,
    recorder: RunRecorder,
) -> user_sim.UserFixtures:
    """Create a fresh menu item in the target store before menu gate scenarios."""
    scenario = "menu_available"
    previous_mutate_menu = config.SIM_MUTATE_MENU_SETUP
    if not store_sim.menu_provisioning_enabled():
        config.SIM_MUTATE_MENU_SETUP = True

    try:
        setup_ok = await store_sim.ensure_store_setup(
            client,
            session=store_session,
            recorder=recorder,
            scenario=scenario,
        )
        if not setup_ok:
            raise RuntimeError("Store setup is not complete; cannot create menu item for menus flow.")

        await store_sim.open_store_for_simulation(
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
            step="menus_run_fetch_categories",
        )
        entry = menu_catalog.pick_entry()
        roll = random.random()
        create_new_category = not categories or roll >= 0.5
        if create_new_category:
            category_strategy = "new_category"
            category = await store_sim.create_category(
                client,
                session=store_session,
                name=entry.category_name,
                recorder=recorder,
                scenario=scenario,
                step="menus_run_create_category",
            )
            category_id = int(category["id"])
            category_name = entry.category_name
        else:
            category_strategy = "existing_category"
            chosen = random.choice(categories)
            category_id = int(chosen["id"])
            category_name = str(chosen.get("name") or "")
            entry = menu_catalog.pick_entry_for_category(category_name)

        created_menu = await store_sim.create_menu(
            client,
            session=store_session,
            category_id=category_id,
            status=MENU_AVAILABLE,
            recorder=recorder,
            scenario=scenario,
            step="menus_run_create_item",
            name=entry.menu_name,
            description=entry.description,
            price=entry.price,
            ingredients=entry.ingredients,
        )

        recorder.record_event(
            actor="store",
            action="menus_run_item_created",
            category="store_setup",
            scenario=scenario,
            step="menus_run_create_item",
            details={
                "menu_id": created_menu.get("id"),
                "menu_name": created_menu.get("name") or entry.menu_name,
                "category_id": category_id,
                "category_name": category_name,
                "category_strategy": category_strategy,
                "roll": roll,
                "subentity_id": store_session.store_id,
            },
            track_order=False,
        )
        _sim_log(
            "bootstrap",
            "trace",
            f"menus flow created item {created_menu.get('name') or entry.menu_name} "
            f"(id={created_menu.get('id')}) in {category_strategy} '{category_name}'",
        )

        fixtures = await user_sim.bootstrap_fixtures(
            client,
            session=user_session,
            store_token=store_session.last_mile_token,
            subentity=store_session.subentity,
            recorder=recorder,
            subentity_id=store_session.store_id,
        )
        recorder.set_fixtures(fixtures)
        return fixtures
    finally:
        config.SIM_MUTATE_MENU_SETUP = previous_mutate_menu


def _trace_store_candidates() -> list[str | None]:
    actors = getattr(config, "SIM_ACTORS", {}) or {}
    failure_policy = getattr(config, "SIM_FAILURE_POLICY", "api_only")
    preflight_strategy = getattr(config, "SIM_PREFLIGHT_STRATEGY", "auto_recover")
    actor_store_ids: list[str] = []
    for store in actors.get("stores", []):
        if not isinstance(store, dict):
            continue
        store_id = store.get("store_id")
        if store_id and str(store_id) not in actor_store_ids:
            actor_store_ids.append(str(store_id))

    if not actor_store_ids:
        if is_api_only(failure_policy) and not is_hard_stop(preflight_strategy):
            configured_store = str(getattr(config, "STORE_ID", "") or "").strip()
            return [configured_store or None]
        raise RuntimeError(
            "No stores were found in the selected plan. "
            "All trace runs now require store selection from plan stores only."
        )

    if config.SIM_STORE_EXPLICIT:
        explicit_store = config.STORE_ID or ""
        if explicit_store not in actor_store_ids:
            if is_api_only(failure_policy) and not is_hard_stop(preflight_strategy):
                return [explicit_store or None]
            raise RuntimeError(
                f"Explicit store {explicit_store!r} is not present in the selected plan stores."
            )
        return [explicit_store]

    if not getattr(config, "SIM_DISABLE_RANDOM_STORE", False):
        random.shuffle(actor_store_ids)
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
            _sim_log(
                "bootstrap",
                "trace",
                f"selected store {store_session.store_login_id or candidate or store_session.store_id} "
                f"(subentity_id={store_session.store_id})",
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
            failure_class = classify_issue(
                code="store_candidate_unusable",
                message=str(exc),
                default="precondition",
            )
            hard_stop = is_hard_stop(config.SIM_PREFLIGHT_STRATEGY)
            severity = "warning"
            if failure_class == "api_fault":
                severity = "error"
            elif config.SIM_STORE_EXPLICIT and (
                hard_stop or not is_api_only(config.SIM_FAILURE_POLICY)
            ):
                severity = "error"
            recorder.record_issue(
                severity=severity,
                code="store_candidate_unusable",
                failure_class=failure_class,
                actor="trace",
                scenario="bootstrap",
                step="auto_select_store",
                message=f"Store candidate {candidate or config.STORE_ID or 'default'} could not be used: {exc}",
            )
            if config.SIM_STORE_EXPLICIT and severity == "error":
                raise
            _sim_log("bootstrap", "trace", f"store {candidate or 'default'} could not be used: {exc}")

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


def _save_payment_config() -> tuple[
    str,
    int | None,
    float,
    str,
    dict | None,
    int | None,
    str,
    str,
]:
    return (
        config.SIM_PAYMENT_MODE,
        config.SIM_COUPON_ID,
        config.SIM_FREE_ORDER_AMOUNT,
        config.SIM_PAYMENT_CASE,
        config.SIM_SELECTED_COUPON,
        config.SUBENTITY_ID,
        config.STORE_CURRENCY,
        config.STORE_ID,
    )


def _restore_payment_config(
    saved: tuple[
        str,
        int | None,
        float,
        str,
        dict | None,
        int | None,
        str,
        str,
    ]
) -> None:
    (
        config.SIM_PAYMENT_MODE,
        config.SIM_COUPON_ID,
        config.SIM_FREE_ORDER_AMOUNT,
        config.SIM_PAYMENT_CASE,
        config.SIM_SELECTED_COUPON,
        config.SUBENTITY_ID,
        config.STORE_CURRENCY,
        config.STORE_ID,
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
            severity="warning",
            code="coupon_unavailable",
            failure_class="precondition",
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
    _sim_log(scenario, "user", f"selected coupon {selected.get('code') or config.SIM_COUPON_ID}")
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
    scenario: str = "checkout",
    order_ref: str,
    payment_mode: str,
    payment_case: str,
    coupon_id: int | None,
    save_card: bool,
) -> None:
    coupon_label = coupon_id if coupon_id is not None else "none"
    _sim_log(
        scenario,
        "user",
        f"Checkout decision for order {order_ref}: route={payment_mode}, case={payment_case}, "
        f"coupon={coupon_label}, save_card={str(save_card).lower()}",
    )


def _gate_failure_code(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("websocket_gate_source_unavailable:"):
        return "websocket_gate_source_unavailable"
    if message.startswith("websocket_gate_timeout:"):
        return "websocket_gate_timeout"
    if message.startswith("websocket_sources_timeout:"):
        return "websocket_sources_timeout"
    if message.startswith("websocket_required_sources_timeout:"):
        return "websocket_required_sources_timeout"
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
    timeout_seconds: float | None = None,
) -> bool:
    effective_timeout = float(
        timeout_seconds if timeout_seconds is not None
        else config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS
    )
    _sim_log(
        scenario,
        "websocket",
        f"waiting for status=[bold]{expected_status}[/bold]"
        f"  channels={sorted(sources)}"
        f"  timeout={effective_timeout:.0f}s"
        f"  order={order_db_id} ({order_ref}) …",
    )
    t_start = time.monotonic()
    try:
        event = await observer.wait_for_order_status(
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=expected_status,
            sources=sources,
            timeout_seconds=timeout_seconds,
        )
    except RuntimeError as exc:
        elapsed = time.monotonic() - t_start
        failure_code = _gate_failure_code(exc)
        last_seen = observer.last_seen_status(order_db_id, sources=sources)
        if last_seen:
            last_seen_str = (
                f"{last_seen['status']} (via {last_seen['source']})"
                f"  — expected {expected_status}"
            )
        else:
            last_seen_str = "no events received for this order on these channels"

        if not config.SIM_ENFORCE_WEBSOCKET_GATES:
            recorder.record_issue(
                severity="warning",
                code=failure_code,
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
            _sim_log(
                scenario,
                "websocket",
                f"gate bypassed  status={expected_status}  order={order_db_id} ({order_ref})"
                f"  last seen: {last_seen_str}",
                level="warn",
            )
            return True
        recorder.record_issue(
            severity="error",
            code=failure_code,
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
        _sim_log(scenario, "websocket", f"✗ GATE FAILED  status={expected_status}  order={order_db_id} ({order_ref})", level="error")
        _sim_log(scenario, "websocket", f"  step     : {step}", level="error")
        _sim_log(scenario, "websocket", f"  channels : {', '.join(sorted(sources))}", level="error")
        _sim_log(scenario, "websocket", f"  waited   : {elapsed:.1f}s  ({failure_code})", level="error")
        _sim_log(scenario, "websocket", f"  last seen: {last_seen_str}", level="error")
        _finish_checked(
            recorder,
            scenario,
            actual_final_status=failure_code,
            order_db_id=order_db_id,
            order_ref=order_ref,
            note=f"Websocket gate failed at step={step}",
        )
        return False

    elapsed = time.monotonic() - t_start
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
    _sim_log(
        scenario,
        "websocket",
        f"✓ status=[bold]{expected_status}[/bold]"
        f"  confirmed via [bold]{event.get('source')}[/bold]"
        f"  ({elapsed:.1f}s)  order={order_db_id} ({order_ref})",
        level="success",
    )
    return True


async def _wait_for_store_to_act(
    client: httpx.AsyncClient,
    *,
    order_db_id: int,
    order_ref: str,
    user_session: user_sim.UserSession,
    recorder: RunRecorder,
    scenario: str,
    step: str,
    from_status: str,
) -> str | None:
    """Poll until the real store moves the order away from from_status.

    Returns the new status string, or None on timeout.
    Only called when config.SIM_WAIT_FOR_STORE_ACTION is True.
    """
    timeout = config.SIM_STORE_ACTION_TIMEOUT_SECONDS
    deadline = time.monotonic() + timeout
    _sim_log(scenario, "store", f"waiting for real store to act on order {order_ref} (status={from_status}) …")

    while time.monotonic() < deadline:
        await asyncio.sleep(5.0)
        try:
            order_data = await user_sim.fetch_order(
                client,
                user_token=user_session.token,
                token_source=user_session.token_source,
                order_db_id=order_db_id,
                order_ref=order_ref,
                recorder=recorder,
                action="wait_for_store_action_poll",
                scenario=scenario,
                step=step,
            )
        except Exception:
            continue
        status = str(order_data.get("status") or "").strip().lower()
        if status and status != from_status:
            _sim_log(scenario, "store", f"real store acted — order {order_ref} is now {status} ✓")
            return status

    recorder.record_issue(
        severity="warning",
        code="real_store_action_timeout",
        actor="store",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        message=(
            f"Timed out waiting for real store to act "
            f"(waited {timeout:.0f}s, order {order_ref} stayed {from_status})"
        ),
    )
    _sim_log(scenario, "store", f"real store did not act within {timeout:.0f}s — timed out")
    return None


async def _fulfill_placed_order(
    client: httpx.AsyncClient,
    *,
    order: dict[str, Any],
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
    scenario: str,
) -> str:
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
        return "websocket_gate_failed"

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

    if config.SIM_WAIT_FOR_STORE_ACTION:
        store_decision = await _wait_for_store_to_act(
            client,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            user_session=user_session,
            recorder=recorder,
            scenario=scenario,
            step="wait_real_store_accept",
            from_status="pending",
        )
        if store_decision is None:
            _sim_log(scenario, "store", f"real store did not act on order {order['order_ref']} — timed out waiting for accept/reject", level="error")
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="store_action_timeout",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note="Timed out waiting for real store to act on pending order.",
            )
            return "store_action_timeout"
        if store_decision == "rejected":
            if not await _wait_for_ws_gate(
                observer,
                recorder=recorder,
                scenario=scenario,
                step="wait_rejected_by_real_store",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                expected_status="rejected",
                sources={"user_orders", "store_orders"},
                phase="result",
            ):
                return "websocket_gate_failed"
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="rejected",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note="Real store rejected the order.",
            )
            return "rejected"
    else:
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
            _sim_log(scenario, "store", f"failed to accept order {order['order_ref']} — PATCH to payment_processing returned error", level="error")
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="accept_failed",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
            )
            return "accept_failed"

    _sim_log(scenario, "store", f"accepted order {order['order_ref']} → payment_processing", level="success")
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
        return "websocket_gate_failed"

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
        scenario=scenario,
        order_ref=order["order_ref"],
        payment_mode=payment_mode,
        payment_case=config.SIM_PAYMENT_CASE,
        coupon_id=config.SIM_COUPON_ID,
        save_card=config.SIM_SAVE_CARD,
    )

    _sim_log(scenario, "payment", f"processing payment for order {order['order_ref']} (mode={payment_mode}) …")
    if payment_mode == "stripe":
        paid = await stripe_sim.pay_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_ref=order["order_ref"],
            order_db_id=order["order_db_id"],
            amount=float(order["order_total"]),
            store_subentity_id=int(order["store_subentity_id"]),
            currency=str(order["store_currency"]),
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
            store_subentity_id=int(order["store_subentity_id"]),
            currency=str(order["store_currency"]),
            recorder=recorder,
            scenario=scenario,
            step="complete_free_order",
        )
    if not paid:
        _sim_log(scenario, "payment", f"order {order['order_ref']} payment failed — Stripe/free-order endpoint returned error", level="error")
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="payment_failed",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
        )
        return "payment_failed"

    _sim_log(scenario, "payment", f"order {order['order_ref']} payment succeeded ✓", level="success")
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
        return "websocket_gate_failed"

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

    if config.SIM_WAIT_FOR_STORE_ACTION:
        ready_status = await _wait_for_store_to_act(
            client,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            user_session=user_session,
            recorder=recorder,
            scenario=scenario,
            step="wait_real_store_ready",
            from_status="order_processing",
        )
        if ready_status is None:
            _sim_log(scenario, "store", f"real store did not mark order {order['order_ref']} ready — timed out waiting", level="error")
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="store_ready_timeout",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note="Timed out waiting for real store to mark food ready.",
            )
            return "store_ready_timeout"
        if ready_status != "ready":
            _finish_checked(
                recorder,
                scenario,
                actual_final_status=ready_status,
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note=f"Real store moved order to {ready_status} instead of ready.",
            )
            return ready_status
    else:
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
            _sim_log(scenario, "store", f"failed to mark order {order['order_ref']} ready — PATCH to ready returned error", level="error")
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="ready_failed",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
            )
            return "ready_failed"

    _sim_log(scenario, "store", f"food ready for order {order['order_ref']} ✓", level="success")
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
        return "websocket_gate_failed"

    _sim_log(scenario, "robot", f"starting delivery lifecycle for order {order['order_ref']} …")
    previous_status = "ready"
    for status in robot_sim.ROBOT_LIFECYCLE:
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
            return "websocket_gate_failed"
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
            return "robot_status_failed"
        _sim_log(scenario, "robot", f"order {order['order_ref']} → {status}")
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
            return "websocket_gate_failed"
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
    return (
        str(final_state.get("status") or "completed_timeout")
        if final_state
        else "completed_timeout"
    )


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
    _sim_log(scenario, "user", "placing order …")
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
        _sim_log(scenario, "user", "order placement failed — could not create order", level="error")
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
            note="Order could not be created.",
        )
        return

    _sim_log(scenario, "user", f"order {order['order_ref']} created (total={order.get('order_total')}) ✓", level="success")
    actual_final_status = await _fulfill_placed_order(
        client,
        order=order,
        user_session=user_session,
        store_session=store_session,
        recorder=recorder,
        timing=timing,
        observer=observer,
        scenario=scenario,
    )
    reorder_result = None
    if actual_final_status == "completed" and config.SIM_RUN_POST_ORDER_ACTIONS:
        reorder_result = await post_order_actions.run_post_order_actions(
            client,
            recorder=recorder,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            subentity=fixtures.store,
            scenario=scenario,
        )
    if actual_final_status == "completed" and scenario == "receipt_review_reorder":
        second_status = await _run_reorder_second_order(
            client,
            user_session=user_session,
            store_session=store_session,
            fixtures=fixtures,
            recorder=recorder,
            timing=timing,
            observer=observer,
            source_order_db_id=order["order_db_id"],
            source_order_ref=order["order_ref"],
            reorder_result=reorder_result,
        )
        if second_status != "completed":
            actual_final_status = second_status
    expected = (recorder.scenarios.get(scenario) or {}).get("expected_final_status")
    status_level = "success" if actual_final_status == expected else "error"
    _sim_log(
        scenario,
        "trace",
        f"order {order['order_ref']} final status: {actual_final_status}"
        + (f" ✓" if status_level == "success" else f"  ✗  (expected {expected})"),
        level=status_level,
    )
    _finish_checked(
        recorder,
        scenario,
        actual_final_status=actual_final_status,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
    )


async def _run_place_order(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    observer: WebsocketObserver,
) -> None:
    scenario = "place_order"
    order_count = max(1, int(config.SIM_ORDERS))
    recorder.start_scenario(
        scenario,
        expected_final_status="pending",
        note="Seeds pending live orders for manual store-app inspection.",
    )
    seeded_orders: list[dict[str, Any]] = []

    for index in range(1, order_count + 1):
        step = f"place_order_{index}"
        _sim_log(scenario, "user", f"placing pending seed order {index}/{order_count} ...")
        order = await user_sim.place_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            worker_id=index,
            fixtures=fixtures,
            recorder=recorder,
            scenario=scenario,
            step=step,
        )
        if order is None:
            _sim_log(
                scenario,
                "user",
                f"pending seed order {index}/{order_count} failed at placement",
                level="error",
            )
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="placement_failed",
                note=f"Order {index}/{order_count} could not be created.",
            )
            return

        if not await _wait_for_ws_gate(
            observer,
            recorder=recorder,
            scenario=scenario,
            step=f"wait_pending_seeded_{index}",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            expected_status="pending",
            sources={"store_orders"},
            phase="result",
        ):
            return

        seeded_orders.append(order)
        recorder.record_event(
            actor="user",
            action="pending_order_seeded",
            category="manual_seed",
            scenario=scenario,
            step=f"pending_order_seeded_{index}",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            observed_status="pending",
            details={
                "order_index": index,
                "order_count": order_count,
                "cleanup_policy": "left_pending_for_manual_inspection",
            },
        )
        _sim_log(
            scenario,
            "trace",
            f"order {order['order_ref']} seeded and left pending for manual inspection",
            level="success",
        )

    last = seeded_orders[-1] if seeded_orders else {}
    _finish_checked(
        recorder,
        scenario,
        actual_final_status="pending",
        order_db_id=last.get("order_db_id"),
        order_ref=last.get("order_ref"),
        note=f"Seeded {len(seeded_orders)} pending order(s) for manual inspection.",
    )


async def _run_reorder_second_order(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
    source_order_db_id: int,
    source_order_ref: str,
    reorder_result: Any | None = None,
) -> str:
    scenario = "receipt_review_reorder_second"
    recorder.start_scenario(scenario, expected_final_status="completed")

    if reorder_result is None:
        reorder_result = await post_order_actions.fetch_reorder(
            client,
            recorder=recorder,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_db_id=source_order_db_id,
            order_ref=source_order_ref,
            scenario="receipt_review_reorder",
        )
    if reorder_result is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="reorder_fetch_failed",
            order_db_id=source_order_db_id,
            order_ref=source_order_ref,
        )
        return "reorder_fetch_failed"

    reorder_items = post_order_actions.parse_reorder_cart_items(reorder_result.payload)
    payload = post_order_actions.build_reorder_order_payload(
        fixtures=fixtures,
        reorder_items=reorder_items,
        recorder=recorder,
        scenario=scenario,
        source_order_db_id=source_order_db_id,
    )
    if payload is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="reorder_cart_empty",
            order_db_id=source_order_db_id,
            order_ref=source_order_ref,
        )
        return "reorder_cart_empty"

    _sim_log("receipt_review_reorder", "user", f"placing reorder cart from source order {source_order_ref} …")
    order = await user_sim.place_order_with_payload(
        client,
        user_token=user_session.token,
        token_source=user_session.token_source,
        worker_id=1,
        fixtures=fixtures,
        recorder=recorder,
        payload=payload,
        scenario=scenario,
        step="reorder_place_order",
    )
    if order is None:
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="reorder_placement_failed",
            order_db_id=source_order_db_id,
            order_ref=source_order_ref,
        )
        return "reorder_placement_failed"

    return await _fulfill_placed_order(
        client,
        order=order,
        user_session=user_session,
        store_session=store_session,
        recorder=recorder,
        timing=timing,
        observer=observer,
        scenario=scenario,
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
    _sim_log(scenario, "user", "placing order …")
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
        _sim_log(scenario, "user", "order placement failed — could not create order", level="error")
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
        )
        return

    _sim_log(scenario, "user", f"order {order['order_ref']} created ✓", level="success")
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
        return "websocket_gate_failed"

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

    if config.SIM_WAIT_FOR_STORE_ACTION:
        store_decision = await _wait_for_store_to_act(
            client,
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            user_session=user_session,
            recorder=recorder,
            scenario=scenario,
            step="wait_real_store_reject",
            from_status="pending",
        )
        if store_decision is None:
            _finish_checked(
                recorder,
                scenario,
                actual_final_status="store_action_timeout",
                order_db_id=order["order_db_id"],
                order_ref=order["order_ref"],
                note="Timed out waiting for real store to reject the order.",
            )
            return
        rejected = store_decision == "rejected"
    else:
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

    _sim_log(scenario, "store", f"rejected order {order['order_ref']} ✓", level="success")
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
    _sim_log(scenario, "user", "placing order …")
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
        _sim_log(scenario, "user", "order placement failed — could not create order", level="error")
        _finish_checked(
            recorder,
            scenario,
            actual_final_status="placement_failed",
        )
        return

    _sim_log(scenario, "user", f"order {order['order_ref']} created ✓ — cancelling …", level="success")
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


BackendAutoCancelObserveOutcome = Literal["cancelled", "timeout", "terminal_early"]

_BACKEND_AUTO_CANCEL_TERMINALS = frozenset({"cancelled", "rejected", "refunded"})


def _backend_auto_cancel_tick_interval(total_seconds: float) -> float:
    total = max(1.0, float(total_seconds))
    if total <= 30.0:
        return min(10.0, total)
    return min(30.0, max(10.0, total / 3.0))


async def _run_backend_auto_cancel_observe_countdown(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    order_db_id: int,
    order_ref: str,
    recorder: RunRecorder,
    scenario: str,
    total_seconds: float,
    event_prefix: str,
    phase_label: str,
    tick_interval: float | None = None,
    eligible_status: str = "payment_processing",
) -> tuple[BackendAutoCancelObserveOutcome, str]:
    """Log countdown ticks while eligible; observe cancelled (no store PATCH)."""
    total = max(1.0, float(total_seconds))
    interval = (
        float(tick_interval)
        if tick_interval is not None
        else _backend_auto_cancel_tick_interval(total)
    )
    eligible = str(eligible_status or "payment_processing").strip().lower()
    step = f"{event_prefix}_countdown"
    deadline_mono = time.monotonic() + total
    deadline_iso = (
        datetime.now(timezone.utc) + timedelta(seconds=total)
    ).replace(microsecond=0).isoformat()

    def _record_terminal_early(
        status: str,
        *,
        remaining_seconds: float,
    ) -> tuple[BackendAutoCancelObserveOutcome, str]:
        recorder.record_event(
            actor="simulator",
            action=f"{event_prefix}_terminal_early",
            category="scenario",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status=status,
            details={
                "remaining_seconds": max(0.0, remaining_seconds),
                "eligible_status": eligible,
            },
        )
        _sim_log(
            scenario,
            "backend",
            f"order {order_db_id} left {phase_label} observe window early "
            f"(unexpected status={status}, {max(0.0, remaining_seconds):.0f}s remaining)",
            level="warn",
        )
        return "terminal_early", status

    def _record_cancelled_observed(
        *,
        remaining_seconds: float,
    ) -> tuple[BackendAutoCancelObserveOutcome, str]:
        recorder.record_event(
            actor="backend",
            action=f"{event_prefix}_observed",
            category="terminal",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status="cancelled",
            details={
                "remaining_seconds": max(0.0, remaining_seconds),
                "eligible_status": eligible,
            },
        )
        console.print(
            Panel.fit(
                f"[bold green]Backend auto-cancel fired[/bold green]\n"
                f"Order [bold]{order_db_id}[/bold] ({order_ref}) was cancelled by the backend automatically.\n"
                f"Phase: {phase_label}  |  {max(0.0, remaining_seconds):.0f}s remaining in observe window.",
                border_style="green",
                title="[bold green]✓ backend_auto_cancel[/bold green]",
            )
        )
        return "cancelled", "cancelled"

    recorder.record_event(
        actor="simulator",
        action=f"{event_prefix}_armed",
        category="scenario",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        details={
            "total_seconds": total,
            "tick_interval_seconds": interval,
            "deadline_iso": deadline_iso,
            "eligible_status": eligible,
        },
    )
    _sim_log(
        scenario,
        "backend",
        f"watching order {order_db_id} for {phase_label} auto-cancel "
        f"({total:.0f}s window, status={eligible})",
    )

    async def _current_status() -> str:
        payload = await user_sim.fetch_order(
            client,
            user_token=user_session.token,
            token_source=user_session.token_source,
            order_db_id=order_db_id,
            order_ref=order_ref,
            recorder=recorder,
            action=f"{event_prefix}_poll",
            scenario=scenario,
            step=step,
        )
        return str(payload.get("status") or "").strip().lower()

    while True:
        remaining = deadline_mono - time.monotonic()
        if remaining <= 0:
            break
        sleep_for = min(interval, remaining)
        await asyncio.sleep(sleep_for)
        remaining_after = deadline_mono - time.monotonic()
        try:
            status = await _current_status()
        except Exception:
            status = ""
        if status == "cancelled":
            return _record_cancelled_observed(remaining_seconds=remaining_after)
        if status in _BACKEND_AUTO_CANCEL_TERMINALS:
            return _record_terminal_early(status, remaining_seconds=remaining_after)
        if status and status != eligible:
            return _record_terminal_early(status, remaining_seconds=remaining_after)

        remaining_display = max(0.0, remaining_after)
        recorder.record_event(
            actor="simulator",
            action=f"{event_prefix}_tick",
            category="scenario",
            scenario=scenario,
            step=step,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status=status or eligible,
            details={
                "remaining_seconds": round(remaining_display, 1),
                "eligible_status": eligible,
            },
        )
        _sim_log(
            scenario,
            "backend",
            f"order {order_db_id} still {status or eligible} — {phase_label} cancel window: {remaining_display:.0f}s remaining",
        )

    try:
        status = await _current_status()
    except Exception:
        status = ""
    if status == "cancelled":
        return _record_cancelled_observed(remaining_seconds=0.0)
    if status in _BACKEND_AUTO_CANCEL_TERMINALS:
        return _record_terminal_early(status, remaining_seconds=0.0)
    if status != eligible:
        return _record_terminal_early(status or "unknown", remaining_seconds=0.0)

    recorder.record_event(
        actor="backend",
        action=f"{event_prefix}_timeout",
        category="scenario",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        observed_status=status or eligible,
        details={"eligible_status": eligible},
    )
    _sim_log(
        scenario,
        "backend",
        f"order {order_db_id} {phase_label} observe window expired — backend did NOT auto-cancel "
        f"(status={status or eligible})",
        level="warn",
    )
    return "timeout", status or eligible


async def _finish_backend_auto_cancel_observe(
    recorder: RunRecorder,
    *,
    scenario: str,
    order: dict[str, Any],
    cancel_seconds: float,
    outcome: BackendAutoCancelObserveOutcome,
    terminal_status: str,
    observer: WebsocketObserver,
    ws_step: str,
    timeout_note: str,
    success_note: str,
    terminal_early_note: str,
) -> None:
    if outcome == "timeout":
        recorder.record_issue(
            severity="warning",
            code="auto_cancel_not_observed",
            actor="backend",
            scenario=scenario,
            step=f"{scenario}_observe_countdown",
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            message=timeout_note,
        )
        recorder.finish_scenario(
            scenario,
            verdict="unsupported",
            actual_final_status=str(terminal_status or "unknown"),
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            note=(
                "Diagnostic: backend auto-cancel was not observed inside the "
                "configured window (does not fail the overall run)."
            ),
        )
        return

    if outcome == "terminal_early":
        _finish_checked(
            recorder,
            scenario,
            actual_final_status=str(terminal_status or "unknown"),
            order_db_id=order["order_db_id"],
            order_ref=order["order_ref"],
            note=terminal_early_note.format(terminal_status=terminal_status),
        )
        return

    ws_timeout = cancel_seconds + 30.0
    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step=ws_step,
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        expected_status="cancelled",
        sources={"user_orders", "store_orders"},
        phase="result",
        timeout_seconds=ws_timeout,
    ):
        return

    _finish_checked(
        recorder,
        scenario,
        actual_final_status="cancelled",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        note=success_note,
    )


async def _run_backend_auto_cancel(
    client: httpx.AsyncClient,
    *,
    user_session: user_sim.UserSession,
    store_session: store_sim.StoreSession,
    fixtures: user_sim.UserFixtures,
    recorder: RunRecorder,
    timing: TimingProfile,
    observer: WebsocketObserver,
) -> None:
    scenario = "backend_auto_cancel"
    cancel_seconds = timing.auto_cancel_wait_seconds
    recorder.start_scenario(
        scenario,
        expected_final_status="cancelled",
        note=(
            "Diagnostic: store tablet idle on pending; observe whether backend or "
            f"customer moves the order to cancelled within {cancel_seconds:.0f}s."
        ),
    )
    _sim_log(scenario, "user", "placing order (store will not act — watching for backend auto-cancel) …")
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
        _sim_log(scenario, "user", "order placement failed — could not create order", level="error")
        recorder.finish_scenario(
            scenario,
            verdict="unsupported",
            actual_final_status="placement_failed",
            note="Order could not be created.",
        )
        return

    _sim_log(scenario, "user", f"order {order['order_ref']} created ✓ — withholding store action, watching for backend cancel …", level="success")
    if not await _wait_for_ws_gate(
        observer,
        recorder=recorder,
        scenario=scenario,
        step="wait_pending_before_backend_auto_cancel",
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

    recorder.record_event(
        actor="store",
        action="withhold_store_action",
        category="scenario",
        scenario=scenario,
        step="withhold_store_action",
        order_db_id=order["order_db_id"],
        order_ref=order["order_ref"],
        details={
            "reason": "Waiting to see whether backend auto-cancels the untouched pending order."
        },
        track_order=False,
    )

    outcome, terminal_status = await _run_backend_auto_cancel_observe_countdown(
        client,
        user_session=user_session,
        order_db_id=int(order["order_db_id"]),
        order_ref=str(order["order_ref"]),
        recorder=recorder,
        scenario=scenario,
        total_seconds=cancel_seconds,
        event_prefix="pending_backend_auto_cancel",
        phase_label="pending",
        eligible_status="pending",
    )

    await _finish_backend_auto_cancel_observe(
        recorder,
        scenario=scenario,
        order=order,
        cancel_seconds=cancel_seconds,
        outcome=outcome,
        terminal_status=terminal_status,
        observer=observer,
        ws_step="wait_pending_backend_auto_cancel",
        timeout_note=(
            "Backend or customer did not cancel the untouched pending order "
            "within the diagnostic window."
        ),
        success_note="Backend auto-cancelled the untouched pending order.",
        terminal_early_note=(
            "Order left pending before backend/customer cancelled (status={terminal_status})."
        ),
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
            severity="warning",
            code="new_user_not_created",
            failure_class="precondition",
            actor="user",
            scenario=scenario,
            step="setup_account",
            message=(
                "The phone number was already setup_complete=true, so this did "
                "not prove the new-user account creation path."
            ),
        )
        recorder.finish_scenario(
            scenario,
            verdict="unsupported",
            actual_final_status="account_already_setup",
            note="Selected phone is already setup_complete and cannot prove fresh signup.",
        )
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
    store_sessions_by_subentity_id: dict[int, store_sim.StoreSession] | None = None,
) -> None:
    saved = _save_payment_config()
    try:
        effective_store_session = store_session
        effective_fixtures = fixtures

        async def _recover_coupon_by_store_retry() -> tuple[bool, bool]:
            nonlocal effective_store_session, effective_fixtures
            if config.SIM_STORE_EXPLICIT:
                return False, False
            if config.SIM_PREFLIGHT_STRATEGY != "auto_recover":
                return False, False
            candidate_ids = [
                candidate
                for candidate in _trace_store_candidates()
                if candidate
                and str(candidate) != str(effective_store_session.store_login_id or config.STORE_ID or "")
            ]
            api_fault_seen = False
            for candidate_id in candidate_ids:
                recorder.record_decision(
                    actor="trace",
                    action="retry_coupon_with_alternate_store",
                    status="called",
                    reason="coupon_missing_try_next_store",
                    message=f"Coupon unavailable on current store context; trying alternate store {candidate_id}.",
                    scenario=scenario,
                    step="checkout_coupon",
                    reason_code="coupon_missing_try_next_store",
                    reason_message="Attempting alternate store context for coupon flow.",
                    next_action="bootstrap_next_store",
                    run_continued=True,
                    failure_class="precondition",
                )
                try:
                    next_store = await _bootstrap_store_auth(
                        client,
                        recorder,
                        store_id=candidate_id,
                    )
                    next_fixtures = await user_sim.bootstrap_fixtures(
                        client,
                        session=user_session,
                        store_token=next_store.last_mile_token,
                        subentity=next_store.subentity,
                        recorder=recorder,
                        subentity_id=next_store.store_id,
                    )
                except store_sim.HttpApiError as exc:
                    failure_class = classify_http_status(exc.status_code)
                    recorder.record_issue(
                        severity="error" if failure_class == "api_fault" else "warning",
                        code="coupon_retry_store_api_error",
                        failure_class=failure_class,
                        actor="trace",
                        scenario=scenario,
                        step="checkout_coupon",
                        message=(
                            f"Alternate store {candidate_id} could not be used during coupon recovery: {exc}"
                        ),
                    )
                    if failure_class == "api_fault":
                        api_fault_seen = True
                    continue
                except RuntimeError as exc:
                    failure_class = classify_issue(
                        code="coupon_retry_store_unusable",
                        message=str(exc),
                        default="precondition",
                    )
                    recorder.record_issue(
                        severity="error" if failure_class == "api_fault" else "warning",
                        code="coupon_retry_store_unusable",
                        failure_class=failure_class,
                        actor="trace",
                        scenario=scenario,
                        step="checkout_coupon",
                        message=(
                            f"Alternate store {candidate_id} could not be used during coupon recovery: {exc}"
                        ),
                    )
                    if failure_class == "api_fault":
                        api_fault_seen = True
                    continue
                recorder.set_store_identity(
                    subentity_id=next_store.store_id,
                    login_id=next_store.store_login_id or candidate_id,
                    raw_store=next_store.subentity,
                )
                if store_sessions_by_subentity_id is not None:
                    store_sessions_by_subentity_id[next_store.store_id] = next_store
                recorder.set_fixtures(next_fixtures)
                effective_store_session = next_store
                effective_fixtures = next_fixtures
                coupon_ready = await _ensure_coupon_for_scenario(
                    client,
                    scenario=scenario,
                    user_session=user_session,
                    fixtures=effective_fixtures,
                    recorder=recorder,
                )
                if coupon_ready and config.SIM_COUPON_ID is not None:
                    return True, api_fault_seen
            return False, api_fault_seen

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
                fixtures=effective_fixtures,
                recorder=recorder,
            )
            if not coupon_ready:
                recovered, api_fault_seen = await _recover_coupon_by_store_retry()
                if recovered:
                    coupon_ready = True
                elif api_fault_seen and is_api_only(config.SIM_FAILURE_POLICY):
                    raise RuntimeError(
                        "Coupon recovery encountered API fault on alternate store candidate(s)."
                    )
                else:
                    recorder.start_scenario(scenario, expected_final_status="completed")
                    recorder.finish_scenario(
                        scenario,
                        verdict="unsupported",
                        actual_final_status="coupon_missing",
                        note="No coupon available in this context; scenario skipped in api_only mode.",
                    )
                    return
            if config.SIM_COUPON_ID is None:
                recorder.start_scenario(scenario, expected_final_status="completed")
                recorder.record_issue(
                    severity="warning",
                    code="coupon_required",
                    failure_class="precondition",
                    actor="user",
                    scenario=scenario,
                    step="checkout_coupon",
                    message="SIM_COUPON_ID is required for paid coupon checkout.",
                )
                recorder.finish_scenario(
                    scenario,
                    verdict="unsupported",
                    actual_final_status="coupon_missing",
                    note="Coupon precondition missing for paid coupon path.",
                )
                return
        elif scenario == "returning_free_with_coupon":
            config.SIM_PAYMENT_MODE = "free"
            config.SIM_PAYMENT_CASE = "free_with_coupon"
            config.SIM_FREE_ORDER_AMOUNT = 0.0
            coupon_ready = await _ensure_coupon_for_scenario(
                client,
                scenario=scenario,
                user_session=user_session,
                fixtures=effective_fixtures,
                recorder=recorder,
            )
            if not coupon_ready:
                recovered, api_fault_seen = await _recover_coupon_by_store_retry()
                if recovered:
                    coupon_ready = True
                elif api_fault_seen and is_api_only(config.SIM_FAILURE_POLICY):
                    raise RuntimeError(
                        "Coupon recovery encountered API fault on alternate store candidate(s)."
                    )
                else:
                    recorder.start_scenario(scenario, expected_final_status="completed")
                    recorder.finish_scenario(
                        scenario,
                        verdict="unsupported",
                        actual_final_status="coupon_missing",
                        note="No coupon available in this context; scenario skipped in api_only mode.",
                    )
                    return
            if config.SIM_COUPON_ID is None:
                recorder.start_scenario(scenario, expected_final_status="completed")
                recorder.record_issue(
                    severity="warning",
                    code="coupon_required",
                    failure_class="precondition",
                    actor="user",
                    scenario=scenario,
                    step="checkout_coupon",
                    message="SIM_COUPON_ID is required for free coupon checkout.",
                )
                recorder.finish_scenario(
                    scenario,
                    verdict="unsupported",
                    actual_final_status="coupon_missing",
                    note="Coupon precondition missing for free coupon path.",
                )
                return
        await _run_completed(
            client,
            user_session=user_session,
            store_session=effective_store_session,
            fixtures=effective_fixtures,
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
    timing = resolve_effective_timing_profile(timing_profile)
    resolved = resolve_trace_scenarios(suite=suite, scenarios=scenarios)
    _sim_log("bootstrap", "trace", f"running scenarios: {', '.join(resolved)} (timing={timing.name})")
    actors = getattr(config, "SIM_ACTORS", {}) or {}
    actor_users = actors.get("users", [])
    failure_policy = getattr(config, "SIM_FAILURE_POLICY", "api_only")
    preflight_strategy = getattr(config, "SIM_PREFLIGHT_STRATEGY", "auto_recover")
    if not actor_users:
        message = "No users were found in the selected plan. Trace runs require users defined in plan users[]."
        if is_api_only(failure_policy) and not is_hard_stop(preflight_strategy):
            recorder.record_issue(
                severity="warning",
                code="plan_users_missing",
                failure_class="precondition",
                actor="system",
                scenario=resolved[0] if resolved else None,
                step="plan_validation",
                message=message,
            )
        else:
            raise RuntimeError(message)
    allowed_phones = {str(user.get("phone")) for user in actor_users if isinstance(user, dict) and user.get("phone")}
    configured_phone = str(getattr(config, "USER_PHONE_NUMBER", "") or "").strip()
    if configured_phone and allowed_phones and configured_phone not in allowed_phones:
        message = f"Configured phone {configured_phone!r} is not present in selected plan users[]."
        if is_api_only(failure_policy) and not is_hard_stop(preflight_strategy):
            recorder.record_issue(
                severity="warning",
                code="plan_user_phone_mismatch",
                failure_class="precondition",
                actor="system",
                scenario=resolved[0] if resolved else None,
                step="plan_validation",
                message=message,
            )
        else:
            raise RuntimeError(message)

    _sim_log("bootstrap", "trace", "bootstrapping auth …")
    bootstrap_scenario = "new_user_setup" if "new_user_setup" in resolved else None
    try:
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
    except RuntimeError as exc:
        timeout_fatal = bool(config.SIM_TIMEOUT_FAILS) and (
            isinstance(exc, app_probes.ProbeTimeoutFatalError)
            or str(getattr(exc, "reason_code", "")).strip().lower() == "http_timeout"
        )
        if timeout_fatal:
            raise
        hard_stop = is_hard_stop(config.SIM_PREFLIGHT_STRATEGY)
        failure_class = classify_issue(
            code="trace_bootstrap_failed",
            message=str(exc),
            default="precondition",
        )
        if hard_stop or not is_api_only(config.SIM_FAILURE_POLICY) or failure_class == "api_fault":
            raise
        recorder.record_issue(
            severity="warning",
            code="trace_bootstrap_precondition",
            failure_class="precondition",
            actor="trace",
            scenario="bootstrap",
            step="bootstrap",
            message=f"Trace bootstrap precondition prevented full run: {exc}",
        )
        for name in resolved:
            if name == "bootstrap":
                continue
            recorder.start_scenario(name)
            recorder.finish_scenario(
                name,
                verdict="unsupported",
                actual_final_status="precondition_unmet",
                note="Scenario skipped because bootstrap preconditions were not met in api_only mode.",
            )
        return

    order_scenarios = {
        "completed",
        "rejected",
        "cancelled",
        "backend_auto_cancel",
        "place_order",
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
    store_sessions_by_subentity_id: dict[int, store_sim.StoreSession] = {
        store_session.store_id: store_session
    }
    unresolved_orders: list[dict[str, Any]] = []
    websocket_health_task: asyncio.Task[None] | None = None
    async with httpx.AsyncClient() as client:
        if observer is not None:
            await observer.start()
            if config.SIM_ENFORCE_WEBSOCKET_GATES:
                try:
                    startup = await observer.wait_for_sources_connected(
                        sources=set(REQUIRED_WEBSOCKET_SOURCES),
                    )
                except RuntimeError as exc:
                    failure_code = _gate_failure_code(exc)
                    recorder.record_issue(
                        severity="error",
                        code=failure_code,
                        actor="websocket",
                        scenario="bootstrap",
                        step="websocket_startup_gate",
                        message=f"Required websocket channels did not become active: {exc}",
                        details={
                            "required_sources": sorted(REQUIRED_WEBSOCKET_SOURCES),
                            "enforced": True,
                        },
                    )
                    raise RuntimeError(
                        "websocket_enforcement_startup_failed: "
                        f"required_sources={sorted(REQUIRED_WEBSOCKET_SOURCES)} reason={exc}"
                    ) from exc

                recorder.record_event(
                    actor="websocket",
                    action="websocket_startup_gate_ready",
                    category="websocket_gate",
                    scenario="bootstrap",
                    step="websocket_startup_gate",
                    details={
                        "required_sources": startup.get("required_sources"),
                        "connected_sources": startup.get("connected_sources"),
                        "enforced": True,
                    },
                    track_order=False,
                )
                websocket_health_task = asyncio.create_task(
                    observer.monitor_required_sources(
                        sources=set(REQUIRED_WEBSOCKET_SOURCES),
                    )
                )
        if _is_menus_flow_run(resolved) and fixtures is not None:
            fixtures = await _provision_menus_flow_inventory(
                client,
                store_session=store_session,
                user_session=user_session,
                recorder=recorder,
            )
        try:
            for name in resolved:
                if websocket_health_task is not None and websocket_health_task.done():
                    try:
                        await websocket_health_task
                    except RuntimeError as exc:
                        failure_code = _gate_failure_code(exc)
                        recorder.record_issue(
                            severity="error",
                            code=failure_code,
                            actor="websocket",
                            scenario=name,
                            step="websocket_runtime_gate",
                            message=(
                                "Required websocket channels dropped and did not recover "
                                f"within retry window: {exc}"
                            ),
                            details={
                                "required_sources": sorted(REQUIRED_WEBSOCKET_SOURCES),
                                "enforced": True,
                            },
                        )
                        raise RuntimeError(
                            "websocket_enforcement_runtime_failed: "
                            f"required_sources={sorted(REQUIRED_WEBSOCKET_SOURCES)} reason={exc}"
                        ) from exc
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
                elif name == "place_order":
                    await _run_place_order(
                        client,
                        user_session=user_session,
                        fixtures=fixtures,
                        recorder=recorder,
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
                elif name == "backend_auto_cancel":
                    await _run_backend_auto_cancel(
                        client,
                        user_session=user_session,
                        store_session=store_session,
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
                        store_sessions_by_subentity_id=store_sessions_by_subentity_id,
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
            unresolved_orders = await order_contract.enforce_order_closure(
                recorder=recorder,
                user_sessions_by_id={user_session.user_id: user_session},
                store_sessions_by_subentity_id=store_sessions_by_subentity_id,
                scenario="simulation_cleanup",
            )
        finally:
            if websocket_health_task is not None:
                websocket_health_task.cancel()
                await asyncio.gather(websocket_health_task, return_exceptions=True)
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
    if unresolved_orders:
        unresolved_ids = ", ".join(
            f"{item['order_db_id']}:{item['status']}" for item in unresolved_orders
        )
        raise RuntimeError(
            "order_contract_failed: unresolved non-terminal orders remain after cleanup: "
            f"{unresolved_ids}"
        )
