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
        auth_header_name="Fainzy-Token",
        auth_scheme=None,
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

def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _extract_customer_id(user: dict[str, Any] | None) -> str | None:
    if not isinstance(user, dict):
        return None

    keys = (
        "customer_id",
        "stripe_customer_id",
        "stripeCustomerId",
        "customer",
        "customerId",
    )

    for key in keys:
        value = user.get(key)
        if _present(value):
            return str(value)

    for parent in ("stripe", "payment", "payment_profile", "profile"):
        nested = user.get(parent)
        if not isinstance(nested, dict):
            continue

        for key in keys:
            value = nested.get(key)
            if _present(value):
                return str(value)

    return None


def _extract_probe_token(result: HttpResult | None) -> str | None:
    if result is None:
        return None

    data = api_data(result.payload)

    if isinstance(data, str) and data.strip():
        return data.strip()

    if isinstance(data, dict):
        for key in ("token", "access", "access_token", "auth_token", "key"):
            value = data.get(key)
            if _present(value):
                return str(value)

    if isinstance(result.payload, dict):
        for key in ("token", "access", "access_token", "auth_token", "key"):
            value = result.payload.get(key)
            if _present(value):
                return str(value)

    return None


def _record_probe_decision(
    recorder: RunRecorder,
    *,
    spec: ProbeSpec,
    status: str,
    reason: str,
    message: str,
    scenario: str | None,
    step: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    next_action = "continue_run"
    run_continued = True
    if status == "skipped":
        next_action = "skip_api_call"
    if status == "failed":
        next_action = "record_warning_and_continue"
    if hasattr(recorder, "record_decision"):
        recorder.record_decision(
            actor=spec.actor,
            action=spec.action,
            status=status,
            reason=reason,
            message=message,
            scenario=scenario,
            step=step or spec.name,
            reason_code=reason,
            reason_message=message,
            next_action=next_action,
            run_continued=run_continued,
            details=details or {},
        )
        return

    recorder.record_event(
        actor=spec.actor,
        action=spec.action,
        category="decision",
        status=status,
        scenario=scenario,
        step=step or spec.name,
        details={
            "reason": reason,
            "message": message,
            **(details or {}),
        },
        track_order=False,
    )

def _probe_preflight(
    *,
    spec: ProbeSpec,
    context: dict[str, Any],
    token: str | None,
    customer_id: str | None = None,
) -> tuple[bool, str, str]:
    if spec.name == "pricing":
        if not _present(context.get("currency")):
            return False, "missing_currency", "Pricing was skipped because currency is missing."
        if not _present(token):
            return False, "missing_product_auth", "Pricing was skipped because product authentication was not available."
        return True, "preflight_passed", "Pricing has product authentication and currency."

    if spec.name == "saved_cards":
        if not _present(token):
            return False, "missing_user_token", "Saved cards were skipped because user authentication is missing."
        if not _present(customer_id):
            return False, "no_customer_id", "Saved cards were skipped because this user has no Stripe/customer ID."
        return True, "preflight_passed", "Saved cards can be checked."

    if spec.name == "coupons":
        if not _present(token):
            return False, "missing_user_token", "Coupons were skipped because user authentication is missing."
        return True, "preflight_passed", "Coupons can be checked."

    if spec.name == "user_active_orders":
        if not _present(token):
            return False, "missing_user_token", "Active orders were skipped because user authentication is missing."
        if not _present(context.get("user_id")):
            return False, "missing_user_id", "Active orders were skipped because user_id is missing."
        return True, "preflight_passed", "Active orders can be checked."

    if spec.name in {"store_orders", "store_statistics", "top_customers"}:
        if not _present(token):
            return False, "missing_store_token", f"{spec.name} was skipped because store token is missing."
        if not _present(context.get("subentity_id")):
            return False, "missing_subentity_id", f"{spec.name} was skipped because subentity_id is missing."
        return True, "preflight_passed", f"{spec.name} can be checked."

    if spec.auth_header_name and not _present(token):
        return False, "missing_auth_token", f"{spec.name} was skipped because required auth token is missing."

    return True, "preflight_passed", f"{spec.name} can be checked."

async def run_probe(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    spec: ProbeSpec,
    context: dict[str, Any] | None = None,
    token: str | None = None,
    token_source: str | None = None,
    customer_id: str | None = None,
    scenario: str | None = None,
    step: str | None = None,
    request_func: RequestFunc = request_json,
) -> HttpResult | None:
    context = context or {}

    allowed, reason, message = _probe_preflight(
        spec=spec,
        context=context,
        token=token,
        customer_id=customer_id,
    )

    if not allowed:
        _record_probe_decision(
            recorder,
            spec=spec,
            status="skipped",
            reason=reason,
            message=message,
            scenario=scenario,
            step=step,
            details={
                "probe": spec.name,
                "context": context,
                "customer_id_present": bool(customer_id),
                "token_present": bool(token),
            },
        )
        return None

    endpoint = spec.endpoint.format(**context)
    params = _format_map(spec.params, context)
    headers, auth_header_name, auth_token, auth_scheme = _auth_headers(
        spec=spec,
        token=token,
    )

    _record_probe_decision(
        recorder,
        spec=spec,
        status="called",
        reason="preflight_passed",
        message=message,
        scenario=scenario,
        step=step,
        details={
            "probe": spec.name,
            "endpoint": endpoint,
            "params": params,
            "auth_header": auth_header_name,
        },
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
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
        )
    except Exception as exc:
        recorder.record_issue(
            severity="warning",
            code="probe_failed",
            actor=spec.actor,
            scenario=scenario,
            step=step or spec.name,
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
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
    user: dict[str, Any] | None = None,
    scenario: str | None = "app_bootstrap",
) -> None:
    customer_id = _extract_customer_id(user)

    await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("global_config"),
        context={"user_id": user_id, "currency": currency},
        scenario=scenario,
    )

    product_auth_result = await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("product_auth"),
        context={"user_id": user_id, "currency": currency},
        scenario=scenario,
    )

    product_token = _extract_probe_token(product_auth_result)

    await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("pricing"),
        context={"user_id": user_id, "currency": currency},
        token=product_token,
        token_source="product_auth" if product_token else None,
        scenario=scenario,
    )

    await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("saved_cards"),
        context={"user_id": user_id, "currency": currency},
        token=user_token,
        token_source=token_source,
        customer_id=customer_id,
        scenario=scenario,
    )

    await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("coupons"),
        context={"user_id": user_id, "currency": currency},
        token=user_token,
        token_source=token_source,
        scenario=scenario,
    )

    await run_probe(
        client,
        recorder=recorder,
        spec=probe_spec("user_active_orders"),
        context={"user_id": user_id, "currency": currency},
        token=user_token,
        token_source=token_source,
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
