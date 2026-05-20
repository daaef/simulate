from __future__ import annotations

import base64
import json
import os
import shlex
import urllib.error
import urllib.request
from typing import Any

GITHUB_API = "https://api.github.com"
SECRET_NAME = "SIMULATOR_WEBHOOK_PROJECT_SECRETS"
VARIABLE_NAME = "SIMULATOR_WEBHOOK_REPO_ALLOWLIST"


def _config_repo() -> str:
    return os.getenv("SIMULATOR_GITHUB_CONFIG_REPO", "Fainzy-Technologies/simulator").strip()


def _config_token() -> str:
    return os.getenv("SIMULATOR_GITHUB_CONFIG_TOKEN", "").strip()


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name:
        raise ValueError(f"invalid repository {repo!r}")
    return owner, name


def _github_request(
    method: str,
    path: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    url = f"{GITHUB_API}{path}"
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fainzy-simulator-webhook-sync",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8") if exc.fp else ""
    except urllib.error.URLError as exc:
        raise RuntimeError(f"github request failed: {exc}") from exc

    parsed: dict[str, Any] | list[Any] | None = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
    return status, parsed


def _encrypt_secret(public_key_b64: str, plaintext: str) -> str:
    from nacl import encoding, public

    key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(key)
    encrypted = sealed.encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def _upsert_actions_secret(owner: str, repo: str, token: str, secret_value: str) -> None:
    status, payload = _github_request(
        "GET",
        f"/repos/{owner}/{repo}/actions/secrets/public-key",
        token=token,
    )
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to fetch actions public key (status {status})")

    key_id = str(payload.get("key_id") or "")
    key_b64 = str(payload.get("key") or "")
    if not key_id or not key_b64:
        raise RuntimeError("github public key response missing key_id or key")

    encrypted_value = _encrypt_secret(key_b64, secret_value)
    put_status, _ = _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/actions/secrets/{SECRET_NAME}",
        token=token,
        body={
            "encrypted_value": encrypted_value,
            "key_id": key_id,
        },
    )
    if put_status not in {201, 204}:
        raise RuntimeError(f"failed to update actions secret (status {put_status})")


def _upsert_actions_variable(owner: str, repo: str, token: str, variable_value: str) -> None:
    patch_status, _ = _github_request(
        "PATCH",
        f"/repos/{owner}/{repo}/actions/variables/{VARIABLE_NAME}",
        token=token,
        body={"name": VARIABLE_NAME, "value": variable_value},
    )
    if patch_status == 204:
        return
    if patch_status != 404:
        raise RuntimeError(f"failed to update actions variable (status {patch_status})")

    post_status, _ = _github_request(
        "POST",
        f"/repos/{owner}/{repo}/actions/variables",
        token=token,
        body={"name": VARIABLE_NAME, "value": variable_value},
    )
    if post_status != 201:
        raise RuntimeError(f"failed to create actions variable (status {post_status})")


def build_gh_commands(secrets_map: dict[str, str], allowlist_map: dict[str, list[str]]) -> dict[str, str]:
    repo = _config_repo()
    secrets_body = json.dumps(secrets_map, separators=(",", ":"))
    allowlist_body = json.dumps(allowlist_map, separators=(",", ":"))
    return {
        "secret": (
            f"gh secret set {SECRET_NAME} --repo {repo} "
            f"--body {shlex.quote(secrets_body)}"
        ),
        "allowlist": (
            f"gh variable set {VARIABLE_NAME} --repo {repo} "
            f"--body {shlex.quote(allowlist_body)}"
        ),
    }


def sync_to_github(secrets_map: dict[str, str], allowlist_map: dict[str, list[str]]) -> dict[str, Any]:
    sync_commands = build_gh_commands(secrets_map, allowlist_map)
    token = _config_token()
    if not token:
        return {
            "sync_status": "skipped",
            "sync_error": "SIMULATOR_GITHUB_CONFIG_TOKEN is not configured on the API server.",
            "sync_commands": sync_commands,
        }

    repo = _config_repo()
    owner, name = _split_repo(repo)
    secrets_json = json.dumps(secrets_map, separators=(",", ":"))
    allowlist_json = json.dumps(allowlist_map, separators=(",", ":"))

    try:
        _upsert_actions_secret(owner, name, token, secrets_json)
        _upsert_actions_variable(owner, name, token, allowlist_json)
    except Exception as exc:
        return {
            "sync_status": "failed",
            "sync_error": str(exc),
            "sync_commands": sync_commands,
        }

    return {
        "sync_status": "ok",
        "sync_error": None,
        "sync_commands": sync_commands,
        "sync_message": (
            "Synced to GitHub. Run deploy (or wait for the next push to main) "
            "so host .env picks up the new values. Webhooks use the local file immediately."
        ),
    }
