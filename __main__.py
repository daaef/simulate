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
from reporting import RunRecorder
import robot_sim
import store_sim
import trace_runner
import user_sim
from websocket_observer import validate_websocket_events

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fainzy last-mile order simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
    return parser.parse_args()


def _apply_args(args: argparse.Namespace) -> None:
    config.SIM_RUN_MODE = args.mode
    config.SIM_TRACE_SUITE = args.suite
    config.SIM_TRACE_SCENARIOS = [item.lower() for item in (args.scenario or config.SIM_TRACE_SCENARIOS)]
    config.SIM_TIMING_PROFILE = args.timing
    config.N_USERS = args.users
    config.ORDER_INTERVAL_SECONDS = args.interval
    config.REJECT_RATE = args.reject
    config.SIM_ORDERS = args.orders
    config.SIM_CONTINUOUS = args.continuous


def _validate_config() -> None:
    if config.SIM_RUN_MODE not in {"load", "trace"}:
        raise RuntimeError("SIM_RUN_MODE must be either load or trace.")
    if config.SIM_PAYMENT_MODE not in {"stripe", "free"}:
        raise RuntimeError("SIM_PAYMENT_MODE must be either stripe or free.")
    if config.SIM_PAYMENT_MODE == "stripe" and not config.STRIPE_SECRET_KEY:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is required when SIM_PAYMENT_MODE=stripe. "
            "The key must be from the same Stripe test account used by backend webhooks."
        )
    if config.SIM_PAYMENT_MODE == "free" and config.SIM_FREE_ORDER_AMOUNT > 0:
        raise RuntimeError(
            "SIM_FREE_ORDER_AMOUNT must be 0 or less for free-order simulation."
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
    # Phase 1: bootstrap user auth + store auth + fixtures (sequential).
    # This sets config.SUBENTITY_ID so store/robot sims can connect to the
    # correct websocket channel.
    console.print("[cyan]main:[/] Bootstrapping user + store auth ...")
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

    # Robot needs a store token + SUBENTITY_ID (already set by store auth above).
    async with httpx.AsyncClient() as bootstrap_client:
        robot_session = await robot_sim.bootstrap_auth(bootstrap_client, recorder)

    # Phase 2: launch all three sim workers concurrently.
    user_task = asyncio.create_task(
        user_sim.run(recorder=recorder, session=user_session, fixtures=fixtures)
    )
    store_task = asyncio.create_task(
        store_sim.run(recorder=recorder, session=store_session)
    )
    robot_task = asyncio.create_task(
        robot_sim.run(recorder=recorder, session=robot_session)
    )

    try:
        if config.SIM_CONTINUOUS:
            await asyncio.gather(user_task, store_task, robot_task)
            return

        # In bounded mode, user_sim.run() returns when its order quota is met.
        # After that, give store/robot sims a drain period to finish processing.
        await user_task
        console.print("[bold green]main:[/] User sim finished its order quota.")
        if config.SIM_WEBSOCKET_DRAIN_SECONDS > 0:
            await asyncio.sleep(config.SIM_WEBSOCKET_DRAIN_SECONDS)
    finally:
        for task in (user_task, store_task, robot_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(user_task, store_task, robot_task, return_exceptions=True)


async def main() -> None:
    args = _parse_args()
    _apply_args(args)
    _validate_config()

    console.print(
        Panel.fit(
            f"[bold]Fainzy Order Simulation[/]\n\n"
            f"  Mode        : {config.SIM_RUN_MODE}\n"
            f"  Timing      : {config.SIM_TIMING_PROFILE}\n"
            f"  Users       : {config.N_USERS}\n"
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
