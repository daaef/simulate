from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Optional[Literal["trace", "load"]] = None
    store_id: Optional[str] = None
    phone: Optional[str] = None
    all_users: bool = False
    no_auto_provision: bool = False
    post_order_actions: Optional[bool] = None
    extra_args: List[str] = Field(default_factory=list)


class RunProfileUpsertRequest(BaseModel):
    name: str
    description: Optional[str] = None
    flow: str = Field(default="doctor")
    plan: str = Field(default="sim_actors.json")
    timing: Literal["fast", "realistic"] = "fast"
    mode: Optional[Literal["trace", "load"]] = None
    store_id: Optional[str] = None
    phone: Optional[str] = None
    all_users: bool = False
    no_auto_provision: bool = False
    post_order_actions: Optional[bool] = None
    extra_args: List[str] = Field(default_factory=list)