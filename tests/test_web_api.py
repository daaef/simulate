from __future__ import annotations

import json
import os
import pathlib
import tempfile
import threading
import time
import unittest
from unittest import mock

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
