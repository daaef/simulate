"""Reusable probes for real app API surfaces outside the core order mutation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

import config
from reporting import RunRecorder
from session_probe_reference import (
    ALLOWED_SESSION_DOCS,
    probe_contract,
    session_reference_details,
)
from transport import HttpResult, RequestError, api_data, request_json, sanitize_payload


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
        next_action = (
            "request_sample_from_user"
            if reason == "missing_reference_sample"
            else "skip_api_call"
        )
    elif status == "failed":
        next_action = "record_warning_and_continue"
    elif status == "inconclusive":
        next_action = "continue_run"

    merged_details = {**session_reference_details(spec.name), **(details or {})}

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
            details=merged_details,
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
            **merged_details,
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
    contract = probe_contract(spec.name) or {}
    variants = tuple(contract.get("variants") or ())
    if not variants:
        return (
            False,
            "missing_reference_sample",
            f"{spec.name} was skipped because no reference sample exists in the allowed session docs.",
        )

    def _requirement_value(field: str) -> Any:
        if field == "auth_token":
            return token
        if field == "user_id":
            return context.get("user_id")
        if field == "subentity_id":
            return context.get("subentity_id")
        if field == "currency":
            return context.get("currency")
        if field == "customer_id":
            return customer_id
        return context.get(field)

    for requirement in tuple(contract.get("preflight") or ()):
        field = str(requirement.get("field") or "").strip()
        if not field:
            continue
        if _present(_requirement_value(field)):
            continue
        reason = str(requirement.get("reason_code") or "missing_required_probe_data")
        message = str(requirement.get("message") or f"{spec.name} was skipped because {field} is missing.")
        return False, reason, message

    if spec.auth_header_name and not _present(token):
        return False, "missing_auth_token", f"{spec.name} was skipped because required auth token is missing."

    return True, "preflight_passed", f"{spec.name} preflight passed with documented contract requirements."


def _path_value(payload: Any, path: tuple[str, ...] | None) -> tuple[bool, Any]:
    if path is None:
        return True, payload
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _scalar_matches(value: Any, expected_kind: str | None) -> bool:
    if expected_kind is None:
        return True
    if expected_kind == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected_kind == "number":
        return isinstance(value, (int, float))
    if expected_kind == "boolean":
        return isinstance(value, bool)
    return False


def _matches_variant(payload: Any, variant: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    envelope_keys = tuple(variant.get("envelope_keys") or ())
    if any(key not in payload for key in envelope_keys):
        return False

    container_path = variant.get("container_path")
    if container_path is not None:
        found, container = _path_value(payload, tuple(container_path))
        if not found or not isinstance(container, dict):
            return False
        required_keys = tuple(variant.get("container_required_keys") or ())
        if any(key not in container for key in required_keys):
            return False

    list_path = variant.get("list_path")
    if list_path is not None:
        found, list_value = _path_value(payload, tuple(list_path))
        if not found or not isinstance(list_value, list):
            return False
        list_state = str(variant.get("list_state") or "any").strip().lower()
        if list_state == "empty" and list_value:
            return False
        if list_state == "nonempty" and not list_value:
            return False
        if not list_value:
            return bool(variant.get("list_allow_empty", True))
        item_keys = tuple(variant.get("list_item_required_keys") or ())
        if not item_keys:
            return True
        for item in list_value:
            if not isinstance(item, dict):
                return False
            if any(key not in item for key in item_keys):
                return False

    scalar_path = variant.get("scalar_path")
    if scalar_path is not None:
        found, scalar = _path_value(payload, tuple(scalar_path))
        scalar_kind = variant.get("scalar_kind")
        expected_kind = str(scalar_kind) if scalar_kind is not None else None
        if not found or not _scalar_matches(scalar, expected_kind):
            return False

    return True


def _variant_label(variant: dict[str, Any]) -> str:
    source_doc = str(variant.get("source_doc") or "unknown-doc")
    source_phase = str(variant.get("source_phase") or "unknown-phase")
    return f"{source_doc} ({source_phase})"


def _validate_probe_response(spec: ProbeSpec, result: HttpResult) -> tuple[str, str, str, dict[str, Any]]:
    contract = probe_contract(spec.name) or {}
    variants = tuple(contract.get("variants") or ())
    details: dict[str, Any] = {
        "raw_payload": sanitize_payload(result.payload),
        "http_status": result.response.status_code,
    }
    if not variants:
        return (
            "skipped",
            "missing_reference_sample",
            f"{spec.name} has no documented sample variant in allowed session docs.",
            {
                **details,
                "next_action": "request_sample_from_user",
                "allowed_source_docs": list(ALLOWED_SESSION_DOCS),
            },
        )

    status_code = result.response.status_code
    status_variants = [
        variant
        for variant in variants
        if status_code in tuple(variant.get("allowed_http_statuses") or ())
    ]
    if not status_variants:
        documented_statuses = sorted(
            {
                int(code)
                for variant in variants
                for code in tuple(variant.get("allowed_http_statuses") or ())
            }
        )
        return (
            "inconclusive",
            "probe_status_undocumented",
            f"Probe {spec.name} returned HTTP {status_code}; documented statuses are {documented_statuses}.",
            {**details, "documented_http_statuses": documented_statuses},
        )

    matched_variant = next(
        (variant for variant in status_variants if _matches_variant(result.payload, variant)),
        None,
    )
    if matched_variant is None:
        return (
            "inconclusive",
            "probe_schema_undocumented",
            f"Probe {spec.name} returned HTTP {status_code}, but payload shape is not documented.",
            {
                **details,
                "status_matched_variants": [_variant_label(variant) for variant in status_variants],
            },
        )

    return (
        "passed",
        "probe_response_ok",
        f"Probe {spec.name} matches documented sample variant from {_variant_label(matched_variant)}.",
        {**details, "matched_variant": _variant_label(matched_variant)},
    )


def _record_probe_outcome(
    recorder: RunRecorder,
    *,
    spec: ProbeSpec,
    result: HttpResult,
    scenario: str | None,
    step: str | None,
) -> None:
    status, reason, message, details = _validate_probe_response(spec, result)

    if result.event:
        details["related_event_id"] = result.event.get("id")
        preview = result.event.get("response_preview")
        if preview:
            details["response_preview"] = preview

    _record_probe_decision(
        recorder,
        spec=spec,
        status=status,
        reason=reason,
        message=message,
        scenario=scenario,
        step=step,
        details=details,
    )


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
        if reason == "missing_reference_sample":
            recorder.record_issue(
                severity="warning",
                code="probe_sample_needed",
                actor=spec.actor,
                scenario=scenario,
                step=step or spec.name,
                message=(
                    f"Probe {spec.name} skipped because no sample exists in approved session docs; "
                    "please provide a sample payload."
                ),
                details={
                    "reason_code": reason,
                    "next_action": "request_sample_from_user",
                    "allowed_source_docs": list(ALLOWED_SESSION_DOCS),
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
        result = await request_func(
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
        status_code: int | None = None
        if exc.result is not None:
            status_code = exc.result.response.status_code

        if status_code is not None and status_code < 500 and exc.result is not None:
            _record_probe_outcome(
                recorder,
                spec=spec,
                result=exc.result,
                scenario=scenario,
                step=step,
            )
            return exc.result

        reason = "probe_http_error"
        if status_code is not None and status_code >= 500:
            reason = "probe_http_server_error"
        _record_probe_decision(
            recorder,
            spec=spec,
            status="failed",
            reason=reason,
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
            scenario=scenario,
            step=step,
            details={
                "related_event_id": exc.event["id"] if exc.event else None,
                "raw_payload": sanitize_payload(
                    exc.result.payload if exc.result else exc.event
                ),
            },
        )
        recorder.record_issue(
            severity="warning",
            code="probe_failed",
            actor=spec.actor,
            scenario=scenario,
            step=step or spec.name,
            related_event_id=exc.event["id"] if exc.event else None,
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
        )
        return None
    except Exception as exc:
        _record_probe_decision(
            recorder,
            spec=spec,
            status="failed",
            reason="probe_unexpected_error",
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
            scenario=scenario,
            step=step,
        )
        recorder.record_issue(
            severity="warning",
            code="probe_failed",
            actor=spec.actor,
            scenario=scenario,
            step=step or spec.name,
            message=f"Probe {spec.name} failed after preflight passed: {exc}",
        )
        return None

    _record_probe_outcome(
        recorder,
        spec=spec,
        result=result,
        scenario=scenario,
        step=step,
    )
    return result


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
