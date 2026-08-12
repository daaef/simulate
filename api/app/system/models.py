from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


TimezonePolicyMode = Literal["all", "allowlist"]


class TimezonePolicyUpdateRequest(BaseModel):
    mode: TimezonePolicyMode = "all"
    allowed_timezones: Optional[List[str]] = Field(default=None)


EmailEventTrigger = Literal["run_failed", "schedule_launch_failed", "critical_alert", "socket_failure"]


class EmailSettingsPayload(BaseModel):
    email_enabled: bool = False
    email_from_email: str = ""
    email_from_name: str = ""
    email_subject_prefix: str = ""
    email_recipients: List[str] = Field(default_factory=list)
    email_event_triggers: List[EmailEventTrigger] = Field(default_factory=list)


class RetentionPolicyUpdateRequest(BaseModel):
    active_days: int = Field(default=30, ge=1, le=3650)
    archive_days: int = Field(default=180, ge=1, le=3650)


class EmailSettingsUpdateRequest(BaseModel):
    email_enabled: bool = False
    email_from_email: str = ""
    email_from_name: str = ""
    email_subject_prefix: str = ""
    email_recipients: Union[List[str], str] = Field(default_factory=list)
    email_event_triggers: List[EmailEventTrigger] = Field(default_factory=list)


class IntegrationAutomationSettings(BaseModel):
    automation_enabled: bool = True


class IntegrationAutomationUpdateRequest(BaseModel):
    automation_enabled: bool = True
