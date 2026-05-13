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
        self.assertEqual(snapshot["extra_args"], ["--strict-plan"])
        self.assertIn("python3 -u -m simulate doctor", snapshot["command"])
        self.assertIn("--suite doctor", snapshot["command"])
        self.assertIn("--scenario app_bootstrap", snapshot["command"])
        self.assertIn("--enforce-websocket-gates", snapshot["command"])

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


class FlowCapabilitiesTests(unittest.TestCase):
    def test_flows_payload_includes_capabilities(self) -> None:
        payload = web_api._flows_payload()
        self.assertIn("flows", payload)
        self.assertIn("capabilities", payload)
        self.assertIn("doctor", payload["capabilities"])
        doctor = payload["capabilities"]["doctor"]
        self.assertEqual(doctor["resolved_mode"], "trace")
        self.assertIn("suite", doctor["allowed_optional_flags"])
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
                "endpoint": "/v1/core/cards/",
                "http_status": 404,
                "message": "no saved card",
                "ok": False,
            },
            {
                "id": 2,
                "actor": "user",
                "action": "place_order",
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
                "related_event_id": 1,
            },
            {
                "severity": "error",
                "code": "payment_intent_http_error",
                "message": "HTTP error creating payment intent",
                "related_event_id": 2,
            },
        ]

        with mock.patch.object(overview_service, "_load_latest_run", return_value=run):
            with mock.patch.object(overview_service, "_load_events", return_value=(events, artifact_issues, {})):
                with mock.patch.object(overview_service, "_load_metrics", return_value=None):
                    payload = overview_service.latest_run_overview()

        issues = payload["issues"]
        self.assertGreaterEqual(len(issues), 1)
        self.assertTrue(any((issue.get("route") == "/v1/core/orders/") for issue in issues))
        self.assertFalse(any(("missing_user_token" == issue.get("code")) for issue in issues))
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

    def test_delete_run_removes_only_selected_log_file_and_keeps_shared_log_dir(self) -> None:
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
                self.assertFalse(first_log.exists())
                self.assertTrue(second_log.exists())
                deleted = {os.path.realpath(path) for path in result["deleted_files"]}
                self.assertIn(os.path.realpath(str(first_log)), deleted)
                self.assertNotIn(os.path.realpath(str(second_log)), deleted)
            finally:
                try:
                    web_api._delete_run_logic(int(second["id"]))
                except Exception:
                    pass

    def test_delete_run_removes_only_selected_artifact_folder(self) -> None:
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
                self.assertFalse(first_artifacts.exists())
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


class RunProfilesApiTests(unittest.TestCase):
    class _FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

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

        replay_response = self.client.post(f"/api/v1/runs/{launched_run_id}/replay")
        self.assertEqual(replay_response.status_code, 200)
        replayed_run = replay_response.json()["run"]
        self.assertNotEqual(replayed_run["id"], launched_run_id)
        self.assertEqual(replay_response.json()["snapshot"]["flow"], "doctor")

        delete_response = self.client.delete(f"/api/v1/run-profiles/{profile_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])


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
        self.assertEqual(len(trigger_response.json()["runs"]), 2)
        self.assertTrue(trigger_response.json()["execution"].get("execution_chain_key"))

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
        future_anchor = (datetime.now(timezone.utc) + timedelta(minutes=3)).replace(second=0, microsecond=0)
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
                "end_at": (anchor + timedelta(minutes=2)).isoformat(),
                "runs_per_period": 1,
                "all_day": True,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        schedule_id = int(create_response.json()["schedule"]["id"])
        initial_next_run = create_response.json()["schedule"]["next_run_at"]
        self.assertEqual(initial_next_run, anchor.isoformat())

        # Listing should preserve persisted next_run_at instead of nulling it during hydration.
        list_response = self.client.get("/api/v1/schedules")
        self.assertEqual(list_response.status_code, 200)
        listed = next(item for item in list_response.json()["schedules"] if int(item["id"]) == schedule_id)
        self.assertEqual(listed["next_run_at"], initial_next_run)

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
