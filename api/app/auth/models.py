from __future__ import annotations

from pydantic import BaseModel


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class SessionUserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    created_at: str | object
    last_login: str | object | None = None
    preferences: dict[str, object] = {}
