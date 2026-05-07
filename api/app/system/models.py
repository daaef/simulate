from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


TimezonePolicyMode = Literal["all", "allowlist"]


class TimezonePolicyUpdateRequest(BaseModel):
    mode: TimezonePolicyMode = "all"
    allowed_timezones: Optional[List[str]] = Field(default=None)

