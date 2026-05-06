from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException

from .dependencies import get_current_user

Role = str

FINAL_ROLES: set[Role] = {
    "admin",
    "operator",
    "runner",
    "viewer",
    "auditor",
}

LEGACY_ROLE_ALIASES: dict[str, Role] = {
    "user": "operator",
}

ROLE_PERMISSIONS: dict[Role, set[tuple[str, str]]] = {
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

        ("archives", "read"),
        ("archives", "delete"),

        ("retention", "read"),
        ("retention", "update"),

        ("system", "read"),
        ("system", "configure"),
    },
    "operator": {
        ("runs", "create"),
        ("runs", "read"),
        ("runs", "cancel"),

        ("dashboard", "read"),

        ("archives", "read"),
        ("retention", "read"),
    },
    "runner": {
        ("runs", "create"),
        ("runs", "read"),

        ("dashboard", "read"),
    },
    "viewer": {
        ("runs", "read"),

        ("dashboard", "read"),
        ("archives", "read"),
    },
    "auditor": {
        ("runs", "read"),

        ("dashboard", "read"),
        ("archives", "read"),
        ("retention", "read"),
    },
}


def normalize_role(role: str | None) -> Role:
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


def require_roles(*roles: Iterable[str] | str):
    allowed: set[str] = set()

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