from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionStatus = Literal["called", "blocked", "skipped", "recovered", "failed"]


@dataclass(frozen=True)
class ActionDecision:
    action: str
    status: DecisionStatus
    reason: str
    message: str
    actor: str | None = None
    scenario: str | None = None
    step: str | None = None
    required: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def should_call(self) -> bool:
        return self.status == "called"


def require_fields(
    *,
    action: str,
    actor: str,
    fields: dict[str, Any],
    scenario: str | None = None,
    step: str | None = None,
) -> ActionDecision:
    required = {
        key: value is not None and not (isinstance(value, str) and not value.strip())
        for key, value in fields.items()
    }
    missing = [key for key, ok in required.items() if not ok]

    if missing:
        return ActionDecision(
            action=action,
            actor=actor,
            scenario=scenario,
            step=step,
            status="skipped",
            reason="missing_required_data",
            message=f"{action} was skipped because required data is missing: {', '.join(missing)}.",
            required=required,
            details={"missing": missing},
        )

    return ActionDecision(
        action=action,
        actor=actor,
        scenario=scenario,
        step=step,
        status="called",
        reason="preflight_passed",
        message=f"{action} has all required data and can be called.",
        required=required,
    )