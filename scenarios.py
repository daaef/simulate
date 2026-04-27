"""Scenario and timing configuration for simulation modes."""

from __future__ import annotations

from dataclasses import dataclass
import random


TRACE_SCENARIOS = ("completed", "rejected", "cancelled", "auto_cancel")
TRACE_SUITES = {
    "core": ("completed", "rejected", "cancelled"),
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
        auto_cancel_wait_seconds=180.0,
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
    return unique


def resolve_timing_profile(name: str) -> TimingProfile:
    profile = TIMING_PROFILES.get(name)
    if profile is None:
        raise RuntimeError(
            f"Unsupported timing profile {name!r}. "
            f"Expected one of {', '.join(sorted(TIMING_PROFILES))}."
        )
    return profile
