from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import service as auth_service


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SESSION_COOKIE_NAME = os.getenv("SIMULATOR_SESSION_COOKIE_NAME", "simulator_session")
SESSION_COOKIE_MAX_AGE = max(
    300,
    int(os.getenv("SIMULATOR_SESSION_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60))),
)
SESSION_COOKIE_SECURE = _as_bool(os.getenv("SIMULATOR_SESSION_COOKIE_SECURE"), default=False)
SESSION_COOKIE_SAMESITE = os.getenv("SIMULATOR_SESSION_COOKIE_SAMESITE", "lax").lower()

security = HTTPBearer(auto_error=False)


def _local_dev_user() -> dict:
    return {
        "id": None,
        "username": "local-dev",
        "email": "local-dev@simulator.local",
        "role": "admin",
        "is_active": True,
        "preferences": {},
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    if not auth_service.is_auth_enabled():
        if auth_service.is_auth_disabled_explicitly() and not auth_service.is_production():
            return _local_dev_user()

        raise HTTPException(
            status_code=503,
            detail="Authentication is not available.",
        )

    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        auth_manager = auth_service.get_auth_manager()
        user = auth_manager.get_user_by_session_token(session_token)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Session is no longer active",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_manager = auth_service.get_auth_manager()
    payload = auth_manager.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    if not auth_service.is_auth_enabled():
        if auth_service.is_auth_disabled_explicitly() and not auth_service.is_production():
            return _local_dev_user()
        return None

    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def set_session_cookie(response: JSONResponse, session_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
    )