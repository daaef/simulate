"""
Fainzy Order Simulation — Entry Point

Responsibilities:
  - Parse CLI arguments, validate config
  - Launch independent sims (user, store, robot) and trace runner
  - Start the passive WebsocketObserver for reporting
  - Write run artifacts on exit

Each simulator handles its own auth, seeding, and active websocket.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent))

import config
import app_probes
from flow_presets import FLOW_PRESETS, resolve_flow
from interaction_catalog import PAYMENT_CASES
from reporting import RunRecorder
import robot_sim
from scenarios import resolve_trace_scenarios
import store_sim
import trace_runner
import user_sim
from websocket_observer import WebsocketObserver, validate_websocket_events

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fainzy last-mile order simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "flow",
        nargs="?",
        default=None,
        help=(
            "Simple flow preset: "
            + ", ".join(sorted(FLOW_PRESETS))
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["load", "trace"],
        default=config.SIM_RUN_MODE,
        help="Simulation mode",
    )
    parser.add_argument(
        "--suite",
        default=config.SIM_TRACE_SUITE,
        help="Trace suite name. Only used in trace mode.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Trace scenario to run. Repeat to run multiple scenarios.",
    )
    parser.add_argument(
        "--timing",
        choices=["fast", "realistic"],
        default=config.SIM_TIMING_PROFILE,
        help="Timing profile for trace mode",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=config.N_USERS,
        help="Number of concurrent user workers. Load mode only.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=config.ORDER_INTERVAL_SECONDS,
        help="Seconds between each user placing a new order. Load mode only.",
    )
    parser.add_argument(
        "--reject",
        type=float,
        default=config.REJECT_RATE,
        help="Probability (0.0–1.0) that the store rejects an order. Load mode only.",
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=config.SIM_ORDERS,
        help="Total orders to place in bounded load mode.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        default=config.SIM_CONTINUOUS,
        help="Run indefinitely in load mode.",
    )
    parser.add_argument(
        "--phone",
        type=str,
        default=None,
        help="Override user phone number (must be in sim_actors.json).",
    )
    parser.add_argument(
        "--store",
        type=str,
        default=None,
        help="Override store ID, login only this store (must be in sim_actors.json).",
    )
    parser.add_argument(
        "--all-users",
        action="store_true",
        default=False,
        help="Auth and run all users from sim_actors.json.",
    )
    parser.add_argument(
        "--plan",
        type=str,
        default=None,
        help="JSON run plan with users, GPS coordinates, and store IDs.",
    )
    parser.add_argument(
        "--strict-plan",
        action="store_true",
        default=config.SIM_STRICT_PLAN,
        help="Require every plan user to have GPS coordinates and every store to have an ID.",
    )
    parser.add_argument(
        "--skip-app-probes",
        action="store_true",
        default=False,
        help="Skip non-order user app probes such as config, pricing, cards, and coupons.",
    )
    parser.add_argument(
        "--skip-store-dashboard-probes",
        action="store_true",
        default=False,
        help="Skip store dashboard/statistics probes.",
    )
    parser.add_argument(
        "--post-order-actions",
        action="store_true",
        default=config.SIM_RUN_POST_ORDER_ACTIONS,
        help="Run receipt, review, and reorder checks after completed orders.",
    )
    parser.add_argument(
        "--no-auto-provision",
        action="store_true",
        default=False,
        help="Do not auto-create missing store setup/category/menu prerequisites.",
    )
    return parser.parse_args()


_store_from_cli = False
_active_flow = ""


def _has_cli_flag(argv: list[str], *flags: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in argv for flag in flags)


def _explicit_config_overrides(argv: list[str]) -> set[str]:
    mapping = {
        "--mode": "SIM_RUN_MODE",
        "--suite": "SIM_TRACE_SUITE",
        "--scenario": "SIM_TRACE_SCENARIOS",
        "--timing": "SIM_TIMING_PROFILE",
        "--users": "N_USERS",
        "--interval": "ORDER_INTERVAL_SECONDS",
        "--reject": "REJECT_RATE",
        "--orders": "SIM_ORDERS",
        "--continuous": "SIM_CONTINUOUS",
        "--phone": "USER_PHONE_NUMBER",
        "--store": "STORE_ID",
        "--all-users": "ALL_USERS",
        "--strict-plan": "SIM_STRICT_PLAN",
        "--skip-app-probes": "SIM_RUN_APP_PROBES",
        "--skip-store-dashboard-probes": "SIM_RUN_STORE_DASHBOARD_PROBES",
        "--post-order-actions": "SIM_RUN_POST_ORDER_ACTIONS",
        "--no-auto-provision": "SIM_AUTO_PROVISION_FIXTURES",
    }
    return {
        attr
        for flag, attr in mapping.items()
        if _has_cli_flag(argv, flag)
    }


def _apply_args(args: argparse.Namespace) -> None:
    global _store_from_cli, _active_flow
    argv = sys.argv[1:]
    explicit_overrides = _explicit_config_overrides(argv)
    if args.plan:
        config.set_sim_actors_path(args.plan)
    if args.phone:
        config.USER_PHONE_NUMBER = args.phone
    if args.store:
        config.STORE_ID = args.store
        _store_from_cli = True
    config.SIM_STORE_EXPLICIT = _store_from_cli

    actors = config.load_sim_actors(preserve=explicit_overrides)

    if _has_cli_flag(argv, "--mode"):
        config.SIM_RUN_MODE = args.mode
    if _has_cli_flag(argv, "--suite"):
        config.SIM_TRACE_SUITE = args.suite
    if _has_cli_flag(argv, "--scenario"):
        config.SIM_TRACE_SCENARIOS = [item.lower() for item in (args.scenario or [])]
    if _has_cli_flag(argv, "--timing"):
        config.SIM_TIMING_PROFILE = args.timing
    if _has_cli_flag(argv, "--users"):
        config.N_USERS = args.users
    if _has_cli_flag(argv, "--interval"):
        config.ORDER_INTERVAL_SECONDS = args.interval
    if _has_cli_flag(argv, "--reject"):
        config.REJECT_RATE = args.reject
    if _has_cli_flag(argv, "--orders"):
        config.SIM_ORDERS = args.orders
    if _has_cli_flag(argv, "--continuous"):
        config.SIM_CONTINUOUS = args.continuous
    if _has_cli_flag(argv, "--all-users"):
        config.ALL_USERS = args.all_users
    if _has_cli_flag(argv, "--strict-plan"):
        config.SIM_STRICT_PLAN = args.strict_plan
    if _has_cli_flag(argv, "--skip-app-probes"):
        config.SIM_RUN_APP_PROBES = not args.skip_app_probes
    if _has_cli_flag(argv, "--skip-store-dashboard-probes"):
        config.SIM_RUN_STORE_DASHBOARD_PROBES = not args.skip_store_dashboard_probes
    if _has_cli_flag(argv, "--post-order-actions"):
        config.SIM_RUN_POST_ORDER_ACTIONS = args.post_order_actions
    if _has_cli_flag(argv, "--no-auto-provision") and args.no_auto_provision:
        config.SIM_AUTO_PROVISION_FIXTURES = False

    flow_name = args.flow
    if not flow_name:
        explicit_flow_flags = {"--mode", "--suite", "--scenario"}
        if not any(flag in sys.argv[1:] for flag in explicit_flow_flags):
            flow_name = config.SIM_FLOW
    preset = resolve_flow(flow_name)
    if preset is None:
        return

    _active_flow = preset["name"]
    config.SIM_FLOW = _active_flow
    config.SIM_RUN_MODE = preset.get("mode", config.SIM_RUN_MODE)
    if preset.get("suite"):
        config.SIM_TRACE_SUITE = str(preset["suite"])
        config.SIM_TRACE_SCENARIOS = []
    if preset.get("scenarios"):
        config.SIM_TRACE_SUITE = ""
        config.SIM_TRACE_SCENARIOS = [str(item) for item in preset["scenarios"]]
    if "payment_mode" in preset:
        config.SIM_PAYMENT_MODE = str(preset["payment_mode"])
    if "payment_case" in preset:
        config.SIM_PAYMENT_CASE = str(preset["payment_case"])
    if "free_order_amount" in preset:
        config.SIM_FREE_ORDER_AMOUNT = float(preset["free_order_amount"])
    if "coupon_id" in preset:
        coupon_id = preset["coupon_id"]
        config.SIM_COUPON_ID = int(coupon_id) if coupon_id not in {None, ""} else None
    if "post_order_actions" in preset:
        config.SIM_RUN_POST_ORDER_ACTIONS = bool(preset["post_order_actions"])
    config.apply_actor_selection(
        actors,
        user_role=preset.get("user_role"),
        store_id=config.STORE_ID,
    )


def _validate_config() -> None:
    if config.SIM_RUN_MODE not in {"load", "trace"}:
        raise RuntimeError("SIM_RUN_MODE must be either load or trace.")
    if config.SIM_PAYMENT_MODE not in {"stripe", "free"}:
        raise RuntimeError("SIM_PAYMENT_MODE must be either stripe or free.")
    if config.SIM_PAYMENT_CASE not in PAYMENT_CASES:
        raise RuntimeError(
            f"SIM_PAYMENT_CASE must be one of {', '.join(PAYMENT_CASES)}."
        )
    trace_scenarios = (
        resolve_trace_scenarios(
            suite=config.SIM_TRACE_SUITE,
            scenarios=config.SIM_TRACE_SCENARIOS,
        )
        if config.SIM_RUN_MODE == "trace"
        else []
    )
    trace_requires_stripe = any(
        name
        in {
            "completed",
            "returning_paid_no_coupon",
            "returning_paid_with_coupon",
            "store_accept",
            "robot_complete",
            "receipt_review_reorder",
        }
        for name in trace_scenarios
    )
    if (
        config.SIM_PAYMENT_MODE == "stripe"
        and not config.STRIPE_SECRET_KEY
        and (config.SIM_RUN_MODE == "load" or trace_requires_stripe)
    ):
        raise RuntimeError(
            "STRIPE_SECRET_KEY is required when SIM_PAYMENT_MODE=stripe. "
            "The key must be from the same Stripe test account used by backend webhooks."
        )
    if config.SIM_PAYMENT_MODE == "free" and config.SIM_FREE_ORDER_AMOUNT > 0:
        raise RuntimeError(
            "SIM_FREE_ORDER_AMOUNT must be 0 or less for free-order simulation."
        )
    trace_scenarios_for_coupon = set(trace_scenarios)
    if (
        {"returning_paid_with_coupon", "returning_free_with_coupon"}
        & trace_scenarios_for_coupon
        and config.SIM_COUPON_ID is None
        and not config.SIM_AUTO_SELECT_COUPON
    ):
        raise RuntimeError(
            "SIM_COUPON_ID is required for coupon flows. Put it in .env or "
            "sim_actors.json defaults, or enable SIM_AUTO_SELECT_COUPON=true."
        )
    if not 0 <= config.REJECT_RATE <= 1:
        raise RuntimeError("--reject must be between 0.0 and 1.0.")
    if config.SIM_RUN_MODE == "load":
        if config.N_USERS < 1:
            raise RuntimeError("--users must be >= 1.")
        if config.SIM_ORDERS < 1:
            raise RuntimeError("--orders must be >= 1.")
    if config.SIM_RUN_MODE == "trace" and config.SIM_CONTINUOUS:
        raise RuntimeError("--continuous is only supported in load mode.")


async def _run_load_mode(*, recorder: RunRecorder) -> None:
    # Phase 0: Load actors from sim_actors.json (applies defaults to config).
    actors = config.load_sim_actors()
    actor_stores = actors.get("stores", [])
    actor_users = actors.get("users", [])

    if not actor_stores:
        raise RuntimeError(
            "No stores were found in the selected plan. "
            "Load runs require stores explicitly defined in plan stores[]."
        )

    plan_store_ids = [str(store.get("store_id")) for store in actor_stores if store.get("store_id")]
    if _store_from_cli and config.STORE_ID:
        matching = [s for s in actor_stores if s.get("store_id") == config.STORE_ID]
        if not matching:
            raise RuntimeError(
                f"Explicit store {config.STORE_ID!r} is not present in the selected plan stores."
            )
        actor_stores = matching
    elif config.STORE_ID:
        matching = [s for s in actor_stores if s.get("store_id") == config.STORE_ID]
        if matching:
            actor_stores = matching
        else:
            raise RuntimeError(
                f"Configured store {config.STORE_ID!r} is not present in the selected plan stores: {plan_store_ids}."
            )

    # Determine which user(s) to auth.
    if config.ALL_USERS:
        user_phones = [u.get("phone", "") for u in actor_users if u.get("phone")]
    else:
        user_phones = [config.USER_PHONE_NUMBER] if config.USER_PHONE_NUMBER else []
    allowed_phones = {str(u.get("phone")) for u in actor_users if u.get("phone")}
    out_of_plan_users = [phone for phone in user_phones if phone and phone not in allowed_phones]
    if out_of_plan_users:
        raise RuntimeError(
            "All load-run users must be defined in the selected plan users[]. "
            f"Out-of-plan phone(s): {out_of_plan_users}"
        )

    if not user_phones:
        raise RuntimeError(
            "No user phone numbers available. Set USER_PHONE_NUMBER in .env, "
            "add users to sim_actors.json, or use --phone."
        )

    # ── Phase 1: Bootstrap ALL stores ──────────────────────────────────────
    console.print(
        f"[cyan]main:[/] Phase 1 — Logging in {len(actor_stores)} store(s) ..."
    )
    store_sessions: list[store_sim.StoreSession] = []

    async with httpx.AsyncClient() as bootstrap_client:
        if actor_stores:
            for store_cfg in actor_stores:
                sid = store_cfg.get("store_id", "")
                if not sid:
                    continue
                try:
                    ss = await store_sim.bootstrap_auth(
                        bootstrap_client, recorder, store_id=sid
                    )
                    store_sessions.append(ss)
                    if len(store_sessions) == 1:
                        recorder.set_store_identity(
                            subentity_id=ss.store_id,
                            login_id=ss.store_login_id or sid,
                            raw_store=ss.subentity,
                        )
                except Exception as exc:
                    console.print(
                        f"[yellow]main:[/] Store {sid} login failed: {exc}  (skipping)"
                    )

    if not store_sessions:
        raise RuntimeError("No stores could be logged in. Cannot proceed.")

    store_status_restores: list[tuple[store_sim.StoreSession, int]] = []
    if store_sim.provisioning_preflight_enabled():
        console.print(
            f"[cyan]main:[/] Phase 1b — Preparing {len(store_sessions)} store(s) for ordering ..."
        )
        async with httpx.AsyncClient() as preflight_client:
            for store_session in store_sessions:
                original_status = await trace_runner._run_store_first_setup(
                    preflight_client,
                    store_session=store_session,
                    recorder=recorder,
                    scenario=f"load_store_preflight_{store_session.store_id}",
                )
                if original_status is not None:
                    store_status_restores.append((store_session, original_status))

    console.print(
        f"[green]main:[/] {len(store_sessions)} store(s) logged in successfully."
    )

    # ── Phase 2: Bootstrap user(s) ─────────────────────────────────────────
    console.print(
        f"[cyan]main:[/] Phase 2 — Authenticating {len(user_phones)} user(s) ..."
    )
    user_bundles: list[
        tuple[user_sim.UserSession, user_sim.UserFixtures]
    ] = []

    # Use first store with valid GPS for initial fixtures.
    primary_store = store_sessions[0]
    user_by_phone = {
        str(user.get("phone")): user
        for user in actor_users
        if user.get("phone")
    }

    async with httpx.AsyncClient() as bootstrap_client:
        for phone in user_phones:
            try:
                us = await user_sim.bootstrap_auth(
                    bootstrap_client, recorder, phone=phone
                )
                user_phone = (
                    us.user.get("phone_number")
                    or us.user.get("phone")
                    or phone
                    or getattr(config, "USER_PHONE_NUMBER", "")
                )
                recorder.set_user_identity(
                    user_id=us.user_id,
                    phone=str(user_phone) if user_phone else None,
                    raw_user=us.user,
                )
                user_lat, user_lng = config.actor_gps(user_by_phone.get(phone))
                fixtures = await user_sim.bootstrap_fixtures(
                    bootstrap_client,
                    session=us,
                    store_token=primary_store.last_mile_token,
                    subentity=primary_store.subentity,
                    recorder=recorder,
                    lat=user_lat,
                    lng=user_lng,
                    subentity_id=primary_store.store_id,
                )
                if config.SIM_RUN_APP_PROBES:
                    await app_probes.run_user_app_probes(
                        bootstrap_client,
                        recorder=recorder,
                        user_id=us.user_id,
                        user_token=us.token,
                        user=us.user,
                        token_source=us.token_source,
                        currency=fixtures.currency,
                        scenario="load_app_probes",
                    )
                user_bundles.append((us, fixtures))
            except Exception as exc:
                console.print(
                    f"[yellow]main:[/] User {phone} auth failed: {exc}  (skipping)"
                )

    if not user_bundles:
        raise RuntimeError("No users could be authenticated. Cannot proceed.")

    console.print(
        f"[green]main:[/] {len(user_bundles)} user(s) authenticated successfully."
    )

    # ── Phase 3: Build robot sessions from store sessions ──────────────────
    robot_sessions: list[robot_sim.RobotSession] = []
    async with httpx.AsyncClient() as bootstrap_client:
        for ss in store_sessions:
            if config.SIM_RUN_STORE_DASHBOARD_PROBES:
                await app_probes.run_store_dashboard_probes(
                    bootstrap_client,
                    recorder=recorder,
                    subentity_id=ss.store_id,
                    store_token=ss.last_mile_token,
                    token_source=ss.token_source,
                    scenario="load_store_dashboard",
                )
            rs = await robot_sim.bootstrap_auth(
                bootstrap_client, recorder,
                store_token=ss.last_mile_token,
                subentity_id=ss.store_id,
            )
            robot_sessions.append(rs)

    # ── Phase 4: Launch all workers concurrently ───────────────────────────
    console.print(
        f"[bold green]main:[/] Launching {len(user_bundles)} user worker(s), "
        f"{len(store_sessions)} store listener(s), "
        f"{len(robot_sessions)} robot listener(s) ..."
    )

    all_tasks: list[asyncio.Task] = []

    primary_user_id = user_bundles[0][0].user_id
    primary_store_id = store_sessions[0].store_id
    observer = WebsocketObserver(
        recorder=recorder,
        user_id=primary_user_id,
        store_id=primary_store_id,
    )
    await observer.start()

    # Store listeners.
    for ss in store_sessions:
        all_tasks.append(
            asyncio.create_task(store_sim.run(recorder=recorder, session=ss))
        )

    # Robot listeners.
    all_tasks.append(
        asyncio.create_task(
            robot_sim.run(recorder=recorder, sessions=robot_sessions)
        )
    )

    # User workers.
    user_tasks: list[asyncio.Task] = []
    for us, fixtures in user_bundles:
        t = asyncio.create_task(
            user_sim.run(
                recorder=recorder,
                session=us,
                fixtures=fixtures,
                store_sessions=store_sessions,
            )
        )
        user_tasks.append(t)
        all_tasks.append(t)

    try:
        if config.SIM_CONTINUOUS:
            await asyncio.gather(*all_tasks)
            return

        # In bounded mode, wait for all user tasks to finish, then drain.
        await asyncio.gather(*user_tasks)
        console.print("[bold green]main:[/] All user sim(s) finished.")
        if config.SIM_WEBSOCKET_DRAIN_SECONDS > 0:
            await asyncio.sleep(config.SIM_WEBSOCKET_DRAIN_SECONDS)
    finally:
        await observer.stop()
        recorder.set_websocket_coverage(observer.coverage_summary())

        for task in all_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)
        if store_status_restores:
            async with httpx.AsyncClient() as cleanup_client:
                for store_session, original_status in store_status_restores:
                    await store_sim.restore_store_status(
                        cleanup_client,
                        session=store_session,
                        original_status=original_status,
                        recorder=recorder,
                        scenario="simulation_cleanup",
                    )


async def main() -> None:
    args = _parse_args()
    _apply_args(args)
    _validate_config()

    all_users_label = "all" if config.ALL_USERS else "1"
    console.print(
        Panel.fit(
            f"[bold]Fainzy Order Simulation[/]\n\n"
            f"  Mode        : {config.SIM_RUN_MODE}\n"
            f"  Flow        : {_active_flow or config.SIM_FLOW or 'custom'}\n"
            f"  Plan        : {config.SIM_ACTORS_PATH}\n"
            f"  Timing      : {config.SIM_TIMING_PROFILE}\n"
            f"  User workers: {config.N_USERS}\n"
            f"  Users       : {all_users_label} ({'--all-users' if config.ALL_USERS else config.USER_PHONE_NUMBER or 'auto'})\n"
            f"  Store       : {config.STORE_ID or 'all from sim_actors.json'}\n"
            f"  Interval    : {config.ORDER_INTERVAL_SECONDS}s\n"
            f"  Orders      : {'continuous' if config.SIM_CONTINUOUS else config.SIM_ORDERS}\n"
            f"  Reject rate : {config.REJECT_RATE:.0%}\n"
            f"  Payment     : {config.SIM_PAYMENT_MODE}\n"
            f"  Base URL    : {config.LASTMILE_BASE_URL}",
            title="[cyan]Starting[/]",
            border_style="cyan",
        )
    )

    recorder = RunRecorder.bootstrap()

    console.print("[bold green]main:[/] Launching simulation ...\n")
    try:
        if config.SIM_RUN_MODE == "trace":
            await trace_runner.run(
                recorder=recorder,
                suite=config.SIM_TRACE_SUITE,
                scenarios=config.SIM_TRACE_SCENARIOS,
                timing_profile=config.SIM_TIMING_PROFILE,
            )
        else:
            await _run_load_mode(recorder=recorder)
    finally:
        validate_websocket_events(recorder)
        events_path, report_path, story_path = recorder.write()
        console.print(f"[green]main:[/] events: {events_path}")
        console.print(f"[green]main:[/] report: {report_path}")
        console.print(f"[green]main:[/] story: {story_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        console.print(f"[bold red]Simulation failed:[/] {exc}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        console.print("\n[bold red]Simulation stopped.[/]")
