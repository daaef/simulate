"""Token and identity acquisition for the simulator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

import config
from reporting import RunRecorder
from transport import RequestError, api_data, build_auth_proof, request_json

console = Console()
ENV_PATH = Path(__file__).parent / ".env"


@dataclass(frozen=True)
class UserSession:
    token: str
    user_id: int
    user: dict[str, Any]
    token_source: str


@dataclass(frozen=True)
class StoreSession:
    last_mile_token: str
    fainzy_token: str | None
    subentity: dict[str, Any]
    token_source: str


class HttpApiError(RuntimeError):
    def __init__(
        self,
        *,
        url: str,
        status_code: int,
        response_text: str,
        related_event_id: int | None = None,
    ) -> None:
        super().__init__(f"HTTP {status_code} from {url}: {response_text[:500]}")
        self.url = url
        self.status_code = status_code
        self.response_text = response_text
        self.related_event_id = related_event_id


def _token(payload: dict[str, Any]) -> str | None:
    data = api_data(payload)
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("token") or payload.get("token")
    return payload.get("token")


def _write_env_values(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        replaced = False
        for key, value in updates.items():
            prefix = f"{key}="
            if line.startswith(prefix):
                new_lines.append(f"{key}={value}")
                seen.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _persist_user_token(*, token: str, user_id: int) -> None:
    config.USER_LASTMILE_TOKEN = token
    config.USER_ID = user_id
    _write_env_values(
        {
            "USER_LASTMILE_TOKEN": token,
            "USER_ID": str(user_id),
        }
    )


def _clear_cached_user_token() -> None:
    config.USER_LASTMILE_TOKEN = ""
    config.USER_ID = None
    _write_env_values(
        {
            "USER_LASTMILE_TOKEN": "",
            "USER_ID": "",
        }
    )


def _otp_response(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {"data": "[redacted]"}
    return "[redacted]"


async def _request(
    client: httpx.AsyncClient,
    *,
    recorder: RunRecorder | None,
    actor: str,
    action: str,
    method: str,
    url: str,
    endpoint: str,
    scenario: str | None = None,
    step: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    auth_header_name: str | None = None,
    auth_token: str | None = None,
    auth_source: str | None = None,
    auth_scheme: str | None = None,
    response_transform=None,
    track_order: bool = False,
) -> Any:
    if recorder is None:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=30.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HttpApiError(
                url=url,
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            ) from exc
        return response.json()

    try:
        result = await request_json(
            client,
            recorder=recorder,
            actor=actor,
            action=action,
            category="auth",
            scenario=scenario,
            step=step,
            method=method,
            url=url,
            endpoint=endpoint,
            params=params,
            json_body=json_body,
            headers=headers,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            auth_source=auth_source,
            auth_scheme=auth_scheme,
            response_transform=response_transform,
            track_order=track_order,
        )
    except RequestError as exc:
        if exc.result is not None:
            raise HttpApiError(
                url=url,
                status_code=exc.result.response.status_code,
                response_text=exc.result.response.text,
                related_event_id=exc.event["id"] if exc.event else None,
            ) from exc
        raise HttpApiError(
            url=url,
            status_code=0,
            response_text=str(exc),
            related_event_id=exc.event["id"] if exc.event else None,
        ) from exc
    return result.payload


async def _validate_cached_user_token(
    client: httpx.AsyncClient,
    *,
    token: str,
    user_id: int,
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> bool:
    await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="validate_cached_user_token",
        method="GET",
        url=f"{config.LASTMILE_BASE_URL}/v1/core/orders/",
        endpoint="/v1/core/orders/",
        scenario=scenario,
        step="auth_validate_cached_user_token",
        params={"user": str(user_id)},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {token}",
        },
        auth_header_name="Authorization",
        auth_token=token,
        auth_source="user_cached_token",
        auth_scheme="Token",
    )
    return True


async def fetch_user_session(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> UserSession:
    if config.USER_LASTMILE_TOKEN:
        if config.USER_ID is None:
            console.print(
                "[yellow]auth:[/] USER_LASTMILE_TOKEN was set without USER_ID; "
                "ignoring cache and refreshing via OTP."
            )
        else:
            console.print("[dim]auth:[/] Validating cached USER_LASTMILE_TOKEN ...")
            try:
                await _validate_cached_user_token(
                    client,
                    token=config.USER_LASTMILE_TOKEN,
                    user_id=config.USER_ID,
                    recorder=recorder,
                    scenario=scenario,
                )
                console.print(
                    f"[green]auth:[/] Reusing cached user token for user_id={config.USER_ID}."
                )
                return UserSession(
                    token=config.USER_LASTMILE_TOKEN,
                    user_id=config.USER_ID,
                    user={"id": config.USER_ID},
                    token_source="user_cached_token",
                )
            except HttpApiError as exc:
                if exc.status_code in {401, 403}:
                    console.print(
                        "[yellow]auth:[/] Cached user token was rejected; refreshing via OTP."
                    )
                    _clear_cached_user_token()
                else:
                    raise

    if not config.USER_PHONE_NUMBER:
        raise RuntimeError(
            "Either USER_LASTMILE_TOKEN or USER_PHONE_NUMBER must be set in .env"
        )

    console.print(f"[dim]auth:[/] Requesting OTP for {config.USER_PHONE_NUMBER} ...")
    otp_payload = await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="request_user_otp",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/otp/send/",
        endpoint="/v1/auth/otp/send/",
        scenario=scenario,
        step="auth_request_user_otp",
        json_body={"phone_number": config.USER_PHONE_NUMBER},
        response_transform=_otp_response,
    )
    otp = api_data(otp_payload)
    if not otp:
        raise RuntimeError(f"OTP response did not contain data: {otp_payload}")

    console.print("[dim]auth:[/] Verifying OTP ...")
    verify_payload = await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="verify_user_otp",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/otp/verify/",
        endpoint="/v1/auth/otp/verify/",
        scenario=scenario,
        step="auth_verify_user_otp",
        json_body={"phone_number": config.USER_PHONE_NUMBER, "otp": str(otp)},
    )
    verify_data = api_data(verify_payload)
    if not isinstance(verify_data, dict):
        raise RuntimeError(f"OTP verify response had an invalid shape: {verify_payload}")
    if verify_data.get("setup_complete") is not True:
        raise RuntimeError(
            "The configured phone number is not setup_complete=true. "
            "Use an already-registered test user before running the simulation."
        )
    if verify_data.get("is_active") is False:
        raise RuntimeError("The configured user is inactive; reactivate it before simulation.")

    console.print("[dim]auth:[/] Fetching user LastMile token ...")
    auth_payload = await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="fetch_user_token",
        method="POST",
        url=f"{config.LASTMILE_BASE_URL}/v1/auth/users/auth/",
        endpoint="/v1/auth/users/auth/",
        scenario=scenario,
        step="auth_fetch_user_token",
        json_body={"phone_number": config.USER_PHONE_NUMBER},
    )
    auth_data = api_data(auth_payload)
    if not isinstance(auth_data, dict):
        raise RuntimeError(f"User auth response had an invalid shape: {auth_payload}")

    token = auth_data.get("token")
    user = auth_data.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not token:
        raise RuntimeError(f"User auth response did not contain a token: {auth_payload}")
    if not user_id:
        raise RuntimeError(f"User auth response did not contain user.id: {auth_payload}")

    _persist_user_token(token=str(token), user_id=int(user_id))
    console.print(f"[green]auth:[/] User token acquired for user_id={user_id}.")
    return UserSession(
        token=str(token),
        user_id=int(user_id),
        user=user,
        token_source="user_otp_auth",
    )


async def fetch_store_token(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> tuple[str, str]:
    if config.STORE_LASTMILE_TOKEN:
        console.print("[dim]store_sim:[/] Using pre-set STORE_LASTMILE_TOKEN from .env")
        if recorder is not None:
            recorder.record_event(
                actor="auth",
                action="reuse_store_env_token",
                category="auth",
                scenario=scenario,
                step="auth_reuse_store_env_token",
                auth=build_auth_proof(
                    header_name="Fainzy-Token",
                    token=config.STORE_LASTMILE_TOKEN,
                    source="store_env_token",
                ),
                details={"mode": "env"},
                track_order=False,
            )
        return config.STORE_LASTMILE_TOKEN, "store_env_token"

    if not config.STORE_ID:
        raise RuntimeError(
            "Either STORE_LASTMILE_TOKEN or STORE_ID must be set in .env"
        )

    console.print("[dim]auth:[/] Fetching store LastMile/Fainzy-Token ...")
    payload = await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="fetch_store_token",
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/biz/product/authentication/",
        endpoint="/v1/biz/product/authentication/",
        scenario=scenario,
        step="auth_fetch_store_token",
        params={"product": "rds"},
    )
    token = _token(payload)
    if not token:
        raise RuntimeError(f"Store auth response did not contain a token: {payload}")

    console.print("[green]auth:[/] Store LastMile token acquired.")
    return str(token), "store_product_auth"


async def fetch_store_session(
    client: httpx.AsyncClient,
    recorder: RunRecorder | None = None,
    *,
    scenario: str | None = None,
) -> StoreSession:
    if not config.STORE_ID:
        raise RuntimeError("STORE_ID is required so fixtures can use a real store profile.")

    last_mile_token, token_source = await fetch_store_token(
        client,
        recorder=recorder,
        scenario=scenario,
    )

    console.print(f"[dim]auth:[/] Fetching store profile for store_id={config.STORE_ID} ...")
    payload = await _request(
        client,
        recorder=recorder,
        actor="auth",
        action="fetch_store_profile",
        method="POST",
        url=f"{config.FAINZY_BASE_URL}/v1/entities/store/login",
        endpoint="/v1/entities/store/login",
        scenario=scenario,
        step="auth_fetch_store_profile",
        json_body={"store_id": config.STORE_ID},
        headers={
            "Content-Type": "application/json",
            "Store-Request": str(config.STORE_ID),
        },
    )
    data = api_data(payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Store login response had an invalid shape: {payload}")

    subentity = data.get("subentity")
    if not isinstance(subentity, dict) or not subentity.get("id"):
        raise RuntimeError(f"Store login response did not contain subentity.id: {payload}")

    config.SUBENTITY_ID = int(subentity["id"])
    if subentity.get("currency"):
        config.STORE_CURRENCY = str(subentity["currency"]).lower()

    console.print(
        f"[green]auth:[/] Store profile acquired for subentity_id={config.SUBENTITY_ID}."
    )
    return StoreSession(
        last_mile_token=last_mile_token,
        fainzy_token=data.get("token"),
        subentity=subentity,
        token_source=token_source,
    )
