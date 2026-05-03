"""Reusable probes for real app API surfaces outside the core order mutation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

import config
from reporting import RunRecorder
from transport import HttpResult, RequestError, api_data, request_json


RequestFunc = Callable[..., Awaitable[HttpResult]]


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    actor: str
    action: str
    method: str
    base: str
    endpoint: str
    params: dict[str, str] = field(default_factory=dict)
    category: str = "probe"
    auth_header_name: str | None = None
    auth_scheme: str | None = None


PROBE_SPECS = (
    ProbeSpec(
        name="global_config",
        actor="app",
        action="probe_global_config",
        method="GET",
        base="fainzy",
        endpoint="/v1/entities/configs/",
    ),
    ProbeSpec(
        name="product_auth",
        actor="app",
        action="probe_product_auth",
        method="POST",
        base="fainzy",
        endpoint="/v1/biz/product/authentication/",
        params={"product": "rds"},
    ),
    ProbeSpec(
        name="pricing",
        actor="user",
        action="probe_pricing",
        method="GET",
        base="fainzy",
        endpoint="/v1/biz/pricing/0/",
        params={"product_name": "lastmile", "currency": "{currency}"},
    ),
    ProbeSpec(
        name="saved_cards",
        actor="user",
        action="probe_saved_cards",
        method="GET",
        base="lastmile",
        endpoint="/v1/core/cards/",
        auth_header_name="Authorization",
        auth_scheme="Token",
    ),
    ProbeSpec(
        name="coupons",
        actor="user",
        action="probe_coupons",
        method="GET",
        base="lastmile",
        endpoint="/v1/core/coupon/",
        auth_header_name="Authorization",
        auth_scheme="Token",
    ),
    ProbeSpec(
        name="user_active_orders",
        actor="user",
        action="probe_user_active_orders",
        method="GET",
        base="lastmile",
        endpoint="/v1/core/orders/",
        params={"user": "{user_id}"},
        auth_header_name="Authorization",
        auth_scheme="Token",
    ),
    ProbeSpec(
        name="store_orders",
        actor="store",
        action="probe_store_orders",
        method="GET",
        base="lastmile",
        endpoint="/v1/core/orders/",
        params={"subentity_id": "{subentity_id}"},
        auth_header_name="Fainzy-Token",
        auth_scheme=None,
    ),
    ProbeSpec(
        name="store_statistics",
        actor="store",
        action="probe_store_statistics",
        method="GET",
        base="lastmile",
        endpoint="/v1/statistics/subentities/{subentity_id}/",
        auth_header_name="Fainzy-Token",
        auth_scheme=None,
    ),
    ProbeSpec(
        name="top_customers",
        actor="store",
        action="probe_top_customers",
        method="GET",
        base="lastmile",
        endpoint="/v1/statistics/subentities/{subentity_id}/top-customers/",
        auth_header_name="Fainzy-Token",
        auth_scheme=None,
    ),
)


def _base_url(name: str) -> str:
    if name == "lastmile":
        return config.LASTMILE_BASE_URL
    if name == "fainzy":
        return config.FAINZY_BASE_URL
    raise ValueError(f"Unsupported probe base {name!r}")


def _format_map(value: dict[str, str], context: dict[str, Any]) -> dict[str, str]:
    formatted: dict[str, str] = {}
    for key, raw in value.items():
        formatted[key] = raw.format(**context)
    return formatted


def _auth_headers(
    *,
    spec: ProbeSpec,
    token: str | None,
) -> tuple[dict[str, str], str | None, str | None, str | None]:
    headers = {"Content-Type": "application/json"}
    if spec.auth_header_name and token:
        value = f"{spec.auth_scheme} {token}" if spec.auth_scheme else token
        headers[spec.auth_header_name] = value
        return headers, spec.auth_header_name, token, spec.auth_scheme
    return headers, None, None, None


async def run_probe(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    spec: ProbeSpec,
    context: dict[str, Any] | None = None,
    token: str | None = None,
    token_source: str | None = None,
    scenario: str | None = None,
    step: str | None = None,
    request_func: RequestFunc = request_json,
) -> HttpResult | None:
    context = context or {}
    endpoint = spec.endpoint.format(**context)
    params = _format_map(spec.params, context)
    headers, auth_header_name, auth_token, auth_scheme = _auth_headers(
        spec=spec,
        token=token,
    )
    try:
        return await request_func(
            client,
            recorder=recorder,
            actor=spec.actor,
            action=spec.action,
            category=spec.category,
            scenario=scenario,
            step=step or spec.name,
            method=spec.method,
            url=f"{_base_url(spec.base)}{endpoint}",
            endpoint=endpoint,
            params=params or None,
            headers=headers,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            auth_source=token_source,
            auth_scheme=auth_scheme,
            track_order=False,
        )
    except RequestError as exc:
        recorder.record_issue(
            severity="warning",
            code="probe_failed",
            actor=spec.actor,
            scenario=scenario,
            step=step or spec.name,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"Probe {spec.name} failed: {exc}",
        )
    except Exception as exc:
        recorder.record_issue(
            severity="warning",
            code="probe_failed",
            actor=spec.actor,
            scenario=scenario,
            step=step or spec.name,
            message=f"Probe {spec.name} failed: {exc}",
        )
    return None


def probe_spec(name: str) -> ProbeSpec:
    for spec in PROBE_SPECS:
        if spec.name == name:
            return spec
    raise KeyError(f"Unknown probe {name!r}")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coupon_discount_amount(coupon: dict[str, Any], order_total: float) -> float:
    config_details = coupon.get("config_details") or {}
    discount = _as_float(config_details.get("discount"))
    if config_details.get("is_percentage") is True:
        return round(order_total * discount / 100.0, 2)
    return round(discount, 2)


def coupon_is_usable(coupon: dict[str, Any], order_total: float | None = None) -> bool:
    if coupon.get("id") is None:
        return False
    if coupon.get("is_valid") is False:
        return False
    if order_total is not None:
        config_details = coupon.get("config_details") or {}
        min_order = _as_float(config_details.get("min_order"))
        if min_order > order_total:
            return False
    return True


def select_coupon(
    coupons: list[dict[str, Any]],
    *,
    order_total: float | None = None,
    prefer_covering: bool = False,
) -> dict[str, Any] | None:
    usable = [coupon for coupon in coupons if coupon_is_usable(coupon, order_total)]
    if not usable:
        return None
    if order_total is None:
        return usable[0]
    if prefer_covering:
        covering = [
            coupon
            for coupon in usable
            if coupon_discount_amount(coupon, order_total) >= order_total
        ]
        if covering:
            return max(covering, key=lambda coupon: coupon_discount_amount(coupon, order_total))
    return max(usable, key=lambda coupon: coupon_discount_amount(coupon, order_total))


async def fetch_user_coupons(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_token: str,
    token_source: str,
    scenario: str | None = "checkout_coupon",
) -> list[dict[str, Any]]:
    result = await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("coupons"),
        token=user_token,
        token_source=token_source,
        scenario=scenario,
        step="checkout_coupon",
    )
    if result is None:
        return []
    data = api_data(result.payload)
    return [coupon for coupon in data if isinstance(coupon, dict)] if isinstance(data, list) else []


async def run_user_app_probes(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    user_id: int,
    user_token: str,
    token_source: str,
    currency: str,
    scenario: str | None = "app_bootstrap",
) -> None:
    for name in (
        "global_config",
        "product_auth",
        "pricing",
        "saved_cards",
        "coupons",
        "user_active_orders",
    ):
        spec = probe_spec(name)
        token = user_token if spec.auth_header_name == "Authorization" else None
        source = token_source if token else None
        await run_probe(
            client,
            recorder=recorder,
            spec=spec,
            context={"user_id": user_id, "currency": currency},
            token=token,
            token_source=source,
            scenario=scenario,
        )


async def run_store_dashboard_probes(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    subentity_id: int,
    store_token: str,
    token_source: str,
    scenario: str | None = "store_dashboard",
) -> None:
    for name in ("store_orders", "store_statistics", "top_customers"):
        await run_probe(
            client,
            recorder=recorder,
            spec=probe_spec(name),
            context={"subentity_id": subentity_id},
            token=store_token,
            token_source=token_source,
            scenario=scenario,
        )
