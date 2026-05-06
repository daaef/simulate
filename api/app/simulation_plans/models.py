from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SimulationPlanUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: dict[str, Any]
