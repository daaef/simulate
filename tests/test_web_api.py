from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile
import threading
import time
import unittest
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SIMULATOR_WORKDIR", str(ROOT))
os.environ.setdefault("SIMULATOR_PROJECT_DIR", str(ROOT))
os.environ.setdefault("RUN_DB_PATH", str(RUNS_DIR / "web-gui-test.sqlite"))
os.environ.setdefault("RUN_LOG_DIR", str(RUNS_DIR / "web-gui-test-logs"))

from api.app import main as web_api
from api.app.overview import service as overview_service


def _build_events(count: int) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for index in range(count):
        payload.append(
            {
                "id": index + 1,
                "ts": f"2026-05-04T10:{index % 60:02d}:00Z",
                "actor": "user",
                "action": "http_call",
                "method": "GET",
                "endpoint": f"/api/v1/mock/{index}",
                "http_status": 200,
                "latency_ms": 20 + index,
                "details": "x" * 120,
                "response_preview": "y" * 200,
            }
        )
    return payload


class EventsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        with web_api.EVENT_CACHE_LOCK:
            web_api.EVENT_CACHE.clear()

    def test_events_cache_hits_without_reparse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "events.json"
            path.write_text(json.dumps(_build_events(10)), encoding="utf-8")

            with mock.patch.object(web_api, "_load_events", wraps=web_api._load_events) as loader:
                first = web_api._load_events_cached(path)
                second = web_api._load_events_cached(path)

            self.assertEqual(loader.call_count, 1)
            self.assertIs(first, second)
            self.assertEqual(len(second.events), 10)

    def test_events_cache_invalidates_on_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "events.json"
            path.write_text(json.dumps(_build_events(10)), encoding="utf-8")

            with mock.patch.object(web_api, "_load_events", wraps=web_api._load_events) as loader:
                first = web_api._load_events_cached(path)
                updated_payload = _build_events(12)
                path.write_text(json.dumps(updated_payload), encoding="utf-8")
                os.utime(path, None)
                second = web_api._load_events_cached(path)

            self.assertEqual(loader.call_count, 2)
            self.assertNotEqual(first.size, second.size)
            self.assertEqual(len(second.events), 12)

    def test_artifact_events_endpoint_reuses_cached_parse_for_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "events.json"
            path.write_text(json.dumps(_build_events(250)), encoding="utf-8")
            fake_run = {"events_path": str(path), "report_path": None, "story_path": None}

            with mock.patch.object(web_api, "_get_run", return_value=fake_run):
                with mock.patch.object(web_api, "_load_events", wraps=web_api._load_events) as loader:
                    first = web_api.get_run_artifact(
                        run_id=1,
                        kind="events",
                        offset=0,
                        limit=120,
                        compact=True,
                    )
                    second = web_api.get_run_artifact(
                        run_id=1,
                        kind="events",
                        offset=120,
                        limit=120,
                        compact=True,
                    )

            self.assertEqual(loader.call_count, 1)
            self.assertEqual(first["count"], 120)
            self.assertEqual(second["count"], 120)
            self.assertEqual(first["total_count"], 250)
            self.assertEqual(second["total_count"], 250)
            first_row = first["content"][0]
            self.assertIn("method", first_row)
            self.assertIn("endpoint", first_row)
            self.assertNotIn("metadata", first_row)

    def test_runs_and_summary_stay_responsive_during_slow_events_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "events.json"
            path.write_text(json.dumps(_build_events(500)), encoding="utf-8")
            fake_run = {"events_path": str(path), "report_path": None, "story_path": None}
            errors: list[Exception] = []

            original_load = web_api._load_events

            def slow_load(p: pathlib.Path) -> list[dict[str, object]]:
                time.sleep(0.35)
                return original_load(p)  # type: ignore[return-value]

            def fire_events_request() -> None:
                try:
                    web_api.get_run_artifact(
                        run_id=777,
                        kind="events",
                        offset=0,
                        limit=120,
                        compact=True,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

            with mock.patch.object(web_api, "_get_run", return_value=fake_run):
                with mock.patch.object(web_api, "_load_events", side_effect=slow_load):
                    thread = threading.Thread(target=fire_events_request)
                    thread.start()
                    time.sleep(0.08)
                    started = time.perf_counter()
                    runs_payload = web_api._list_runs(limit=5)
                    summary_payload = web_api.dashboard_summary()
                    elapsed = time.perf_counter() - started
                    thread.join()

        self.assertFalse(errors)
        self.assertIsInstance(runs_payload, list)
        self.assertIn("total_runs", summary_payload)
        self.assertLess(elapsed, 0.45)

    def test_compact_event_keeps_decision_status(self) -> None:
        compact = web_api._compact_event(
            {
                "id": 1,
                "ts": "2026-05-17T22:00:00Z",
                "actor": "user",
                "action": "probe_saved_cards",
                "category": "decision",
                "status": "inconclusive",
                "reason_code": "probe_schema_undocumented",
                "reason_message": "shape not documented",
                "next_action": "continue_run",
                "run_continued": True,
                "ok": True,
            }
        )
        self.assertEqual(compact["status"], "inconclusive")
        self.assertEqual(compact["category"], "decision")

    def test_event_metrics_count_only_real_failures(self) -> None:
        metrics = web_api._event_metrics(
            [
                {
                    "id": 1,
                    "category": "decision",
                    "status": "skipped",
                    "ok": False,
                    "reason_code": "missing_reference_sample",
                },
                {
                    "id": 2,
                    "category": "decision",
                    "status": "inconclusive",
                    "ok": False,
                    "reason_code": "probe_schema_undocumented",
                },
                {
                    "id": 3,
                    "category": "decision",
                    "status": "passed",
                    "ok": True,
                },
                {
                    "id": 4,
                    "category": "http",
                    "method": "GET",
                    "endpoint": "/v1/statistics/subentities/7/",
                    "http_status": 404,
                    "ok": False,
                },
                {
                    "id": 5,
                    "category": "http",
                    "method": "GET",
                    "endpoint": "/v1/core/orders/",
                    "http_status": 503,
                    "ok": False,
                },
                {
                    "id": 6,
                    "category": "decision",
                    "status": "failed",
                    "ok": False,
                    "reason_code": "probe_http_server_error",
                },
            ]
        )
        self.assertEqual(metrics["failed_events"], 2)


class AuthSeedTests(unittest.TestCase):
    def test_default_admin_seed_password_matches_documented_credentials(self) -> None:
        try:
            import bcrypt
        except ImportError as exc:  # pragma: no cover - local env may omit API deps
            self.skipTest(f"bcrypt is not installed: {exc}")

        migration = (ROOT / "api" / "migrations" / "001-initial-schema.sql").read_text(
            encoding="utf-8"
        )
        match = re.search(r"'(\$2b\$12\$[^']+)'\s*, -- bcrypt hash of \"admin123\"", migration)
        self.assertIsNotNone(match)

        self.assertTrue(bcrypt.checkpw(b"admin123", match.group(1).encode("utf-8")))


class _FakeCookieAuthManager:
    def __init__(self) -> None:
        self.users = {
            "alice": {
                "id": 7,
                "username": "alice",
                "email": "alice@example.com",
                "role": "admin",
                "created_at": "2026-05-06T00:00:00Z",
                "last_login": None,
                "preferences": {},
            },
            "bob": {
                "id": 8,
                "username": "bob",
                "email": "bob@example.com",
                "role": "viewer",
                "created_at": "2026-05-06T00:00:00Z",
                "last_login": None,
                "preferences": {},
            },
        }
        self.active_session_by_user_id: dict[int, str] = {}

    def authenticate_user(self, username: str, password: str) -> dict[str, object] | None:
        if password == "secret" and username in self.users:
            return dict(self.users[username])
        return None

    def create_session(self, user_id: int, *, user_agent: str | None = None, ip_address: str | None = None) -> str:
        token = f"session-{user_id}-{len(self.active_session_by_user_id) + 1}"
        self.active_session_by_user_id[user_id] = token
        return token

    def get_user_by_session_token(self, session_token: str) -> dict[str, object] | None:
        for user in self.users.values():
            if self.active_session_by_user_id.get(int(user["id"])) == session_token:
                return dict(user)
        return None

    def invalidate_session(self, session_token: str) -> bool:
        for user_id, active_token in list(self.active_session_by_user_id.items()):
            if active_token == session_token:
                del self.active_session_by_user_id[user_id]
                return True
        return False

    def list_users(self) -> list[dict[str, object]]:
        return [dict(user) for user in self.users.values()]


class CookieSessionAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.client = TestClient(web_api.app)

    def tearDown(self) -> None:
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def test_login_sets_cookie_and_session_endpoint_reads_it(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(web_api.SESSION_COOKIE_NAME, response.cookies)

        session_response = self.client.get("/api/v1/auth/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["username"], "alice")

    def test_form_login_redirects_to_overview_and_sets_cookie(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "alice", "password": "secret"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/overview")
        self.assertIn(web_api.SESSION_COOKIE_NAME, response.cookies)

    def test_second_login_invalidates_prior_session(self) -> None:
        first = self.client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret"},
        )
        first_cookie = first.cookies.get(web_api.SESSION_COOKIE_NAME)
        self.assertIsNotNone(first_cookie)

        second_client = TestClient(web_api.app)
        try:
            second = second_client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "secret"},
            )
            second_cookie = second.cookies.get(web_api.SESSION_COOKIE_NAME)
            self.assertIsNotNone(second_cookie)
            self.assertNotEqual(first_cookie, second_cookie)

            stale_client = TestClient(web_api.app)
            try:
                stale_client.cookies.set(web_api.SESSION_COOKIE_NAME, first_cookie)
                stale_response = stale_client.get("/api/v1/auth/session")
                self.assertEqual(stale_response.status_code, 401)
            finally:
                stale_client.close()

            second_client.cookies.set(web_api.SESSION_COOKIE_NAME, second_cookie)
            fresh_response = second_client.get("/api/v1/auth/session")
            self.assertEqual(fresh_response.status_code, 200)
            self.assertEqual(fresh_response.json()["username"], "alice")
        finally:
            second_client.close()

    def test_protected_runs_route_rejects_anonymous_requests(self) -> None:
        response = TestClient(web_api.app).get("/api/v1/runs")
        self.assertEqual(response.status_code, 401)

    def test_viewer_can_read_runs_but_cannot_access_admin_users(self) -> None:
        viewer_client = TestClient(web_api.app)
        try:
            login = viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "secret"},
            )
            self.assertEqual(login.status_code, 200)

            runs_response = viewer_client.get("/api/v1/runs")
            self.assertEqual(runs_response.status_code, 200)

            admin_response = viewer_client.get("/api/v1/admin/users")
            self.assertEqual(admin_response.status_code, 403)
        finally:
            viewer_client.close()

    def test_viewer_can_read_archive_and_retention_summaries(self) -> None:
        viewer_client = TestClient(web_api.app)
        try:
            login = viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "secret"},
            )
            self.assertEqual(login.status_code, 200)

            archive_response = viewer_client.get("/api/v1/archives/summary")
            retention_response = viewer_client.get("/api/v1/retention/summary")

            self.assertEqual(archive_response.status_code, 200)
            self.assertEqual(retention_response.status_code, 200)
            self.assertIn("counts", archive_response.json())
            self.assertIn("queue", retention_response.json())
        finally:
            viewer_client.close()

    def test_operator_can_delete_schedule_and_profile(self) -> None:
        self.fake_auth.users["bob"]["role"] = "operator"
        operator_client = TestClient(web_api.app)
        try:
            login = operator_client.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "secret"},
            )
            self.assertEqual(login.status_code, 200)

            profile_response = operator_client.post(
                "/api/v1/run-profiles",
                json={
                    "name": f"operator-profile-{time.time_ns()}",
                    "flow": "doctor",
                    "plan": "sim_actors.json",
                    "timing": "fast",
                },
            )
            self.assertEqual(profile_response.status_code, 200)
            profile_id = int(profile_response.json()["profile"]["id"])

            schedule_response = operator_client.post(
                "/api/v1/schedules",
                json={
                    "name": f"operator-schedule-{time.time_ns()}",
                    "schedule_type": "simple",
                    "profile_id": profile_id,
                    "anchor_start_at": "2026-05-19T08:00:00Z",
                    "period": "daily",
                    "stop_rule": "never",
                    "repeat": "daily",
                    "runs_per_period": 1,
                    "timezone": "UTC",
                    "run_slots": [{"time": "08:00"}],
                    "campaign_steps": [{"profile_id": profile_id, "repeat_count": 1, "spacing_seconds": 0, "timeout_seconds": 900, "failure_policy": "continue", "execution_mode": "saved_profile"}],
                },
            )
            self.assertEqual(schedule_response.status_code, 200)
            schedule_id = int(schedule_response.json()["schedule"]["id"])

            delete_schedule_response = operator_client.post(f"/api/v1/schedules/{schedule_id}/delete")
            self.assertEqual(delete_schedule_response.status_code, 200)
            self.assertEqual(delete_schedule_response.json()["schedule"]["status"], "deleted")

            delete_profile_response = operator_client.delete(f"/api/v1/run-profiles/{profile_id}")
            self.assertEqual(delete_profile_response.status_code, 200)
        finally:
            operator_client.close()


class RunExecutionSnapshotTests(unittest.TestCase):
    def test_create_run_persists_execution_snapshot(self) -> None:
        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self) -> None:
                return None

        request = web_api.RunCreateRequest(
            flow="doctor",
            plan="sim_actors.json",
            timing="fast",
            mode="trace",
            suite="doctor",
            scenarios=["app_bootstrap", "store_dashboard"],
            store_id="FZY_123",
            phone="+2348000000000",
            all_users=False,
            strict_plan=True,
            skip_app_probes=True,
            skip_store_dashboard_probes=True,
            no_auto_provision=False,
            enforce_websocket_gates=True,
            timeout_fails=True,
            post_order_actions=True,
            extra_args=["--strict-plan"],
        )

        with mock.patch.object(web_api.threading, "Thread", _FakeThread):
            run = web_api._create_run(request)

        snapshot = run.get("execution_snapshot")
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["flow"], "doctor")
        self.assertEqual(snapshot["plan"], "sim_actors.json")
        self.assertEqual(snapshot["suite"], "doctor")
        self.assertEqual(snapshot["scenarios"], ["app_bootstrap", "store_dashboard"])
        self.assertEqual(snapshot["store_id"], "FZY_123")
        self.assertEqual(snapshot["phone"], "+2348000000000")
        self.assertTrue(snapshot["strict_plan"])
        self.assertTrue(snapshot["skip_app_probes"])
        self.assertTrue(snapshot["skip_store_dashboard_probes"])
        self.assertTrue(snapshot["enforce_websocket_gates"])
        self.assertTrue(snapshot["timeout_fails"])
        self.assertEqual(snapshot["extra_args"], ["--strict-plan"])
        self.assertIn("python3 -u -m simulate doctor", snapshot["command"])
        self.assertIn("--suite doctor", snapshot["command"])
        self.assertIn("--scenario app_bootstrap", snapshot["command"])
        self.assertIn("--enforce-websocket-gates", snapshot["command"])
        self.assertIn("--timeout-fails", snapshot["command"])

    def test_create_run_passes_launch_env_overrides_to_runner_thread(self) -> None:
        class _FakeThread:
            instances: list["_FakeThread"] = []

            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon
                _FakeThread.instances.append(self)

            def start(self) -> None:
                return None

        request = web_api.RunCreateRequest(
            flow="doctor",
            plan="sim_actors.json",
            timing="fast",
        )

        with mock.patch.object(web_api.threading, "Thread", _FakeThread):
            web_api._create_run(request)

        self.assertTrue(_FakeThread.instances)
        launch_env_overrides = _FakeThread.instances[-1].args[3]
        self.assertEqual(launch_env_overrides["USER_PHONE_NUMBER"], "")
        self.assertEqual(launch_env_overrides["STORE_ID"], "")
        self.assertEqual(launch_env_overrides["SIM_DISABLE_RANDOM_PHONE"], "0")
        self.assertEqual(launch_env_overrides["SIM_DISABLE_RANDOM_STORE"], "0")

    def test_build_command_rejects_invalid_mode_combinations(self) -> None:
        with self.assertRaises(web_api.HTTPException) as trace_continuous:
            web_api._build_command(
                web_api.RunCreateRequest(
                    flow="doctor",
                    plan="sim_actors.json",
                    timing="fast",
                    mode="trace",
                    continuous=True,
                )
            )
        self.assertIn("only supported in load mode", str(trace_continuous.exception.detail))

        with self.assertRaises(web_api.HTTPException) as load_trace_controls:
            web_api._build_command(
                web_api.RunCreateRequest(
                    flow="load",
                    plan="sim_actors.json",
                    timing="fast",
                    mode="load",
                    suite="doctor",
                )
            )
        self.assertIn("only supported in trace mode", str(load_trace_controls.exception.detail))

        with self.assertRaises(web_api.HTTPException) as bad_reject:
            web_api._build_command(
                web_api.RunCreateRequest(
                    flow="load",
                    plan="sim_actors.json",
                    timing="fast",
                    mode="load",
                    reject=2.0,
                )
            )
        self.assertIn("between 0.0 and 1.0", str(bad_reject.exception.detail))

        with self.assertRaises(web_api.HTTPException) as trace_orders:
            web_api._build_command(
                web_api.RunCreateRequest(
                    flow="doctor",
                    plan="sim_actors.json",
                    timing="fast",
                    mode="trace",
                    orders=2,
                )
            )
        self.assertIn("orders is only supported in trace mode for place-order", str(trace_orders.exception.detail))

    def test_build_command_allows_place_order_trace_orders_with_cap(self) -> None:
        request = web_api.RunCreateRequest(
            flow="place-order",
            plan="sim_actors.json",
            timing="fast",
            orders=3,
        )

        command = web_api._build_command(request)

        self.assertEqual(command[:7], ["python3", "-u", "-m", "simulate", "place-order", "--plan", "sim_actors.json"])
        self.assertIn("--orders", command)
        self.assertEqual(command[command.index("--orders") + 1], "3")

        with self.assertRaises(web_api.HTTPException) as too_many:
            web_api._build_command(
                web_api.RunCreateRequest(
                    flow="place-order",
                    plan="sim_actors.json",
                    timing="fast",
                    orders=11,
                )
            )
        self.assertIn("orders must be <= 10 for place-order", str(too_many.exception.detail))

    def test_launch_env_overrides_default_to_random_actor_selection(self) -> None:
        request = web_api.RunCreateRequest(
            flow="doctor",
            plan="sim_actors.json",
            timing="fast",
            extra_args=[],
        )
        overrides = web_api._launch_env_overrides_for_request(request)
        self.assertEqual(overrides["USER_PHONE_NUMBER"], "")
        self.assertEqual(overrides["STORE_ID"], "")
        self.assertEqual(overrides["SIM_DISABLE_RANDOM_PHONE"], "0")
        self.assertEqual(overrides["SIM_DISABLE_RANDOM_STORE"], "0")

    def test_launch_env_overrides_preserve_explicit_actor_and_random_flags(self) -> None:
        request = web_api.RunCreateRequest(
            flow="doctor",
            plan="sim_actors.json",
            timing="fast",
            store_id="FZY_123",
            phone="+2348000000000",
            extra_args=["--no-random-phone", "--no-random-store"],
        )
        overrides = web_api._launch_env_overrides_for_request(request)
        self.assertEqual(overrides["USER_PHONE_NUMBER"], "+2348000000000")
        self.assertEqual(overrides["STORE_ID"], "FZY_123")
        self.assertEqual(overrides["SIM_DISABLE_RANDOM_PHONE"], "1")
        self.assertEqual(overrides["SIM_DISABLE_RANDOM_STORE"], "1")


class FlowCapabilitiesTests(unittest.TestCase):
    def test_flows_payload_includes_capabilities(self) -> None:
        payload = web_api._flows_payload()
        self.assertIn("flows", payload)
        self.assertIn("capabilities", payload)
        self.assertIn("doctor", payload["capabilities"])
        doctor = payload["capabilities"]["doctor"]
        self.assertEqual(doctor["resolved_mode"], "trace")
        self.assertIn("suite", doctor["allowed_optional_flags"])
        place_order = payload["capabilities"]["place-order"]
        self.assertEqual(place_order["resolved_mode"], "trace")
        self.assertEqual(place_order["default_scenarios"], ["place_order"])
        self.assertIn("orders", place_order["allowed_optional_flags"])
        self.assertIn("load", payload["capabilities"])


class OverviewLatestRunTests(unittest.TestCase):
    def test_latest_run_overview_filters_non_server_failures_and_keeps_failed_route(self) -> None:
        run = {
            "id": 999,
            "status": "failed",
            "flow": "doctor",
            "mode": "trace",
            "timing": "fast",
            "trigger_source": "github",
            "trigger_label": "GitHub integration: fainzy-dashboard/production",
            "trigger_context": {"project": "fainzy-dashboard", "environment": "production"},
        }
        events = [
            {
                "id": 1,
                "actor": "user",
                "action": "probe_saved_cards",
                "scenario": "returning_paid_no_coupon",
                "step": "probe_saved_cards",
                "method": "GET",
                "endpoint": "/v1/core/cards/",
                "http_status": 404,
                "message": "no saved card",
                "ok": False,
            },
            {
                "id": 2,
                "actor": "user",
                "action": "place_order",
                "scenario": "returning_paid_no_coupon",
                "step": "place_order",
                "method": "POST",
                "endpoint": "/v1/core/orders/",
                "http_status": 503,
                "message": "service unavailable",
                "ok": False,
            },
        ]
        artifact_issues = [
            {
                "severity": "error",
                "code": "missing_user_token",
                "message": "Saved cards were skipped because user authentication is missing.",
                "scenario": "returning_paid_no_coupon",
                "step": "probe_saved_cards",
                "related_event_id": 1,
            },
            {
                "severity": "error",
                "code": "payment_intent_http_error",
                "message": "HTTP error creating payment intent",
                "scenario": "returning_paid_no_coupon",
                "step": "place_order",
                "related_event_id": 2,
            },
        ]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, artifact_issues, {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        issues = payload["issues"]
        findings = payload["findings"]
        self.assertGreaterEqual(len(issues), 1)
        self.assertTrue(any((issue.get("route") == "/v1/core/orders/") for issue in issues))
        self.assertFalse(any(("missing_user_token" == issue.get("code")) for issue in issues))
        self.assertEqual(issues, findings["critical"])
        self.assertTrue(any(item.get("code") == "missing_user_token" for item in findings["operational"]))
        self.assertEqual(payload["metrics"]["failed_events"], 1)
        critical = findings["critical"][0]
        self.assertEqual(critical.get("flow"), "returning_paid_no_coupon")
        self.assertEqual(critical.get("step"), "place_order")
        self.assertEqual(critical.get("method"), "POST")
        self.assertEqual(critical.get("http_status"), 503)
        self.assertTrue(critical.get("preceding_steps"))

    def test_latest_run_overview_classifies_websocket_and_gate_buckets(self) -> None:
        run = {"id": 1001, "status": "failed"}
        artifact_issues = [
            {
                "severity": "warning",
                "code": "websocket_event_missing",
                "message": "No websocket event observed for status pending",
            },
            {
                "severity": "warning",
                "code": "websocket_gate_timeout",
                "message": "Websocket gate bypassed",
                "details": {"enforced": False},
            },
            {
                "severity": "error",
                "code": "websocket_gate_timeout",
                "message": "Websocket gate failed",
                "details": {"enforced": True},
            },
        ]
        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=([], artifact_issues, {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        critical_codes = {item.get("code") for item in payload["findings"]["critical"]}
        operational_codes = {item.get("code") for item in payload["findings"]["operational"]}
        self.assertIn("websocket_event_missing", critical_codes)
        self.assertIn("websocket_gate_timeout", critical_codes)
        self.assertEqual(len(operational_codes), 1)
        self.assertIn("websocket_gate_timeout", operational_codes)

    def test_latest_run_overview_backfills_operational_from_metric_failed_events(self) -> None:
        run = {"id": 1003, "status": "failed"}
        events = [
            {
                "id": 1,
                "actor": "user",
                "action": "place_order",
                "scenario": "load_burst",
                "step": "place_order",
                "method": "POST",
                "endpoint": "/v1/core/orders/",
                "http_status": 503,
                "message": "service unavailable",
                "ok": False,
            },
            {
                "id": 2,
                "actor": "user",
                "category": "decision",
                "action": "probe_coupons",
                "status": "failed",
                "reason_code": "coupon_probe_failed",
                "message": "coupon list unavailable for profile",
                "ok": False,
            },
            {
                "id": 3,
                "actor": "store",
                "action": "rejected_order",
                "scenario": "load_burst",
                "status": "rejected",
                "ok": False,
            },
        ]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, [], {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        findings = payload["findings"]
        critical_codes = {item.get("code") for item in findings["critical"]}
        operational_codes = {item.get("code") for item in findings["operational"]}
        self.assertIn("place_order", critical_codes)
        self.assertIn("probe_coupons", operational_codes)
        self.assertIn("rejected_order", operational_codes)
        self.assertEqual(payload["metrics"]["failed_events"], 3)

    def test_latest_run_overview_skips_duplicate_operational_when_issue_covers_event(self) -> None:
        run = {"id": 1004, "status": "failed"}
        events = [
            {
                "id": 10,
                "actor": "user",
                "category": "decision",
                "action": "probe_saved_cards",
                "status": "failed",
                "reason_code": "probe_failed",
                "message": "schema mismatch",
                "ok": False,
            },
        ]
        artifact_issues = [
            {
                "severity": "warning",
                "code": "probe_failed",
                "message": "Saved cards probe failed",
                "related_event_id": 10,
            },
        ]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, artifact_issues, {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        operational = payload["findings"]["operational"]
        self.assertEqual(len(operational), 1)
        self.assertEqual(operational[0].get("code"), "probe_failed")
        operational_codes = {item.get("code") for item in operational}
        self.assertEqual(len(operational_codes), 1)

    def test_latest_run_overview_treats_informational_decisions_as_non_failures(self) -> None:
        run = {"id": 1002, "status": "failed"}
        events = [
            {
                "id": 1,
                "actor": "user",
                "category": "decision",
                "action": "probe_saved_cards",
                "status": "skipped",
                "reason_code": "no_customer_id",
                "message": "Saved cards were skipped because this user has no Stripe/customer ID.",
                "ok": False,
            },
            {
                "id": 2,
                "actor": "user",
                "action": "probe_user_active_orders",
                "endpoint": "/v1/core/orders/",
                "code": "probe_failed",
                "message": "connection timed out",
                "ok": False,
            },
        ]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, [], {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        critical_codes = {item.get("code") for item in payload["findings"]["critical"]}
        operational_codes = {item.get("code") for item in payload["findings"]["operational"]}
        self.assertNotIn("no_customer_id", critical_codes)
        self.assertNotIn("no_customer_id", operational_codes)
        self.assertIn("probe_user_active_orders", critical_codes)
        self.assertEqual(payload["metrics"]["failed_events"], 1)

    def test_latest_run_overview_tolerates_malformed_issue_payloads(self) -> None:
        run = {"id": 1000, "status": "failed"}
        events = [{"id": 5, "action": "probe", "endpoint": "/x", "http_status": 502, "ok": False}]
        artifact_issues = [{"severity": "error", "code": object(), "message": object(), "related_event_id": "bad"}]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, artifact_issues, {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        self.assertIn("issues", payload)
        self.assertIsInstance(payload["issues"], list)

    def test_run_overview_uses_run_id_lookup(self) -> None:
        run = {"id": 321, "status": "succeeded"}
        with mock.patch.object(overview_service.runs_service, "get_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=([], [], {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.run_overview(321)

        self.assertIsNotNone(payload.get("run"))
        self.assertEqual(payload["run"]["id"], 321)

    def test_run_overview_findings_cover_all_metric_failed_events(self) -> None:
        from api.app.event_failure import is_metric_failed_event

        run = {"id": 2001, "status": "failed"}
        events = [
            {
                "id": 1,
                "actor": "user",
                "action": "place_order",
                "scenario": "completed",
                "step": "place_order",
                "method": "POST",
                "endpoint": "/v1/core/orders/",
                "http_status": 503,
                "message": "service unavailable",
                "ok": False,
            },
            {
                "id": 2,
                "actor": "store",
                "action": "rejected_order",
                "scenario": "rejected",
                "status": "rejected",
                "ok": False,
            },
            {
                "id": 3,
                "actor": "user",
                "category": "decision",
                "action": "probe_coupons",
                "status": "failed",
                "reason_code": "coupon_probe_failed",
                "message": "coupon list unavailable",
                "ok": False,
            },
        ]
        failed_ids = {event["id"] for event in events if is_metric_failed_event(event)}

        with mock.patch.object(overview_service.runs_service, "get_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, [], {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.run_overview(2001)

        findings = payload["findings"]
        represented_ids = set()
        for row in findings["critical"] + findings["operational"]:
            related = row.get("related_event_id")
            if related is not None:
                represented_ids.add(int(related))

        self.assertEqual(failed_ids, represented_ids)
        meta = payload.get("findings_meta") or {}
        self.assertEqual(meta.get("failed_events_total"), len(failed_ids))
        self.assertEqual(meta.get("represented_failed_events"), len(failed_ids))
        self.assertFalse(meta.get("truncated"))

    def test_run_log_payload_rejects_mismatched_log_path(self) -> None:
        run = {"id": 55, "log_path": str(web_api.LOG_DIR / "run-999.log")}
        with mock.patch.object(web_api, "_get_run", return_value=run):
            payload = web_api._run_log_payload(55, 100)
        self.assertEqual(payload["log"], "")

    def test_run_log_payload_tails_matching_log_path(self) -> None:
        log_dir = web_api.LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "run-56.log"
        log_path.write_text("line-one\nline-two\n", encoding="utf-8")
        run = {"id": 56, "log_path": str(log_path)}
        with mock.patch.object(web_api, "_get_run", return_value=run):
            payload = web_api._run_log_payload(56, 10)
        self.assertIn("line-two", payload["log"])


class RunDeletionSafetyTests(unittest.TestCase):
    class _FakeThread:
        instances: list["RunDeletionSafetyTests._FakeThread"] = []

        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.instances.append(self)

        def start(self) -> None:
            return None

    def setUp(self) -> None:
        self.thread_patch = mock.patch.object(web_api.threading, "Thread", self._FakeThread)
        self.thread_patch.start()

    def tearDown(self) -> None:
        self.thread_patch.stop()
        self._FakeThread.instances.clear()

    def _create_run_row(self, *, flow: str = "doctor") -> dict[str, object]:
        return web_api._create_run(
            web_api.RunCreateRequest(
                flow=flow,
                plan="sim_actors.json",
                timing="fast",
                store_id="FZY_123",
                phone="+2348000000000",
                all_users=False,
                no_auto_provision=False,
                enforce_websocket_gates=False,
                post_order_actions=False,
                extra_args=[],
            )
        )

    def test_delete_run_archives_without_removing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            first = self._create_run_row()
            second = self._create_run_row()
            first_log = log_dir / f"run-{first['id']}.log"
            second_log = log_dir / f"run-{second['id']}.log"
            first_log.write_text("first log\n", encoding="utf-8")
            second_log.write_text("second log\n", encoding="utf-8")
            web_api._update_run(int(first["id"]), log_path=str(first_log))
            web_api._update_run(int(second["id"]), log_path=str(second_log))

            try:
                result = web_api._delete_run_logic(int(first["id"]))
                self.assertTrue(log_dir.exists())
                self.assertTrue(first_log.exists())
                self.assertTrue(second_log.exists())
                self.assertTrue(result.get("archived"))
                archived = web_api._fetch_run_row(int(first["id"]))
                self.assertIsNotNone(archived.get("archived_at"))
            finally:
                try:
                    web_api._delete_run_logic(int(second["id"]))
                except Exception:
                    pass

    def test_delete_run_archives_without_removing_artifact_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_dir = root / "web-gui"
            log_dir.mkdir()
            first = self._create_run_row()
            second = self._create_run_row()
            first_log = log_dir / f"run-{first['id']}.log"
            second_log = log_dir / f"run-{second['id']}.log"
            first_log.write_text("first log\n", encoding="utf-8")
            second_log.write_text("second log\n", encoding="utf-8")
            first_artifacts = root / f"run-{first['id']}-artifacts"
            second_artifacts = root / f"run-{second['id']}-artifacts"
            first_artifacts.mkdir()
            second_artifacts.mkdir()
            first_report = first_artifacts / "report.md"
            first_story = first_artifacts / "story.md"
            first_events = first_artifacts / "events.json"
            second_report = second_artifacts / "report.md"
            second_story = second_artifacts / "story.md"
            second_events = second_artifacts / "events.json"
            for path in (first_report, first_story, first_events, second_report, second_story, second_events):
                path.write_text(path.name, encoding="utf-8")
            web_api._update_run(
                int(first["id"]),
                log_path=str(first_log),
                report_path=str(first_report),
                story_path=str(first_story),
                events_path=str(first_events),
            )
            web_api._update_run(
                int(second["id"]),
                log_path=str(second_log),
                report_path=str(second_report),
                story_path=str(second_story),
                events_path=str(second_events),
            )

            try:
                web_api._delete_run_logic(int(first["id"]))
                self.assertTrue(first_artifacts.exists())
                self.assertTrue(second_artifacts.exists())
                self.assertTrue(second_report.exists())
                self.assertTrue(second_story.exists())
                self.assertTrue(second_events.exists())
            finally:
                try:
                    web_api._delete_run_logic(int(second["id"]))
                except Exception:
                    pass

    def test_create_run_recreates_missing_log_directory_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "missing-web-gui"
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                run = self._create_run_row()

            self.assertTrue(log_dir.is_dir())
            launched_log_path = self._FakeThread.instances[-1].args[2]
            self.assertEqual(launched_log_path, log_dir / f"run-{run['id']}.log")

    def test_running_run_does_not_hydrate_artifacts_from_old_log_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row()
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            stale_events = pathlib.Path(tmpdir) / "stale-events.json"
            stale_events.write_text("[]", encoding="utf-8")
            log_path.write_text(
                f"main: events: {stale_events}\n",
                encoding="utf-8",
            )
            web_api._update_run(run_id, status="running", log_path=str(log_path))
            with web_api.RUN_LOCK:
                web_api.RUN_PROCESSES[run_id] = RunControlTests._FakeProcess()

            hydrated = web_api._get_run(run_id)
            self.assertIsNone(hydrated.get("events_path"))

    def test_hydrate_run_artifacts_reassembles_wrapped_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_dir = root / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row()
            run_id = int(run["id"])

            artifacts_dir = root / "artifacts"
            artifacts_dir.mkdir()
            events_path = artifacts_dir / "events.json"
            report_path = artifacts_dir / "report.md"
            story_path = artifacts_dir / "story.md"
            events_path.write_text("[]", encoding="utf-8")
            report_path.write_text("# report\n", encoding="utf-8")
            story_path.write_text("# story\n", encoding="utf-8")

            log_path = log_dir / f"run-{run_id}.log"
            wrapped_events = str(events_path).replace(".json", ".")
            wrapped_report = str(report_path).replace(".md", ".")
            wrapped_story = str(story_path).replace(".md", ".m")
            log_path.write_text(
                "\n".join(
                    [
                        "main: events:",
                        wrapped_events,
                        "json",
                        "main: report:",
                        wrapped_report,
                        "md",
                        "main: story:",
                        wrapped_story,
                        "d",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            web_api._update_run(
                run_id,
                status="succeeded",
                log_path=str(log_path),
                events_path=None,
                report_path=None,
                story_path=None,
            )

            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                hydrated = web_api._get_run(run_id)
            self.assertEqual(hydrated.get("events_path"), str(events_path))
            self.assertEqual(hydrated.get("report_path"), str(report_path))
            self.assertEqual(hydrated.get("story_path"), str(story_path))


class RunControlTests(unittest.TestCase):
    _REAL_THREAD = threading.Thread

    class _FakeProcess:
        def __init__(self, returncode: int | None = None) -> None:
            self._returncode = returncode

        def poll(self) -> int | None:
            return self._returncode

        def terminate(self) -> None:
            self._returncode = -15

    class _FakeThread(_REAL_THREAD):
        instances: list["RunControlTests._FakeThread"] = []

        def __init__(self, target=None, args=(), daemon=None, **kwargs):
            super().__init__(target=target, args=args, daemon=daemon, **kwargs)
            self._suppress_start = getattr(target, "__name__", "") == "_run_simulation"
            self.instances.append(self)

        def start(self) -> None:
            if self._suppress_start:
                return None
            super().start()

    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.thread_patch = mock.patch.object(web_api.threading, "Thread", self._FakeThread)
        self.thread_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        with web_api.RUN_LOCK:
            web_api.RUN_PROCESSES.clear()
            web_api.RUN_CANCELLED.clear()
        with web_api.RUN_LOG_STAT_LOCK:
            web_api.RUN_LOG_STAT.clear()
        self.thread_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self._FakeThread.instances.clear()
        self.client.close()

    def _create_run_row(self, *, flow: str = "doctor") -> dict[str, object]:
        return web_api._create_run(
            web_api.RunCreateRequest(
                flow=flow,
                plan="sim_actors.json",
                timing="fast",
                store_id="FZY_123",
                phone="+2348000000000",
                all_users=False,
                no_auto_provision=False,
                enforce_websocket_gates=False,
                post_order_actions=False,
                extra_args=[],
            )
        )

    def test_cancel_run_requires_running_and_live_process(self) -> None:
        run = self._create_run_row()
        run_id = int(run["id"])
        resp = self.client.post(f"/api/v1/runs/{run_id}/cancel")
        self.assertEqual(resp.status_code, 409)

    def test_cancel_run_terminates_live_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row()
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("starting\n", encoding="utf-8")
            web_api._update_run(run_id, status="running", log_path=str(log_path), started_at=web_api._utc_now())
            process = self._FakeProcess()
            with web_api.RUN_LOCK:
                web_api.RUN_PROCESSES[run_id] = process
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                resp = self.client.post(f"/api/v1/runs/{run_id}/cancel")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json().get("status"), "cancelling")
            self.assertIsNotNone(process.poll())

    def test_delete_orphan_running_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row()
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("stale\n", encoding="utf-8")
            web_api._update_run(run_id, status="running", log_path=str(log_path), started_at=web_api._utc_now())
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                resp = self.client.delete(f"/api/v1/runs/{run_id}")
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json().get("deleted"))
            active_runs = self.client.get("/api/v1/runs").json().get("runs", [])
            self.assertFalse(any(int(item.get("id")) == run_id for item in active_runs))
            archived_runs = self.client.get("/api/v1/runs?include_archived=true").json().get("runs", [])
            archived_row = next(item for item in archived_runs if int(item.get("id")) == run_id)
            self.assertIsNotNone(archived_row.get("archived_at"))

    def test_delete_blocked_while_actively_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row()
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("line\n", encoding="utf-8")
            web_api._update_run(run_id, status="running", log_path=str(log_path), started_at=web_api._utc_now())
            process = self._FakeProcess()
            with web_api.RUN_LOCK:
                web_api.RUN_PROCESSES[run_id] = process
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                with web_api.RUN_LOG_STAT_LOCK:
                    web_api.RUN_LOG_STAT[run_id] = (0, log_path.stat().st_mtime)
                log_path.write_text("line\nmore\n", encoding="utf-8")
                resp = self.client.delete(f"/api/v1/runs/{run_id}")
            self.assertEqual(resp.status_code, 409)

    def test_restore_archived_run(self) -> None:
        run = self._create_run_row()
        run_id = int(run["id"])
        delete_response = self.client.delete(f"/api/v1/runs/{run_id}")
        self.assertEqual(delete_response.status_code, 200)
        restore_response = self.client.post(f"/api/v1/runs/{run_id}/restore")
        self.assertEqual(restore_response.status_code, 200)
        restored = restore_response.json().get("run", {})
        self.assertIsNone(restored.get("archived_at"))
        active_runs = self.client.get("/api/v1/runs").json().get("runs", [])
        self.assertTrue(any(int(item.get("id")) == run_id for item in active_runs))

    def test_reconcile_finalizes_succeeded_from_log_instead_of_orphan_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row(flow="free-coupon")
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text(
                "\n".join(
                    [
                        'main: identity_context: {"user_phone": "+2348166675609", "store_name": "Ask Me"}',
                        "trace: Selected store FZY_926025 (subentity_id=7).",
                        "main: events: /tmp/runs/sample/events.json",
                        "main: report: /tmp/runs/20260519T-free-coupon-FZY_926025-user5609/report.md",
                        "main: story: /tmp/runs/20260519T-free-coupon-FZY_926025-user5609/story.md",
                    ]
                ),
                encoding="utf-8",
            )
            web_api._update_run(
                run_id,
                status="running",
                log_path=str(log_path),
                started_at=web_api._utc_now(),
                last_heartbeat_at=(datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
                store_id="",
                phone="",
            )
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                payload = web_api._get_run(run_id)
            self.assertEqual(payload.get("status"), "succeeded")
            self.assertEqual(payload.get("store_id"), "FZY_926025")
            self.assertEqual(payload.get("exit_code"), 0)

    def test_infer_run_outcome_strips_rich_console_markup(self) -> None:
        lines = [
            "[green]main:[/] report: /tmp/runs/20260519T-free-coupon-FZY_926025-user5609/report.md",
        ]
        outcome = web_api._infer_run_outcome_from_log(lines)
        self.assertEqual(outcome, ("succeeded", None, 0))

    def test_reconcile_waits_while_log_recently_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row(flow="free-coupon")
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("trace: still finalizing\n", encoding="utf-8")
            web_api._update_run(
                run_id,
                status="running",
                log_path=str(log_path),
                started_at=web_api._utc_now(),
            )
            row = web_api._fetch_run_row(run_id)
            liveness = web_api._run_liveness(row)
            self.assertFalse(web_api._should_reconcile_stale_run(row, liveness))
            reconciled = web_api._reconcile_stale_run(run_id, row)
            self.assertIsNone(reconciled)
            self.assertEqual(web_api._fetch_run_row(run_id)["status"], "running")

    def test_reconcile_keeps_running_when_detached_pid_is_live_and_identity_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row(flow="free-coupon")
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("trace: still running\n", encoding="utf-8")
            stale_started = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
            stale_heartbeat = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
            web_api._update_run(
                run_id,
                status="running",
                log_path=str(log_path),
                started_at=stale_started,
                process_pid=99999,
                launcher_instance_id="legacy-launcher",
                last_heartbeat_at=stale_heartbeat,
                ownership_state="attached_live",
            )
            row = web_api._fetch_run_row(run_id)
            command_tokens = row["command"].split()
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                with mock.patch.object(web_api, "_pid_is_live", return_value=True):
                    with mock.patch.object(web_api, "_read_pid_cmdline_tokens", return_value=command_tokens):
                        payload = web_api._get_run(run_id)
            self.assertEqual(payload.get("status"), "running")
            control = payload.get("control") or {}
            self.assertEqual(control.get("ownership_state"), "detached_live")
            self.assertTrue(control.get("detached_live"))

    def test_reconcile_marks_failed_when_detached_pid_dead_without_terminal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row(flow="free-coupon")
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text("trace: interrupted\n", encoding="utf-8")
            stale_mtime = time.time() - (web_api.RUN_ORPHAN_LOG_IDLE_SECONDS + 5)
            os.utime(log_path, (stale_mtime, stale_mtime))
            stale_started = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
            stale_heartbeat = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
            web_api._update_run(
                run_id,
                status="running",
                log_path=str(log_path),
                started_at=stale_started,
                process_pid=77777,
                launcher_instance_id="legacy-launcher",
                last_heartbeat_at=stale_heartbeat,
                ownership_state="attached_live",
            )
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                with mock.patch.object(web_api, "_pid_is_live", return_value=False):
                    with mock.patch.object(web_api, "_send_email_notification", return_value={"sent": False}):
                        payload = web_api._get_run(run_id)
            self.assertEqual(payload.get("status"), "failed")
            self.assertIn("detached_process_dead_no_terminal_evidence", str(payload.get("error") or ""))
            self.assertEqual(payload.get("ownership_state"), "detached_dead")

    def test_reconcile_finalizes_failed_from_log_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir) / "web-gui"
            log_dir.mkdir()
            run = self._create_run_row(flow="free-coupon")
            run_id = int(run["id"])
            log_path = log_dir / f"run-{run_id}.log"
            log_path.write_text(
                "\n".join(
                    [
                        "trace: Running scenario",
                        "Simulation failed: request timeout",
                    ]
                ),
                encoding="utf-8",
            )
            stale_mtime = time.time() - (web_api.RUN_ORPHAN_LOG_IDLE_SECONDS + 5)
            os.utime(log_path, (stale_mtime, stale_mtime))
            stale_started = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
            web_api._update_run(
                run_id,
                status="running",
                log_path=str(log_path),
                started_at=stale_started,
                process_pid=88888,
                last_heartbeat_at=(datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
            )
            with mock.patch.object(web_api, "LOG_DIR", log_dir):
                with mock.patch.object(web_api, "_pid_is_live", return_value=False):
                    with mock.patch.object(web_api, "_send_email_notification", return_value={"sent": False}):
                        payload = web_api._get_run(run_id)
            self.assertEqual(payload.get("status"), "failed")
            self.assertEqual(payload.get("exit_code"), 1)
            self.assertIn("from log", str(payload.get("error") or ""))

    def test_run_payload_includes_control_flags(self) -> None:
        run = self._create_run_row()
        run_id = int(run["id"])
        payload = self.client.get(f"/api/v1/runs/{run_id}").json()
        run_row = payload["run"] if isinstance(payload.get("run"), dict) else payload
        self.assertIn("process_pid", run_row)
        self.assertIn("launcher_instance_id", run_row)
        self.assertIn("last_heartbeat_at", run_row)
        self.assertIn("ownership_state", run_row)
        control = run_row.get("control") or {}
        self.assertIn("can_stop", control)
        self.assertIn("can_delete", control)
        self.assertIn("ownership_state", control)
        self.assertFalse(control.get("actively_running"))


class RunProfilesApiTests(unittest.TestCase):
    _REAL_THREAD = threading.Thread

    class _FakeThread(_REAL_THREAD):
        def __init__(self, target=None, args=(), daemon=None, **kwargs):
            super().__init__(target=target, args=args, daemon=daemon, **kwargs)
            self._suppress_start = getattr(target, "__name__", "") == "_run_simulation"

        def start(self) -> None:
            if self._suppress_start:
                return None
            super().start()

    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.thread_patch = mock.patch.object(web_api.threading, "Thread", self._FakeThread)
        self.thread_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.thread_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def test_profile_crud_launch_and_replay(self) -> None:
        profile_name = f"doctor-profile-{time.time_ns()}"
        create_response = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": profile_name,
                "description": "profile for replay test",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
                "mode": "trace",
                "suite": "doctor",
                "scenarios": ["app_bootstrap", "store_dashboard"],
                "store_id": "FZY_123",
                "phone": "+2348000001111",
                "all_users": False,
                "strict_plan": True,
                "skip_app_probes": True,
                "skip_store_dashboard_probes": True,
                "no_auto_provision": False,
                "enforce_websocket_gates": True,
                "timeout_fails": True,
                "post_order_actions": True,
                "continuous": False,
                "extra_args": ["--strict-plan"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        profile = create_response.json()["profile"]
        profile_id = profile["id"]

        list_response = self.client.get("/api/v1/run-profiles")
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(any(item["id"] == profile_id for item in list_response.json()["profiles"]))

        launch_response = self.client.post(f"/api/v1/run-profiles/{profile_id}/launch")
        self.assertEqual(launch_response.status_code, 200)
        launched_run = launch_response.json()["run"]
        launched_run_id = launched_run["id"]

        snapshot_response = self.client.get(f"/api/v1/runs/{launched_run_id}/execution-snapshot")
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertTrue(snapshot_response.json()["available"])
        self.assertEqual(snapshot_response.json()["snapshot"]["store_id"], "FZY_123")
        self.assertEqual(snapshot_response.json()["snapshot"]["suite"], "doctor")
        self.assertEqual(snapshot_response.json()["snapshot"]["scenarios"], ["app_bootstrap", "store_dashboard"])
        self.assertTrue(snapshot_response.json()["snapshot"]["strict_plan"])
        self.assertTrue(snapshot_response.json()["snapshot"]["enforce_websocket_gates"])
        self.assertTrue(snapshot_response.json()["snapshot"]["timeout_fails"])

        replay_response = self.client.post(f"/api/v1/runs/{launched_run_id}/replay")
        self.assertEqual(replay_response.status_code, 200)
        replayed_run = replay_response.json()["run"]
        self.assertNotEqual(replayed_run["id"], launched_run_id)
        self.assertEqual(replay_response.json()["snapshot"]["flow"], "doctor")

        delete_response = self.client.delete(f"/api/v1/run-profiles/{profile_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])

        list_after_delete = self.client.get("/api/v1/run-profiles")
        self.assertEqual(list_after_delete.status_code, 200)
        self.assertFalse(any(item["id"] == profile_id for item in list_after_delete.json()["profiles"]))

        archived_list = self.client.get("/api/v1/run-profiles?include_archived=true")
        self.assertEqual(archived_list.status_code, 200)
        archived = next(item for item in archived_list.json()["profiles"] if item["id"] == profile_id)
        self.assertEqual(archived["status"], "archived")

        restore_response = self.client.post(f"/api/v1/run-profiles/{profile_id}/restore")
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.json()["profile"]["status"], "active")


class SchedulesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.run_simulation_patch = mock.patch.object(web_api, "_run_simulation", return_value=None)
        self.run_simulation_patch.start()
        web_api._set_allowed_timezones_setting(None)
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.run_simulation_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def _create_profile(self) -> int:
        response = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": f"scheduled-doctor-{time.time_ns()}",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
                "store_id": "FZY_123",
                "phone": "+2348000001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        return int(response.json()["profile"]["id"])

    def test_simple_schedule_crud_manual_trigger_and_state_controls(self) -> None:
        profile_id = self._create_profile()
        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"daily-doctor-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "Africa/Lagos",
                "active_from": "2026-05-06T08:00:00+01:00",
                "run_window_start": "08:00",
                "run_window_end": "18:00",
                "blackout_dates": ["2026-12-25"],
            },
        )

        self.assertEqual(create_response.status_code, 200)
        schedule = create_response.json()["schedule"]
        schedule_id = schedule["id"]
        self.assertEqual(schedule["status"], "active")
        self.assertIsNone(schedule["profile_id"])
        self.assertEqual(schedule["schedule_type"], "campaign")
        self.assertEqual(len(schedule["campaign_steps"]), 1)
        self.assertEqual(int(schedule["campaign_steps"][0]["profile_id"]), profile_id)
        self.assertIsNotNone(schedule["next_run_at"])
        self.assertEqual(schedule["execution_mode_label"], "automatic")
        self.assertIn(schedule["next_run_reason"], {"computed", "shifted_to_window_start", "blackout_skipped"})

        list_response = self.client.get("/api/v1/schedules")
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(any(item["id"] == schedule_id for item in list_response.json()["schedules"]))

        trigger_response = self.client.post(f"/api/v1/schedules/{schedule_id}/trigger")
        self.assertEqual(trigger_response.status_code, 200)
        self.assertEqual(trigger_response.json()["execution"]["status"], "launched")
        self.assertEqual(trigger_response.json()["run"]["flow"], "doctor")
        self.assertTrue(trigger_response.json()["execution"].get("execution_chain_key"))

        summary_response = self.client.get("/api/v1/schedules/summary")
        self.assertEqual(summary_response.status_code, 200)
        self.assertIn("recent_schedule_states", summary_response.json())
        lifecycle_rows = [
            row
            for row in summary_response.json()["recent_executions"]
            if row["schedule_id"] == schedule_id and row.get("execution_chain_key") == trigger_response.json()["execution"]["execution_chain_key"]
        ]
        self.assertGreaterEqual(len(lifecycle_rows), 3)
        self.assertTrue(all(row.get("execution_chain_key") for row in lifecycle_rows))
        schedule_states = [
            row for row in summary_response.json()["recent_schedule_states"] if int(row["schedule_id"]) == int(schedule_id)
        ]
        self.assertEqual(len(schedule_states), 1)
        self.assertEqual(schedule_states[0]["schedule_phase"], "launched")
        self.assertEqual(int(schedule_states[0]["latest_run_id"]), int(trigger_response.json()["run"]["id"]))
        self.assertTrue(isinstance(schedule_states[0]["latest_run_status"], str))

        pause_response = self.client.post(f"/api/v1/schedules/{schedule_id}/pause")
        self.assertEqual(pause_response.status_code, 200)
        self.assertEqual(pause_response.json()["schedule"]["status"], "paused")

        resume_response = self.client.post(f"/api/v1/schedules/{schedule_id}/resume")
        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(resume_response.json()["schedule"]["status"], "active")

        disable_response = self.client.post(f"/api/v1/schedules/{schedule_id}/disable")
        self.assertEqual(disable_response.status_code, 200)
        self.assertEqual(disable_response.json()["schedule"]["status"], "disabled")
        self.assertIsNone(disable_response.json()["schedule"]["next_run_at"])

        restore_response = self.client.post(f"/api/v1/schedules/{schedule_id}/restore")
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.json()["schedule"]["status"], "active")
        self.assertIsNotNone(restore_response.json()["schedule"]["next_run_at"])

    def test_campaign_schedule_persists_steps_and_rejects_empty_campaigns(self) -> None:
        profile_id = self._create_profile()

        bad_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": "empty-campaign",
                "schedule_type": "campaign",
                "cadence": "custom",
                "timezone": "UTC",
                "campaign_steps": [],
            },
        )
        self.assertEqual(bad_response.status_code, 400)

        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"doctor-campaign-{time.time_ns()}",
                "schedule_type": "campaign",
                "cadence": "custom",
                "timezone": "UTC",
                "custom_anchor_at": "2026-05-10T14:20:00+00:00",
                "custom_every_n_days": 3,
                "failure_policy": "continue",
                "campaign_steps": [
                    {
                        "profile_id": profile_id,
                        "repeat_count": 2,
                        "spacing_seconds": 30,
                        "timeout_seconds": 900,
                        "failure_policy": "continue",
                        "execution_mode": "saved_profile",
                    }
                ],
            },
        )

        self.assertEqual(create_response.status_code, 200)
        campaign = create_response.json()["schedule"]
        self.assertEqual(campaign["schedule_type"], "campaign")
        self.assertEqual(campaign["failure_policy"], "continue")
        self.assertEqual(campaign["campaign_steps"][0]["repeat_count"], 2)
        self.assertEqual(campaign["execution_mode_label"], "automatic")

        trigger_response = self.client.post(f"/api/v1/schedules/{campaign['id']}/trigger")
        self.assertEqual(trigger_response.status_code, 200)
        self.assertEqual(trigger_response.json()["execution"]["status"], "launched")
        self.assertEqual(len(trigger_response.json()["runs"]), 1)
        self.assertEqual(trigger_response.json()["execution"]["detail"]["overlap_skipped_count"], 1)
        self.assertTrue(trigger_response.json()["execution"].get("execution_chain_key"))

    def test_schedule_trigger_serializes_identical_overlap_runs(self) -> None:
        profile_id = self._create_profile()
        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"overlap-guard-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "UTC",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        schedule_id = int(create_response.json()["schedule"]["id"])

        first_trigger = self.client.post(f"/api/v1/schedules/{schedule_id}/trigger")
        self.assertEqual(first_trigger.status_code, 200)
        self.assertEqual(first_trigger.json()["execution"]["status"], "launched")
        first_run_id = int(first_trigger.json()["run"]["id"])

        second_trigger = self.client.post(f"/api/v1/schedules/{schedule_id}/trigger")
        self.assertEqual(second_trigger.status_code, 200)
        self.assertEqual(second_trigger.json()["execution"]["status"], "overlap_skipped")
        self.assertEqual(second_trigger.json().get("runs"), [])
        overlap = second_trigger.json().get("overlap_skipped") or []
        self.assertGreaterEqual(len(overlap), 1)
        self.assertEqual(int(overlap[0]["existing_run_id"]), first_run_id)

    def test_schedule_restore_fails_when_profile_is_archived(self) -> None:
        profile_id = self._create_profile()
        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"archived-profile-schedule-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "anchor_start_at": "2026-05-19T08:00:00Z",
                "period": "daily",
                "repeat": "daily",
                "stop_rule": "never",
                "runs_per_period": 1,
                "run_slots": [{"time": "08:00"}],
                "timezone": "UTC",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        schedule_id = int(create_response.json()["schedule"]["id"])

        delete_schedule_response = self.client.post(f"/api/v1/schedules/{schedule_id}/delete")
        self.assertEqual(delete_schedule_response.status_code, 200)

        delete_profile_response = self.client.delete(f"/api/v1/run-profiles/{profile_id}")
        self.assertEqual(delete_profile_response.status_code, 200)

        restore_response = self.client.post(f"/api/v1/schedules/{schedule_id}/restore")
        self.assertEqual(restore_response.status_code, 409)

    def test_new_contract_schedule_shifts_into_run_window(self) -> None:
        profile_id = self._create_profile()

        now = datetime.now(timezone.utc)
        anchor = now - timedelta(minutes=30)
        window_start_dt = now + timedelta(minutes=1)
        window_end_dt = now + timedelta(hours=2)
        run_window_start = f"{window_start_dt.hour:02d}:{window_start_dt.minute:02d}"
        run_window_end = f"{window_end_dt.hour:02d}:{window_end_dt.minute:02d}"

        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"new-contract-window-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "anchor_start_at": anchor.isoformat(),
                "period": "daily",
                "repeat": "daily",
                "stop_rule": "never",
                "runs_per_period": 1,
                "run_slots": [{"time": "00:00"}],
                "timezone": "UTC",
                "run_window_start": run_window_start,
                "run_window_end": run_window_end,
                "blackout_dates": [],
            },
        )

        self.assertEqual(create_response.status_code, 200)
        schedule = create_response.json()["schedule"]
        next_run_at = datetime.fromisoformat(schedule["next_run_at"].replace("Z", "+00:00"))

        expected = datetime(
            now.year,
            now.month,
            now.day,
            window_start_dt.hour,
            window_start_dt.minute,
            tzinfo=timezone.utc,
        )
        if expected <= now:
            expected += timedelta(days=1)

        self.assertEqual(next_run_at, expected)
        self.assertEqual(schedule["next_run_reason"], "shifted_to_window_start")

    def test_schedule_rejects_invalid_date_range_and_blackout_dates(self) -> None:
        profile_id = self._create_profile()

        invalid_range_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"invalid-range-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "active_from": "2026-05-08T10:00:00+01:00",
                "active_until": "2026-05-08T09:00:00+01:00",
            },
        )
        self.assertEqual(invalid_range_response.status_code, 400)
        self.assertIn("Active until", invalid_range_response.json()["detail"])

        invalid_blackout_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"invalid-blackout-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "blackout_dates": ["2026/12/25"],
            },
        )
        self.assertEqual(invalid_blackout_response.status_code, 400)
        self.assertIn("Blackout dates", invalid_blackout_response.json()["detail"])

    def test_custom_cadence_requires_custom_fields_and_rejects_them_for_non_custom(self) -> None:
        profile_id = self._create_profile()
        missing_custom = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"custom-missing-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "custom",
                "timezone": "UTC",
            },
        )
        self.assertEqual(missing_custom.status_code, 400)
        self.assertIn("custom_anchor_at", missing_custom.json()["detail"])

        unexpected_custom = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"daily-with-custom-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "UTC",
                "custom_anchor_at": "2026-05-10T14:20:00+00:00",
                "custom_every_n_days": 3,
            },
        )
        self.assertEqual(unexpected_custom.status_code, 400)
        self.assertIn("only allowed", unexpected_custom.json()["detail"])

    def test_new_period_window_contract_fields_and_preview_metadata(self) -> None:
        profile_id = self._create_profile()
        future_anchor = datetime(2026, 6, 10, 11, 0, 0, tzinfo=timezone.utc)
        response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"period-window-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "timezone": "UTC",
                "anchor_start_at": future_anchor.isoformat(),
                "period": "daily",
                "repeat": "daily",
                "stop_rule": "duration",
                "duration_seconds": 18000,
                "runs_per_period": 5,
                "run_window_start": "08:00",
                "run_window_end": "18:00",
                "run_slots": [{"time": "09:00"}, {"time": "10:00"}, {"time": "11:00"}, {"time": "12:00"}, {"time": "13:00"}],
                "campaign_steps": [{"profile_id": profile_id, "repeat_count": 1, "spacing_seconds": 0, "timeout_seconds": 900, "failure_policy": "continue", "execution_mode": "saved_profile"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        schedule = response.json()["schedule"]
        self.assertEqual(schedule["period"], "daily")
        self.assertEqual(schedule["stop_rule"], "duration")
        self.assertEqual(schedule["runs_per_period"], 5)
        self.assertEqual(schedule["requested_runs_per_period"], 5)
        self.assertTrue(isinstance(schedule["feasible_runs_per_period"], int))
        self.assertTrue(isinstance(schedule["schedule_warnings"], list))
        expected_next = future_anchor
        if expected_next.hour * 60 + expected_next.minute < 8 * 60:
            expected_next = expected_next.replace(hour=8, minute=0)
        elif expected_next.hour * 60 + expected_next.minute > 18 * 60:
            expected_next = (expected_next + timedelta(days=1)).replace(hour=8, minute=0)
        self.assertEqual(schedule["next_run_at"], expected_next.isoformat())

    def test_schedule_hydration_does_not_clear_persisted_next_run(self) -> None:
        profile_id = self._create_profile()
        anchor = (datetime.now(timezone.utc) + timedelta(seconds=10)).replace(microsecond=0)
        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"persisted-next-run-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "timezone": "UTC",
                "anchor_start_at": anchor.isoformat(),
                "period": "daily",
                "repeat": "daily",
                "stop_rule": "end_at",
                "end_at": (anchor + timedelta(days=1)).isoformat(),
                "runs_per_period": 1,
                "all_day": True,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        schedule_id = int(create_response.json()["schedule"]["id"])
        initial_next_run = create_response.json()["schedule"]["next_run_at"]
        self.assertIsNotNone(initial_next_run)

        listed = web_api._get_schedule(schedule_id)
        self.assertEqual(listed["next_run_at"], initial_next_run)

        list_response = self.client.get("/api/v1/schedules")
        self.assertEqual(list_response.status_code, 200)
        listed_http = next(item for item in list_response.json()["schedules"] if int(item["id"]) == schedule_id)
        self.assertEqual(listed_http["next_run_at"], initial_next_run)

    def test_viewer_can_read_but_cannot_mutate_schedules(self) -> None:
        viewer_client = TestClient(web_api.app)
        try:
            login = viewer_client.post("/api/v1/auth/login", json={"username": "bob", "password": "secret"})
            self.assertEqual(login.status_code, 200)

            list_response = viewer_client.get("/api/v1/schedules")
            self.assertEqual(list_response.status_code, 200)

            create_response = viewer_client.post(
                "/api/v1/schedules",
                json={"name": "viewer-schedule", "schedule_type": "simple", "profile_id": 1},
            )
            self.assertEqual(create_response.status_code, 403)
        finally:
            viewer_client.close()


class SystemTimezonesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.run_simulation_patch = mock.patch.object(web_api, "_run_simulation", return_value=None)
        self.run_simulation_patch.start()
        web_api._set_allowed_timezones_setting(None)
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.run_simulation_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def _create_profile(self) -> int:
        response = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": f"scheduled-doctor-{time.time_ns()}",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
                "store_id": "FZY_123",
                "phone": "+2348000001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        return int(response.json()["profile"]["id"])

    def test_default_policy_allows_valid_timezones(self) -> None:
        get_response = self.client.get("/api/v1/system/timezones")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["mode"], "all")
        self.assertIsNone(get_response.json()["allowed_timezones"])
        self.assertTrue(len(get_response.json()["available_timezones"]) > 10)

        profile_id = self._create_profile()
        create_response = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"tz-default-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "America/New_York",
            },
        )
        self.assertEqual(create_response.status_code, 200)

    def test_allowlist_rejects_disallowed_schedule_timezone(self) -> None:
        put_response = self.client.put(
            "/api/v1/system/timezones",
            json={"mode": "allowlist", "allowed_timezones": ["UTC"]},
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(put_response.json()["mode"], "allowlist")
        self.assertEqual(put_response.json()["allowed_timezones"], ["UTC"])

        profile_id = self._create_profile()
        rejected = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"tz-reject-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "Africa/Lagos",
            },
        )
        self.assertEqual(rejected.status_code, 400)

        accepted = self.client.post(
            "/api/v1/schedules",
            json={
                "name": f"tz-accept-{time.time_ns()}",
                "schedule_type": "simple",
                "profile_id": profile_id,
                "cadence": "daily",
                "timezone": "UTC",
            },
        )
        self.assertEqual(accepted.status_code, 200)

    def test_put_rejects_unknown_timezones(self) -> None:
        response = self.client.put(
            "/api/v1/system/timezones",
            json={"mode": "allowlist", "allowed_timezones": ["Not/AZone"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_read_or_configure_system_timezones(self) -> None:
        viewer_client = TestClient(web_api.app)
        try:
            login = viewer_client.post("/api/v1/auth/login", json={"username": "bob", "password": "secret"})
            self.assertEqual(login.status_code, 200)

            get_response = viewer_client.get("/api/v1/system/timezones")
            self.assertEqual(get_response.status_code, 403)

            put_response = viewer_client.put(
                "/api/v1/system/timezones",
                json={"mode": "all"},
            )
            self.assertEqual(put_response.status_code, 403)
        finally:
            viewer_client.close()


class SystemEmailApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.run_simulation_patch = mock.patch.object(web_api, "_run_simulation", return_value=None)
        self.run_simulation_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200
        web_api._save_email_settings(
            {
                "email_enabled": False,
                "email_from_email": "",
                "email_from_name": "",
                "email_subject_prefix": "",
                "email_recipients": [],
                "email_event_triggers": [],
            }
        )
        web_api.EMAIL_TEST_LAST_SENT_AT = 0.0
        web_api.EMAIL_EVENT_LAST_SENT.clear()

    def tearDown(self) -> None:
        self.run_simulation_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def test_get_and_update_email_settings(self) -> None:
        get_response = self.client.get("/api/v1/system/email")
        self.assertEqual(get_response.status_code, 200)
        self.assertFalse(get_response.json()["email_enabled"])

        put_response = self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_from_name": "Simulator",
                "email_subject_prefix": "[SIM]",
                "email_recipients": "ops@example.com,\neng@example.com",
                "email_event_triggers": ["run_failed", "critical_alert"],
            },
        )
        self.assertEqual(put_response.status_code, 200)
        payload = put_response.json()
        self.assertEqual(payload["email_recipients"], ["ops@example.com", "eng@example.com"])
        self.assertEqual(payload["email_event_triggers"], ["run_failed", "critical_alert"])

    def test_update_email_settings_rejects_invalid_values(self) -> None:
        bad_email = self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "not-an-email",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["run_failed"],
            },
        )
        self.assertEqual(bad_email.status_code, 400)

        missing_recipients = self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": [],
                "email_event_triggers": ["run_failed"],
            },
        )
        self.assertEqual(missing_recipients.status_code, 400)

    def test_test_email_endpoint_success_and_cooldown(self) -> None:
        self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_from_name": "Simulator",
                "email_subject_prefix": "[SIM]",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["run_failed"],
            },
        )
        env_patch = mock.patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "user",
                "SMTP_PASSWORD": "pass",
                "SMTP_TLS_MODE": "starttls",
            },
            clear=False,
        )
        with env_patch, mock.patch.object(web_api, "send_plain_text_email", return_value={"ok": True}):
            first = self.client.post("/api/v1/system/email/test")
            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.json()["sent"])
            second = self.client.post("/api/v1/system/email/test")
            self.assertEqual(second.status_code, 429)

    def test_failed_run_event_sends_when_trigger_enabled(self) -> None:
        self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["run_failed"],
            },
        )
        env_patch = mock.patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "user",
                "SMTP_PASSWORD": "pass",
                "SMTP_TLS_MODE": "starttls",
            },
            clear=False,
        )
        with env_patch, mock.patch.object(web_api, "send_plain_text_email", return_value={"ok": True}) as sender:
            run = web_api._create_run(web_api.RunCreateRequest(flow="doctor", plan="sim_actors.json", timing="fast"))
            web_api._update_run(int(run["id"]), status="failed", finished_at="2026-05-13T00:00:00+00:00", error="boom")
            self.assertTrue(sender.called)
            body = str(sender.call_args.kwargs.get("body") or "")
            lines = body.splitlines()
            self.assertGreaterEqual(len(lines), 4)
            self.assertTrue(lines[0].startswith("Profile:"))
            self.assertEqual(lines[1], "Trigger: manual")
            self.assertEqual(lines[2], "Project: N/A")
            self.assertEqual(lines[3], "Repository: N/A")
            self.assertIn("How to read this", body)
            self.assertIn("/healthz", body)

    def test_webhook_run_failure_email_includes_project_and_repository(self) -> None:
        self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["run_failed"],
            },
        )
        env_patch = mock.patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "user",
                "SMTP_PASSWORD": "pass",
                "SMTP_TLS_MODE": "starttls",
            },
            clear=False,
        )
        with env_patch, mock.patch.object(web_api, "send_plain_text_email", return_value={"ok": True}) as sender:
            run = web_api._create_run(
                web_api.RunCreateRequest(
                    flow="doctor",
                    plan="sim_actors.json",
                    timing="fast",
                    trigger_source="github",
                    trigger_context={
                        "project": "fainzy-dashboard",
                        "repository": "daaef/fainzy-dashboard",
                        "profile_name": "dashboard",
                    },
                    profile_id=9,
                )
            )
            web_api._update_run(int(run["id"]), status="failed", finished_at="2026-05-13T00:00:00+00:00", error="boom")
            body = str(sender.call_args.kwargs.get("body") or "")
            self.assertIn("Profile: dashboard", body)
            self.assertIn("Trigger: github webhook", body)
            self.assertIn("Project: fainzy-dashboard", body)
            self.assertIn("Repository: daaef/fainzy-dashboard", body)
            self.assertIn("How to read this", body)
            self.assertIn("/healthz", body)

    def test_schedule_launch_failure_email_includes_profile_first_context(self) -> None:
        self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["schedule_launch_failed"],
            },
        )
        env_patch = mock.patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "user",
                "SMTP_PASSWORD": "pass",
                "SMTP_TLS_MODE": "starttls",
            },
            clear=False,
        )
        with env_patch, mock.patch.object(web_api, "send_plain_text_email", return_value={"ok": True}) as sender:
            profile_response = self.client.post(
                "/api/v1/run-profiles",
                json={
                    "name": "dashboard-profile",
                    "flow": "doctor",
                    "plan": "sim_actors.json",
                    "timing": "fast",
                    "store_id": "FZY_123",
                    "phone": "+2348000001111",
                },
            )
            self.assertEqual(profile_response.status_code, 200)
            profile_id = int(profile_response.json()["profile"]["id"])
            schedule_response = self.client.post(
                "/api/v1/schedules",
                json={
                    "name": "dashboard schedule",
                    "schedule_type": "simple",
                    "profile_id": profile_id,
                    "cadence": "daily",
                    "timezone": "UTC",
                },
            )
            self.assertEqual(schedule_response.status_code, 200)
            schedule_id = int(schedule_response.json()["schedule"]["id"])
            with mock.patch.object(web_api, "_create_run", side_effect=RuntimeError("launch failed")):
                response = self.client.post(f"/api/v1/schedules/{schedule_id}/trigger")
            self.assertEqual(response.status_code, 500)
            body = str(sender.call_args.kwargs.get("body") or "")
            lines = body.splitlines()
            self.assertGreaterEqual(len(lines), 5)
            self.assertTrue(lines[0].startswith("Profile:"))
            self.assertEqual(lines[1], "Trigger: schedule")
            self.assertEqual(lines[2], "Project: N/A")
            self.assertEqual(lines[3], "Repository: N/A")
            self.assertIn("How to read this", body)
            self.assertIn("/healthz", body)


class AlertsAndRetentionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.run_simulation_patch = mock.patch.object(web_api, "_run_simulation", return_value=None)
        self.run_simulation_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.run_simulation_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def test_alerts_surface_failed_runs_and_retention_backlog(self) -> None:
        failed_run = web_api._create_run(
            web_api.RunCreateRequest(flow="doctor", plan="sim_actors.json", timing="fast")
        )
        old_date = "2025-10-01T00:00:00+00:00"
        web_api._update_run(int(failed_run["id"]), status="failed", created_at=old_date, error="forced failure")

        response = self.client.get("/api/v1/alerts")

        self.assertEqual(response.status_code, 200)
        alerts = response.json()["alerts"]
        self.assertTrue(any(item["domain"] == "runs" and item["severity"] == "critical" for item in alerts))
        self.assertTrue(any(item["domain"] == "retention" for item in alerts))

    def test_retention_summary_includes_lifecycle_policy_and_retained_summary_fields(self) -> None:
        response = self.client.get("/api/v1/retention/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("retained_summary_fields", payload)
        self.assertIn("verdict", payload["retained_summary_fields"])
        self.assertEqual(payload["policies"]["active_days"], web_api.ACTIVE_RETENTION_DAYS)
        self.assertEqual(payload["policies"]["archive_days"], web_api.ARCHIVE_RETENTION_DAYS)


class SimulationPlansApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.plans_dir_patch = mock.patch.object(
            web_api,
            "SIMULATION_PLANS_DIR",
            pathlib.Path(self.tmpdir.name),
            create=True,
        )
        self.plans_dir_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.client.close()
        self.plans_dir_patch.stop()
        self.tmpdir.cleanup()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()

    def test_plan_crud_validates_and_returns_launchable_path(self) -> None:
        content = {
            "schema_version": 2,
            "runtime_defaults": {"flow": "doctor", "mode": "trace", "timing_profile": "fast"},
            "payment_defaults": {"mode": "free", "case": "free_with_coupon", "coupon_id": 301},
            "users": [{"phone": "+2348000001111"}],
            "stores": [{"store_id": "FZY_123"}],
        }
        create_response = self.client.post(
            "/api/v1/simulation-plans",
            json={"name": "Daily Doctor", "content": content},
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()["plan"]
        plan_id = created["id"]
        self.assertTrue(created["path"].startswith("runs/gui-plans/"))
        self.assertEqual(created["content"]["payment_defaults"]["coupon_id"], 301)

        list_response = self.client.get("/api/v1/simulation-plans")
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(any(item["id"] == plan_id for item in list_response.json()["plans"]))

        read_response = self.client.get(f"/api/v1/simulation-plans/{plan_id}")
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["plan"]["content"]["runtime_defaults"]["flow"], "doctor")

        updated_content = {**content, "runtime_defaults": {"flow": "full", "mode": "trace"}}
        update_response = self.client.put(
            f"/api/v1/simulation-plans/{plan_id}",
            json={"name": "Full Audit", "content": updated_content},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["plan"]["name"], "Full Audit")
        self.assertEqual(update_response.json()["plan"]["content"]["runtime_defaults"]["flow"], "full")

        delete_response = self.client.delete(f"/api/v1/simulation-plans/{plan_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])

    def test_get_default_sim_actors_plan_by_id(self) -> None:
        default_plan = {
            "id": "sim-actors",
            "name": "sim_actors",
            "path": "sim_actors.json",
            "content": {
                "users": [{"phone": "+2348000001111"}],
                "stores": [{"store_id": "FZY_123"}],
            },
        }
        with mock.patch.object(web_api, "_default_sim_actors_plan_payload", return_value=default_plan):
            response = self.client.get("/api/v1/simulation-plans/sim-actors")

        self.assertEqual(response.status_code, 200)
        plan = response.json()["plan"]
        self.assertEqual(plan["id"], "sim-actors")
        self.assertEqual(plan["path"], "sim_actors.json")
        self.assertIn("content", plan)
        self.assertIsInstance(plan["content"], dict)

    def test_get_default_sim_actors_plan_by_id_returns_404_when_default_missing(self) -> None:
        with mock.patch.object(web_api, "_default_sim_actors_plan_payload", return_value=None):
            response = self.client.get("/api/v1/simulation-plans/sim-actors")

        self.assertEqual(response.status_code, 404)
        self.assertIn("sim_actors.json", response.json()["detail"])

    def test_create_plan_rejects_reserved_sim_actors_id(self) -> None:
        response = self.client.post(
            "/api/v1/simulation-plans",
            json={
                "name": "sim actors",
                "content": {
                    "users": [{"phone": "+2348000001111"}],
                    "stores": [{"store_id": "FZY_123"}],
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sim-actors", response.json()["detail"])
        self.assertIn("reserved", response.json()["detail"].lower())

    def test_update_reserved_sim_actors_id_is_rejected(self) -> None:
        response = self.client.put(
            "/api/v1/simulation-plans/sim-actors",
            json={
                "name": "attempted override",
                "content": {
                    "users": [{"phone": "+2348000001111"}],
                    "stores": [{"store_id": "FZY_123"}],
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sim-actors", response.json()["detail"])
        self.assertIn("reserved", response.json()["detail"].lower())

    def test_list_plans_dedupes_legacy_gui_sim_actors_entry(self) -> None:
        legacy_path = pathlib.Path(self.tmpdir.name) / "sim-actors.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "name": "legacy-sim-actors",
                    "users": [{"phone": "+2348000001111"}],
                    "stores": [{"store_id": "FZY_123"}],
                }
            ),
            encoding="utf-8",
        )
        default_plan = {
            "id": "sim-actors",
            "name": "sim_actors",
            "path": "sim_actors.json",
            "content": {"users": [], "stores": []},
        }
        with mock.patch.object(web_api, "_default_sim_actors_plan_payload", return_value=default_plan):
            response = self.client.get("/api/v1/simulation-plans")

        self.assertEqual(response.status_code, 200)
        plans = response.json()["plans"]
        reserved = [item for item in plans if item["id"] == "sim-actors"]
        self.assertEqual(len(reserved), 1)
        self.assertEqual(reserved[0]["path"], "sim_actors.json")

    def test_plan_api_rejects_sensitive_content(self) -> None:
        response = self.client.post(
            "/api/v1/simulation-plans",
            json={
                "name": "Bad Plan",
                "content": {
                    "payment_defaults": {"stripe_secret_key": "sk_test_should_not_be_here"},
                    "users": [{"phone": "+2348000001111"}],
                    "stores": [{"store_id": "FZY_123"}],
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sensitive key", response.json()["detail"])

    def test_viewer_cannot_write_simulation_plans(self) -> None:
        viewer_client = TestClient(web_api.app)
        try:
            login = viewer_client.post("/api/v1/auth/login", json={"username": "bob", "password": "secret"})
            self.assertEqual(login.status_code, 200)
            response = viewer_client.post(
                "/api/v1/simulation-plans",
                json={
                    "name": "Viewer Plan",
                    "content": {
                        "users": [{"phone": "+2348000001111"}],
                        "stores": [{"store_id": "FZY_123"}],
                    },
                },
            )
            self.assertEqual(response.status_code, 403)
        finally:
            viewer_client.close()


class IntegrationsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200
        self._old_allowlist = (
            dict(web_api.SIMULATOR_WEBHOOK_REPO_ALLOWLIST)
            if isinstance(web_api.SIMULATOR_WEBHOOK_REPO_ALLOWLIST, dict)
            else {}
        )
        self._old_secrets = (
            dict(web_api.SIMULATOR_WEBHOOK_PROJECT_SECRETS)
            if isinstance(web_api.SIMULATOR_WEBHOOK_PROJECT_SECRETS, dict)
            else {}
        )

    def tearDown(self) -> None:
        web_api.SIMULATOR_WEBHOOK_REPO_ALLOWLIST = self._old_allowlist
        web_api.SIMULATOR_WEBHOOK_PROJECT_SECRETS = self._old_secrets
        self.client.close()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()

    @staticmethod
    def _signature(secret: str, body: bytes) -> str:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_list_integration_mappings_includes_route_by(self) -> None:
        response = self.client.get("/api/v1/integrations/github/mappings")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("mappings", body)
        self.assertIn(body.get("route_by"), {"environment", "branch"})

    def test_list_integration_mappings_reports_branch_mode(self) -> None:
        with mock.patch.dict(os.environ, {"SIMULATOR_WEBHOOK_ROUTE_BY": "branch"}, clear=False):
            response = self.client.get("/api/v1/integrations/github/mappings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("route_by"), "branch")

    def test_delete_mapping_archives_and_restore_mapping(self) -> None:
        create_profile = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": "Archive Mapping Profile",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
            },
        )
        self.assertEqual(create_profile.status_code, 200)
        profile_id = int(create_profile.json()["profile"]["id"])

        create_mapping = self.client.post(
            "/api/v1/integrations/github/mappings",
            json={
                "project": "backend",
                "environment": f"archive-{time.time_ns()}",
                "profile_id": profile_id,
                "enabled": True,
            },
        )
        self.assertEqual(create_mapping.status_code, 200)
        mapping_id = int(create_mapping.json()["mapping"]["id"])

        delete_response = self.client.delete(f"/api/v1/integrations/github/mappings/{mapping_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json().get("deleted"))

        active_mappings = self.client.get("/api/v1/integrations/github/mappings").json().get("mappings", [])
        self.assertFalse(any(int(item.get("id")) == mapping_id for item in active_mappings))

        archived_mappings = self.client.get("/api/v1/integrations/github/mappings?include_archived=true").json().get("mappings", [])
        archived_item = next(item for item in archived_mappings if int(item.get("id")) == mapping_id)
        self.assertEqual(str(archived_item.get("status")).lower(), "archived")
        self.assertIsNotNone(archived_item.get("archived_at"))

        restore_response = self.client.post(f"/api/v1/integrations/github/mappings/{mapping_id}/restore")
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(str(restore_response.json()["mapping"].get("status")).lower(), "active")

    def test_archives_endpoint_lists_archived_mappings(self) -> None:
        create_profile = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": "Archives Mapping Profile",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
            },
        )
        self.assertEqual(create_profile.status_code, 200)
        profile_id = int(create_profile.json()["profile"]["id"])
        create_mapping = self.client.post(
            "/api/v1/integrations/github/mappings",
            json={
                "project": "backend",
                "environment": f"archives-mapping-{time.time_ns()}",
                "profile_id": profile_id,
                "enabled": True,
            },
        )
        self.assertEqual(create_mapping.status_code, 200)
        mapping_id = int(create_mapping.json()["mapping"]["id"])
        self.assertEqual(self.client.delete(f"/api/v1/integrations/github/mappings/{mapping_id}").status_code, 200)
        archived_payload = self.client.get("/api/v1/archives/integration-mappings")
        self.assertEqual(archived_payload.status_code, 200)
        self.assertTrue(any(int(item.get("id")) == mapping_id for item in archived_payload.json().get("mappings", [])))

    def test_deployment_webhook_rejects_non_allowlisted_repository(self) -> None:
        web_api.SIMULATOR_WEBHOOK_REPO_ALLOWLIST = {"backend": ["org/backend"]}
        web_api.SIMULATOR_WEBHOOK_PROJECT_SECRETS = {"backend": "backend-secret"}
        payload = {
            "repository": {"full_name": "org/unknown"},
            "deployment": {"id": 10, "environment": "production", "sha": "abc123"},
            "deployment_status": {"id": 11, "state": "success"},
        }
        body = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            "/api/v1/integrations/github/deployment-complete",
            data=body,
            headers={
                "X-GitHub-Event": "deployment_status",
                "X-Hub-Signature-256": self._signature("backend-secret", body),
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "rejected")
        self.assertEqual(response.json()["reason"], "repository_not_allowlisted")

    def test_restore_mapping_fails_when_profile_archived(self) -> None:
        create_profile = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": "Archived Target Profile",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
            },
        )
        self.assertEqual(create_profile.status_code, 200)
        profile_id = int(create_profile.json()["profile"]["id"])
        create_mapping = self.client.post(
            "/api/v1/integrations/github/mappings",
            json={
                "project": "backend",
                "environment": f"restore-conflict-{time.time_ns()}",
                "profile_id": profile_id,
                "enabled": True,
            },
        )
        self.assertEqual(create_mapping.status_code, 200)
        mapping_id = int(create_mapping.json()["mapping"]["id"])
        self.assertEqual(self.client.delete(f"/api/v1/integrations/github/mappings/{mapping_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/run-profiles/{profile_id}").status_code, 200)

        restore_response = self.client.post(f"/api/v1/integrations/github/mappings/{mapping_id}/restore")
        self.assertEqual(restore_response.status_code, 409)
        self.assertIn("archived profile", str(restore_response.json().get("detail", "")).lower())

    def test_deployment_webhook_queues_when_mapping_exists(self) -> None:
        web_api.SIMULATOR_WEBHOOK_REPO_ALLOWLIST = {"backend": ["org/backend"]}
        web_api.SIMULATOR_WEBHOOK_PROJECT_SECRETS = {"backend": "backend-secret"}

        create_profile = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": "Backend Prod",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
            },
        )
        self.assertEqual(create_profile.status_code, 200)
        profile_id = create_profile.json()["profile"]["id"]

        mapping_response = self.client.post(
            "/api/v1/integrations/github/mappings",
            json={
                "project": "backend",
                "environment": "production",
                "profile_id": profile_id,
                "enabled": True,
            },
        )
        self.assertEqual(mapping_response.status_code, 200)

        dep_id = int(time.time_ns() % 1_000_000_000) + 10_000_000
        status_id = dep_id + 1
        payload = {
            "repository": {"full_name": "org/backend"},
            "deployment": {"id": dep_id, "environment": "production", "sha": f"deadbeef{dep_id}"},
            "deployment_status": {"id": status_id, "state": "success"},
        }
        body = json.dumps(payload).encode("utf-8")
        with mock.patch.object(web_api, "_enqueue_integration_profile_launch") as launch_mock:
            response = self.client.post(
                "/api/v1/integrations/github/deployment-complete",
                data=body,
                headers={
                    "X-GitHub-Event": "deployment_status",
                    "X-Hub-Signature-256": self._signature("backend-secret", body),
                    "Content-Type": "application/json",
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["accepted"])
        self.assertIsNotNone(payload["trigger_id"])
        launch_mock.assert_called_once()

    def test_workflow_run_webhook_records_github_trigger_on_run(self) -> None:
        wf_secret = "wf-secret-test"
        env_overlay = {
            "SIMULATOR_WEBHOOK_PROJECT_SECRETS": json.dumps({"wfbackend": wf_secret}),
            "SIMULATOR_WEBHOOK_REPO_ALLOWLIST": json.dumps({"wfbackend": ["org/wf-backend"]}),
        }
        workflow_run_id = time.time_ns()
        with mock.patch.dict(os.environ, env_overlay, clear=False):
            with mock.patch.object(web_api, "_run_simulation", return_value=None):
                create_profile = self.client.post(
                    "/api/v1/run-profiles",
                    json={
                        "name": "WF Webhook Profile",
                        "flow": "doctor",
                        "plan": "sim_actors.json",
                        "timing": "fast",
                    },
                )
                self.assertEqual(create_profile.status_code, 200)
                profile_id = int(create_profile.json()["profile"]["id"])

                mapping_response = self.client.post(
                    "/api/v1/integrations/github/mappings",
                    json={
                        "project": "wfbackend",
                        "environment": "production",
                        "profile_id": profile_id,
                        "enabled": True,
                    },
                )
                self.assertEqual(mapping_response.status_code, 200)

                payload = {
                    "action": "completed",
                    "repository": {"full_name": "org/wf-backend"},
                    "workflow_run": {
                        "id": workflow_run_id,
                        "run_attempt": 1,
                        "conclusion": "success",
                        "status": "completed",
                        "head_sha": "deadbeef",
                        "head_branch": "main",
                        "name": "CI",
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                response = self.client.post(
                    "/api/v1/integrations/github/deployment-complete",
                    data=body,
                    headers={
                        "X-GitHub-Event": "workflow_run",
                        "X-Hub-Signature-256": self._signature(wf_secret, body),
                        "Content-Type": "application/json",
                    },
                )

        self.assertEqual(response.status_code, 200)
        hook = response.json()
        self.assertTrue(hook.get("accepted"))
        run_id = hook.get("run_id")
        self.assertIsNotNone(run_id)

        run_resp = self.client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(run_resp.status_code, 200)
        body = run_resp.json()
        run = body["run"] if isinstance(body.get("run"), dict) else body
        self.assertEqual(run["trigger_source"], "github")
        self.assertEqual(run["trigger_label"], "GitHub integration: wfbackend/production")
        self.assertEqual(run["integration_trigger_id"], hook["trigger_id"])
        ctx = run.get("trigger_context") or {}
        self.assertEqual(ctx.get("github_event"), "workflow_run")
        self.assertEqual(ctx.get("repository"), "org/wf-backend")
        self.assertEqual(ctx.get("project"), "wfbackend")
        self.assertEqual(ctx.get("environment"), "production")
        self.assertEqual(ctx.get("profile_id"), profile_id)
        self.assertEqual(ctx.get("profile_name"), "WF Webhook Profile")
        self.assertEqual(ctx.get("workflow_summary", {}).get("workflow_run_id"), workflow_run_id)

    def test_workflow_run_webhook_routes_by_branch_when_configured(self) -> None:
        wf_secret = "wf-secret-branch"
        env_overlay = {
            "SIMULATOR_WEBHOOK_PROJECT_SECRETS": json.dumps({"wfbackend": wf_secret}),
            "SIMULATOR_WEBHOOK_REPO_ALLOWLIST": json.dumps({"wfbackend": ["org/wf-backend"]}),
            "SIMULATOR_WEBHOOK_ROUTE_BY": "branch",
        }
        workflow_run_id = time.time_ns() + 1
        with mock.patch.dict(os.environ, env_overlay, clear=False):
            with mock.patch.object(web_api, "_run_simulation", return_value=None):
                create_profile = self.client.post(
                    "/api/v1/run-profiles",
                    json={
                        "name": "WF Dev Branch Profile",
                        "flow": "doctor",
                        "plan": "sim_actors.json",
                        "timing": "fast",
                    },
                )
                self.assertEqual(create_profile.status_code, 200)
                profile_id = int(create_profile.json()["profile"]["id"])

                mapping_response = self.client.post(
                    "/api/v1/integrations/github/mappings",
                    json={
                        "project": "wfbackend",
                        "environment": "dev",
                        "profile_id": profile_id,
                        "enabled": True,
                    },
                )
                self.assertEqual(mapping_response.status_code, 200)

                payload = {
                    "action": "completed",
                    "repository": {"full_name": "org/wf-backend"},
                    "workflow_run": {
                        "id": workflow_run_id,
                        "run_attempt": 1,
                        "conclusion": "success",
                        "status": "completed",
                        "head_sha": "cafebabe",
                        "head_branch": "dev",
                        "name": "CI",
                    },
                }
                body = json.dumps(payload).encode("utf-8")
                response = self.client.post(
                    "/api/v1/integrations/github/deployment-complete",
                    data=body,
                    headers={
                        "X-GitHub-Event": "workflow_run",
                        "X-Hub-Signature-256": self._signature(wf_secret, body),
                        "Content-Type": "application/json",
                    },
                )

        self.assertEqual(response.status_code, 200)
        hook = response.json()
        self.assertTrue(hook.get("accepted"))
        self.assertEqual(hook.get("environment"), "dev")
        run_id = hook.get("run_id")
        self.assertIsNotNone(run_id)

        run_resp = self.client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(run_resp.status_code, 200)
        body = run_resp.json()
        run = body["run"] if isinstance(body.get("run"), dict) else body
        self.assertEqual(run["trigger_label"], "GitHub integration: wfbackend/dev")
        self.assertEqual((run.get("trigger_context") or {}).get("environment"), "dev")


class IntegrationWebhookProjectsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self._tmpdir = tempfile.TemporaryDirectory()
        self._projects_file = pathlib.Path(self._tmpdir.name) / "webhook-projects.json"
        self._env_patch = mock.patch.dict(
            os.environ,
            {
                "SIMULATOR_WEBHOOK_PROJECTS_FILE": str(self._projects_file),
                "SIMULATOR_WEBHOOK_PROJECT_SECRETS": "{}",
                "SIMULATOR_WEBHOOK_REPO_ALLOWLIST": "{}",
                "SIMULATOR_GITHUB_CONFIG_TOKEN": "",
            },
            clear=False,
        )
        self._env_patch.start()
        self._sync_patch = mock.patch(
            "api.app.integrations.github_webhook_sync.sync_to_github",
            return_value={
                "sync_status": "skipped",
                "sync_error": None,
                "sync_commands": {
                    "secret": "gh secret set SIMULATOR_WEBHOOK_PROJECT_SECRETS --repo test/repo --body '{}'",
                    "allowlist": "gh variable set SIMULATOR_WEBHOOK_REPO_ALLOWLIST --repo test/repo --body '{}'",
                },
            },
        )
        self._sync_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self._sync_patch.stop()
        self._env_patch.stop()
        self._tmpdir.cleanup()
        self.client.close()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()

    @staticmethod
    def _signature(secret: str, body: bytes) -> str:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_create_and_list_webhook_project(self) -> None:
        suffix = str(time.time_ns())
        project_name = f"gui-project-{suffix}"
        create_response = self.client.post(
            "/api/v1/integrations/github/projects",
            json={
                "project": project_name,
                "repositories": [f"org/gui-repo-{suffix}"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created_body = create_response.json()
        created = created_body["project"]
        self.assertEqual(created["project"], project_name)
        self.assertTrue(created.get("secret"))
        self.assertTrue(created.get("secret_display_once"))
        self.assertIn("sync_commands", created_body)

        list_response = self.client.get("/api/v1/integrations/github/projects")
        self.assertEqual(list_response.status_code, 200)
        listed = list_response.json()
        self.assertIn("webhook_url", listed)
        match = next(item for item in listed["projects"] if item["project"] == project_name)
        self.assertNotIn("secret", match)
        self.assertEqual(match["repositories"], [f"org/gui-repo-{suffix}"])

    def test_create_duplicate_webhook_project_conflict(self) -> None:
        project_name = f"dup-project-{time.time_ns()}"
        first = self.client.post(
            "/api/v1/integrations/github/projects",
            json={"project": project_name, "repositories": []},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/v1/integrations/github/projects",
            json={"project": project_name, "repositories": []},
        )
        self.assertEqual(second.status_code, 409)

    def test_delete_webhook_project(self) -> None:
        project_name = f"del-project-{time.time_ns()}"
        self.assertEqual(
            self.client.post(
                "/api/v1/integrations/github/projects",
                json={"project": project_name, "repositories": []},
            ).status_code,
            200,
        )
        delete_response = self.client.delete(f"/api/v1/integrations/github/projects/{project_name}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json().get("deleted"))

        recreate = self.client.post(
            "/api/v1/integrations/github/projects",
            json={"project": project_name, "repositories": []},
        )
        self.assertEqual(recreate.status_code, 200)

    def test_deployment_webhook_uses_file_project_secret(self) -> None:
        suffix = str(time.time_ns())
        project_name = f"db-secret-{suffix}"
        repo = f"org/db-secret-{suffix}"
        create_response = self.client.post(
            "/api/v1/integrations/github/projects",
            json={"project": project_name, "repositories": [repo]},
        )
        self.assertEqual(create_response.status_code, 200)
        secret = create_response.json()["project"]["secret"]

        create_profile = self.client.post(
            "/api/v1/run-profiles",
            json={
                "name": "DB Secret Profile",
                "flow": "doctor",
                "plan": "sim_actors.json",
                "timing": "fast",
            },
        )
        self.assertEqual(create_profile.status_code, 200)
        profile_id = int(create_profile.json()["profile"]["id"])

        mapping_response = self.client.post(
            "/api/v1/integrations/github/mappings",
            json={
                "project": project_name,
                "environment": "production",
                "profile_id": profile_id,
                "enabled": True,
            },
        )
        self.assertEqual(mapping_response.status_code, 200)

        dep_id = int(time.time_ns() % 1_000_000_000) + 20_000_000
        status_id = dep_id + 1
        payload = {
            "repository": {"full_name": repo},
            "deployment": {"id": dep_id, "environment": "production", "sha": f"dbsecret{dep_id}"},
            "deployment_status": {"id": status_id, "state": "success"},
        }
        body = json.dumps(payload).encode("utf-8")
        with mock.patch.object(web_api, "_enqueue_integration_profile_launch") as launch_mock:
            response = self.client.post(
                "/api/v1/integrations/github/deployment-complete",
                data=body,
                headers={
                    "X-GitHub-Event": "deployment_status",
                    "X-Hub-Signature-256": self._signature(secret, body),
                    "Content-Type": "application/json",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        launch_mock.assert_called_once()


class CatalogSeedTests(unittest.TestCase):
    def _reset_catalog_rows(self) -> None:
        from api.app import catalog_seed

        now = web_api._utc_now()
        if web_api.USE_POSTGRES:
            conn = web_api._get_db_connection()
            try:
                with conn.cursor() as cursor:
                    for spec in catalog_seed.PROFILE_SPECS:
                        cursor.execute(
                            """
                            UPDATE run_profiles
                            SET status = %s, archived_at = %s, catalog_managed = TRUE, updated_at = %s
                            WHERE catalog_slug = %s
                            """,
                            ("active", None, now, spec["catalog_slug"]),
                        )
                    for spec in catalog_seed.SCHEDULE_SPECS:
                        cursor.execute(
                            """
                            UPDATE schedules
                            SET status = %s, catalog_managed = TRUE, updated_at = %s
                            WHERE catalog_slug = %s
                            """,
                            (str(spec.get("status") or "paused"), now, spec["catalog_slug"]),
                        )
                conn.commit()
            finally:
                conn.close()
            return

        with web_api.DB_LOCK, web_api._db() as conn:
            for spec in catalog_seed.PROFILE_SPECS:
                conn.execute(
                    """
                    UPDATE run_profiles
                    SET status = ?, archived_at = ?, catalog_managed = 1, updated_at = ?
                    WHERE catalog_slug = ?
                    """,
                    ("active", None, now, spec["catalog_slug"]),
                )
            for spec in catalog_seed.SCHEDULE_SPECS:
                conn.execute(
                    """
                    UPDATE schedules
                    SET status = ?, catalog_managed = 1, updated_at = ?
                    WHERE catalog_slug = ?
                    """,
                    (str(spec.get("status") or "paused"), now, spec["catalog_slug"]),
                )

    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.run_simulation_patch = mock.patch.object(web_api, "_run_simulation", return_value=None)
        self.run_simulation_patch.start()
        web_api._set_allowed_timezones_setting(None)
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200
        self._reset_catalog_rows()
        from api.app import catalog_seed
        catalog_seed.ensure_catalog_seed()

    def tearDown(self) -> None:
        self.run_simulation_patch.stop()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()
        self.client.close()

    def test_catalog_profiles_seeded_with_expected_fields(self) -> None:
        from api.app import catalog_seed

        profiles = web_api._list_run_profiles()
        by_slug = {p["catalog_slug"]: p for p in profiles if p.get("catalog_slug")}
        self.assertEqual(len(by_slug), len(catalog_seed.PROFILE_SPECS))
        for spec in catalog_seed.PROFILE_SPECS:
            slug = spec["catalog_slug"]
            self.assertIn(slug, by_slug, msg=f"missing catalog profile {slug}")
            row = by_slug[slug]
            self.assertEqual(row["flow"], spec["flow"])
            self.assertEqual(row.get("suite"), spec.get("suite"))
            if slug == "bounded-load-smoke":
                self.assertEqual(row["mode"], "load")
                self.assertEqual(row["users"], 2)
                self.assertEqual(row["orders"], 3)
                self.assertIn("--bounded-load-smoke-policy", row["extra_args"])
            if slug == "api-sweep-max":
                self.assertEqual(row["mode"], "trace")
                self.assertTrue(row["enforce_websocket_gates"])
                self.assertTrue(row["post_order_actions"])
                self.assertEqual(
                    row["scenarios"],
                    ["completed", "rejected", "cancelled", "backend_auto_cancel"],
                )

    def test_catalog_profiles_are_pinned_with_api_sweep_max_first(self) -> None:
        profiles = web_api._list_run_profiles()
        self.assertTrue(profiles)
        self.assertEqual(profiles[0].get("catalog_slug"), "api-sweep-max")

    def test_catalog_schedules_exist_with_expected_status_and_slots(self) -> None:
        from api.app import catalog_seed

        schedules = web_api._list_schedules(include_deleted=True)["schedules"]
        by_slug = {s["catalog_slug"]: s for s in schedules if s.get("catalog_slug")}
        for spec in catalog_seed.SCHEDULE_SPECS:
            sched_slug = spec["catalog_slug"]
            prof_slug = spec["profile_catalog_slug"]
            self.assertIn(sched_slug, by_slug, msg=f"missing catalog schedule {sched_slug}")
            sched = by_slug[sched_slug]
            expected_status = spec.get("status", "paused")
            self.assertEqual(sched["status"], expected_status)
            if expected_status == "paused":
                self.assertEqual(sched.get("next_run_reason"), "no_future_run")
            else:
                self.assertIsNotNone(sched.get("next_run_at"))
            self.assertEqual(sched.get("period"), spec.get("period", "daily"))
            self.assertEqual(sched.get("repeat"), spec.get("repeat", "daily"))
            self.assertEqual(
                int(sched.get("runs_per_period") or 0),
                int(spec.get("runs_per_period") or 1),
            )
            self.assertEqual(sched.get("run_slots") or [], spec.get("run_slots") or [])
            prof_id = next(p["id"] for p in web_api._list_run_profiles() if p.get("catalog_slug") == prof_slug)
            steps = sched.get("campaign_steps") or []
            self.assertTrue(steps)
            self.assertEqual(int(steps[0]["profile_id"]), int(prof_id))

    def test_catalog_bounded_load_command(self) -> None:
        profiles = web_api._list_run_profiles()
        row = next(p for p in profiles if p.get("catalog_slug") == "bounded-load-smoke")
        req = web_api._profile_request_to_run_request(row)
        cmd = web_api._build_command(req)
        self.assertIn("load", cmd)
        self.assertIn("--users", cmd)
        self.assertIn("2", cmd)
        self.assertIn("--orders", cmd)
        self.assertIn("3", cmd)
        self.assertIn("--bounded-load-smoke-policy", cmd)
        self.assertIn("--bounded-baseline-min-completed", cmd)
        self.assertIn("--reject", cmd)
        reject_idx = cmd.index("--reject")
        self.assertEqual(cmd[reject_idx + 1], "0.35")
        self.assertNotIn("--bounded-tail-reject-rate", cmd)

    def test_catalog_api_sweep_max_command_uses_full_suite_without_awaiting_payment_auto_cancel(self) -> None:
        profiles = web_api._list_run_profiles()
        row = next(p for p in profiles if p.get("catalog_slug") == "api-sweep-max")
        req = web_api._profile_request_to_run_request(row)
        cmd = web_api._build_command(req)
        self.assertIn("--suite", cmd)
        idx = cmd.index("--suite")
        self.assertEqual(cmd[idx + 1], "full")
        scenario_values = [cmd[i + 1] for i, token in enumerate(cmd[:-1]) if token == "--scenario"]
        self.assertIn("completed", scenario_values)
        self.assertIn("rejected", scenario_values)
        self.assertIn("cancelled", scenario_values)
        self.assertIn("backend_auto_cancel", scenario_values)
        self.assertNotIn("auto_cancel", scenario_values)
        self.assertIn("--enforce-websocket-gates", cmd)
        self.assertIn("--post-order-actions", cmd)

    def test_catalog_profile_delete_archives_profile(self) -> None:
        profiles = web_api._list_run_profiles(include_archived=True)
        catalog = next((p for p in profiles if p.get("catalog_slug")), None)
        if catalog is None:
            self.skipTest("No catalog profile found in this test database state.")
        resp = self.client.delete(f"/api/v1/run-profiles/{catalog['id']}")
        self.assertEqual(resp.status_code, 200)
        archived = web_api._get_run_profile(int(catalog["id"]), include_archived=True)
        self.assertEqual(archived.get("status"), "archived")
        self.assertFalse(bool(archived.get("catalog_managed")))

    def test_catalog_schedule_soft_delete_is_allowed(self) -> None:
        schedules = web_api._list_schedules(include_deleted=True)["schedules"]
        cat = next((s for s in schedules if s.get("catalog_slug")), None)
        if cat is None:
            self.skipTest("No catalog schedule found in this test database state.")
        resp = self.client.post(f"/api/v1/schedules/{cat['id']}/delete")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["schedule"]
        self.assertEqual(payload.get("status"), "deleted")
        self.assertFalse(bool(payload.get("catalog_managed")))

    def test_catalog_seed_respects_detached_rows(self) -> None:
        profiles = web_api._list_run_profiles(include_archived=True)
        catalog = next(p for p in profiles if p.get("catalog_slug") == "api-sweep-max")
        web_api._delete_run_profile(int(catalog["id"]))
        from api.app import catalog_seed
        catalog_seed.ensure_catalog_seed()
        archived = web_api._get_run_profile(int(catalog["id"]), include_archived=True)
        self.assertEqual(archived.get("status"), "archived")

    def test_catalog_seed_skip_requested_honors_env(self) -> None:
        from api.app import catalog_seed

        with mock.patch.dict(os.environ, {"SIM_SKIP_CATALOG_SEED": "1"}, clear=False):
            self.assertTrue(catalog_seed.catalog_seed_skip_requested())
        with mock.patch.dict(os.environ, {"SIM_SKIP_CATALOG_SEED": ""}, clear=False):
            self.assertFalse(catalog_seed.catalog_seed_skip_requested())


class SocketMonitorCoreTests(unittest.TestCase):
    def test_resolves_store_target_from_env_first(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = pathlib.Path(tmpdir) / "sim_actors.json"
            plan.write_text(json.dumps({"defaults": {"store_id": "FZY_FROM_PLAN"}}), encoding="utf-8")
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech",
                store_id="FZY_FROM_ENV",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            target = resolve_socket_target(config)

        self.assertEqual(target["store_id"], "FZY_FROM_ENV")
        self.assertEqual(target["source"], "SIM_SOCKET_MONITOR_STORE_ID")
        self.assertEqual(target["base_url"], "https://lastmile.fainzy.tech")

    def test_resolves_store_target_from_plan_default(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = pathlib.Path(tmpdir) / "sim_actors.json"
            plan.write_text(json.dumps({"defaults": {"store_id": "FZY_FROM_PLAN"}}), encoding="utf-8")
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech/",
                store_id="",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            target = resolve_socket_target(config)

        self.assertEqual(target["store_id"], "FZY_FROM_PLAN")
        self.assertEqual(target["source"], "sim_actors.json defaults.store_id")
        self.assertEqual(target["base_url"], "https://lastmile.fainzy.tech")

    def test_missing_store_target_returns_none(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, resolve_socket_target

        with tempfile.TemporaryDirectory() as tmpdir:
            config = SocketMonitorConfig(
                enabled=True,
                project_dir=pathlib.Path(tmpdir),
                lastmile_base_url="https://lastmile.fainzy.tech",
                store_id="",
                interval_seconds=60,
                connect_timeout_seconds=5.0,
                failure_threshold=2,
                notification_dedupe_seconds=600,
            )

            self.assertIsNone(resolve_socket_target(config))

    def test_reduces_socket_rows_to_overall_status(self) -> None:
        from api.app.socket_monitor import reduce_socket_status

        self.assertEqual(reduce_socket_status([{"status": "up"}, {"status": "up"}]), "up")
        self.assertEqual(reduce_socket_status([{"status": "up"}, {"status": "degraded"}]), "degraded")
        self.assertEqual(reduce_socket_status([{"status": "down"}, {"status": "up"}]), "down")
        self.assertEqual(reduce_socket_status([]), "unknown")

    def test_snapshot_uses_failure_threshold(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, SocketMonitor

        config = SocketMonitorConfig(
            enabled=True,
            project_dir=ROOT,
            lastmile_base_url="https://lastmile.fainzy.tech",
            store_id="FZY_TEST",
            interval_seconds=60,
            connect_timeout_seconds=5.0,
            failure_threshold=2,
            notification_dedupe_seconds=600,
        )
        sent: list[dict[str, object]] = []
        monitor = SocketMonitor(
            config=config,
            send_failure_email=lambda snapshot: sent.append(snapshot) or {"sent": True},
            load_notification_state=lambda: {},
            save_notification_state=lambda payload: None,
            now=lambda: "2026-06-18T12:00:00+00:00",
            now_epoch=lambda: 1000.0,
        )

        first = monitor.build_snapshot_from_probe_results(
            [
                {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
                {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
            ]
        )
        second = monitor.build_snapshot_from_probe_results(
            [
                {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
                {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
            ]
        )

        self.assertEqual(first["status"], "degraded")
        self.assertEqual(second["status"], "down")
        self.assertEqual(second["required"][0]["failure_streak"], 2)
        self.assertEqual(len(sent), 1)

    def test_notification_dedupe_uses_persisted_signature_and_window(self) -> None:
        from api.app.socket_monitor import SocketMonitorConfig, SocketMonitor

        state: dict[str, object] = {}
        sent: list[dict[str, object]] = []
        epoch = {"value": 1000.0}
        config = SocketMonitorConfig(
            enabled=True,
            project_dir=ROOT,
            lastmile_base_url="https://lastmile.fainzy.tech",
            store_id="FZY_TEST",
            interval_seconds=60,
            connect_timeout_seconds=5.0,
            failure_threshold=1,
            notification_dedupe_seconds=600,
        )
        monitor = SocketMonitor(
            config=config,
            send_failure_email=lambda snapshot: sent.append(snapshot) or {"sent": True},
            load_notification_state=lambda: dict(state),
            save_notification_state=lambda payload: state.update(payload),
            now=lambda: "2026-06-18T12:00:00+00:00",
            now_epoch=lambda: epoch["value"],
        )
        failed_probe = [
            {"key": "store_orders", "label": "Orders", "ok": False, "latency_ms": None, "reason": "timeout"},
            {"key": "store_stats", "label": "Stats", "ok": True, "latency_ms": 12, "reason": None},
        ]

        monitor.build_snapshot_from_probe_results(failed_probe)
        monitor.build_snapshot_from_probe_results(failed_probe)
        epoch["value"] = 1701.0
        monitor.build_snapshot_from_probe_results(failed_probe)

        self.assertEqual(len(sent), 2)


class SocketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_auth = _FakeCookieAuthManager()
        self.auth_enabled_patch = mock.patch.object(web_api.auth_service, "AUTH_ENABLED", True)
        self.auth_enabled_patch.start()
        self.auth_manager_patch = mock.patch.object(web_api.auth_service, "get_auth_manager", return_value=self.fake_auth)
        self.auth_manager_patch.start()
        self.client = TestClient(web_api.app)
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
        assert login.status_code == 200

    def tearDown(self) -> None:
        self.client.close()
        self.auth_manager_patch.stop()
        self.auth_enabled_patch.stop()

    def test_socket_status_endpoint_returns_cached_status_and_latest_evidence(self) -> None:
        status_payload = {
            "enabled": True,
            "status": "up",
            "checked_at": "2026-06-18T12:00:00+00:00",
            "target": {"store_id": "FZY_1", "source": "SIM_SOCKET_MONITOR_STORE_ID", "base_url": "https://lastmile.fainzy.tech"},
            "required": [{"key": "store_orders", "label": "Orders", "status": "up", "latency_ms": 10, "failure_streak": 0, "reason": None}],
            "reason": None,
        }
        run = {"id": 44, "status": "succeeded"}
        events = [
            {"id": 1, "actor": "store", "action": "mark_ready", "expect_websocket": True, "websocket_match": {"matched": True}},
            {"id": 2, "actor": "websocket", "category": "websocket", "details": {"source": "store_orders"}},
        ]
        with mock.patch.object(overview_service, "_socket_status_provider", return_value=status_payload):
            with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
                with mock.patch.object(overview_service, "_load_events", return_value=(events, [], {})):
                    response = self.client.get("/api/v1/overview/socket-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "up")
        self.assertEqual(payload["latest_run_evidence"]["run_id"], 44)
        self.assertEqual(payload["latest_run_evidence"]["matched"], 1)
        self.assertEqual(payload["latest_run_evidence"]["missed"], 0)

    def test_socket_down_adds_alert(self) -> None:
        with mock.patch.object(
            web_api,
            "_socket_monitor_status_payload",
            return_value={
                "enabled": True,
                "status": "down",
                "checked_at": "2026-06-18T12:00:00+00:00",
                "target": {"store_id": "FZY_1"},
                "required": [{"key": "store_stats", "label": "Stats", "status": "down", "reason": "timeout"}],
            },
        ):
            response = self.client.get("/api/v1/alerts")

        self.assertEqual(response.status_code, 200)
        alerts = response.json()["alerts"]
        self.assertTrue(any(alert["id"] == "socket-monitor-down" and alert["domain"] == "sockets" for alert in alerts))

    def test_email_settings_accept_socket_failure_trigger(self) -> None:
        response = self.client.put(
            "/api/v1/system/email",
            json={
                "email_enabled": True,
                "email_from_email": "alerts@example.com",
                "email_recipients": ["ops@example.com"],
                "email_event_triggers": ["socket_failure"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email_event_triggers"], ["socket_failure"])
