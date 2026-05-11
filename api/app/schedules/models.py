from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


ScheduleType = Literal["simple", "campaign"]
ScheduleStatus = Literal["active", "paused", "disabled", "deleted"]
Cadence = Literal["hourly", "daily", "weekdays", "weekly", "monthly", "custom"]
Period = Literal["hourly", "daily", "weekly", "monthly"]
StopRule = Literal["never", "end_at", "duration"]
RepeatRule = Literal["none", "daily", "weekly", "monthly", "annually", "weekdays", "custom"]
FailurePolicy = Literal["continue", "stop"]
ExecutionMode = Literal["saved_profile", "exact_snapshot"]


class CampaignStep(BaseModel):
    profile_id: int
    repeat_count: int = Field(default=1, ge=1, le=100)
    spacing_seconds: int = Field(default=0, ge=0)
    timeout_seconds: int = Field(default=900, ge=1)
    failure_policy: FailurePolicy = "continue"
    execution_mode: ExecutionMode = "saved_profile"


class ScheduleUpsertRequest(BaseModel):
    name: str
    description: Optional[str] = None
    schedule_type: ScheduleType = "simple"
    profile_id: Optional[int] = None
    anchor_start_at: Optional[str] = None
    period: Optional[Period] = None
    stop_rule: Optional[StopRule] = None
    end_at: Optional[str] = None
    duration_seconds: Optional[int] = Field(default=None, ge=1)
    runs_per_period: int = Field(default=1, ge=1)
    repeat: Optional[RepeatRule] = None
    all_day: bool = False
    recurrence_config: Optional[dict[str, Any]] = None
    run_slots: List[dict[str, Any]] = Field(default_factory=list)
    cadence: Cadence = "daily"
    timezone: str = "UTC"
    active_from: Optional[str] = None
    active_until: Optional[str] = None
    run_window_start: Optional[str] = None
    run_window_end: Optional[str] = None
    custom_anchor_at: Optional[str] = None
    custom_every_n_days: Optional[int] = Field(default=None, ge=1)
    blackout_dates: List[str] = Field(default_factory=list)
    failure_policy: FailurePolicy = "continue"
    campaign_steps: List[CampaignStep] = Field(default_factory=list)
