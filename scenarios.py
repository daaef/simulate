"""Scenario and timing configuration for simulation modes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import random

import config


TRACE_SCENARIOS = (
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
    "store_first_setup",
    "store_accept",
    "store_reject",
    "robot_complete",
    "app_bootstrap",
    "store_dashboard",
    "receipt_review_reorder",
)
TRACE_SUITES = {
    "core": ("completed", "rejected", "cancelled", "backend_auto_cancel"),
    "payments": (
        "returning_paid_no_coupon",
        "returning_paid_with_coupon",
        "returning_free_with_coupon",
    ),
    "menus": (
        "menu_available",
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
    ),
    "store": ("store_first_setup", "store_accept", "store_reject", "backend_auto_cancel"),
    "audit": (
        "app_bootstrap",
        "new_user_setup",
        "store_first_setup",
        "store_dashboard",
        "menu_available",
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
        "returning_paid_no_coupon",
        "returning_paid_with_coupon",
        "returning_free_with_coupon",
        "store_accept",
        "store_reject",
        "robot_complete",
        "receipt_review_reorder",
        "backend_auto_cancel",
    ),
    "doctor": (
        "app_bootstrap",
        "store_first_setup",
        "store_dashboard",
        "menu_available",
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
        "returning_paid_no_coupon",
        "store_accept",
        "store_reject",
        "robot_complete",
        "receipt_review_reorder",
        "backend_auto_cancel",
    ),
    "full": (
        "app_bootstrap",
        "new_user_setup",
        "store_first_setup",
        "store_dashboard",
        "menu_available",
        "menu_unavailable",
        "menu_sold_out",
        "menu_store_closed",
        "returning_paid_no_coupon",
        "returning_paid_with_coupon",
        "returning_free_with_coupon",
        "store_accept",
        "store_reject",
        "robot_complete",
        "receipt_review_reorder",
        "completed",
        "rejected",
        "cancelled",
        "backend_auto_cancel",
    ),
}


@dataclass(frozen=True)
class DelayRange:
    min_seconds: float
    max_seconds: float

    def pick(self) -> float:
        return random.uniform(self.min_seconds, self.max_seconds)


@dataclass(frozen=True)
class TimingProfile:
    name: str
    store_decision_delay: DelayRange
    store_prep_delay: DelayRange
    robot_delays: dict[str, DelayRange]
    auto_cancel_wait_seconds: float

    def robot_delay(self, status: str) -> float:
        delay = self.robot_delays.get(status)
        if delay is None:
            raise KeyError(f"No delay configured for robot status {status!r}")
        return delay.pick()


TIMING_PROFILES = {
    "fast": TimingProfile(
        name="fast",
        store_decision_delay=DelayRange(0.2, 0.5),
        store_prep_delay=DelayRange(0.2, 0.5),
        robot_delays={
            "enroute_pickup": DelayRange(0.2, 0.5),
            "robot_arrived_for_pickup": DelayRange(0.2, 0.4),
            "enroute_delivery": DelayRange(0.2, 0.6),
            "robot_arrived_for_delivery": DelayRange(0.2, 0.4),
            "completed": DelayRange(0.2, 0.3),
        },
        auto_cancel_wait_seconds=30.0,
    ),
    "realistic": TimingProfile(
        name="realistic",
        store_decision_delay=DelayRange(3.0, 12.0),
        store_prep_delay=DelayRange(20.0, 90.0),
        robot_delays={
            "enroute_pickup": DelayRange(20.0, 60.0),
            "robot_arrived_for_pickup": DelayRange(5.0, 20.0),
            "enroute_delivery": DelayRange(30.0, 120.0),
            "robot_arrived_for_delivery": DelayRange(5.0, 20.0),
            "completed": DelayRange(2.0, 8.0),
        },
        auto_cancel_wait_seconds=120.0,
    ),
}


def resolve_trace_scenarios(
    *,
    suite: str | None,
    scenarios: list[str] | tuple[str, ...] | None,
) -> list[str]:
    resolved: list[str] = []
    if suite:
        resolved.extend(TRACE_SUITES.get(suite, ()))
    if scenarios:
        resolved.extend(scenarios)

    if not resolved:
        resolved.extend(TRACE_SUITES["core"])

    unique: list[str] = []
    for name in resolved:
        if name not in TRACE_SCENARIOS:
            raise RuntimeError(
                f"Unsupported trace scenario {name!r}. "
                f"Expected one of {', '.join(TRACE_SCENARIOS)}."
            )
        if name not in unique:
            unique.append(name)
    if "place_order" in unique and len(unique) > 1:
        raise RuntimeError(
            "place_order cannot be combined with other trace scenarios or suites."
        )
    return unique


def resolve_timing_profile(name: str) -> TimingProfile:
    profile = TIMING_PROFILES.get(name)
    if profile is None:
        raise RuntimeError(
            f"Unsupported timing profile {name!r}. "
            f"Expected one of {', '.join(sorted(TIMING_PROFILES))}."
        )
    return profile


def resolve_effective_timing_profile(name: str) -> TimingProfile:
    """Timing profile with plan-only auto_cancel awaiting-payment observe override when set."""
    profile = resolve_timing_profile(name)
    override = getattr(config, "SIM_PLAN_STORE_AUTO_CANCEL_SECONDS", None)
    if override is None:
        return profile
    return replace(profile, auto_cancel_wait_seconds=float(override))
