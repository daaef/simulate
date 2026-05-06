"""JSON run-plan parsing for simulator operators."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


class PlanValidationError(ValueError):
    """Raised when a simulator run plan is malformed."""


SENSITIVE_KEY_PARTS = ("secret", "token", "password", "api_key", "private_key")


def _as_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gps_pair(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = raw.get("gps")
    lat = raw.get("lat")
    lng = raw.get("lng")
    if isinstance(gps, dict):
        lat = gps.get("lat", gps.get("latitude", lat))
        lng = gps.get("lng", gps.get("longitude", lng))
    return _as_float(lat), _as_float(lng)


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dict_section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _find_sensitive_keys(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            lowered = key_text.lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                findings.append(child_path)
            findings.extend(_find_sensitive_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_sensitive_keys(child, path=f"{path}[{index}]"))
    return findings


@dataclass(frozen=True)
class PlanUser:
    phone: str
    role: str = "returning"
    lat: float | None = None
    lng: float | None = None
    orders: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlanUser":
        lat, lng = _gps_pair(raw)
        return cls(
            phone=str(raw.get("phone") or raw.get("phone_number") or ""),
            role=str(raw.get("role") or "returning"),
            lat=lat,
            lng=lng,
            orders=_optional_int(raw.get("orders")),
            raw=dict(raw),
        )

    def to_actor(self) -> dict[str, Any]:
        data: dict[str, Any] = {"phone": self.phone, "role": self.role}
        if self.lat is not None:
            data["lat"] = self.lat
        if self.lng is not None:
            data["lng"] = self.lng
        if self.orders is not None:
            data["orders"] = self.orders
        return data


@dataclass(frozen=True)
class PlanStore:
    store_id: str
    subentity_id: int | None = None
    name: str = ""
    branch: str = ""
    currency: str = ""
    status: int | None = None
    lat: float | None = None
    lng: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlanStore":
        lat, lng = _gps_pair(raw)
        return cls(
            store_id=str(raw.get("store_id") or raw.get("id") or ""),
            subentity_id=_optional_int(raw.get("subentity_id")),
            name=str(raw.get("name") or ""),
            branch=str(raw.get("branch") or ""),
            currency=str(raw.get("currency") or ""),
            status=_optional_int(raw.get("status")),
            lat=lat,
            lng=lng,
            raw=dict(raw),
        )

    def to_actor(self) -> dict[str, Any]:
        data: dict[str, Any] = {"store_id": self.store_id}
        if self.subentity_id is not None:
            data["subentity_id"] = self.subentity_id
        if self.name:
            data["name"] = self.name
        if self.branch:
            data["branch"] = self.branch
        if self.currency:
            data["currency"] = self.currency
        if self.status is not None:
            data["status"] = self.status
        if self.lat is not None:
            data["lat"] = self.lat
        if self.lng is not None:
            data["lng"] = self.lng
        return data


@dataclass(frozen=True)
class RunPlan:
    schema_version: int = 1
    name: str = ""
    defaults: dict[str, Any] = field(default_factory=dict)
    runtime_defaults: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)
    fixture_defaults: dict[str, Any] = field(default_factory=dict)
    payment_defaults: dict[str, Any] = field(default_factory=dict)
    review_defaults: dict[str, Any] = field(default_factory=dict)
    new_user_defaults: dict[str, Any] = field(default_factory=dict)
    users: list[PlanUser] = field(default_factory=list)
    stores: list[PlanStore] = field(default_factory=list)
    source_path: Path | None = None

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        *,
        source_path: Path | None = None,
    ) -> "RunPlan":
        users = [
            PlanUser.from_dict(item)
            for item in raw.get("users", [])
            if isinstance(item, dict)
        ]
        stores = [
            PlanStore.from_dict(item)
            for item in raw.get("stores", [])
            if isinstance(item, dict)
        ]
        defaults = _dict_section(raw, "defaults")
        return cls(
            schema_version=int(raw.get("schema_version") or 1),
            name=str(raw.get("name") or ""),
            defaults=defaults,
            runtime_defaults=_dict_section(raw, "runtime_defaults"),
            rules=_dict_section(raw, "rules"),
            fixture_defaults=_dict_section(raw, "fixture_defaults"),
            payment_defaults=_dict_section(raw, "payment_defaults"),
            review_defaults=_dict_section(raw, "review_defaults"),
            new_user_defaults=_dict_section(raw, "new_user_defaults"),
            users=users,
            stores=stores,
            source_path=source_path,
        )

    def validate(self, *, strict: bool = False) -> None:
        errors: list[str] = []
        sensitive_keys = _find_sensitive_keys(self.to_raw())
        if sensitive_keys:
            errors.append(
                "sensitive key is not allowed in run plans: "
                + ", ".join(sensitive_keys)
            )
        if strict and not self.users:
            errors.append("users must contain at least one user")
        if strict and not self.stores:
            errors.append("stores must contain at least one store")
        for index, user in enumerate(self.users):
            if not user.phone:
                errors.append(f"users[{index}].phone is required")
            if strict and (user.lat is None or user.lng is None):
                errors.append(f"users[{index}].lat/lng is required")
        for index, store in enumerate(self.stores):
            if not store.store_id:
                errors.append(f"stores[{index}].store_id is required")
            if strict and (store.lat is None or store.lng is None):
                errors.append(f"stores[{index}].lat/lng is required")
        if errors:
            raise PlanValidationError("; ".join(errors))

    def to_actors(self) -> dict[str, Any]:
        return {
            "defaults": dict(self.defaults),
            "users": [user.to_actor() for user in self.users],
            "stores": [store.to_actor() for store in self.stores],
        }

    def to_raw(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.schema_version != 1:
            payload["schema_version"] = self.schema_version
        if self.name:
            payload["name"] = self.name
        payload["defaults"] = dict(self.defaults)
        if self.runtime_defaults:
            payload["runtime_defaults"] = dict(self.runtime_defaults)
        if self.rules:
            payload["rules"] = dict(self.rules)
        if self.fixture_defaults:
            payload["fixture_defaults"] = dict(self.fixture_defaults)
        if self.payment_defaults:
            payload["payment_defaults"] = dict(self.payment_defaults)
        if self.review_defaults:
            payload["review_defaults"] = dict(self.review_defaults)
        if self.new_user_defaults:
            payload["new_user_defaults"] = dict(self.new_user_defaults)
        payload["users"] = [user.to_actor() for user in self.users]
        payload["stores"] = [store.to_actor() for store in self.stores]
        return payload


def load_run_plan(path: str | Path, *, strict: bool = False) -> RunPlan:
    resolved = Path(path).expanduser()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanValidationError(f"Plan file not found: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"Plan file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PlanValidationError("Plan root must be a JSON object")
    plan = RunPlan.from_dict(raw, source_path=resolved)
    plan.validate(strict=strict)
    return plan
