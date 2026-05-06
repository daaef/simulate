from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class SessionUserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    created_at: Any
    last_login: Optional[Any] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)