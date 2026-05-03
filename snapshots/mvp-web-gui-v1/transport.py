"""HTTP tracing, masking, and delay helpers for simulation runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Any, Callable, Optional, Tuple

import httpx

from reporting import RunRecorder


ResponseTransform = Callable[[Any], Any]
ResponseOrderInfo = Callable[[Any], Tuple[Optional[int], Optional[str], Optional[str]]]
ResponseStatus = Callable[[Any], Optional[str]]


_SENSITIVE_TEXT_PATTERNS = (
    (re.compile(r'("token"\s*:\s*")([^"]+)(")', re.IGNORECASE), r'\1[redacted]\3'),
    (re.compile(r'("client_secret"\s*:\s*")([^"]+)(")', re.IGNORECASE), r'\1[redacted]\3'),
    (re.compile(r'("otp"\s*:\s*")([^"]+)(")', re.IGNORECASE), r'\1[redacted]\3'),
)


@dataclass(frozen=True)
class HttpResult:
    response: httpx.Response
    payload: Any
    event: dict[str, Any]
    latency_ms: int


class RequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        event: dict[str, Any] | None = None,
        result: HttpResult | None = None,
    ) -> None:
        super().__init__(message)
        self.event = event
        self.result = result


def api_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def token_preview(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"


def build_auth_proof(
    *,
    header_name: str | None,
    token: str | None,
    source: str | None,
    scheme: str | None = None,
) -> dict[str, Any] | None:
    if not header_name or not token:
        return None
    return {
        "header_name": header_name,
        "scheme": scheme,
        "source": source,
        "fingerprint": token_fingerprint(token),
        "preview": token_preview(token),
    }


def sanitize_payload(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    return value


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return (
        normalized == "email"
        or normalized == "phone"
        or normalized == "phone_number"
        or normalized == "user"
        or normalized == "user_data"
        or normalized == "otp"
        or "token" in normalized
        or "authorization" in normalized
        or "secret" in normalized
        or "password" in normalized
        or "card" in normalized
        or normalized == "payment_method"
    )


def _response_preview(payload: Any, raw_text: str) -> str:
    if payload is not None:
        safe = sanitize_payload(payload)
        text = json.dumps(safe, ensure_ascii=False, default=str)
        return text[:2000]
    return redact_text(raw_text)[:2000]


def _full_url(url: str, params: dict[str, Any] | None) -> str:
    request = httpx.Request("GET", url, params=params)
    return str(request.url)


def _request_body(
    *,
    json_body: dict[str, Any] | None,
    data_body: dict[str, Any] | None,
) -> tuple[Any, str]:
    if json_body is not None:
        return sanitize_payload(json_body), "json"
    if data_body is not None:
        return sanitize_payload(data_body), "form"
    return None, "none"


def _safe_payload(payload: Any, transform: ResponseTransform | None) -> Any:
    if transform is not None:
        return transform(payload)
    return sanitize_payload(payload)


async def request_json(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder,
    actor: str,
    action: str,
    method: str,
    url: str,
    endpoint: str,
    category: str = "http",
    scenario: str | None = None,
    step: str | None = None,
    order_db_id: int | None = None,
    order_ref: str | None = None,
    status: str | None = None,
    expected_status: str | None = None,
    observed_status: str | None = None,
    poll_attempt: int | None = None,
    expect_websocket: bool = False,
    track_order: bool = True,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    auth_header_name: str | None = None,
    auth_token: str | None = None,
    auth_source: str | None = None,
    auth_scheme: str | None = None,
    timeout: float = 30.0,
    details: dict[str, Any] | None = None,
    response_transform: ResponseTransform | None = None,
    response_order_info: ResponseOrderInfo | None = None,
    response_status_getter: ResponseStatus | None = None,
) -> HttpResult:
    body, body_encoding = _request_body(json_body=json_body, data_body=data_body)
    auth = build_auth_proof(
        header_name=auth_header_name,
        token=auth_token,
        source=auth_source,
        scheme=auth_scheme,
    )
    started = time.perf_counter()
    full_url = _full_url(url, params)
    try:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            data=data_body,
            headers=headers,
            timeout=timeout,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        event = recorder.record_event(
            actor=actor,
            action=action,
            category=category,
            scenario=scenario,
            step=step,
            ok=False,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=status,
            expected_status=expected_status,
            observed_status=observed_status,
            method=method.upper(),
            endpoint=endpoint,
            full_url=full_url,
            query_params=params,
            body=body,
            body_encoding=body_encoding,
            auth=auth,
            latency_ms=latency_ms,
            poll_attempt=poll_attempt,
            details={**(details or {}), "error": str(exc)},
            expect_websocket=expect_websocket,
            track_order=track_order,
        )
        raise RequestError(
            f"{method.upper()} {full_url} failed: {exc}",
            event=event,
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    try:
        parsed = response.json()
    except ValueError:
        parsed = None

    resolved_order_db_id = order_db_id
    resolved_order_ref = order_ref
    if response_order_info is not None:
        candidate_db_id, candidate_ref, candidate_status = response_order_info(parsed)
        if resolved_order_db_id is None:
            resolved_order_db_id = candidate_db_id
        if resolved_order_ref is None:
            resolved_order_ref = candidate_ref
        if observed_status is None:
            observed_status = candidate_status
    if observed_status is None and response_status_getter is not None:
        observed_status = response_status_getter(parsed)

    safe_payload = _safe_payload(parsed, response_transform) if parsed is not None else None
    preview = _response_preview(safe_payload, response.text)
    event = recorder.record_event(
        actor=actor,
        action=action,
        category=category,
        scenario=scenario,
        step=step,
        ok=response.status_code < 400,
        order_db_id=resolved_order_db_id,
        order_ref=resolved_order_ref,
        status=status,
        expected_status=expected_status,
        observed_status=observed_status,
        method=method.upper(),
        endpoint=endpoint,
        full_url=full_url,
        query_params=params,
        body=body,
        body_encoding=body_encoding,
        auth=auth,
        http_status=response.status_code,
        response_payload=safe_payload,
        response_preview=preview,
        latency_ms=latency_ms,
        poll_attempt=poll_attempt,
        details=details,
        expect_websocket=expect_websocket,
        track_order=track_order,
    )
    result = HttpResult(
        response=response,
        payload=parsed,
        event=event,
        latency_ms=latency_ms,
    )
    if response.status_code >= 400:
        raise RequestError(
            f"{method.upper()} {full_url} returned HTTP {response.status_code}",
            event=event,
            result=result,
        )
    return result


async def traced_sleep(
    seconds: float,
    *,
    recorder: RunRecorder,
    actor: str,
    action: str,
    scenario: str | None = None,
    step: str | None = None,
    order_db_id: int | None = None,
    order_ref: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    recorder.record_event(
        actor=actor,
        action=action,
        category="delay",
        scenario=scenario,
        step=step,
        order_db_id=order_db_id,
        order_ref=order_ref,
        planned_delay_ms=int(seconds * 1000),
        details=details,
        track_order=False,
    )
    await asyncio.sleep(seconds)
