from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile
import threading
import time
import unittest
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
            store_id="FZY_123",
            phone="+2348000000000",
            all_users=False,
            no_auto_provision=False,
            post_order_actions=True,
            extra_args=["--strict-plan"],
        )

        with mock.patch.object(web_api.threading, "Thread", _FakeThread):
            run = web_api._create_run(request)

        snapshot = run.get("execution_snapshot")
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["flow"], "doctor")
        self.assertEqual(snapshot["plan"], "sim_actors.json")
        self.assertEqual(snapshot["store_id"], "FZY_123")
        self.assertEqual(snapshot["phone"], "+2348000000000")
        self.assertEqual(snapshot["extra_args"], ["--strict-plan"])
        self.assertIn("python3 -u -m simulate doctor", snapshot["command"])


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
                "store_id": "FZY_123",
                "phone": "+2348000001111",
                "all_users": False,
                "no_auto_provision": False,
                "post_order_actions": True,
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
        self.assertEqual(schedule["profile_id"], profile_id)
        self.assertEqual(schedule["schedule_type"], "simple")
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
                "stop_rule": "duration",
                "duration_seconds": 18000,
                "runs_per_period": 5,
                "run_window_start": "08:00",
                "run_window_end": "18:00",
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
        self.assertEqual(schedule["next_run_at"], future_anchor.isoformat())

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
                "stop_rule": "end_at",
                "end_at": (anchor + timedelta(minutes=2)).isoformat(),
                "runs_per_period": 1,
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
