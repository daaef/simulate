from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse

from . import service as auth_service
from .dependencies import SESSION_COOKIE_NAME, clear_session_cookie, get_current_user, set_session_cookie
from .models import RefreshTokenRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register")
def register_user(user_data: auth_service.UserCreate) -> dict[str, Any]:
    raise HTTPException(status_code=403, detail="Self-service registration is disabled")


async def _parse_login_credentials(request: Request) -> auth_service.UserLogin:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        return auth_service.UserLogin(**payload)

    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body, keep_blank_values=True)
    return auth_service.UserLogin(
        username=form.get("username", [""])[0],
        password=form.get("password", [""])[0],
    )


def _is_browser_form_submission(request: Request) -> bool:
    content_type = request.headers.get("content-type", "").lower()
    return "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type


@router.post("/login")
async def login_user(request: Request):
    if not auth_service.is_auth_enabled():
        return JSONResponse({"message": "Authentication not enabled"})

    credentials = await _parse_login_credentials(request)

    auth_manager = auth_service.get_auth_manager()
    user = auth_manager.authenticate_user(credentials.username, credentials.password)
    if not user:
        if _is_browser_form_submission(request):
            return RedirectResponse(url="/auth/login?error=invalid_credentials", status_code=303)
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_token = auth_manager.create_session(
        int(user["id"]),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    user_payload = {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user["role"],
        "created_at": user["created_at"],
        "last_login": user.get("last_login"),
        "preferences": user.get("preferences", {}),
    }
    if _is_browser_form_submission(request):
        response = RedirectResponse(url="/overview", status_code=303)
    else:
        response = JSONResponse(
            jsonable_encoder({
                "message": "Login successful",
                "user": user_payload,
            })
        )
    set_session_cookie(response, session_token)
    return response


@router.post("/refresh")
def refresh_token(payload: RefreshTokenRequest) -> auth_service.TokenResponse:
    if not auth_service.is_auth_enabled():
        raise HTTPException(status_code=501, detail="Authentication not enabled")

    auth_manager = auth_service.get_auth_manager()
    tokens = auth_manager.refresh_access_token(payload.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.post("/logout")
def logout(request: Request) -> JSONResponse:
    response = JSONResponse({"message": "Logged out successfully"})
    clear_session_cookie(response)
    if not auth_service.is_auth_enabled():
        return response

    auth_manager = auth_service.get_auth_manager()
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        auth_manager.invalidate_session(session_token)
    return response


@router.get("/session")
@router.get("/me")
def get_current_user_profile(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": current_user.get("id"),
        "username": current_user["username"],
        "email": current_user.get("email"),
        "role": current_user["role"],
        "created_at": current_user.get("created_at"),
        "last_login": current_user.get("last_login"),
        "preferences": current_user.get("preferences", {}),
    }
