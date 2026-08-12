from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Only one delivery type is honored per mapping (§ allowlist, not denylist): the mapping
# must declare exactly the event it launches on, not merely which events it rejects.
IntegrationTriggerEvent = Literal["workflow_run", "deployment_status"]


class IntegrationMappingUpsertRequest(BaseModel):
    project: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=120)
    profile_id: int = Field(ge=1)
    enabled: bool = True
    trigger_event: IntegrationTriggerEvent
    trigger_workflow: Optional[str] = Field(default=None, max_length=255)
    # Deliberately a single value, not a list: "success" is the only workflow/deployment
    # conclusion that should ever start a run. Kept as a field (not hardcoded) so a future
    # need for a second value doesn't require a schema change, not to invite widening it.
    trigger_conclusion: str = Field(default="success", min_length=1, max_length=40)

    @model_validator(mode="after")
    def _validate_trigger_spec(self) -> "IntegrationMappingUpsertRequest":
        workflow = (self.trigger_workflow or "").strip()
        if self.trigger_event == "workflow_run":
            if not workflow:
                raise ValueError("trigger_workflow is required when trigger_event is 'workflow_run'.")
            self.trigger_workflow = workflow
        else:
            self.trigger_workflow = None

        conclusion = self.trigger_conclusion.strip().lower()
        if not conclusion:
            raise ValueError("trigger_conclusion must not be empty.")
        self.trigger_conclusion = conclusion
        return self


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


class IntegrationWebhookProjectCreateRequest(BaseModel):
    project: str = Field(min_length=1, max_length=120)
    repositories: list[str] = Field(default_factory=list)


class IntegrationWebhookProjectRepositoriesRequest(BaseModel):
    repositories: list[str] = Field(default_factory=list)
