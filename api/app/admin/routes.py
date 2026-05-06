from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import service as auth_service
from ..auth.policies import require_roles

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.get("/users")
def list_users(current_user: dict = Depends(require_roles("admin"))) -> dict[str, Any]:
    if not auth_service.is_auth_enabled():
        return {"users": []}

    auth_manager = auth_service.get_auth_manager()
    users = auth_manager.list_users()
    return {"users": users}


@router.post("/users")
def create_user(
    user_data: auth_service.UserCreate,
    current_user: dict = Depends(require_roles("admin")),
) -> dict[str, Any]:
    if not auth_service.is_auth_enabled():
        raise HTTPException(status_code=501, detail="Authentication not enabled")

    auth_manager = auth_service.get_auth_manager()
    try:
        user = auth_manager.create_user(user_data)
        return {"message": "User created successfully", "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: dict,
    current_user: dict = Depends(require_roles("admin")),
) -> dict[str, Any]:
    if not auth_service.is_auth_enabled():
        raise HTTPException(status_code=501, detail="Authentication not enabled")

    auth_manager = auth_service.get_auth_manager()
    try:
        user = auth_manager.update_user(user_id, user_data)
        return {"message": "User updated successfully", "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update user")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: dict = Depends(require_roles("admin")),
) -> dict[str, Any]:
    if not auth_service.is_auth_enabled():
        raise HTTPException(status_code=501, detail="Authentication not enabled")

    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    auth_manager = auth_service.get_auth_manager()
    try:
        success = auth_manager.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete user")


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user: dict = Depends(require_roles("admin")),
) -> dict[str, Any]:
    if not auth_service.is_auth_enabled():
        raise HTTPException(status_code=501, detail="Authentication not enabled")

    auth_manager = auth_service.get_auth_manager()
    try:
        success = auth_manager.reset_password(user_id, payload.new_password)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "Password reset successfully"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to reset password")
