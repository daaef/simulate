#!/usr/bin/env python3
"""Capture live API responses from the local simulator backend, writing unredacted
responses into each api_docs/internal/<group>/<use_case>.json skeleton.

Run against a local dev server only. Refuses to run if DATABASE_URL looks like prod.
Session-cookie-based auth (simulator_session). Phases: read-only first (all GETs),
then seed (create minimal rows), then ID-dependent GETs, finally skip GitHub-external calls.

    cd api_docs/tools
    python3 capture_internal.py                    # phases 1-3 (read + seed + ID-dependent)
    python3 capture_internal.py --only auth/login  # re-run a single use case
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.cookiejar import CookieJar, Cookie

TOOLS_DIR = Path(__file__).resolve().parent
API_DOCS = TOOLS_DIR.parent
REPO_SIMULATE = API_DOCS.parent
REPO_FAINZY = REPO_SIMULATE.parent

# Localhost API - refuse to run against production
BASE_URL = os.getenv("SIMULATOR_BASE_URL", "http://localhost:8080")
DATABASE_URL = os.getenv("DATABASE_URL", "")

if "prod" in DATABASE_URL.lower() or "fainzy.tech" in DATABASE_URL:
    print(f"FATAL: DATABASE_URL looks like production: {DATABASE_URL}")
    sys.exit(1)

if not BASE_URL.startswith("http://localhost") and not BASE_URL.startswith("http://127.0.0.1"):
    print(f"WARNING: BASE_URL is not localhost: {BASE_URL}")
    print("This script is only meant for local dev databases. Continue? (y/n) ", end="")
    if input().strip().lower() != "y":
        sys.exit(1)

ADMIN_USERNAME = os.getenv("SIMULATOR_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("SIMULATOR_ADMIN_PASSWORD", "admin123")
SESSION_COOKIE_NAME = "simulator_session"

# --------------------------------------------------------------------------- HTTP Client

class HttpResult:
    def __init__(self, status, payload, elapsed_ms, headers=None):
        self.status = status
        self.payload = payload
        self.elapsed_ms = elapsed_ms
        self.headers = headers or {}


def http(method: str, url: str, headers: dict, body=None, cookies=None, timeout=20) -> HttpResult:
    """Make an HTTP request, returning status, parsed JSON payload, and elapsed time."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", **headers}

    req = urllib.request.Request(url, data=data, method=method, headers=headers)

    # Add cookies to request
    if cookies:
        for name, value in cookies.items():
            req.add_header("Cookie", f"{name}={value}")

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            elapsed = int((time.monotonic() - t0) * 1000)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"_raw": raw[:40000]}
            return HttpResult(r.status, payload, elapsed, dict(r.headers))
    except urllib.error.HTTPError as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"_raw": raw[:40000]} if raw else {"_status": e.code}
        response_headers = dict(e.headers) if hasattr(e, "headers") else {}
        return HttpResult(e.code, payload, elapsed, response_headers)
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        return HttpResult(None, {"_exception": str(e)}, elapsed)


# --------------------------------------------------------------------------- Skeleton I/O

def skeleton_path(use_case_ref: str) -> Path:
    """use_case_ref is 'group/use_case' or bare 'use_case' (searched across groups)."""
    if "/" in use_case_ref:
        group, name = use_case_ref.split("/", 1)
        return API_DOCS / "internal" / group / f"{name}.json"
    matches = list(API_DOCS.glob(f"internal/*/{use_case_ref}.json"))
    if not matches:
        raise FileNotFoundError(f"no skeleton found for use case {use_case_ref!r}")
    return matches[0]


def load_skeleton(use_case_ref: str) -> dict:
    return json.loads(skeleton_path(use_case_ref).read_text())


def already_fresh(skel: dict) -> bool:
    """Check if capture is today and status is success."""
    capture = skel.get("capture", {})
    verified_at = capture.get("verifiedAt")
    status = capture.get("status")
    if not verified_at or status not in (200, 201):
        return False
    try:
        d = datetime.datetime.fromisoformat(verified_at).date()
    except ValueError:
        return False
    return d == datetime.date.today()


def write_capture(
    use_case_ref: str,
    *,
    path_params: dict | None = None,
    query_params: dict | None = None,
    body_params: dict | None = None,
    auth_value: str | None,
    result: HttpResult,
) -> None:
    """Write captured response to skeleton file."""
    p = skeleton_path(use_case_ref)
    skel = json.loads(p.read_text())

    if path_params is not None:
        skel["params"]["path"] = path_params
    if query_params is not None:
        skel["params"]["query"] = query_params
    if body_params is not None:
        skel["params"]["body"] = body_params
    if auth_value is not None:
        skel["auth"]["value"] = auth_value

    skel["capture"] = {
        "verifiedAt": datetime.datetime.now().astimezone().isoformat(),
        "status": result.status,
        "tool": "capture_internal.py",
        "flavor": "development",
    }
    skel["response"] = result.payload
    p.write_text(json.dumps(skel, indent=2, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- Session State

class Session:
    """Carries real IDs forward between phases."""

    def __init__(self):
        self.session_cookie: str | None = None
        self.run_id: int | None = None
        self.run_profile_id: int | None = None
        self.schedule_id: int | None = None
        self.simulation_plan_id: int | None = None
        self.admin_user_id: int | None = None
        self.test_user_id: int | None = None
        self.github_project: str | None = None
        self.github_mapping_id: int | None = None
        self.results: list[tuple[str, int | None, int]] = []

    def record(self, use_case: str, result: HttpResult):
        self.results.append((use_case, result.status, result.elapsed_ms))
        mark = "OK " if result.status in (200, 201) else f"!! ({result.status})"
        print(f"  {mark} {use_case:40s} {result.elapsed_ms:5d}ms")


def cookies_dict(session: Session) -> dict:
    """Return cookies dict for request."""
    if session.session_cookie:
        return {SESSION_COOKIE_NAME: session.session_cookie}
    return {}


# --------------------------------------------------------------------------- Phase 1: Login and Read

def phase_auth_endpoints(sess: Session, only: str | None) -> None:
    """Capture remaining auth endpoints (register and refresh, logout at the end)."""
    print("\n== Phase 1b: Auth endpoints (register and refresh) ==")

    # Refresh token (if supported - may not be implemented)
    refresh_body = {"refresh_token": "dummy"}
    r = http("POST", f"{BASE_URL}/api/v1/auth/refresh", {}, body=refresh_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "auth/refresh_token", r, body_params=refresh_body, auth_value=sess.session_cookie)

    # Register user (should be 403)
    register_body = {
        "username": "test_register",
        "email": "test@example.com",
        "password": "Test123!",
        "role": "operator",
    }
    r = http("POST", f"{BASE_URL}/api/v1/auth/register", {}, body=register_body)
    maybe_capture(sess, only, "auth/register_user", r, body_params=register_body, auth_value=None)


def phase_logout(sess: Session, only: str | None) -> None:
    """Logout at the end (invalidates session)."""
    print("\n== Final: Logout ==")
    r = http("POST", f"{BASE_URL}/api/v1/auth/logout", {}, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "auth/logout_user", r, auth_value=sess.session_cookie)


def phase_login(sess: Session, only: str | None) -> bool:
    """Login and establish session cookie."""
    print("\n== Phase 1: Login ==")

    login_body = {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    r = http("POST", f"{BASE_URL}/api/v1/auth/login", {}, body=login_body)

    maybe_capture(sess, only, "auth/login_user", r, body_params=login_body, auth_value=None)

    if r.status != 200:
        print(f"Login failed (status={r.status}): {r.payload}")
        return False

    # Extract session cookie from Set-Cookie header
    set_cookie = r.headers.get("set-cookie", "")
    if set_cookie:
        # Parse "simulator_session=VALUE; HttpOnly; Max-Age=..."
        parts = set_cookie.split(";")
        if parts and "=" in parts[0]:
            cookie_part = parts[0].strip()
            name, value = cookie_part.split("=", 1)
            if name.strip() == SESSION_COOKIE_NAME:
                sess.session_cookie = value.strip()

    if not sess.session_cookie:
        print("ERROR: Could not extract session cookie from login response")
        return False

    print(f"  Login successful, session_cookie={sess.session_cookie[:20]}...")
    return True


def phase_read_get_endpoints(sess: Session, only: str | None) -> None:
    """Call all GET endpoints that don't require path parameters."""
    print("\n== Phase 2: Read-only GET endpoints ==")

    endpoints = [
        ("auth/get_session", "GET", "/api/v1/auth/session"),
        ("auth/get_me", "GET", "/api/v1/auth/me"),
        ("runs/list_flows", "GET", "/api/v1/flows"),
        ("runs/list_runs", "GET", "/api/v1/runs"),
        ("runs/get_runs_count", "GET", "/api/v1/runs/count"),
        ("runs/get_dashboard_summary", "GET", "/api/v1/dashboard/summary"),
        ("run_profiles/list_run_profiles", "GET", "/api/v1/run-profiles"),
        ("archives/get_archive_summary", "GET", "/api/v1/archives/summary"),
        ("archives/list_archived_runs", "GET", "/api/v1/archives/runs"),
        ("archives/list_archived_profiles", "GET", "/api/v1/archives/profiles"),
        ("archives/list_archived_schedules", "GET", "/api/v1/archives/schedules"),
        ("archives/list_archived_integration_mappings", "GET", "/api/v1/archives/integration-mappings"),
        ("retention/get_retention_summary", "GET", "/api/v1/retention/summary"),
        ("schedules/list_schedules", "GET", "/api/v1/schedules"),
        ("schedules/get_schedule_summary", "GET", "/api/v1/schedules/summary"),
        ("alerts/list_alerts", "GET", "/api/v1/alerts"),
        ("simulation_plans/list_simulation_plans", "GET", "/api/v1/simulation-plans"),
        ("system/get_system_timezones", "GET", "/api/v1/system/timezones"),
        ("system/get_system_email", "GET", "/api/v1/system/email"),
        ("system/get_system_retention", "GET", "/api/v1/system/retention"),
        ("integrations/list_github_mappings", "GET", "/api/v1/integrations/github/mappings"),
        ("integrations/list_github_triggers", "GET", "/api/v1/integrations/github/triggers"),
        ("integrations/list_github_projects", "GET", "/api/v1/integrations/github/projects"),
        ("orders/orders_auto_login", "GET", "/api/v1/orders/auto-login"),
        ("orders/orders_get_config", "GET", "/api/v1/orders/config"),
        ("orders/orders_list_stores", "GET", "/api/v1/orders/stores"),
        ("overview/get_latest_run_overview", "GET", "/api/v1/overview/latest-run"),
        ("overview/get_socket_status", "GET", "/api/v1/overview/socket-status"),
        ("admin/list_users", "GET", "/api/v1/admin/users"),
    ]

    for use_case, method, path in endpoints:
        url = BASE_URL + path
        r = http(method, url, {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, use_case, r, auth_value=sess.session_cookie)


def phase_seed_resources(sess: Session, only: str | None) -> None:
    """Create minimal seed data for ID-dependent endpoints."""
    print("\n== Phase 3: Seed resources for ID-dependent endpoints ==")

    # Create a run
    run_body = {
        "flow": "doctor",
        "plan": "sim_actors.json",
        "timing": "fast",
        "trigger_source": "manual",
        "trigger_label": "API docs capture",
    }
    r = http("POST", f"{BASE_URL}/api/v1/runs", {}, body=run_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "runs/create_run", r, body_params=run_body, auth_value=sess.session_cookie)

    if r.status in (200, 201) and isinstance(r.payload, dict):
        data = r.payload.get("data") or r.payload
        sess.run_id = data.get("id")
        print(f"  Created run id={sess.run_id}")

    # Create a run profile
    profile_body = {
        "name": "api_docs_capture",
        "description": "Captured for API documentation",
        "flow": "doctor",
        "plan": "sim_actors.json",
        "timing": "fast",
    }
    r = http("POST", f"{BASE_URL}/api/v1/run-profiles", {}, body=profile_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "run_profiles/create_run_profile", r, body_params=profile_body, auth_value=sess.session_cookie)

    if r.status in (200, 201) and isinstance(r.payload, dict):
        # Try multiple possible response structures
        data = r.payload.get("profile") or r.payload.get("data") or r.payload
        sess.run_profile_id = data.get("id") if isinstance(data, dict) else None
        if sess.run_profile_id:
            print(f"  Created run profile id={sess.run_profile_id}")

    # Create a schedule (requires profile_id for simple type)
    if sess.run_profile_id:
        schedule_body = {
            "name": "api_docs_capture",
            "description": "Captured for API documentation",
            "schedule_type": "simple",
            "profile_id": sess.run_profile_id,
            "cadence": "daily",
            "timezone": "UTC",
        }
        r = http("POST", f"{BASE_URL}/api/v1/schedules", {}, body=schedule_body, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "schedules/create_schedule", r, body_params=schedule_body, auth_value=sess.session_cookie)

        if r.status in (200, 201) and isinstance(r.payload, dict):
            # Try multiple possible response structures
            data = r.payload.get("schedule") or r.payload.get("data") or r.payload
            sess.schedule_id = data.get("id") if isinstance(data, dict) else None
            if sess.schedule_id:
                print(f"  Created schedule id={sess.schedule_id}")
    else:
        print("  Skipped schedule creation (no run profile ID)")

    # Create a simulation plan
    plan_body = {
        "name": "api_docs_capture",
        "content": {"flow": "doctor", "plan": "sim_actors.json"},
    }
    r = http("POST", f"{BASE_URL}/api/v1/simulation-plans", {}, body=plan_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "simulation_plans/create_simulation_plan", r, body_params=plan_body, auth_value=sess.session_cookie)

    if r.status in (200, 201) and isinstance(r.payload, dict):
        # Try multiple possible response structures
        data = r.payload.get("plan") or r.payload.get("data") or r.payload
        sess.simulation_plan_id = data.get("id") if isinstance(data, dict) else None
        if sess.simulation_plan_id:
            print(f"  Created simulation plan id={sess.simulation_plan_id}")

    # Create a test user for admin operations
    # Use a unique timestamp-based username to avoid conflicts
    timestamp = int(time.time())
    test_username = f"test_api_docs_{timestamp}"
    user_body = {
        "username": test_username,
        "email": f"test-api-docs-{timestamp}@example.com",
        "password": "TestPassword123!",
        "role": "operator",
    }
    r = http("POST", f"{BASE_URL}/api/v1/admin/users", {}, body=user_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "admin/create_user", r, body_params=user_body, auth_value=sess.session_cookie)

    if r.status in (200, 201) and isinstance(r.payload, dict):
        # Try multiple possible response structures
        data = r.payload.get("user") or r.payload.get("data") or r.payload
        sess.test_user_id = data.get("id") if isinstance(data, dict) else None
        if sess.test_user_id:
            print(f"  Created test user id={sess.test_user_id}")


def phase_id_dependent_endpoints(sess: Session, only: str | None) -> None:
    """Call endpoints that require IDs from seeded resources."""
    print("\n== Phase 4: ID-dependent GET and mutation endpoints ==")

    if sess.run_id:
        # GET endpoints for runs
        endpoints = [
            ("runs/get_run", f"/api/v1/runs/{sess.run_id}"),
            ("runs/get_run_log", f"/api/v1/runs/{sess.run_id}/log"),
            ("runs/get_run_artifacts", f"/api/v1/runs/{sess.run_id}/artifacts/report"),
            ("runs/get_run_metrics", f"/api/v1/runs/{sess.run_id}/metrics"),
            ("runs/get_execution_snapshot", f"/api/v1/runs/{sess.run_id}/execution-snapshot"),
            ("overview/get_run_overview", f"/api/v1/overview/runs/{sess.run_id}"),
        ]
        for use_case, path in endpoints:
            url = BASE_URL + path
            r = http("GET", url, {}, cookies=cookies_dict(sess))
            path_params = {"run_id": sess.run_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie)

        # Mutation endpoints for runs
        mutation_endpoints = [
            ("runs/cancel_run", f"/api/v1/runs/{sess.run_id}/cancel", "POST"),
            ("runs/delete_run", f"/api/v1/runs/{sess.run_id}", "DELETE"),
            ("runs/restore_run", f"/api/v1/runs/{sess.run_id}/restore", "POST"),
            ("runs/replay_run", f"/api/v1/runs/{sess.run_id}/replay", "POST"),
        ]
        for use_case, path, method in mutation_endpoints:
            url = BASE_URL + path
            r = http(method, url, {}, cookies=cookies_dict(sess))
            path_params = {"run_id": sess.run_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie)

    if sess.run_profile_id:
        # Update profile with minimal required fields
        update_body = {
            "name": "api_docs_capture_updated",
            "description": "Updated for API documentation",
            "flow": "doctor",
            "plan": "sim_actors.json",
            "timing": "fast",
        }
        endpoints = [
            ("run_profiles/update_run_profile", f"/api/v1/run-profiles/{sess.run_profile_id}", "PUT", update_body),
            ("run_profiles/delete_run_profile", f"/api/v1/run-profiles/{sess.run_profile_id}", "DELETE", None),
            ("run_profiles/restore_run_profile", f"/api/v1/run-profiles/{sess.run_profile_id}/restore", "POST", None),
            ("run_profiles/launch_run_profile", f"/api/v1/run-profiles/{sess.run_profile_id}/launch", "POST", None),
        ]
        for use_case, path, method, body in endpoints:
            url = BASE_URL + path
            r = http(method, url, {}, body=body, cookies=cookies_dict(sess))
            path_params = {"profile_id": sess.run_profile_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie, body_params=body if method == "PUT" else None)

    if sess.schedule_id:
        # Update schedule with required fields
        update_schedule_body = {
            "name": "api_docs_capture_updated",
            "description": "Updated for API documentation",
            "schedule_type": "simple",
            "profile_id": sess.run_profile_id,
            "cadence": "daily",
            "timezone": "UTC",
        }
        endpoints = [
            ("schedules/update_schedule", f"/api/v1/schedules/{sess.schedule_id}", "PUT", update_schedule_body),
            ("schedules/trigger_schedule", f"/api/v1/schedules/{sess.schedule_id}/trigger", "POST", None),
            ("schedules/pause_schedule", f"/api/v1/schedules/{sess.schedule_id}/pause", "POST", None),
            ("schedules/resume_schedule", f"/api/v1/schedules/{sess.schedule_id}/resume", "POST", None),
            ("schedules/disable_schedule", f"/api/v1/schedules/{sess.schedule_id}/disable", "POST", None),
            ("schedules/delete_schedule", f"/api/v1/schedules/{sess.schedule_id}/delete", "POST", None),
            ("schedules/restore_schedule", f"/api/v1/schedules/{sess.schedule_id}/restore", "POST", None),
        ]
        for use_case, path, method, body in endpoints:
            url = BASE_URL + path
            r = http(method, url, {}, body=body, cookies=cookies_dict(sess))
            path_params = {"schedule_id": sess.schedule_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie, body_params=body if method == "PUT" else None)

        # Purge schedule (only after deleting it)
        r = http("POST", f"{BASE_URL}/api/v1/archives/schedules/{sess.schedule_id}/purge", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "archives/purge_schedule", r, path_params={"schedule_id": sess.schedule_id}, auth_value=sess.session_cookie)

    if sess.simulation_plan_id:
        # Update plan with required content field
        update_body = {
            "name": "api_docs_capture_updated",
            "content": {"flow": "doctor", "plan": "sim_actors.json", "updated": True},
        }
        endpoints = [
            ("simulation_plans/get_simulation_plan", f"/api/v1/simulation-plans/{sess.simulation_plan_id}", "GET", None),
            ("simulation_plans/update_simulation_plan", f"/api/v1/simulation-plans/{sess.simulation_plan_id}", "PUT", update_body),
            ("simulation_plans/delete_simulation_plan", f"/api/v1/simulation-plans/{sess.simulation_plan_id}", "DELETE", None),
        ]
        for use_case, path, method, body in endpoints:
            url = BASE_URL + path
            r = http(method, url, {}, body=body, cookies=cookies_dict(sess))
            path_params = {"plan_id": sess.simulation_plan_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie, body_params=body if method == "PUT" else None)

    if sess.test_user_id:
        # Reset user password
        reset_body = {"new_password": "NewPassword123!"}
        r = http("POST", f"{BASE_URL}/api/v1/admin/users/{sess.test_user_id}/reset-password", {}, body=reset_body, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "admin/reset_user_password", r, path_params={"user_id": sess.test_user_id}, auth_value=sess.session_cookie, body_params=reset_body)

        # Update user with required fields
        update_body = {
            "username": f"test_api_docs_updated_{sess.test_user_id}",
            "email": f"test-api-docs-updated-{sess.test_user_id}@example.com",
            "password": "UpdatedPassword123!",
            "role": "viewer",
        }
        endpoints = [
            ("admin/update_user", f"/api/v1/admin/users/{sess.test_user_id}", "PUT", update_body),
            ("admin/delete_user", f"/api/v1/admin/users/{sess.test_user_id}", "DELETE", None),
        ]
        for use_case, path, method, body in endpoints:
            url = BASE_URL + path
            r = http(method, url, {}, body=body, cookies=cookies_dict(sess))
            path_params = {"user_id": sess.test_user_id}
            maybe_capture(sess, only, use_case, r, path_params=path_params, auth_value=sess.session_cookie, body_params=body if method == "PUT" else None)

    # Purge operations for runs and profiles
    if sess.run_id:
        r = http("POST", f"{BASE_URL}/api/v1/archives/runs/{sess.run_id}/purge", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "archives/purge_run", r, path_params={"run_id": sess.run_id}, auth_value=sess.session_cookie)

    if sess.run_profile_id:
        r = http("POST", f"{BASE_URL}/api/v1/archives/profiles/{sess.run_profile_id}/purge", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "archives/purge_profile", r, path_params={"profile_id": sess.run_profile_id}, auth_value=sess.session_cookie)


def phase_github_integrations(sess: Session, only: str | None) -> None:
    """Create and test GitHub integration mappings (non-external-call endpoints)."""
    print("\n== Phase 5: GitHub integration endpoints (non-external) ==")

    # Create a GitHub mapping (just DB record, no external call)
    if sess.run_profile_id:
        mapping_body = {
            "project": "test-project",
            "environment": "development",
            "profile_id": sess.run_profile_id,
            "enabled": True,
        }
        r = http("POST", f"{BASE_URL}/api/v1/integrations/github/mappings", {}, body=mapping_body, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "integrations/create_github_mapping", r, body_params=mapping_body, auth_value=sess.session_cookie)

        if r.status in (200, 201) and isinstance(r.payload, dict):
            # Try multiple possible response structures
            data = r.payload.get("mapping") or r.payload.get("data") or r.payload
            sess.github_mapping_id = data.get("id") if isinstance(data, dict) else None
            if sess.github_mapping_id:
                print(f"  Created GitHub mapping id={sess.github_mapping_id}")

    # Test operations on GitHub mapping
    if sess.github_mapping_id:
        # First delete it (archives it)
        r = http("DELETE", f"{BASE_URL}/api/v1/integrations/github/mappings/{sess.github_mapping_id}", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "integrations/delete_github_mapping", r, path_params={"mapping_id": sess.github_mapping_id}, auth_value=sess.session_cookie)

        # Purge the GitHub mapping (only after deleting it)
        r = http("POST", f"{BASE_URL}/api/v1/archives/integration-mappings/{sess.github_mapping_id}/purge", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "archives/purge_integration_mapping", r, path_params={"mapping_id": sess.github_mapping_id}, auth_value=sess.session_cookie)

        # Restore it from archive
        r = http("POST", f"{BASE_URL}/api/v1/integrations/github/mappings/{sess.github_mapping_id}/restore", {}, cookies=cookies_dict(sess))
        maybe_capture(sess, only, "integrations/restore_github_mapping", r, path_params={"mapping_id": sess.github_mapping_id}, auth_value=sess.session_cookie)


def phase_skip_external_and_special() -> None:
    """Mark endpoints as skipped - they need external APIs, special headers, or special configuration."""
    print("\n== Phase 5a: Skipped endpoints (external APIs / special requirements) ==")

    skipped_endpoints = {
        "orders/orders_store_login": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_lookup": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_list": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_store_stats": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_customer_stats": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_customer_search": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "orders/orders_update_status": "Makes real external calls to fainzy.tech/lastmile.fainzy.tech APIs",
        "subentities/list_subentities": "Requires x_fainzy_auth_token header and makes external calls to fainzy.tech",
        "subentities/search_subentities": "Requires x_fainzy_auth_token header and makes external calls to fainzy.tech",
    }

    for use_case, reason in skipped_endpoints.items():
        try:
            p = skeleton_path(use_case)
            skel = json.loads(p.read_text())
            skel["capture"] = {
                "verifiedAt": datetime.datetime.now().astimezone().isoformat(),
                "status": None,
                "tool": "capture_internal.py",
                "flavor": "development",
            }
            skel["note"] = f"Skipped: {reason}"
            skel["response"] = None
            p.write_text(json.dumps(skel, indent=2, ensure_ascii=False) + "\n")
            print(f"  {use_case:40s} SKIPPED")
        except FileNotFoundError:
            pass


def phase_system_mutations(sess: Session, only: str | None) -> None:
    """Capture system configuration mutation endpoints."""
    print("\n== Phase 5b: System configuration endpoints ==")

    # Update timezones
    tz_body = {"timezone": "UTC"}
    r = http("PUT", f"{BASE_URL}/api/v1/system/timezones", {}, body=tz_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "system/update_system_timezones", r, body_params=tz_body, auth_value=sess.session_cookie)

    # Update email
    email_body = {
        "smtp_host": "localhost",
        "smtp_port": 1025,
        "smtp_username": "test",
        "smtp_password": "test",
        "sender_email": "test@example.com",
    }
    r = http("PUT", f"{BASE_URL}/api/v1/system/email", {}, body=email_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "system/update_system_email", r, body_params=email_body, auth_value=sess.session_cookie)

    # Test email
    r = http("POST", f"{BASE_URL}/api/v1/system/email/test", {}, body={}, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "system/test_system_email", r, auth_value=sess.session_cookie)

    # Update retention
    retention_body = {
        "days": 90,
        "archive_after_days": 30,
    }
    r = http("PUT", f"{BASE_URL}/api/v1/system/retention", {}, body=retention_body, cookies=cookies_dict(sess))
    maybe_capture(sess, only, "system/update_system_retention", r, body_params=retention_body, auth_value=sess.session_cookie)


def phase_skip_github_external(sess: Session, only: str | None) -> None:
    """Document GitHub-external and webhook endpoints that need to be skipped."""
    print("\n== Phase 6: Skip GitHub-external endpoints ==")

    skipped_endpoints = [
        ("integrations/create_github_project", "Skipped: endpoint makes real external calls to GitHub API (github_webhook_sync.sync_to_github)"),
        ("integrations/rotate_github_project_secret", "Skipped: endpoint makes real external calls to GitHub API (github_webhook_sync.sync_to_github)"),
        ("integrations/update_github_project_repositories", "Skipped: endpoint makes real external calls to GitHub API (github_webhook_sync.sync_to_github)"),
        ("integrations/delete_github_project", "Skipped: endpoint makes real external calls to GitHub API (github_webhook_sync.sync_to_github)"),
        ("integrations/github_deployment_complete_webhook", "Skipped: webhook endpoint that requires GitHub webhook headers and payload"),
    ]

    for use_case, reason in skipped_endpoints:
        try:
            p = skeleton_path(use_case)
            skel = json.loads(p.read_text())
            skel["capture"] = {
                "verifiedAt": datetime.datetime.now().astimezone().isoformat(),
                "status": None,
                "tool": "capture_internal.py",
                "flavor": "development",
            }
            skel["note"] = reason
            skel["response"] = None
            p.write_text(json.dumps(skel, indent=2, ensure_ascii=False) + "\n")
            print(f"  {use_case:40s} SKIPPED")
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- Helpers

def maybe_capture(
    sess: Session, only: str | None, use_case: str, result: HttpResult,
    *, path_params=None, query_params=None, body_params=None, auth_value,
) -> None:
    """Conditionally capture if not already fresh or if explicitly requested."""
    if only and only != use_case and only != use_case.split("/", 1)[-1]:
        return

    try:
        skel = load_skeleton(use_case)
    except FileNotFoundError:
        print(f"  !! no skeleton for {use_case}, skipping write")
        sess.record(use_case, result)
        return

    if already_fresh(skel) and only is None:
        print(f"  == {use_case:40s} already fresh today, skipping")
        return

    write_capture(
        use_case, path_params=path_params, query_params=query_params, body_params=body_params,
        auth_value=auth_value, result=result,
    )
    sess.record(use_case, result)


# --------------------------------------------------------------------------- Main

def main() -> int:
    parser = argparse.ArgumentParser(description="Capture internal API responses")
    parser.add_argument("--only", default=None, help="Capture single use case, e.g. auth/login")
    args = parser.parse_args()

    print(f"Capturing internal API responses from {BASE_URL}")
    print(f"Database: {DATABASE_URL if DATABASE_URL else '(not specified)'}")

    sess = Session()

    if phase_login(sess, args.only):
        phase_auth_endpoints(sess, args.only)
        phase_read_get_endpoints(sess, args.only)
        phase_seed_resources(sess, args.only)
        phase_id_dependent_endpoints(sess, args.only)
        phase_github_integrations(sess, args.only)
        phase_system_mutations(sess, args.only)
        phase_logout(sess, args.only)
        phase_skip_external_and_special()
        phase_skip_github_external(sess, args.only)

    print(f"\n{'use case':45s} {'status':>7s} {'ms':>6s}")
    for use_case, status, ms in sess.results:
        print(f"{use_case:45s} {str(status or 'SKIP'):>7s} {ms:6d}")

    ok = sum(1 for _, s, _ in sess.results if s in (200, 201))
    print(f"\n{ok}/{len(sess.results)} captures succeeded.")
    print("Next: python3 build_docs.py --strict")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
