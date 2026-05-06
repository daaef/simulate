from __future__ import annotations

import logging

from pydantic import BaseModel

try:
    from ...auth import UserCreate, UserLogin, TokenResponse, get_auth_manager, init_auth
except ImportError as exc:  # pragma: no cover - fallback for partial local environments
    class UserCreate(BaseModel):
        username: str
        email: str
        password: str

    class UserLogin(BaseModel):
        username: str
        password: str

    class TokenResponse(BaseModel):
        access_token: str
        refresh_token: str
        token_type: str = "bearer"
        expires_in: int

    def init_auth(db_connection_string: str) -> None:
        raise RuntimeError(f"Auth module not available: {exc}")

    def get_auth_manager():
        raise RuntimeError(f"Auth module not available: {exc}")

    FALLBACK_IMPORT_ERROR = exc
else:
    FALLBACK_IMPORT_ERROR = None

LOGGER = logging.getLogger("simulate.web_api.auth")
AUTH_ENABLED = FALLBACK_IMPORT_ERROR is None
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15


def init_auth_system(postgres_url: str, use_postgres: bool) -> bool:
    global AUTH_ENABLED
    if not AUTH_ENABLED or not use_postgres:
        return AUTH_ENABLED and use_postgres
    try:
        init_auth(postgres_url)
        LOGGER.info("Authentication system initialized")
        return True
    except Exception as exc:
        LOGGER.error("Failed to initialize authentication: %s", exc)
        AUTH_ENABLED = False
        return False


def is_auth_enabled() -> bool:
    return AUTH_ENABLED


__all__ = [
    "AUTH_ENABLED",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "TokenResponse",
    "UserCreate",
    "UserLogin",
    "get_auth_manager",
    "init_auth_system",
    "is_auth_enabled",
]
