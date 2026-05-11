from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class IntegrationMappingUpsertRequest(BaseModel):
    project: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=120)
    profile_id: int = Field(ge=1)
    enabled: bool = True


class GitHubDeploymentWebhookResponse(BaseModel):
    accepted: bool
    trigger_id: Optional[int] = None
    status: str
    reason: Optional[str] = None
    run_id: Optional[int] = None
    project: Optional[str] = None
    environment: Optional[str] = None
    repository: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
