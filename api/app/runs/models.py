from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Optional[Literal["trace", "load"]] = None
    suite: Optional[str] = None
    scenarios: List[str] = Field(default_factory=list)
    store_id: Optional[str] = None
    phone: Optional[str] = None
    all_users: bool = False
    strict_plan: bool = False
    skip_app_probes: bool = False
    skip_store_dashboard_probes: bool = False
    no_auto_provision: bool = False
    enforce_websocket_gates: bool = False
    post_order_actions: Optional[bool] = None
    users: Optional[int] = None
    orders: Optional[int] = None
    interval: Optional[float] = None
    reject: Optional[float] = None
    continuous: bool = False
    extra_args: List[str] = Field(default_factory=list)

    trigger_source: Optional[
        Literal["manual", "profile", "schedule", "github", "replay"]
    ] = "manual"
    trigger_label: Optional[str] = "Manual launch"
    trigger_context: Dict[str, Any] = Field(default_factory=dict)
    profile_id: Optional[int] = None
    schedule_id: Optional[int] = None
    integration_trigger_id: Optional[int] = None
    launched_by_user_id: Optional[int] = None


class RunProfileUpsertRequest(BaseModel):
    name: str
    description: Optional[str] = None
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Optional[Literal["trace", "load"]] = None
    suite: Optional[str] = None
    scenarios: List[str] = Field(default_factory=list)
    store_id: Optional[str] = None
    phone: Optional[str] = None
    all_users: bool = False
    strict_plan: bool = False
    skip_app_probes: bool = False
    skip_store_dashboard_probes: bool = False
    no_auto_provision: bool = False
    enforce_websocket_gates: bool = False
    post_order_actions: Optional[bool] = None
    users: Optional[int] = None
    orders: Optional[int] = None
    interval: Optional[float] = None
    reject: Optional[float] = None
    continuous: bool = False
    extra_args: List[str] = Field(default_factory=list)
