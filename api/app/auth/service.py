from __future__ import annotations

import logging
import os

from pydantic import BaseModel

LOGGER = logging.getLogger("simulate.web_api.auth")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SIM_ENV = os.getenv("SIM_ENV", "development").strip().lower()
AUTH_DISABLED = _as_bool(os.getenv("SIM_AUTH_DISABLED"), default=False)

try:
    from ...auth import UserCreate, UserLogin, TokenResponse, get_auth_manager, init_auth
except ImportError as exc:  # pragma: no cover - fallback for partial local environments
    class UserCreate(BaseModel):
        username: str
        email: str
        password: str
        role: str = "operator"

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

AUTH_ENABLED = False
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15


def init_auth_system(postgres_url: str, use_postgres: bool) -> bool:
    global AUTH_ENABLED

    if AUTH_DISABLED and SIM_ENV in {"production", "prod"}:
        raise RuntimeError("SIM_AUTH_DISABLED=true is not allowed in production.")

    if AUTH_DISABLED:
        LOGGER.warning("Authentication is explicitly disabled via SIM_AUTH_DISABLED=true.")
        AUTH_ENABLED = False
        return False

    if FALLBACK_IMPORT_ERROR is not None:
        LOGGER.error("Authentication module import failed: %s", FALLBACK_IMPORT_ERROR)
        AUTH_ENABLED = False
        return False

    if not use_postgres:
        LOGGER.error("Authentication requires PostgreSQL. Auth is disabled because PostgreSQL is not enabled.")
        AUTH_ENABLED = False
        return False

    try:
        init_auth(postgres_url)
        AUTH_ENABLED = True
        LOGGER.info("Authentication system initialized")
        return True
    except Exception as exc:
        LOGGER.error("Failed to initialize authentication: %s", exc)
        AUTH_ENABLED = False
        return False


def is_auth_enabled() -> bool:
    return AUTH_ENABLED


def is_auth_disabled_explicitly() -> bool:
    return AUTH_DISABLED


def is_production() -> bool:
    return SIM_ENV in {"production", "prod"}


__all__ = [
    "AUTH_ENABLED",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "TokenResponse",
    "UserCreate",
    "UserLogin",
    "get_auth_manager",
    "init_auth_system",
    "is_auth_enabled",
    "is_auth_disabled_explicitly",
    "is_production",
]