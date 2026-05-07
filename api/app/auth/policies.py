from __future__ import annotations

from typing import Iterable, Optional, Set, Tuple, Dict

from fastapi import Depends, HTTPException

from .dependencies import get_current_user

Role = str
Permission = Tuple[str, str]

FINAL_ROLES: Set[Role] = {
    "admin",
    "operator",
    "runner",
    "viewer",
    "auditor",
}

LEGACY_ROLE_ALIASES: Dict[str, Role] = {
    "user": "operator",
}

ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    "admin": {
        ("users", "create"),
        ("users", "read"),
        ("users", "update"),
        ("users", "delete"),
        ("users", "reset_password"),

        ("runs", "create"),
        ("runs", "read"),
        ("runs", "update"),
        ("runs", "cancel"),
        ("runs", "delete"),

        ("dashboard", "read"),

        ("schedules", "create"),
        ("schedules", "read"),
        ("schedules", "update"),
        ("schedules", "delete"),
        ("schedules", "trigger"),

        ("archives", "read"),
        ("archives", "delete"),

        ("retention", "read"),
        ("retention", "update"),

        ("alerts", "read"),

        ("system", "read"),
        ("system", "configure"),
    },
    "operator": {
        ("runs", "create"),
        ("runs", "read"),
        ("runs", "cancel"),

        ("dashboard", "read"),

        ("schedules", "create"),
        ("schedules", "read"),
        ("schedules", "update"),
        ("schedules", "trigger"),

        ("archives", "read"),
        ("retention", "read"),
        ("alerts", "read"),
    },
    "runner": {
        ("runs", "create"),
        ("runs", "read"),

        ("dashboard", "read"),
        ("schedules", "read"),
        ("alerts", "read"),
    },
    "viewer": {
        ("runs", "read"),

        ("dashboard", "read"),
        ("schedules", "read"),
        ("archives", "read"),
        ("retention", "read"),
        ("alerts", "read"),
    },
    "auditor": {
        ("runs", "read"),

        ("dashboard", "read"),
        ("schedules", "read"),
        ("archives", "read"),
        ("retention", "read"),
        ("alerts", "read"),
    },
}


def normalize_role(role: Optional[str]) -> Role:
    if not role:
        return "viewer"

    value = role.strip().lower()
    return LEGACY_ROLE_ALIASES.get(value, value)


def has_permission(user: dict, resource: str, action: str) -> bool:
    role = normalize_role(user.get("role"))
    return (resource, action) in ROLE_PERMISSIONS.get(role, set())


def require_permission(resource: str, action: str):
    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, resource, action):
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user

    return dependency


def require_roles(*roles):
    allowed: Set[str] = set()

    for role in roles:
        if isinstance(role, str):
            allowed.add(normalize_role(role))
        else:
            allowed.update(normalize_role(item) for item in role)

    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if normalize_role(current_user.get("role")) not in allowed:
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user

    return dependency
