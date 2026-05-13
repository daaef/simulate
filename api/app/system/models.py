from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


TimezonePolicyMode = Literal["all", "allowlist"]


class TimezonePolicyUpdateRequest(BaseModel):
    mode: TimezonePolicyMode = "all"
    allowed_timezones: Optional[List[str]] = Field(default=None)


EmailEventTrigger = Literal["run_failed", "schedule_launch_failed", "critical_alert"]


class EmailSettingsPayload(BaseModel):
    email_enabled: bool = False
    email_from_email: str = ""
    email_from_name: str = ""
    email_subject_prefix: str = ""
    email_recipients: List[str] = Field(default_factory=list)
    email_event_triggers: List[EmailEventTrigger] = Field(default_factory=list)


class EmailSettingsUpdateRequest(BaseModel):
    email_enabled: bool = False
    email_from_email: str = ""
    email_from_name: str = ""
    email_subject_prefix: str = ""
    email_recipients: Union[List[str], str] = Field(default_factory=list)
    email_event_triggers: List[EmailEventTrigger] = Field(default_factory=list)
