import pathlib
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from reporting import RunRecorder
from transport import build_auth_proof, sanitize_payload, token_fingerprint
from websocket_observer import validate_websocket_events


def _fixtures():
    return types.SimpleNamespace(
        user_id=13,
        store={"id": 1, "name": "Test Store", "branch": "Main", "currency": "jpy"},
        location={"id": 5, "name": "Campus", "address": "Campus Road"},
        menu_items=[{"id": 1}, {"id": 2}],
        currency="jpy",
    )


class TransportProofTests(unittest.TestCase):
    def test_masking_and_fingerprint(self) -> None:
        proof = build_auth_proof(
            header_name="Authorization",
            token="abcdef1234567890",
            source="user_cached_token",
            scheme="Token",
        )
        self.assertEqual(proof["preview"], "abcd...7890")
        self.assertEqual(proof["fingerprint"], token_fingerprint("abcdef1234567890"))

        payload = sanitize_payload(
            {
                "token": "secret-token",
                "user": {"email": "user@example.com", "phone_number": "+123"},
                "nested": {"client_secret": "pi_secret"},
                "payment_method": "pm_card_visa",
            }
        )
        self.assertEqual(payload["token"], "[redacted]")
        self.assertEqual(payload["user"], "[redacted]")
        self.assertEqual(payload["nested"]["client_secret"], "[redacted]")
        self.assertEqual(payload["payment_method"], "[redacted]")


class RecorderTests(unittest.TestCase):
    def test_status_path_and_report_generation(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.set_fixtures(_fixtures())
        recorder.start_scenario("completed", expected_final_status="completed")

        first = recorder.record_event(
            actor="user",
            action="place_order",
            category="status",
            scenario="completed",
            step="place_order",
            order_db_id=101,
            order_ref="#101",
            observed_status="pending",
            method="POST",
            endpoint="/v1/core/orders/",
            full_url="https://example.test/v1/core/orders/",
            auth=build_auth_proof(
                header_name="Authorization",
                token="abcdef1234567890",
                source="user_cached_token",
                scheme="Token",
            ),
            body={"status": "pending"},
            response_preview='{"status":"pending"}',
            expect_websocket=True,
        )
        recorder.record_websocket(
            source="user_orders",
            raw='{"message":"{\\"id\\":101,\\"order_id\\":\\"#101\\",\\"status\\":\\"pending\\"}"}',
            payload={"message": '{"id":101,"order_id":"#101","status":"pending"}'},
            nested={"id": 101, "order_id": "#101", "status": "pending"},
            order_db_id=101,
            order_ref="#101",
            status="pending",
        )
        recorder.record_event(
            actor="store",
            action="accept_order",
            category="status",
            scenario="completed",
            step="accept_order",
            order_db_id=101,
            order_ref="#101",
            observed_status="payment_processing",
            method="PATCH",
            endpoint="/v1/core/orders/",
            full_url="https://example.test/v1/core/orders/?order_id=101",
            response_preview='{"status":"payment_processing"}',
            expect_websocket=True,
        )
        recorder.record_websocket(
            source="store_orders",
            raw='{"message":"{\\"id\\":101,\\"order_id\\":\\"#101\\",\\"status\\":\\"payment_processing\\"}"}',
            payload={"message": '{"id":101,"order_id":"#101","status":"payment_processing"}'},
            nested={"id": 101, "order_id": "#101", "status": "payment_processing"},
            order_db_id=101,
            order_ref="#101",
            status="payment_processing",
        )
        recorder.finish_scenario(
            "completed",
            verdict="passed",
            actual_final_status="payment_processing",
            order_db_id=101,
            order_ref="#101",
        )

        validate_websocket_events(recorder)

        self.assertEqual(
            [item["status"] for item in recorder.orders["101"]["statuses"]],
            ["pending", "payment_processing"],
        )
        self.assertTrue(first["websocket_match"]["matched"])

        report = recorder._render_markdown()
        story = recorder._render_story()
        self.assertIn("Technical Trace", report)
        self.assertIn("Auth proof", report)
        self.assertIn("Fainzy Simulation Story", story)

    def test_missing_websocket_creates_issue(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.set_fixtures(_fixtures())
        recorder.record_event(
            actor="store",
            action="mark_ready",
            category="status",
            scenario="completed",
            step="mark_ready",
            order_db_id=202,
            order_ref="#202",
            observed_status="ready",
            expect_websocket=True,
        )
        validate_websocket_events(recorder)
        codes = [issue["code"] for issue in recorder.issues]
        self.assertIn("websocket_event_missing", codes)

    def test_write_outputs_all_artifacts(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.set_fixtures(_fixtures())
        recorder.start_scenario("cancelled", expected_final_status="cancelled")
        recorder.record_event(
            actor="user",
            action="cancel_order",
            category="status",
            scenario="cancelled",
            step="cancel_order",
            order_db_id=303,
            order_ref="#303",
            observed_status="cancelled",
        )
        recorder.finish_scenario(
            "cancelled",
            verdict="passed",
            actual_final_status="cancelled",
            order_db_id=303,
            order_ref="#303",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder.run_dir = pathlib.Path(tmpdir) / "run"
            events_path, report_path, story_path = recorder.write()
            self.assertTrue(events_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(story_path.exists())
            self.assertIn("cancelled", story_path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
