import asyncio
import importlib.util
import pathlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from interaction_catalog import (
    MENU_AVAILABLE,
    MENU_SOLD_OUT,
    MENU_UNAVAILABLE,
    store_counts_menu_available,
    user_can_add_menu_item,
    user_menu_block_reason,
)
from reporting import RunRecorder
from scenarios import resolve_trace_scenarios
from flow_presets import resolve_flow
from transport import HttpResult, build_auth_proof, sanitize_payload, token_fingerprint
from websocket_observer import validate_websocket_events


def _fixtures():
    return types.SimpleNamespace(
        user_id=13,
        user={"id": 13, "phone_number": "+2348000000000", "first_name": "Test", "last_name": "User"},
        store={"id": 1, "name": "Test Store", "branch": "Main", "currency": "jpy"},
        location={"id": 5, "name": "Campus", "address": "Campus Road"},
        menu_items=[{"id": 1}, {"id": 2}],
        currency="jpy",
    )


def _load_simulate_entrypoint_module():
    module_path = pathlib.Path(__file__).resolve().parents[1] / "__main__.py"
    spec = importlib.util.spec_from_file_location("simulate_entrypoint_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunPlanTests(unittest.TestCase):
    def test_flow_alias_accepts_common_robot_typo(self) -> None:
        resolved = resolve_flow("ronot-complete")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved["name"], "robot-complete")

    def test_loads_json_plan_with_user_gps_and_store_ids(self) -> None:
        from run_plan import load_run_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "plan.json"
            path.write_text(
                """
                {
                  "defaults": {"user_phone": "+100", "store_id": "FZY_1", "location_radius": 2},
                  "users": [
                    {"phone": "+100", "role": "returning", "lat": 35.1, "lng": 136.9, "orders": 3},
                    {"phone": "+200", "role": "new_user", "gps": {"lat": 35.2, "lng": 137.0}}
                  ],
                  "stores": [
                    {"store_id": "FZY_1", "subentity_id": 7, "lat": 35.1, "lng": 136.9},
                    {"store_id": "FZY_2", "subentity_id": 8, "gps": {"latitude": 35.3, "longitude": 137.1}}
                  ]
                }
                """,
                encoding="utf-8",
            )

            plan = load_run_plan(path)

        self.assertEqual(plan.defaults["store_id"], "FZY_1")
        self.assertEqual(plan.users[0].phone, "+100")
        self.assertEqual(plan.users[0].orders, 3)
        self.assertEqual(plan.users[1].lat, 35.2)
        self.assertEqual(plan.users[1].lng, 137.0)
        self.assertEqual(plan.stores[1].store_id, "FZY_2")
        self.assertEqual(plan.stores[1].subentity_id, 8)
        self.assertEqual(plan.stores[1].lat, 35.3)
        self.assertEqual(plan.stores[1].lng, 137.1)

    def test_strict_validation_requires_user_gps_and_store_ids(self) -> None:
        from run_plan import PlanValidationError, load_run_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-plan.json"
            path.write_text(
                '{"users": [{"phone": "+100"}], "stores": [{"name": "No id"}]}',
                encoding="utf-8",
            )

            with self.assertRaises(PlanValidationError) as raised:
                load_run_plan(path, strict=True)

        message = str(raised.exception)
        self.assertIn("users[0].lat/lng", message)
        self.assertIn("stores[0].store_id", message)

    def test_plan_exports_legacy_actor_shape(self) -> None:
        from run_plan import RunPlan, PlanStore, PlanUser

        plan = RunPlan(
            defaults={"user_phone": "+100", "store_id": "FZY_1"},
            users=[PlanUser(phone="+100", role="returning", lat=1.0, lng=2.0)],
            stores=[PlanStore(store_id="FZY_1", subentity_id=5, lat=1.0, lng=2.0)],
        )

        actors = plan.to_actors()

        self.assertEqual(actors["defaults"]["user_phone"], "+100")
        self.assertEqual(actors["users"][0]["phone"], "+100")
        self.assertEqual(actors["users"][0]["lat"], 1.0)
        self.assertEqual(actors["stores"][0]["store_id"], "FZY_1")
        self.assertEqual(actors["stores"][0]["subentity_id"], 5)

    def test_loads_extended_non_sensitive_plan_sections(self) -> None:
        from run_plan import load_run_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "plan.json"
            path.write_text(
                """
                {
                  "schema_version": 2,
                  "defaults": {"user_phone": "+100", "store_id": "FZY_1"},
                  "runtime_defaults": {
                    "flow": "full",
                    "mode": "trace",
                    "trace_suite": "doctor",
                    "timing_profile": "realistic",
                    "users": 4,
                    "orders": 8,
                    "interval_seconds": 2.5,
                    "reject_rate": 0.25,
                    "continuous": false
                  },
                  "rules": {
                    "strict_plan": true,
                    "failure_policy": "api_only",
                    "preflight_strategy": "auto_recover",
                    "run_app_probes": false,
                    "run_store_dashboard_probes": false,
                    "run_post_order_actions": true,
                    "auto_select_store": false,
                    "auto_select_coupon": false,
                    "auto_provision_fixtures": false
                  },
                  "fixture_defaults": {
                    "store_setup": {"name": "Plan Store", "city": "Nagoya"},
                    "menu": {"category_name": "Plan Menu", "name": "Plan Item", "price": 1200}
                  },
                  "payment_defaults": {
                    "mode": "free",
                    "case": "free_with_coupon",
                    "free_order_amount": 0,
                    "coupon_id": 301,
                    "save_card": true,
                    "test_payment_method": "pm_card_visa"
                  },
                  "review_defaults": {"rating": 5, "comment": "Plan review"},
                  "new_user_defaults": {"first_name": "Plan", "last_name": "User", "email": "plan@example.com"},
                  "users": [{"phone": "+100", "lat": 35.1, "lng": 136.9}],
                  "stores": [{"store_id": "FZY_1", "lat": 35.1, "lng": 136.9}]
                }
                """,
                encoding="utf-8",
            )

            plan = load_run_plan(path)

        self.assertEqual(plan.schema_version, 2)
        self.assertEqual(plan.runtime_defaults["flow"], "full")
        self.assertEqual(plan.rules["strict_plan"], True)
        self.assertEqual(plan.rules["failure_policy"], "api_only")
        self.assertEqual(plan.rules["preflight_strategy"], "auto_recover")
        self.assertEqual(plan.fixture_defaults["menu"]["price"], 1200)
        self.assertEqual(plan.payment_defaults["coupon_id"], 301)
        self.assertEqual(plan.review_defaults["comment"], "Plan review")
        self.assertEqual(plan.new_user_defaults["email"], "plan@example.com")

    def test_plan_rejects_sensitive_keys(self) -> None:
        from run_plan import PlanValidationError, load_run_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-plan.json"
            path.write_text(
                """
                {
                  "payment_defaults": {"stripe_secret_key": "sk_test_should_not_be_here"},
                  "users": [{"phone": "+100", "lat": 35.1, "lng": 136.9}],
                  "stores": [{"store_id": "FZY_1", "lat": 35.1, "lng": 136.9}]
                }
                """,
                encoding="utf-8",
            )

            with self.assertRaises(PlanValidationError) as raised:
                load_run_plan(path)

        self.assertIn("sensitive key", str(raised.exception))

    def test_config_applies_plan_defaults_and_preserves_explicit_cli_values(self) -> None:
        import config

        tracked_attrs = (
            "SIM_FLOW",
            "SIM_RUN_MODE",
            "SIM_TRACE_SUITE",
            "SIM_TRACE_SCENARIOS",
            "SIM_TIMING_PROFILE",
            "N_USERS",
            "SIM_ORDERS",
            "ORDER_INTERVAL_SECONDS",
            "REJECT_RATE",
            "SIM_CONTINUOUS",
            "SIM_STRICT_PLAN",
            "SIM_FAILURE_POLICY",
            "SIM_PREFLIGHT_STRATEGY",
            "SIM_RUN_APP_PROBES",
            "SIM_RUN_STORE_DASHBOARD_PROBES",
            "SIM_RUN_POST_ORDER_ACTIONS",
            "SIM_ENFORCE_WEBSOCKET_GATES",
            "SIM_AUTO_SELECT_STORE",
            "SIM_AUTO_SELECT_COUPON",
            "SIM_AUTO_PROVISION_FIXTURES",
            "SIM_PAYMENT_MODE",
            "SIM_PAYMENT_CASE",
            "SIM_FREE_ORDER_AMOUNT",
            "SIM_COUPON_ID",
            "SIM_SAVE_CARD",
            "STRIPE_TEST_PAYMENT_METHOD",
            "SIM_STORE_SETUP_NAME",
            "SIM_STORE_SETUP_CITY",
            "SIM_MENU_CATEGORY_NAME",
            "SIM_MENU_NAME",
            "SIM_MENU_PRICE",
            "SIM_REVIEW_RATING",
            "SIM_REVIEW_COMMENT",
            "SIM_NEW_USER_FIRST_NAME",
            "SIM_NEW_USER_LAST_NAME",
            "SIM_NEW_USER_EMAIL",
            "SIM_ACTORS_PATH",
        )
        previous = {name: getattr(config, name) for name in tracked_attrs}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "plan.json"
            path.write_text(
                """
                {
                  "runtime_defaults": {
                    "flow": "full",
                    "mode": "trace",
                    "trace_suite": "doctor",
                    "trace_scenarios": ["completed", "rejected"],
                    "timing_profile": "realistic",
                    "users": 3,
                    "orders": 9,
                    "interval_seconds": 1.5,
                    "reject_rate": 0.2,
                    "continuous": true
                  },
                  "rules": {
                    "strict_plan": true,
                    "failure_policy": "api_only",
                    "preflight_strategy": "auto_recover",
                    "run_app_probes": false,
                    "run_store_dashboard_probes": false,
                    "run_post_order_actions": true,
                    "run_enforce_websocket_gates": true,
                    "auto_select_store": false,
                    "auto_select_coupon": false,
                    "auto_provision_fixtures": false
                  },
                  "payment_defaults": {
                    "mode": "free",
                    "case": "free_with_coupon",
                    "free_order_amount": 0,
                    "coupon_id": 301,
                    "save_card": true,
                    "test_payment_method": "pm_card_visa"
                  },
                  "fixture_defaults": {
                    "store_setup": {"name": "Plan Store", "city": "Nagoya"},
                    "menu": {"category_name": "Plan Category", "name": "Plan Item", "price": 900}
                  },
                  "review_defaults": {"rating": 5, "comment": "Plan review"},
                  "new_user_defaults": {"first_name": "Plan", "last_name": "User", "email": "plan@example.com"},
                  "users": [{"phone": "+100", "lat": 35.1, "lng": 136.9}],
                  "stores": [{"store_id": "FZY_1", "lat": 35.1, "lng": 136.9}]
                }
                """,
                encoding="utf-8",
            )
            try:
                config.SIM_TIMING_PROFILE = "fast"
                config.load_sim_actors(path, preserve={"SIM_TIMING_PROFILE"})

                self.assertEqual(config.SIM_FLOW, "full")
                self.assertEqual(config.SIM_RUN_MODE, "trace")
                self.assertEqual(config.SIM_TRACE_SUITE, "doctor")
                self.assertEqual(config.SIM_TRACE_SCENARIOS, ["completed", "rejected"])
                self.assertEqual(config.SIM_TIMING_PROFILE, "fast")
                self.assertEqual(config.N_USERS, 3)
                self.assertEqual(config.SIM_ORDERS, 9)
                self.assertEqual(config.ORDER_INTERVAL_SECONDS, 1.5)
                self.assertEqual(config.REJECT_RATE, 0.2)
                self.assertTrue(config.SIM_CONTINUOUS)
                self.assertTrue(config.SIM_STRICT_PLAN)
                self.assertEqual(config.SIM_FAILURE_POLICY, "api_only")
                self.assertEqual(config.SIM_PREFLIGHT_STRATEGY, "auto_recover")
                self.assertFalse(config.SIM_RUN_APP_PROBES)
                self.assertFalse(config.SIM_RUN_STORE_DASHBOARD_PROBES)
                self.assertTrue(config.SIM_RUN_POST_ORDER_ACTIONS)
                self.assertTrue(config.SIM_ENFORCE_WEBSOCKET_GATES)
                self.assertFalse(config.SIM_AUTO_SELECT_STORE)
                self.assertFalse(config.SIM_AUTO_SELECT_COUPON)
                self.assertFalse(config.SIM_AUTO_PROVISION_FIXTURES)
                self.assertEqual(config.SIM_PAYMENT_MODE, "free")
                self.assertEqual(config.SIM_PAYMENT_CASE, "free_with_coupon")
                self.assertEqual(config.SIM_COUPON_ID, 301)
                self.assertTrue(config.SIM_SAVE_CARD)
                self.assertEqual(config.SIM_STORE_SETUP_NAME, "Plan Store")
                self.assertEqual(config.SIM_STORE_SETUP_CITY, "Nagoya")
                self.assertEqual(config.SIM_MENU_CATEGORY_NAME, "Plan Category")
                self.assertEqual(config.SIM_MENU_NAME, "Plan Item")
                self.assertEqual(config.SIM_MENU_PRICE, 900.0)
                self.assertEqual(config.SIM_REVIEW_RATING, 5)
                self.assertEqual(config.SIM_REVIEW_COMMENT, "Plan review")
                self.assertEqual(config.SIM_NEW_USER_FIRST_NAME, "Plan")
                self.assertEqual(config.SIM_NEW_USER_LAST_NAME, "User")
                self.assertEqual(config.SIM_NEW_USER_EMAIL, "plan@example.com")
            finally:
                for name, value in previous.items():
                    setattr(config, name, value)

    def test_bounded_load_policy_transitions_to_tail_after_baseline(self) -> None:
        import config

        previous = (
            config.REJECT_RATE,
            config.SIM_BOUNDED_LOAD_POLICY,
            config.SIM_BOUNDED_BASELINE_MIN_COMPLETED,
            config.SIM_BOUNDED_BASELINE_MAX_ATTEMPTS,
            config.SIM_BOUNDED_TAIL_REJECT_RATE,
            config.SIM_BOUNDED_TAIL_CANCEL_RATE,
        )
        try:
            config.REJECT_RATE = 0.35
            config.configure_bounded_load_policy(
                enabled=True,
                baseline_min_completed=1,
                baseline_max_attempts=3,
                tail_reject_rate=0.35,
                tail_cancel_rate=0.15,
            )
            self.assertEqual(config.REJECT_RATE, 0.0)
            self.assertFalse(config.bounded_load_baseline_met())
            config.bounded_load_mark_order_attempt()
            transitioned = config.bounded_load_mark_completed()
            self.assertTrue(transitioned)
            self.assertTrue(config.bounded_load_baseline_met())
            self.assertEqual(config.REJECT_RATE, 0.35)
            summary = config.bounded_load_summary()
            self.assertTrue(summary["baseline_met"])
            self.assertEqual(summary["baseline_completed"], 1)
            self.assertEqual(summary["attempts"], 1)
        finally:
            (
                config.REJECT_RATE,
                config.SIM_BOUNDED_LOAD_POLICY,
                config.SIM_BOUNDED_BASELINE_MIN_COMPLETED,
                config.SIM_BOUNDED_BASELINE_MAX_ATTEMPTS,
                config.SIM_BOUNDED_TAIL_REJECT_RATE,
                config.SIM_BOUNDED_TAIL_CANCEL_RATE,
            ) = previous
            config.configure_bounded_load_policy(enabled=False)

    def test_bounded_load_baseline_guard_summary_when_not_met(self) -> None:
        import config

        previous = (
            config.REJECT_RATE,
            config.SIM_BOUNDED_LOAD_POLICY,
            config.SIM_BOUNDED_BASELINE_MIN_COMPLETED,
            config.SIM_BOUNDED_BASELINE_MAX_ATTEMPTS,
            config.SIM_BOUNDED_TAIL_REJECT_RATE,
            config.SIM_BOUNDED_TAIL_CANCEL_RATE,
        )
        try:
            config.REJECT_RATE = 0.2
            config.configure_bounded_load_policy(
                enabled=True,
                baseline_min_completed=1,
                baseline_max_attempts=2,
                tail_reject_rate=0.2,
                tail_cancel_rate=0.0,
            )
            config.bounded_load_mark_order_attempt()
            config.bounded_load_mark_order_attempt()
            summary = config.bounded_load_summary()
            self.assertFalse(summary["baseline_met"])
            self.assertEqual(summary["attempts"], 2)
            self.assertEqual(summary["baseline_max_attempts"], 2)
        finally:
            (
                config.REJECT_RATE,
                config.SIM_BOUNDED_LOAD_POLICY,
                config.SIM_BOUNDED_BASELINE_MIN_COMPLETED,
                config.SIM_BOUNDED_BASELINE_MAX_ATTEMPTS,
                config.SIM_BOUNDED_TAIL_REJECT_RATE,
                config.SIM_BOUNDED_TAIL_CANCEL_RATE,
            ) = previous
            config.configure_bounded_load_policy(enabled=False)

    def test_config_plan_path_prefers_existing_cwd_relative_path(self) -> None:
        import config

        previous_path = config.SIM_ACTORS_PATH
        previous_cwd = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            plan_dir = root / "simulate"
            plan_dir.mkdir()
            plan_path = plan_dir / "sim_actors.json"
            plan_path.write_text(
                '{"users": [{"phone": "+100"}], "stores": [{"store_id": "FZY_1"}]}',
                encoding="utf-8",
            )
            try:
                os.chdir(root)
                config.set_sim_actors_path("simulate/sim_actors.json")
                self.assertEqual(config.SIM_ACTORS_PATH.resolve(), plan_path.resolve())
            finally:
                os.chdir(previous_cwd)
                config.SIM_ACTORS_PATH = previous_path

    def test_default_random_selection_uses_plan_phone_and_store(self) -> None:
        import config

        tracked = (
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_PHONE_EXPLICIT",
            "SIM_STORE_EXPLICIT",
            "SIM_DISABLE_RANDOM_PHONE",
            "SIM_DISABLE_RANDOM_STORE",
            "SIM_PHONE_AUTO_SELECTED",
            "SIM_STORE_AUTO_SELECTED",
            "SIM_LAT",
            "SIM_LNG",
            "SUBENTITY_ID",
            "STORE_CURRENCY",
        )
        previous = {name: getattr(config, name) for name in tracked}
        actors = {
            "defaults": {
                "user_phone": "+100",
                "store_id": "FZY_1",
            },
            "users": [
                {"phone": "+100", "role": "returning", "lat": 1.0, "lng": 2.0},
                {"phone": "+200", "role": "returning", "lat": 3.0, "lng": 4.0},
            ],
            "stores": [
                {"store_id": "FZY_1", "subentity_id": 7, "currency": "jpy", "lat": 1.0, "lng": 2.0},
                {"store_id": "FZY_2", "subentity_id": 8, "currency": "jpy", "lat": 3.0, "lng": 4.0},
            ],
        }
        try:
            config.USER_PHONE_NUMBER = ""
            config.STORE_ID = ""
            config.SIM_PHONE_EXPLICIT = False
            config.SIM_STORE_EXPLICIT = False
            config.SIM_DISABLE_RANDOM_PHONE = False
            config.SIM_DISABLE_RANDOM_STORE = False
            config.SIM_PHONE_AUTO_SELECTED = False
            config.SIM_STORE_AUTO_SELECTED = False
            config.SIM_LAT = None
            config.SIM_LNG = None
            with mock.patch.object(
                config.random,
                "choice",
                side_effect=[actors["users"][1], actors["stores"][1]],
            ):
                config.apply_actor_selection(actors)

            self.assertEqual(config.USER_PHONE_NUMBER, "+200")
            self.assertEqual(config.STORE_ID, "FZY_2")
            self.assertEqual(config.SUBENTITY_ID, 8)
            self.assertTrue(config.SIM_PHONE_AUTO_SELECTED)
            self.assertTrue(config.SIM_STORE_AUTO_SELECTED)
        finally:
            for name, value in previous.items():
                setattr(config, name, value)

    def test_no_random_flags_bypass_random_selection(self) -> None:
        import config

        tracked = (
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_PHONE_EXPLICIT",
            "SIM_STORE_EXPLICIT",
            "SIM_DISABLE_RANDOM_PHONE",
            "SIM_DISABLE_RANDOM_STORE",
            "SIM_PHONE_AUTO_SELECTED",
            "SIM_STORE_AUTO_SELECTED",
            "SIM_LAT",
            "SIM_LNG",
            "SUBENTITY_ID",
            "STORE_CURRENCY",
        )
        previous = {name: getattr(config, name) for name in tracked}
        actors = {
            "defaults": {
                "user_phone": "+100",
                "store_id": "FZY_1",
            },
            "users": [
                {"phone": "+100", "role": "returning", "lat": 1.0, "lng": 2.0},
                {"phone": "+200", "role": "returning", "lat": 3.0, "lng": 4.0},
            ],
            "stores": [
                {"store_id": "FZY_1", "subentity_id": 7, "currency": "jpy", "lat": 1.0, "lng": 2.0},
                {"store_id": "FZY_2", "subentity_id": 8, "currency": "jpy", "lat": 3.0, "lng": 4.0},
            ],
        }
        try:
            config.USER_PHONE_NUMBER = ""
            config.STORE_ID = ""
            config.SIM_PHONE_EXPLICIT = False
            config.SIM_STORE_EXPLICIT = False
            config.SIM_DISABLE_RANDOM_PHONE = True
            config.SIM_DISABLE_RANDOM_STORE = True
            config.SIM_PHONE_AUTO_SELECTED = False
            config.SIM_STORE_AUTO_SELECTED = False
            config.SIM_LAT = None
            config.SIM_LNG = None
            with mock.patch.object(config.random, "choice") as random_choice:
                config.apply_actor_selection(actors)
            self.assertEqual(random_choice.call_count, 0)

            self.assertEqual(config.USER_PHONE_NUMBER, "+100")
            self.assertEqual(config.STORE_ID, "FZY_1")
            self.assertEqual(config.SUBENTITY_ID, 7)
            self.assertFalse(config.SIM_PHONE_AUTO_SELECTED)
            self.assertFalse(config.SIM_STORE_AUTO_SELECTED)
        finally:
            for name, value in previous.items():
                setattr(config, name, value)

    def test_explicit_phone_and_store_override_random_selection(self) -> None:
        import config

        tracked = (
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_PHONE_EXPLICIT",
            "SIM_STORE_EXPLICIT",
            "SIM_DISABLE_RANDOM_PHONE",
            "SIM_DISABLE_RANDOM_STORE",
            "SIM_PHONE_AUTO_SELECTED",
            "SIM_STORE_AUTO_SELECTED",
            "SIM_LAT",
            "SIM_LNG",
            "SUBENTITY_ID",
            "STORE_CURRENCY",
        )
        previous = {name: getattr(config, name) for name in tracked}
        actors = {
            "defaults": {
                "user_phone": "+100",
                "store_id": "FZY_1",
            },
            "users": [
                {"phone": "+100", "role": "returning", "lat": 1.0, "lng": 2.0},
                {"phone": "+200", "role": "returning", "lat": 3.0, "lng": 4.0},
            ],
            "stores": [
                {"store_id": "FZY_1", "subentity_id": 7, "currency": "jpy", "lat": 1.0, "lng": 2.0},
                {"store_id": "FZY_2", "subentity_id": 8, "currency": "jpy", "lat": 3.0, "lng": 4.0},
            ],
        }
        try:
            config.USER_PHONE_NUMBER = "+200"
            config.STORE_ID = "FZY_2"
            config.SIM_PHONE_EXPLICIT = True
            config.SIM_STORE_EXPLICIT = True
            config.SIM_DISABLE_RANDOM_PHONE = False
            config.SIM_DISABLE_RANDOM_STORE = False
            config.SIM_PHONE_AUTO_SELECTED = False
            config.SIM_STORE_AUTO_SELECTED = False
            with mock.patch.object(config.random, "choice") as random_choice:
                config.apply_actor_selection(actors)
            self.assertEqual(random_choice.call_count, 0)

            self.assertEqual(config.USER_PHONE_NUMBER, "+200")
            self.assertEqual(config.STORE_ID, "FZY_2")
            self.assertEqual(config.SUBENTITY_ID, 8)
            self.assertFalse(config.SIM_PHONE_AUTO_SELECTED)
            self.assertFalse(config.SIM_STORE_AUTO_SELECTED)
        finally:
            for name, value in previous.items():
                setattr(config, name, value)

    def test_new_user_role_randomizes_within_role_pool(self) -> None:
        import config

        tracked = (
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_PHONE_EXPLICIT",
            "SIM_STORE_EXPLICIT",
            "SIM_DISABLE_RANDOM_PHONE",
            "SIM_DISABLE_RANDOM_STORE",
            "SIM_PHONE_AUTO_SELECTED",
            "SIM_STORE_AUTO_SELECTED",
        )
        previous = {name: getattr(config, name) for name in tracked}
        actors = {
            "defaults": {"store_id": "FZY_1"},
            "users": [
                {"phone": "+100", "role": "returning"},
                {"phone": "+200", "role": "new_user"},
                {"phone": "+300", "role": "new_user"},
            ],
            "stores": [{"store_id": "FZY_1", "subentity_id": 7}],
        }
        try:
            config.USER_PHONE_NUMBER = ""
            config.STORE_ID = "FZY_1"
            config.SIM_PHONE_EXPLICIT = False
            config.SIM_STORE_EXPLICIT = True
            config.SIM_DISABLE_RANDOM_PHONE = False
            config.SIM_DISABLE_RANDOM_STORE = True
            config.SIM_PHONE_AUTO_SELECTED = False
            config.SIM_STORE_AUTO_SELECTED = False

            with mock.patch.object(config.random, "choice", return_value=actors["users"][2]):
                config.apply_actor_selection(actors, user_role="new_user")

            self.assertEqual(config.USER_PHONE_NUMBER, "+300")
            self.assertTrue(config.SIM_PHONE_AUTO_SELECTED)
        finally:
            for name, value in previous.items():
                setattr(config, name, value)

    def test_store_selection_does_not_override_delivery_gps(self) -> None:
        import config

        previous = (
            config.USER_PHONE_NUMBER,
            config.STORE_ID,
            config.SUBENTITY_ID,
            config.STORE_CURRENCY,
            config.SIM_LAT,
            config.SIM_LNG,
        )
        actors = {
            "users": [{"phone": "+100", "role": "returning"}],
            "stores": [
                {
                    "store_id": "FZY_ASK",
                    "subentity_id": 7,
                    "currency": "jpy",
                    "lat": 9.9094,
                    "lng": 8.8912,
                }
            ],
            "defaults": {},
        }
        try:
            config.USER_PHONE_NUMBER = "+100"
            config.STORE_ID = "FZY_ASK"
            config.SIM_LAT = 35.1549
            config.SIM_LNG = 136.9663

            config.apply_actor_selection(actors)

            self.assertEqual(config.STORE_ID, "FZY_ASK")
            self.assertEqual(config.SUBENTITY_ID, 7)
            self.assertEqual(config.SIM_LAT, 35.1549)
            self.assertEqual(config.SIM_LNG, 136.9663)
        finally:
            (
                config.USER_PHONE_NUMBER,
                config.STORE_ID,
                config.SUBENTITY_ID,
                config.STORE_CURRENCY,
                config.SIM_LAT,
                config.SIM_LNG,
            ) = previous

    def test_selected_user_gps_sets_delivery_gps(self) -> None:
        import config

        previous = (
            config.USER_PHONE_NUMBER,
            config.STORE_ID,
            config.SUBENTITY_ID,
            config.STORE_CURRENCY,
            config.SIM_LAT,
            config.SIM_LNG,
        )
        actors = {
            "users": [
                {"phone": "+100", "role": "returning", "lat": 1.25, "lng": 2.5},
                {"phone": "+200", "role": "new_user", "lat": 3.0, "lng": 4.0},
            ],
            "stores": [
                {
                    "store_id": "FZY_ASK",
                    "subentity_id": 7,
                    "currency": "jpy",
                    "lat": 9.9094,
                    "lng": 8.8912,
                }
            ],
            "defaults": {},
        }
        try:
            config.USER_PHONE_NUMBER = "+100"
            config.STORE_ID = "FZY_ASK"
            config.SIM_LAT = None
            config.SIM_LNG = None

            config.apply_actor_selection(actors)

            self.assertEqual(config.SIM_LAT, 1.25)
            self.assertEqual(config.SIM_LNG, 2.5)
        finally:
            (
                config.USER_PHONE_NUMBER,
                config.STORE_ID,
                config.SUBENTITY_ID,
                config.STORE_CURRENCY,
                config.SIM_LAT,
                config.SIM_LNG,
            ) = previous

    def test_selected_user_without_gps_falls_back_to_default_user_gps(self) -> None:
        import config

        previous = (
            config.USER_PHONE_NUMBER,
            config.STORE_ID,
            config.SUBENTITY_ID,
            config.STORE_CURRENCY,
            config.SIM_LAT,
            config.SIM_LNG,
        )
        actors = {
            "defaults": {"user_phone": "+200"},
            "users": [
                {"phone": "+100", "role": "returning"},
                {"phone": "+200", "role": "returning_default", "lat": 5.0, "lng": 6.0},
            ],
            "stores": [{"store_id": "FZY_ASK", "subentity_id": 7}],
        }
        try:
            config.USER_PHONE_NUMBER = "+100"
            config.STORE_ID = "FZY_ASK"
            config.SIM_LAT = None
            config.SIM_LNG = None

            config.apply_actor_selection(actors)

            self.assertEqual(config.SIM_LAT, 5.0)
            self.assertEqual(config.SIM_LNG, 6.0)
        finally:
            (
                config.USER_PHONE_NUMBER,
                config.STORE_ID,
                config.SUBENTITY_ID,
                config.STORE_CURRENCY,
                config.SIM_LAT,
                config.SIM_LNG,
            ) = previous


class TraceBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_setup_runs_before_fixture_bootstrap_when_requested(self) -> None:
        import trace_runner
        import user_sim
        import store_sim

        calls: list[str] = []
        recorder = RunRecorder.bootstrap()

        async def fake_user_auth(client, recorder, scenario=None):
            calls.append("user_auth")
            return user_sim.UserSession(
                token="user-token",
                user_id=13,
                user={"id": 13},
                token_source="test",
            )

        async def fake_store_auth(client, recorder):
            calls.append("store_auth")
            return store_sim.StoreSession(
                last_mile_token="store-token",
                fainzy_token=None,
                subentity={"id": 7, "setup": True},
                store_id=7,
                token_source="test",
            )

        async def fake_bootstrap_fixtures(*args, **kwargs):
            calls.append("fixtures")
            return _fixtures()

        async def fake_store_first_setup(*args, **kwargs):
            calls.append("setup")

        originals = (
            trace_runner.user_sim.bootstrap_auth,
            trace_runner.store_sim.bootstrap_auth,
            trace_runner.user_sim.bootstrap_fixtures,
            trace_runner._run_store_first_setup,
        )
        trace_runner.user_sim.bootstrap_auth = fake_user_auth
        trace_runner.store_sim.bootstrap_auth = fake_store_auth
        trace_runner.user_sim.bootstrap_fixtures = fake_bootstrap_fixtures
        trace_runner._run_store_first_setup = fake_store_first_setup
        try:
            await trace_runner.run(
                recorder=recorder,
                suite=None,
                scenarios=["store_first_setup", "menu_available"],
                timing_profile="fast",
            )
        finally:
            (
                trace_runner.user_sim.bootstrap_auth,
                trace_runner.store_sim.bootstrap_auth,
                trace_runner.user_sim.bootstrap_fixtures,
                trace_runner._run_store_first_setup,
            ) = originals

        self.assertLess(calls.index("setup"), calls.index("fixtures"))

    async def test_auto_provision_runs_before_fixtures_for_app_like_scenarios(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim

        calls: list[str] = []
        recorder = RunRecorder.bootstrap()
        previous_auto = getattr(config, "SIM_AUTO_PROVISION_FIXTURES", None)
        previous_store_mutation = config.SIM_MUTATE_STORE_SETUP
        previous_menu_mutation = config.SIM_MUTATE_MENU_SETUP

        async def fake_user_auth(client, recorder, scenario=None):
            calls.append("user_auth")
            return user_sim.UserSession(
                token="user-token",
                user_id=13,
                user={"id": 13},
                token_source="test",
            )

        async def fake_store_auth(client, recorder):
            calls.append("store_auth")
            return store_sim.StoreSession(
                last_mile_token="store-token",
                fainzy_token=None,
                subentity={"id": 7, "setup": False},
                store_id=7,
                token_source="test",
            )

        async def fake_bootstrap_fixtures(*args, **kwargs):
            calls.append("fixtures")
            return _fixtures()

        async def fake_store_first_setup(*args, **kwargs):
            calls.append("setup")

        originals = (
            trace_runner.user_sim.bootstrap_auth,
            trace_runner.store_sim.bootstrap_auth,
            trace_runner.user_sim.bootstrap_fixtures,
            trace_runner._run_store_first_setup,
        )
        trace_runner.user_sim.bootstrap_auth = fake_user_auth
        trace_runner.store_sim.bootstrap_auth = fake_store_auth
        trace_runner.user_sim.bootstrap_fixtures = fake_bootstrap_fixtures
        trace_runner._run_store_first_setup = fake_store_first_setup
        config.SIM_AUTO_PROVISION_FIXTURES = True
        config.SIM_MUTATE_STORE_SETUP = False
        config.SIM_MUTATE_MENU_SETUP = False
        try:
            await trace_runner.run(
                recorder=recorder,
                suite=None,
                scenarios=["menu_available"],
                timing_profile="fast",
            )
        finally:
            (
                trace_runner.user_sim.bootstrap_auth,
                trace_runner.store_sim.bootstrap_auth,
                trace_runner.user_sim.bootstrap_fixtures,
                trace_runner._run_store_first_setup,
            ) = originals
            if previous_auto is None:
                delattr(config, "SIM_AUTO_PROVISION_FIXTURES")
            else:
                config.SIM_AUTO_PROVISION_FIXTURES = previous_auto
            config.SIM_MUTATE_STORE_SETUP = previous_store_mutation
            config.SIM_MUTATE_MENU_SETUP = previous_menu_mutation

        self.assertLess(calls.index("setup"), calls.index("fixtures"))

    async def test_store_setup_creates_missing_menu_when_auto_provisioning(self) -> None:
        import config
        import trace_runner
        import store_sim

        calls: list[str] = []
        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True},
            store_id=7,
            token_source="test",
        )
        previous_auto = getattr(config, "SIM_AUTO_PROVISION_FIXTURES", None)
        previous_menu_mutation = config.SIM_MUTATE_MENU_SETUP

        async def fake_ensure_store_setup(*args, **kwargs):
            calls.append("ensure_store_setup")
            return True

        async def fake_fetch_categories(*args, **kwargs):
            calls.append("fetch_categories")
            return []

        async def fake_fetch_menus(*args, **kwargs):
            calls.append("fetch_menus")
            return []

        async def fake_create_category(*args, **kwargs):
            calls.append("create_category")
            return {"id": 1, "name": "Drinks"}

        async def fake_create_menu(*args, **kwargs):
            calls.append("create_menu")
            return {"id": 2, "status": "available"}

        async def fake_update_menu_status(*args, **kwargs):
            calls.append("update_menu_status")
            return {"id": 2, "status": "available"}

        async def fake_open_store(*args, **kwargs):
            calls.append("open_store")
            return None

        originals = (
            trace_runner.store_sim.ensure_store_setup,
            trace_runner.store_sim.open_store_for_simulation,
            trace_runner.store_sim.fetch_categories,
            trace_runner.store_sim.fetch_menus,
            trace_runner.store_sim.create_category,
            trace_runner.store_sim.create_menu,
            trace_runner.store_sim.update_menu_status,
        )
        trace_runner.store_sim.ensure_store_setup = fake_ensure_store_setup
        trace_runner.store_sim.open_store_for_simulation = fake_open_store
        trace_runner.store_sim.fetch_categories = fake_fetch_categories
        trace_runner.store_sim.fetch_menus = fake_fetch_menus
        trace_runner.store_sim.create_category = fake_create_category
        trace_runner.store_sim.create_menu = fake_create_menu
        trace_runner.store_sim.update_menu_status = fake_update_menu_status
        config.SIM_AUTO_PROVISION_FIXTURES = True
        config.SIM_MUTATE_MENU_SETUP = False
        try:
            await trace_runner._run_store_first_setup(
                object(),
                store_session=session,
                recorder=recorder,
            )
        finally:
            (
                trace_runner.store_sim.ensure_store_setup,
                trace_runner.store_sim.open_store_for_simulation,
                trace_runner.store_sim.fetch_categories,
                trace_runner.store_sim.fetch_menus,
                trace_runner.store_sim.create_category,
                trace_runner.store_sim.create_menu,
                trace_runner.store_sim.update_menu_status,
            ) = originals
            if previous_auto is None:
                delattr(config, "SIM_AUTO_PROVISION_FIXTURES")
            else:
                config.SIM_AUTO_PROVISION_FIXTURES = previous_auto
            config.SIM_MUTATE_MENU_SETUP = previous_menu_mutation

        self.assertIn("create_category", calls)
        self.assertIn("create_menu", calls)
        self.assertIn("update_menu_status", calls)

    async def test_trace_auto_selects_next_planned_store_when_default_fixture_fails(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim

        recorder = RunRecorder.bootstrap()
        store_login_calls: list[str | None] = []
        previous_store_id = config.STORE_ID
        previous_actors = getattr(config, "SIM_ACTORS", None)
        previous_store_explicit = getattr(config, "SIM_STORE_EXPLICIT", None)
        previous_disable_random_store = getattr(config, "SIM_DISABLE_RANDOM_STORE", False)

        async def fake_user_auth(client, recorder, scenario=None):
            return user_sim.UserSession(
                token="user-token",
                user_id=13,
                user={"id": 13},
                token_source="test",
            )

        async def fake_store_auth(client, recorder, store_id=None):
            store_login_calls.append(store_id)
            subentity_id = 1 if store_id == "FZY_BAD" else 2
            return store_sim.StoreSession(
                last_mile_token=f"store-token-{subentity_id}",
                fainzy_token=None,
                subentity={"id": subentity_id, "setup": True, "name": store_id},
                store_id=subentity_id,
                token_source="test",
                store_login_id=store_id or "",
            )

        async def fake_bootstrap_fixtures(*args, **kwargs):
            if kwargs.get("subentity_id") == 1:
                raise RuntimeError("bad store cannot serve this user")
            return types.SimpleNamespace(
                user_id=13,
                user={"id": 13, "phone_number": "+2348000000000", "first_name": "Test", "last_name": "User"},
                store={"id": 2, "name": "Good Store", "currency": "jpy"},
                location={"id": 5},
                menu_items=[{"id": 7, "status": "available", "price": 100}],
                currency="jpy",
            )

        async def fake_store_first_setup(*args, **kwargs):
            return None

        originals = (
            trace_runner.user_sim.bootstrap_auth,
            trace_runner.store_sim.bootstrap_auth,
            trace_runner.user_sim.bootstrap_fixtures,
            trace_runner._run_store_first_setup,
        )
        trace_runner.user_sim.bootstrap_auth = fake_user_auth
        trace_runner.store_sim.bootstrap_auth = fake_store_auth
        trace_runner.user_sim.bootstrap_fixtures = fake_bootstrap_fixtures
        trace_runner._run_store_first_setup = fake_store_first_setup
        config.STORE_ID = "FZY_BAD"
        config.SIM_ACTORS = {
            "defaults": {},
            "users": [],
            "stores": [
                {"store_id": "FZY_BAD"},
                {"store_id": "FZY_GOOD"},
            ],
        }
        config.SIM_STORE_EXPLICIT = False
        config.SIM_DISABLE_RANDOM_STORE = True
        try:
            await trace_runner.run(
                recorder=recorder,
                suite=None,
                scenarios=["menu_available"],
                timing_profile="fast",
            )
        finally:
            (
                trace_runner.user_sim.bootstrap_auth,
                trace_runner.store_sim.bootstrap_auth,
                trace_runner.user_sim.bootstrap_fixtures,
                trace_runner._run_store_first_setup,
            ) = originals
            config.STORE_ID = previous_store_id
            if previous_actors is None:
                delattr(config, "SIM_ACTORS")
            else:
                config.SIM_ACTORS = previous_actors
            if previous_store_explicit is None:
                delattr(config, "SIM_STORE_EXPLICIT")
            else:
                config.SIM_STORE_EXPLICIT = previous_store_explicit
            config.SIM_DISABLE_RANDOM_STORE = previous_disable_random_store

        self.assertEqual(store_login_calls, ["FZY_BAD", "FZY_GOOD"])
        self.assertEqual(recorder.fixtures_summary["store"]["id"], 2)

    async def test_trace_store_candidates_are_shuffled_when_random_store_enabled(self) -> None:
        import config
        import trace_runner

        tracked = (
            "SIM_ACTORS",
            "SIM_STORE_EXPLICIT",
            "SIM_DISABLE_RANDOM_STORE",
        )
        previous = {name: getattr(config, name) for name in tracked}
        config.SIM_ACTORS = {
            "stores": [
                {"store_id": "FZY_1"},
                {"store_id": "FZY_2"},
                {"store_id": "FZY_3"},
            ],
        }
        config.SIM_STORE_EXPLICIT = False
        config.SIM_DISABLE_RANDOM_STORE = False
        try:
            with mock.patch.object(
                trace_runner.random,
                "shuffle",
                side_effect=lambda values: values.reverse(),
            ):
                candidates = trace_runner._trace_store_candidates()
            self.assertEqual(candidates, ["FZY_3", "FZY_2", "FZY_1"])
        finally:
            for name, value in previous.items():
                setattr(config, name, value)


class StoreSetupPayloadTests(unittest.IsolatedAsyncioTestCase):
    def test_setup_payload_preserves_backend_profile_location_values(self) -> None:
        import store_sim

        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={
                "id": 7,
                "name": "Ask Me Restaurant Jos",
                "branch": "Ask me restaurant",
                "description": "store offering variety of home made and foreign dishes",
                "opening_days": "mon,tue,wed,thu,fri,sat,sun",
                "start_time": "07:00",
                "closing_time": "23:59",
                "setup": False,
                "mobile_number": "+2348166675609",
                "currency": "jpy",
                "status": 3,
                "gps_coordinates": {"type": "Point", "coordinates": [8.8912, 9.9094]},
                "location_details": {
                    "name": "48 Ahmadu Bello Way, Jos 930105, Plateau, Nigeria",
                    "country": "Nigeria",
                    "state": "Plateau",
                    "city": "Jos",
                    "address_details": "48 Ahmadu Bello Way, Jos 930105, Plateau, Nigeria",
                    "gps_coordinates": {
                        "latitude": "9.909435720196303",
                        "longitude": "8.891228847205639",
                    },
                },
            },
            store_id=7,
            token_source="test",
            gps_lat=9.9094,
            gps_lng=8.8912,
        )

        payload = store_sim.build_store_setup_payload(session)

        location = payload["location"][0]
        self.assertEqual(payload["name"], "Ask Me Restaurant Jos")
        self.assertEqual(payload["branch"], "Ask me restaurant")
        self.assertEqual(payload["status"], 3)
        self.assertEqual(location["country"], "Nigeria")
        self.assertEqual(location["state"], "Plateau")
        self.assertEqual(location["city"], "Jos")
        self.assertEqual(
            location["address_details"],
            "48 Ahmadu Bello Way, Jos 930105, Plateau, Nigeria",
        )

    async def test_create_menu_fills_non_image_fields(self) -> None:
        import config
        import store_sim

        captured: dict[str, object] = {}
        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True},
            store_id=7,
            token_source="test",
        )
        previous = (
            config.SIM_MENU_NAME,
            config.SIM_MENU_DESCRIPTION,
            config.SIM_MENU_PRICE,
            getattr(config, "SIM_MENU_INGREDIENTS", None),
            getattr(config, "SIM_MENU_DISCOUNT", None),
            getattr(config, "SIM_MENU_DISCOUNT_PRICE", None),
        )

        async def fake_request_json(*args, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                payload={
                    "status": "success",
                    "data": {"id": 2, **kwargs["json_body"]},
                }
            )

        config.SIM_MENU_NAME = "Simulator Rice Bowl"
        config.SIM_MENU_DESCRIPTION = "Complete simulator menu item."
        config.SIM_MENU_PRICE = 1200.0
        config.SIM_MENU_INGREDIENTS = "rice, sauce, vegetables"
        config.SIM_MENU_DISCOUNT = 0.0
        config.SIM_MENU_DISCOUNT_PRICE = 0.0
        try:
            with mock.patch.object(store_sim, "request_json", fake_request_json):
                await store_sim.create_menu(
                    object(),
                    session=session,
                    category_id=1,
                    status=MENU_AVAILABLE,
                    recorder=recorder,
                    scenario="store_first_setup",
                )
        finally:
            (
                config.SIM_MENU_NAME,
                config.SIM_MENU_DESCRIPTION,
                config.SIM_MENU_PRICE,
                config.SIM_MENU_INGREDIENTS,
                config.SIM_MENU_DISCOUNT,
                config.SIM_MENU_DISCOUNT_PRICE,
            ) = previous

        body = captured["json_body"]
        self.assertEqual(
            body,
            {
                "category": 1,
                "subentity": 7,
                "name": "Simulator Rice Bowl",
                "price": 1200.0,
                "description": "Complete simulator menu item.",
                "currency_symbol": None,
                "ingredients": "rice, sauce, vegetables",
                "discount": 0.0,
                "discount_price": 0.0,
                "status": "available",
            },
        )
        self.assertNotIn("images", body)

    async def test_open_store_for_simulation_restores_original_status(self) -> None:
        import store_sim

        payloads: list[dict[str, object]] = []
        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True, "status": 3},
            store_id=7,
            token_source="test",
        )

        async def fake_request_json(*args, **kwargs):
            payloads.append(kwargs["json_body"])
            return types.SimpleNamespace(
                payload={
                    "status": "success",
                    "data": {"id": 7, "status": kwargs["json_body"]["status"]},
                }
            )

        with mock.patch.object(store_sim, "request_json", fake_request_json):
            original_status = await store_sim.open_store_for_simulation(
                object(),
                session=session,
                recorder=recorder,
                scenario="store_first_setup",
            )
            await store_sim.restore_store_status(
                object(),
                session=session,
                original_status=original_status,
                recorder=recorder,
                scenario="simulation_cleanup",
            )

        self.assertEqual(original_status, 3)
        self.assertEqual(payloads, [{"status": 1}, {"status": 3}])
        self.assertEqual(session.subentity["status"], 3)

    async def test_setup_true_auto_provision_submits_store_update(self) -> None:
        import config
        import store_sim

        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True, "name": "Ask Me Restaurant Jos"},
            store_id=7,
            token_source="test",
        )
        previous_auto = config.SIM_AUTO_PROVISION_FIXTURES
        previous_mutate_store = config.SIM_MUTATE_STORE_SETUP
        captured_actions: list[str] = []

        async def fake_request_json(*args, **kwargs):
            captured_actions.append(str(kwargs.get("action")))
            return types.SimpleNamespace(
                payload={"status": "success", "data": {"id": 7, "setup": True}}
            )

        config.SIM_AUTO_PROVISION_FIXTURES = True
        config.SIM_MUTATE_STORE_SETUP = False
        try:
            with mock.patch.object(store_sim, "request_json", fake_request_json):
                setup_done = await store_sim.ensure_store_setup(
                    object(),
                    session=session,
                    recorder=recorder,
                    scenario="store_first_setup",
                )
        finally:
            config.SIM_AUTO_PROVISION_FIXTURES = previous_auto
            config.SIM_MUTATE_STORE_SETUP = previous_mutate_store

        self.assertTrue(setup_done)
        self.assertEqual(captured_actions, ["submit_store_update"])

    async def test_setup_true_without_auto_provision_skips_store_update(self) -> None:
        import config
        import store_sim

        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True, "name": "Ask Me Restaurant Jos"},
            store_id=7,
            token_source="test",
        )
        previous_auto = config.SIM_AUTO_PROVISION_FIXTURES
        previous_mutate_store = config.SIM_MUTATE_STORE_SETUP

        async def fake_request_json(*args, **kwargs):
            raise AssertionError("request_json should not be called when auto-provision is disabled")

        config.SIM_AUTO_PROVISION_FIXTURES = False
        config.SIM_MUTATE_STORE_SETUP = False
        try:
            with mock.patch.object(store_sim, "request_json", fake_request_json):
                setup_done = await store_sim.ensure_store_setup(
                    object(),
                    session=session,
                    recorder=recorder,
                    scenario="store_first_setup",
                )
        finally:
            config.SIM_AUTO_PROVISION_FIXTURES = previous_auto
            config.SIM_MUTATE_STORE_SETUP = previous_mutate_store

        self.assertTrue(setup_done)
        events = [event for event in recorder.events if event.get("action") == "submit_store_update"]
        self.assertEqual(events, [])


class StoreSetupConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_setup_submission_is_visible_in_console(self) -> None:
        import config
        import store_sim

        previous_auto = config.SIM_AUTO_PROVISION_FIXTURES
        previous_store_mutation = config.SIM_MUTATE_STORE_SETUP
        recorder = RunRecorder.bootstrap()
        session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": False, "name": "Ask Me Restaurant Jos"},
            store_id=7,
            token_source="test",
        )

        async def fake_request_json(*args, **kwargs):
            return types.SimpleNamespace(
                payload={"status": "success", "data": {"id": 7, "setup": True}}
            )

        config.SIM_AUTO_PROVISION_FIXTURES = True
        config.SIM_MUTATE_STORE_SETUP = False
        try:
            with (
                mock.patch.object(store_sim, "request_json", fake_request_json),
                mock.patch.object(store_sim.console, "print") as printed,
            ):
                setup_done = await store_sim.ensure_store_setup(
                    object(),
                    session=session,
                    recorder=recorder,
                    scenario="store_first_setup",
                )
        finally:
            config.SIM_AUTO_PROVISION_FIXTURES = previous_auto
            config.SIM_MUTATE_STORE_SETUP = previous_store_mutation

        messages = "\n".join(
            str(call.args[0]) for call in printed.call_args_list if call.args
        )
        self.assertTrue(setup_done)
        self.assertIn("Store setup is false", messages)
        self.assertIn("Store setup completed", messages)


class AppAutopilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_coupon_flow_auto_selects_valid_coupon_when_none_is_configured(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim

        recorder = RunRecorder.bootstrap()
        calls: list[tuple[int | None, str, str, int | None]] = []
        previous = (
            config.SIM_COUPON_ID,
            config.SIM_PAYMENT_MODE,
            config.SIM_PAYMENT_CASE,
            getattr(config, "SIM_AUTO_SELECT_COUPON", None),
            getattr(config, "SIM_SELECTED_COUPON", None),
        )
        had_auto_select = hasattr(config, "SIM_AUTO_SELECT_COUPON")
        had_selected_coupon = hasattr(config, "SIM_SELECTED_COUPON")
        had_fetch = hasattr(trace_runner.app_probes, "fetch_user_coupons")
        original_fetch = getattr(trace_runner.app_probes, "fetch_user_coupons", None)

        async def fake_fetch_user_coupons(*args, **kwargs):
            return [
                {
                    "id": 301,
                    "code": "#FZ_auto",
                    "is_valid": True,
                    "config_details": {
                        "discount": 2000.0,
                        "is_percentage": False,
                        "min_order": 0.0,
                    },
                }
            ]

        async def fake_run_completed(*args, **kwargs):
            selected = getattr(config, "SIM_SELECTED_COUPON", None) or {}
            calls.append(
                (
                    config.SIM_COUPON_ID,
                    config.SIM_PAYMENT_MODE,
                    config.SIM_PAYMENT_CASE,
                    selected.get("id"),
                )
            )

        original_run_completed = trace_runner._run_completed
        setattr(trace_runner.app_probes, "fetch_user_coupons", fake_fetch_user_coupons)
        trace_runner._run_completed = fake_run_completed
        config.SIM_COUPON_ID = None
        config.SIM_PAYMENT_MODE = "stripe"
        config.SIM_PAYMENT_CASE = "paid_no_coupon"
        config.SIM_AUTO_SELECT_COUPON = True
        config.SIM_SELECTED_COUPON = None
        try:
            await trace_runner._run_payment_scenario(
                object(),
                scenario="returning_free_with_coupon",
                user_session=user_sim.UserSession(
                    token="user-token",
                    user_id=13,
                    user={"id": 13},
                    token_source="test",
                ),
                store_session=store_sim.StoreSession(
                    last_mile_token="store-token",
                    fainzy_token=None,
                    subentity={"id": 7, "setup": True},
                    store_id=7,
                    token_source="test",
                ),
                fixtures=_fixtures(),
                recorder=recorder,
                timing=trace_runner.resolve_timing_profile("fast"),
                observer=None,
            )
        finally:
            trace_runner._run_completed = original_run_completed
            if had_fetch:
                setattr(trace_runner.app_probes, "fetch_user_coupons", original_fetch)
            else:
                delattr(trace_runner.app_probes, "fetch_user_coupons")
            (
                config.SIM_COUPON_ID,
                config.SIM_PAYMENT_MODE,
                config.SIM_PAYMENT_CASE,
                auto_select,
                selected_coupon,
            ) = previous
            if not had_auto_select:
                delattr(config, "SIM_AUTO_SELECT_COUPON")
            else:
                config.SIM_AUTO_SELECT_COUPON = auto_select
            if not had_selected_coupon:
                delattr(config, "SIM_SELECTED_COUPON")
            else:
                config.SIM_SELECTED_COUPON = selected_coupon

        self.assertEqual(calls, [(301, "free", "free_with_coupon", 301)])

    def test_paid_coupon_that_covers_order_uses_free_payment_route(self) -> None:
        import config
        import trace_runner

        previous = (
            config.SIM_COUPON_ID,
            config.SIM_PAYMENT_MODE,
            config.SIM_PAYMENT_CASE,
            getattr(config, "SIM_SELECTED_COUPON", None),
        )
        had_selected_coupon = hasattr(config, "SIM_SELECTED_COUPON")
        config.SIM_COUPON_ID = 301
        config.SIM_PAYMENT_MODE = "stripe"
        config.SIM_PAYMENT_CASE = "paid_with_coupon"
        config.SIM_SELECTED_COUPON = {
            "id": 301,
            "config_details": {"discount": 2000.0, "is_percentage": False},
        }
        try:
            payment_mode = trace_runner._payment_mode_for_order(100.0)
        finally:
            (
                config.SIM_COUPON_ID,
                config.SIM_PAYMENT_MODE,
                config.SIM_PAYMENT_CASE,
                selected_coupon,
            ) = previous
            if not had_selected_coupon:
                delattr(config, "SIM_SELECTED_COUPON")
            else:
                config.SIM_SELECTED_COUPON = selected_coupon

        self.assertEqual(payment_mode, "free")


class DecisionConsoleLogTests(unittest.IsolatedAsyncioTestCase):
    def test_checkout_decision_is_printed_to_console(self) -> None:
        import trace_runner

        with mock.patch.object(trace_runner.console, "print") as printed:
            trace_runner._print_checkout_decision(
                order_ref="#123456",
                payment_mode="free",
                payment_case="free_with_coupon",
                coupon_id=301,
                save_card=False,
            )

        messages = "\n".join(
            str(call.args[0]) for call in printed.call_args_list if call.args
        )
        self.assertIn("Checkout decision", messages)
        self.assertIn("free", messages)
        self.assertIn("coupon=301", messages)

    async def test_free_order_completion_is_printed_to_console(self) -> None:
        import config
        import user_sim

        previous = (
            config.SIM_FREE_ORDER_AMOUNT,
            config.SIM_COUPON_ID,
            config.STORE_CURRENCY,
            config.SUBENTITY_ID,
        )

        async def fake_request_json(*args, **kwargs):
            return types.SimpleNamespace(payload={"status": "success"})

        config.SIM_FREE_ORDER_AMOUNT = 0
        config.SIM_COUPON_ID = 301
        config.STORE_CURRENCY = "jpy"
        config.SUBENTITY_ID = 7
        try:
            with (
                mock.patch.object(user_sim, "request_json", fake_request_json),
                mock.patch.object(user_sim.console, "print") as printed,
            ):
                ok = await user_sim.complete_free_order(
                    object(),
                    user_token="user-token",
                    token_source="test",
                    order_ref="#123456",
                    order_db_id=99,
                    recorder=RunRecorder.bootstrap(),
                    scenario="returning_free_with_coupon",
                    step="complete_free_order",
                )
        finally:
            (
                config.SIM_FREE_ORDER_AMOUNT,
                config.SIM_COUPON_ID,
                config.STORE_CURRENCY,
                config.SUBENTITY_ID,
            ) = previous

        messages = "\n".join(
            str(call.args[0]) for call in printed.call_args_list if call.args
        )
        self.assertTrue(ok)
        self.assertIn("Completing free order", messages)
        self.assertIn("coupon=301", messages)
        self.assertIn("Free order confirmed", messages)

    async def test_post_order_actions_are_printed_to_console(self) -> None:
        import config
        import post_order_actions

        previous = (
            config.SIM_RUN_POST_ORDER_ACTIONS,
            config.SIM_REVIEW_RATING,
            config.SIM_REVIEW_COMMENT,
        )
        printed = mock.Mock()

        async def fake_generate_receipt(*args, **kwargs):
            return None

        async def fake_submit_review(*args, **kwargs):
            return None

        async def fake_fetch_reorder(*args, **kwargs):
            return None

        config.SIM_RUN_POST_ORDER_ACTIONS = True
        config.SIM_REVIEW_RATING = 4
        config.SIM_REVIEW_COMMENT = "Simulator review"
        try:
            with (
                mock.patch.object(
                    post_order_actions,
                    "console",
                    types.SimpleNamespace(print=printed),
                    create=True,
                ),
                mock.patch.object(
                    post_order_actions,
                    "generate_receipt",
                    fake_generate_receipt,
                ),
                mock.patch.object(
                    post_order_actions,
                    "submit_review",
                    fake_submit_review,
                ),
                mock.patch.object(
                    post_order_actions,
                    "fetch_reorder",
                    fake_fetch_reorder,
                ),
            ):
                await post_order_actions.run_post_order_actions(
                    object(),
                    recorder=RunRecorder.bootstrap(),
                    user_token="user-token",
                    token_source="test",
                    order_db_id=99,
                    order_ref="#123456",
                    subentity={"id": 7, "name": "Store"},
                    scenario="receipt_review_reorder",
                )
        finally:
            (
                config.SIM_RUN_POST_ORDER_ACTIONS,
                config.SIM_REVIEW_RATING,
                config.SIM_REVIEW_COMMENT,
            ) = previous

        messages = "\n".join(
            str(call.args[0]) for call in printed.call_args_list if call.args
        )
        self.assertIn("Generating receipt", messages)
        self.assertIn("Submitting review", messages)
        self.assertIn("rating=4", messages)
        self.assertIn("Fetching reorder", messages)


class HealthSummaryTests(unittest.TestCase):
    def test_health_summary_counts_latency_bottlenecks_and_websockets(self) -> None:
        from health import build_health_summary

        events = [
            {
                "id": 1,
                "actor": "user",
                "category": "status",
                "method": "POST",
                "endpoint": "/v1/core/orders/",
                "http_status": 201,
                "latency_ms": 100,
                "expect_websocket": True,
                "websocket_match": {"matched": True, "latency_ms": 35},
            },
            {
                "id": 2,
                "actor": "store",
                "category": "verification",
                "method": "GET",
                "endpoint": "/v1/statistics/subentities/7/",
                "http_status": 404,
                "latency_ms": 900,
            },
            {
                "id": 3,
                "actor": "websocket",
                "category": "websocket",
                "observed_status": "pending",
            },
        ]
        summary = build_health_summary(
            duration_ms=2000,
            scenarios=[{"name": "completed", "effective_verdict": "passed"}],
            orders=[{"final_status": "completed"}],
            events=events,
            issues=[{"severity": "warning"}, {"severity": "error"}],
        )

        self.assertEqual(summary["verdict"], "failed")
        self.assertEqual(summary["issue_counts"]["error"], 1)
        self.assertEqual(summary["http"]["status_groups"]["2xx"], 1)
        self.assertEqual(summary["http"]["status_groups"]["4xx"], 1)
        self.assertEqual(summary["http"]["latency_ms"]["p50"], 500)
        self.assertEqual(summary["http"]["slowest"][0]["endpoint"], "/v1/statistics/subentities/7/")
        self.assertEqual(summary["websockets"]["expected"], 1)
        self.assertEqual(summary["websockets"]["matched"], 1)
        self.assertEqual(summary["websockets"]["match_rate"], 1.0)

    def test_health_summary_api_only_degrades_for_precondition(self) -> None:
        from health import build_health_summary

        summary = build_health_summary(
            duration_ms=500,
            scenarios=[{"name": "coupon", "effective_verdict": "unsupported"}],
            orders=[],
            events=[],
            issues=[
                {
                    "severity": "warning",
                    "failure_class": "precondition",
                    "code": "coupon_required",
                }
            ],
            failure_policy="api_only",
        )
        self.assertEqual(summary["verdict"], "degraded")

    def test_health_summary_api_only_fails_for_api_fault(self) -> None:
        from health import build_health_summary

        summary = build_health_summary(
            duration_ms=500,
            scenarios=[{"name": "payments", "effective_verdict": "degraded"}],
            orders=[],
            events=[],
            issues=[
                {
                    "severity": "error",
                    "failure_class": "api_fault",
                    "code": "probe_http_server_error",
                }
            ],
            failure_policy="api_only",
        )
        self.assertEqual(summary["verdict"], "failed")

    def test_ascii_bar_uses_proportional_width(self) -> None:
        from health import ascii_bar

        self.assertEqual(ascii_bar(5, maximum=10, width=10), "#####-----")
        self.assertEqual(ascii_bar(0, maximum=0, width=6), "------")


class AppProbeTests(unittest.IsolatedAsyncioTestCase):
    def _http_result(self, *, recorder: RunRecorder, action: str, status_code: int, payload: object) -> HttpResult:
        event = recorder.record_event(
            actor="probe",
            action=action,
            category="probe",
            ok=status_code < 400,
            method="GET",
            endpoint="/v1/mock/",
            http_status=status_code,
            track_order=False,
        )
        return HttpResult(
            response=httpx.Response(
                status_code=status_code,
                request=httpx.Request("GET", "https://example.test/v1/mock/"),
            ),
            payload=payload,
            event=event,
            latency_ms=20,
        )

    def test_probe_specs_cover_real_app_surfaces(self) -> None:
        from app_probes import PROBE_SPECS

        names = {spec.name for spec in PROBE_SPECS}

        self.assertIn("global_config", names)
        self.assertIn("product_auth", names)
        self.assertIn("pricing", names)
        self.assertIn("saved_cards", names)
        self.assertIn("coupons", names)
        self.assertIn("store_statistics", names)
        self.assertIn("top_customers", names)

    async def test_safe_probe_records_issue_without_raising(self) -> None:
        from app_probes import probe_spec, run_probe
        from transport import RequestError

        recorder = RunRecorder.bootstrap()
        spec = probe_spec("global_config")

        async def failing_request(*args, **kwargs):
            event = recorder.record_event(
                actor="probe",
                action=spec.action,
                category="probe",
                ok=False,
                track_order=False,
            )
            raise RequestError("boom", event=event)

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=spec,
            request_func=failing_request,
        )

        self.assertIsNone(result)
        self.assertEqual(recorder.issues[0]["code"], "probe_failed")
        self.assertIn(spec.name, recorder.issues[0]["message"])

    async def test_probe_4xx_with_documented_variant_is_passed(self) -> None:
        from app_probes import probe_spec, run_probe
        from transport import RequestError

        recorder = RunRecorder.bootstrap()
        spec = probe_spec("store_statistics")
        result_404 = self._http_result(
            recorder=recorder,
            action=spec.action,
            status_code=404,
            payload={"status": "error", "message": "Object not found"},
        )

        async def request_404(*args, **kwargs):
            raise RequestError("HTTP 404", event=result_404.event, result=result_404)

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=spec,
            context={"subentity_id": 7},
            token="store-token",
            token_source="test",
            request_func=request_404,
        )

        self.assertIsNotNone(result)
        self.assertEqual(recorder.decisions[-1]["status"], "passed")
        self.assertEqual(recorder.decisions[-1]["reason_code"], "probe_response_ok")
        self.assertFalse(any(issue["code"] == "probe_failed" for issue in recorder.issues))

    async def test_probe_4xx_with_undocumented_shape_is_inconclusive(self) -> None:
        from app_probes import probe_spec, run_probe
        from transport import RequestError

        recorder = RunRecorder.bootstrap()
        spec = probe_spec("store_statistics")
        result_404 = self._http_result(
            recorder=recorder,
            action=spec.action,
            status_code=404,
            payload={"status": "error", "unexpected": True},
        )

        async def request_404(*args, **kwargs):
            raise RequestError("HTTP 404", event=result_404.event, result=result_404)

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=spec,
            context={"subentity_id": 7},
            token="store-token",
            token_source="test",
            request_func=request_404,
        )

        self.assertIsNotNone(result)
        self.assertEqual(recorder.decisions[-1]["status"], "inconclusive")
        self.assertEqual(recorder.decisions[-1]["reason_code"], "probe_schema_undocumented")
        self.assertFalse(any(issue["code"] == "probe_failed" for issue in recorder.issues))

    async def test_probe_5xx_is_failed(self) -> None:
        from app_probes import probe_spec, run_probe
        from transport import RequestError

        recorder = RunRecorder.bootstrap()
        spec = probe_spec("store_statistics")
        result_503 = self._http_result(
            recorder=recorder,
            action=spec.action,
            status_code=503,
            payload={"status": "error", "message": "service unavailable"},
        )

        async def request_503(*args, **kwargs):
            raise RequestError("HTTP 503", event=result_503.event, result=result_503)

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=spec,
            context={"subentity_id": 7},
            token="store-token",
            token_source="test",
            request_func=request_503,
        )

        self.assertIsNone(result)
        self.assertEqual(recorder.decisions[-1]["status"], "failed")
        self.assertEqual(recorder.decisions[-1]["reason_code"], "probe_http_server_error")
        self.assertTrue(any(issue["code"] == "probe_failed" for issue in recorder.issues))

    async def test_missing_probe_sample_is_skipped_and_requests_user_sample(self) -> None:
        from app_probes import ProbeSpec, run_probe

        recorder = RunRecorder.bootstrap()

        async def should_not_run(*args, **kwargs):  # pragma: no cover - defensive guard
            raise AssertionError("request function should not run when probe sample is missing")

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=ProbeSpec(
                name="undocumented_probe",
                actor="user",
                action="probe_undocumented",
                method="GET",
                base="lastmile",
                endpoint="/v1/unknown/",
            ),
            request_func=should_not_run,
        )

        self.assertIsNone(result)
        self.assertEqual(recorder.decisions[-1]["status"], "skipped")
        self.assertEqual(recorder.decisions[-1]["reason_code"], "missing_reference_sample")
        self.assertEqual(recorder.decisions[-1]["next_action"], "request_sample_from_user")
        self.assertTrue(any(issue["code"] == "probe_sample_needed" for issue in recorder.issues))


class ProbeContractIntegrityTests(unittest.TestCase):
    def test_probe_contract_references_only_allowed_docs(self) -> None:
        from session_probe_reference import contract_integrity_issues

        self.assertEqual(contract_integrity_issues(), [])

    def test_probe_preflight_requirements_have_source_attribution(self) -> None:
        from session_probe_reference import PROBE_CONTRACTS

        for probe_name, contract in PROBE_CONTRACTS.items():
            for requirement in contract.get("preflight") or ():
                self.assertTrue(
                    str(requirement.get("source_doc") or "").strip(),
                    msg=f"{probe_name} preflight requirement missing source_doc",
                )
                self.assertTrue(
                    str(requirement.get("source_phase") or "").strip(),
                    msg=f"{probe_name} preflight requirement missing source_phase",
                )


class WebsocketGateEnforcementTests(unittest.IsolatedAsyncioTestCase):
    async def test_gate_failure_is_bypassed_when_enforcement_is_off(self) -> None:
        import config
        import trace_runner

        class _FailingObserver:
            async def wait_for_order_status(self, **kwargs):
                raise RuntimeError("websocket_gate_timeout: status=pending")

        recorder = RunRecorder.bootstrap()
        previous = config.SIM_ENFORCE_WEBSOCKET_GATES
        try:
            config.SIM_ENFORCE_WEBSOCKET_GATES = False
            ok = await trace_runner._wait_for_ws_gate(
                _FailingObserver(),
                recorder=recorder,
                scenario="completed",
                step="wait_pending_before_store_decision",
                order_db_id=1,
                order_ref="#1",
                expected_status="pending",
                sources={"store_orders"},
                phase="precondition",
            )
        finally:
            config.SIM_ENFORCE_WEBSOCKET_GATES = previous

        self.assertTrue(ok)
        self.assertTrue(any(issue["severity"] == "warning" for issue in recorder.issues))
        self.assertTrue(any(event.get("action") == "websocket_gate_bypassed" for event in recorder.events))

    async def test_gate_failure_fails_when_enforcement_is_on(self) -> None:
        import config
        import trace_runner

        class _FailingObserver:
            async def wait_for_order_status(self, **kwargs):
                raise RuntimeError("websocket_gate_timeout: status=pending")

        recorder = RunRecorder.bootstrap()
        previous = config.SIM_ENFORCE_WEBSOCKET_GATES
        try:
            config.SIM_ENFORCE_WEBSOCKET_GATES = True
            ok = await trace_runner._wait_for_ws_gate(
                _FailingObserver(),
                recorder=recorder,
                scenario="completed",
                step="wait_pending_before_store_decision",
                order_db_id=1,
                order_ref="#1",
                expected_status="pending",
                sources={"store_orders"},
                phase="precondition",
            )
        finally:
            config.SIM_ENFORCE_WEBSOCKET_GATES = previous

        self.assertFalse(ok)
        self.assertTrue(any(issue["severity"] == "error" for issue in recorder.issues))


class PostOrderActionTests(unittest.TestCase):
    def test_review_payload_matches_user_app_shape(self) -> None:
        from post_order_actions import build_review_payload

        payload = build_review_payload(
            order_db_id=544,
            subentity={"id": 1, "name": "Store", "currency": "jpy"},
            rating=4,
            comment="Cool",
        )

        self.assertEqual(payload["subentity_id"], "1")
        self.assertEqual(payload["comment"], "Cool")
        self.assertEqual(payload["rating"], 4)
        self.assertEqual(payload["order"], 544)
        self.assertEqual(payload["subentity_metadata"]["name"], "Store")

    def test_post_order_specs_use_order_id_paths(self) -> None:
        from post_order_actions import receipt_endpoint, reorder_params

        self.assertEqual(receipt_endpoint(549), "/v1/core/generate-receipt/549/")
        self.assertEqual(reorder_params(549), {"order_id": "549"})

    def test_parse_reorder_cart_items_from_session_shape(self) -> None:
        from post_order_actions import build_reorder_order_payload, parse_reorder_cart_items
        from user_sim import UserFixtures

        payload = {
            "status": "success",
            "message": "Reorder successful",
            "data": [
                {
                    "id": 1,
                    "category": 1,
                    "subentity": 1,
                    "name": "Meal",
                    "price": 2.0,
                    "discount_price": 1.96,
                    "status": "available",
                    "quantity": 1,
                    "sides": [],
                }
            ],
        }
        items = parse_reorder_cart_items(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["_line_price"], 1.96)

        fixtures = UserFixtures(
            user_id=27,
            store={"id": 1, "name": "Cafe", "status": "open"},
            location={"id": 8},
            menu_items=[],
            currency="jpy",
        )
        recorder = RunRecorder.bootstrap()
        order_payload = build_reorder_order_payload(
            fixtures=fixtures,
            reorder_items=items,
            recorder=recorder,
            scenario="receipt_review_reorder_second",
            source_order_db_id=544,
        )
        self.assertIsNotNone(order_payload)
        assert order_payload is not None
        self.assertEqual(len(order_payload["menu"]), 1)
        self.assertEqual(order_payload["menu"][0]["quantity"], 1)
        self.assertEqual(order_payload["total_price"], 1.96)


class SavedCardsProbeTests(unittest.TestCase):
    def _result(self, payload: object) -> HttpResult:
        return HttpResult(
            response=httpx.Response(
                status_code=200,
                request=httpx.Request("GET", "https://example.test/v1/core/cards/"),
            ),
            payload=payload,
            event={"id": 1},
            latency_ms=10,
        )

    def test_empty_cards_list_from_session_is_passed(self) -> None:
        from app_probes import _validate_probe_response, probe_spec

        payload = {
            "status": "success",
            "message": "Cards retrieved successfully",
            "data": {
                "object": "list",
                "data": [],
                "has_more": False,
                "url": "/v1/customers/cus_UQ9ecHvtCOzchX/payment_methods",
            },
        }
        status, reason, message, _details = _validate_probe_response(
            probe_spec("saved_cards"),
            self._result(payload),
        )
        self.assertEqual(status, "passed")
        self.assertEqual(reason, "probe_response_ok")
        self.assertIn("documented sample variant", message)

    def test_nonempty_cards_from_session_passes_shape_check(self) -> None:
        from app_probes import _validate_probe_response, probe_spec

        payload = {
            "status": "success",
            "message": "Cards retrieved successfully",
            "data": {
                "object": "list",
                "data": [
                    {
                        "id": "pm_1TYBKgLfBn92UFOlfVRW4Gq0",
                        "object": "payment_method",
                    }
                ],
                "has_more": False,
                "url": "/v1/customers/cus_test/payment_methods",
            },
        }
        status, reason, _, _ = _validate_probe_response(
            probe_spec("saved_cards"),
            self._result(payload),
        )
        self.assertEqual(status, "passed")
        self.assertEqual(reason, "probe_response_ok")

    def test_malformed_cards_payload_is_inconclusive_not_no_content(self) -> None:
        from app_probes import _validate_probe_response, probe_spec

        status, reason, message, _ = _validate_probe_response(
            probe_spec("saved_cards"),
            self._result({}),
        )
        self.assertEqual(status, "inconclusive")
        self.assertEqual(reason, "probe_schema_undocumented")
        self.assertNotIn("no content", message.lower())

    def test_saved_cards_preflight_allows_missing_customer_id(self) -> None:
        from app_probes import _probe_preflight, probe_spec

        allowed, reason, _ = _probe_preflight(
            spec=probe_spec("saved_cards"),
            context={"user_id": 27, "currency": "jpy"},
            token="user-token",
            customer_id=None,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "preflight_passed")


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
    def test_bootstrap_includes_interaction_catalogue(self) -> None:
        recorder = RunRecorder.bootstrap()
        catalogue = recorder.config_snapshot["interaction_catalogue"]
        self.assertIn("menu_statuses", catalogue["store"])
        self.assertIn(MENU_SOLD_OUT, catalogue["store"]["menu_statuses"])

    def test_expected_status_mismatch_blocks_passed_scenario(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.start_scenario("completed", expected_final_status="completed")
        recorder.finish_scenario(
            "completed",
            verdict="passed",
            actual_final_status="payment_failed",
        )
        self.assertEqual(
            recorder._scenario_effective_verdict(recorder.scenarios["completed"]),
            "blocked",
        )

    def test_status_path_and_report_generation(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.set_fixtures(_fixtures())
        recorder.set_user_identity(user_id=13, name="Simulator User", phone="+2340000000000")
        recorder.set_store_identity(
            subentity_id=1,
            login_id="FZY_1",
            name="Test Store",
            branch="Main",
            phone="+2341111111111",
        )
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
        self.assertIn("Daily Doctor Summary", report)
        self.assertIn("Graphical Summary", report)
        self.assertIn("Bottlenecks", report)
        self.assertIn("Technical Trace", report)
        self.assertIn("Auth proof", report)
        self.assertIn("Scenario Verdicts", report)
        self.assertIn("Order Lifecycle", report)
        self.assertIn("Websocket Assertions", report)
        self.assertIn("Developer Findings", report)
        self.assertIn("| User | Store |", report)
        self.assertIn("Simulator User", report)
        self.assertIn("FZY_1", report)
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

    def test_decision_section_labels_informational_reasons_as_info(self) -> None:
        recorder = RunRecorder.bootstrap()
        recorder.record_decision(
            actor="user",
            action="probe_saved_cards",
            status="skipped",
            reason="no_customer_id",
            message="Saved cards were skipped because this user has no Stripe/customer ID.",
            reason_code="no_customer_id",
            reason_message="Saved cards were skipped because this user has no Stripe/customer ID.",
            next_action="skip_api_call",
            run_continued=True,
        )
        recorder.record_decision(
            actor="store",
            action="websocket_gate",
            status="failed",
            reason="websocket_gate_timeout",
            message="Websocket gate timed out.",
            reason_code="websocket_gate_timeout",
            reason_message="Websocket gate timed out.",
            next_action="abort_scenario",
            run_continued=False,
        )

        report = recorder._render_markdown()

        self.assertIn("info (skipped)", report)
        self.assertIn("| failed | websocket_gate |", report)

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


class LoadWorkerRuntimeTests(unittest.TestCase):
    def test_worker_counts_for_all_users_round_robin_distribution(self) -> None:
        from load_worker_assignment import summarize_worker_user_index_counts

        counts = summarize_worker_user_index_counts(
            all_users=True,
            worker_count=8,
            plan_user_count=3,
        )
        self.assertEqual(counts, {0: 3, 1: 3, 2: 2})

    def test_worker_counts_for_single_user_reuse(self) -> None:
        from load_worker_assignment import summarize_worker_user_index_counts

        counts = summarize_worker_user_index_counts(
            all_users=False,
            worker_count=5,
            plan_user_count=3,
        )
        self.assertEqual(counts, {0: 5})


class WebsocketStatusPrimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_status_ws_succeeds_after_primed_status(self) -> None:
        import user_sim

        queue: asyncio.Queue[str] = asyncio.Queue()
        user_sim._offer_ws_status(queue, "payment_processing")
        status = await user_sim.wait_for_status_ws(
            queue,
            expected_statuses={"payment_processing"},
            timeout_seconds=1.0,
        )
        self.assertEqual(status, "payment_processing")

    async def test_prime_ws_status_from_order_enqueues_current_status(self) -> None:
        import user_sim

        queue: asyncio.Queue[str] = asyncio.Queue()
        recorder = RunRecorder.bootstrap()
        with mock.patch.object(
            user_sim,
            "fetch_order",
            mock.AsyncMock(return_value={"status": "completed", "id": 42}),
        ):
            observed = await user_sim.prime_ws_status_from_order(
                httpx.AsyncClient(),
                queue,
                user_token="token",
                token_source="user_login_token",
                order_db_id=42,
                order_ref="#42",
                recorder=recorder,
            )
        self.assertEqual(observed, "completed")
        self.assertEqual(queue.get_nowait(), "completed")


class CliArgPrecedenceTests(unittest.TestCase):
    def test_explicit_trace_flags_not_overridden_by_flow_preset(self) -> None:
        sim_main = _load_simulate_entrypoint_module()
        config = sim_main.config
        tracked = (
            "SIM_FLOW",
            "SIM_RUN_MODE",
            "SIM_TRACE_SUITE",
            "SIM_TRACE_SCENARIOS",
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_STORE_EXPLICIT",
            "SIM_ACTORS",
        )
        previous = {name: getattr(config, name) for name in tracked}
        previous_store_from_cli = sim_main._store_from_cli
        previous_active_flow = sim_main._active_flow
        previous_argv = list(sim_main.sys.argv)
        original_loader = config.load_sim_actors
        actors = {
            "defaults": {},
            "users": [{"phone": "+15550000001", "role": "returning", "lat": 35.1, "lng": 136.9}],
            "stores": [{"store_id": "FZY_1", "subentity_id": 7, "lat": 35.1, "lng": 136.9}],
        }

        def fake_load_sim_actors(*_args, **_kwargs):
            config.SIM_ACTORS = actors
            return actors

        config.load_sim_actors = fake_load_sim_actors
        try:
            config.USER_PHONE_NUMBER = "+15550000001"
            config.STORE_ID = "FZY_1"
            config.SIM_TRACE_SUITE = "core"
            config.SIM_TRACE_SCENARIOS = []
            sim_main.sys.argv = [
                "simulate",
                "full",
                "--mode",
                "trace",
                "--suite",
                "full",
                "--scenario",
                "completed",
                "--scenario",
                "rejected",
                "--scenario",
                "cancelled",
                "--scenario",
                "auto_cancel",
                "--phone",
                "+15550000001",
                "--store",
                "FZY_1",
            ]
            args = types.SimpleNamespace(
                flow="full",
                mode="trace",
                suite="full",
                scenario=["completed", "rejected", "cancelled", "auto_cancel"],
                timing="fast",
                users=1,
                interval=30.0,
                reject=0.1,
                orders=1,
                continuous=False,
                phone="+15550000001",
                store="FZY_1",
                all_users=False,
                plan=None,
                strict_plan=False,
                skip_app_probes=False,
                skip_store_dashboard_probes=False,
                post_order_actions=False,
                enforce_websocket_gates=None,
                no_auto_provision=False,
                bounded_load_smoke_policy=False,
                bounded_baseline_min_completed=1,
                bounded_baseline_max_attempts=3,
                bounded_tail_reject_rate=None,
                bounded_tail_cancel_rate=0.0,
            )
            sim_main._apply_args(args)
            self.assertEqual(config.SIM_FLOW, "full")
            self.assertEqual(config.SIM_RUN_MODE, "trace")
            self.assertEqual(config.SIM_TRACE_SUITE, "full")
            self.assertEqual(
                config.SIM_TRACE_SCENARIOS,
                ["completed", "rejected", "cancelled", "auto_cancel"],
            )
        finally:
            config.load_sim_actors = original_loader
            sim_main.sys.argv = previous_argv
            sim_main._store_from_cli = previous_store_from_cli
            sim_main._active_flow = previous_active_flow
            for name, value in previous.items():
                setattr(config, name, value)

    def test_explicit_mode_override_not_replaced_by_flow_default(self) -> None:
        sim_main = _load_simulate_entrypoint_module()
        config = sim_main.config
        tracked = (
            "SIM_FLOW",
            "SIM_RUN_MODE",
            "SIM_TRACE_SUITE",
            "SIM_TRACE_SCENARIOS",
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_STORE_EXPLICIT",
            "SIM_ACTORS",
        )
        previous = {name: getattr(config, name) for name in tracked}
        previous_store_from_cli = sim_main._store_from_cli
        previous_active_flow = sim_main._active_flow
        previous_argv = list(sim_main.sys.argv)
        original_loader = config.load_sim_actors
        actors = {
            "defaults": {},
            "users": [{"phone": "+15550000001", "role": "returning", "lat": 35.1, "lng": 136.9}],
            "stores": [{"store_id": "FZY_1", "subentity_id": 7, "lat": 35.1, "lng": 136.9}],
        }

        def fake_load_sim_actors(*_args, **_kwargs):
            config.SIM_ACTORS = actors
            return actors

        config.load_sim_actors = fake_load_sim_actors
        try:
            config.USER_PHONE_NUMBER = "+15550000001"
            config.STORE_ID = "FZY_1"
            sim_main.sys.argv = [
                "simulate",
                "full",
                "--mode",
                "load",
                "--phone",
                "+15550000001",
                "--store",
                "FZY_1",
            ]
            args = types.SimpleNamespace(
                flow="full",
                mode="load",
                suite=None,
                scenario=None,
                timing="fast",
                users=1,
                interval=30.0,
                reject=0.1,
                orders=1,
                continuous=False,
                phone="+15550000001",
                store="FZY_1",
                all_users=False,
                plan=None,
                strict_plan=False,
                skip_app_probes=False,
                skip_store_dashboard_probes=False,
                post_order_actions=False,
                enforce_websocket_gates=None,
                no_auto_provision=False,
                bounded_load_smoke_policy=False,
                bounded_baseline_min_completed=1,
                bounded_baseline_max_attempts=3,
                bounded_tail_reject_rate=None,
                bounded_tail_cancel_rate=0.0,
            )
            sim_main._apply_args(args)
            self.assertEqual(config.SIM_FLOW, "full")
            self.assertEqual(config.SIM_RUN_MODE, "load")
        finally:
            config.load_sim_actors = original_loader
            sim_main.sys.argv = previous_argv
            sim_main._store_from_cli = previous_store_from_cli
            sim_main._active_flow = previous_active_flow
            for name, value in previous.items():
                setattr(config, name, value)

    def test_cli_no_random_flags_disable_default_randomization(self) -> None:
        sim_main = _load_simulate_entrypoint_module()
        config = sim_main.config
        tracked = (
            "SIM_DISABLE_RANDOM_PHONE",
            "SIM_DISABLE_RANDOM_STORE",
            "SIM_FLOW",
            "SIM_RUN_MODE",
            "USER_PHONE_NUMBER",
            "STORE_ID",
            "SIM_PHONE_EXPLICIT",
            "SIM_STORE_EXPLICIT",
            "SIM_ACTORS",
        )
        previous = {name: getattr(config, name) for name in tracked}
        previous_store_from_cli = sim_main._store_from_cli
        previous_phone_from_cli = getattr(sim_main, "_phone_from_cli", False)
        previous_active_flow = sim_main._active_flow
        previous_argv = list(sim_main.sys.argv)
        original_loader = config.load_sim_actors
        actors = {
            "defaults": {},
            "users": [{"phone": "+15550000001", "role": "returning", "lat": 35.1, "lng": 136.9}],
            "stores": [{"store_id": "FZY_1", "subentity_id": 7, "lat": 35.1, "lng": 136.9}],
        }

        def fake_load_sim_actors(*_args, **_kwargs):
            config.SIM_ACTORS = actors
            return actors

        config.load_sim_actors = fake_load_sim_actors
        try:
            config.USER_PHONE_NUMBER = "+15550000001"
            config.STORE_ID = "FZY_1"
            sim_main.sys.argv = [
                "simulate",
                "doctor",
                "--phone",
                "+15550000001",
                "--store",
                "FZY_1",
                "--no-random-phone",
                "--no-random-store",
            ]
            args = types.SimpleNamespace(
                flow="doctor",
                mode="trace",
                suite=None,
                scenario=None,
                timing="fast",
                users=1,
                interval=30.0,
                reject=0.1,
                orders=1,
                continuous=False,
                phone="+15550000001",
                store="FZY_1",
                all_users=False,
                plan=None,
                strict_plan=False,
                skip_app_probes=False,
                skip_store_dashboard_probes=False,
                post_order_actions=False,
                enforce_websocket_gates=None,
                no_auto_provision=False,
                no_random_phone=True,
                no_random_store=True,
                bounded_load_smoke_policy=False,
                bounded_baseline_min_completed=1,
                bounded_baseline_max_attempts=3,
                bounded_tail_reject_rate=None,
                bounded_tail_cancel_rate=0.0,
            )
            sim_main._apply_args(args)
            self.assertTrue(config.SIM_DISABLE_RANDOM_PHONE)
            self.assertTrue(config.SIM_DISABLE_RANDOM_STORE)
        finally:
            config.load_sim_actors = original_loader
            sim_main.sys.argv = previous_argv
            sim_main._store_from_cli = previous_store_from_cli
            sim_main._phone_from_cli = previous_phone_from_cli
            sim_main._active_flow = previous_active_flow
            for name, value in previous.items():
                setattr(config, name, value)


class LoadModeTimingTests(unittest.TestCase):
    def test_fast_timing_profile_uses_sub_second_delays(self) -> None:
        from scenarios import resolve_timing_profile

        fast = resolve_timing_profile("fast")
        self.assertLessEqual(fast.store_decision_delay.max_seconds, 1.0)
        self.assertLessEqual(fast.store_prep_delay.max_seconds, 1.0)
        for status in (
            "enroute_pickup",
            "robot_arrived_for_pickup",
            "enroute_delivery",
            "robot_arrived_for_delivery",
            "completed",
        ):
            self.assertLessEqual(fast.robot_delays[status].max_seconds, 1.0)

    def test_robot_lifecycle_statuses_have_timing_entries(self) -> None:
        import robot_sim
        from scenarios import resolve_timing_profile

        realistic = resolve_timing_profile("realistic")
        for status in robot_sim.ROBOT_LIFECYCLE:
            self.assertIn(status, realistic.robot_delays)


class InteractionCatalogueTests(unittest.TestCase):
    def test_menu_add_to_cart_rules(self) -> None:
        self.assertTrue(
            user_can_add_menu_item(MENU_AVAILABLE, store_is_open=True)
        )
        self.assertFalse(
            user_can_add_menu_item(MENU_UNAVAILABLE, store_is_open=True)
        )
        self.assertFalse(user_can_add_menu_item(MENU_SOLD_OUT, store_is_open=True))
        self.assertFalse(user_can_add_menu_item(MENU_AVAILABLE, store_is_open=False))
        self.assertEqual(
            user_menu_block_reason(MENU_UNAVAILABLE, store_is_open=True),
            "item_sold_out_or_unavailable",
        )
        self.assertTrue(store_counts_menu_available("1"))
        self.assertFalse(user_can_add_menu_item("1", store_is_open=True))

    def test_requested_trace_scenarios_resolve(self) -> None:
        resolved = resolve_trace_scenarios(suite="audit", scenarios=None)
        self.assertIn("new_user_setup", resolved)
        self.assertIn("returning_free_with_coupon", resolved)
        self.assertIn("menu_sold_out", resolved)
        self.assertIn("store_first_setup", resolved)
        self.assertIn("robot_complete", resolved)

    def test_simple_flow_aliases_resolve(self) -> None:
        self.assertEqual(
            resolve_flow("paid")["scenarios"],
            ["returning_paid_no_coupon"],
        )
        self.assertEqual(resolve_flow("free")["payment_mode"], "free")
        self.assertEqual(resolve_flow("store_setup")["name"], "store-setup")
        self.assertEqual(resolve_flow("doctor")["suite"], "doctor")
        self.assertEqual(
            resolve_flow("receipt-review")["scenarios"],
            ["receipt_review_reorder"],
        )
        self.assertEqual(resolve_flow("ronot-complete")["name"], "robot-complete")


class MenusFlowProvisioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_menus_flow_creates_new_menu_item_before_probes(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim

        recorder = RunRecorder.bootstrap()
        calls: list[str] = []
        user_session = user_sim.UserSession(
            token="user-token",
            user_id=13,
            user={"id": 13},
            token_source="test",
        )
        store_session = store_sim.StoreSession(
            last_mile_token="store-token",
            fainzy_token=None,
            subentity={"id": 7, "setup": True},
            store_id=7,
            token_source="test",
        )
        refreshed_fixtures = _fixtures()

        async def fake_ensure_store_setup(*args, **kwargs):
            calls.append("ensure_store_setup")
            return True

        async def fake_open_store(*args, **kwargs):
            calls.append("open_store")
            return 1

        async def fake_fetch_categories(*args, **kwargs):
            calls.append("fetch_categories")
            return [{"id": 11, "name": "Drinks"}]

        async def fake_create_menu(*args, **kwargs):
            calls.append("create_menu")
            return {"id": 99, "name": kwargs.get("name"), "status": "available"}

        async def fake_bootstrap_fixtures(*args, **kwargs):
            calls.append("bootstrap_fixtures")
            return refreshed_fixtures

        originals = (
            store_sim.ensure_store_setup,
            store_sim.open_store_for_simulation,
            store_sim.fetch_categories,
            store_sim.create_menu,
            user_sim.bootstrap_fixtures,
        )
        store_sim.ensure_store_setup = fake_ensure_store_setup
        store_sim.open_store_for_simulation = fake_open_store
        store_sim.fetch_categories = fake_fetch_categories
        store_sim.create_menu = fake_create_menu
        user_sim.bootstrap_fixtures = fake_bootstrap_fixtures
        try:
            result = await trace_runner._provision_menus_flow_inventory(
                object(),
                store_session=store_session,
                user_session=user_session,
                recorder=recorder,
            )
        finally:
            (
                store_sim.ensure_store_setup,
                store_sim.open_store_for_simulation,
                store_sim.fetch_categories,
                store_sim.create_menu,
                user_sim.bootstrap_fixtures,
            ) = originals

        self.assertIs(result, refreshed_fixtures)
        self.assertEqual(
            calls,
            [
                "ensure_store_setup",
                "open_store",
                "fetch_categories",
                "create_menu",
                "bootstrap_fixtures",
            ],
        )
        create_events = [
            event
            for event in recorder.events
            if event.get("action") == "menus_run_item_created"
        ]
        self.assertEqual(len(create_events), 1)
        self.assertEqual(create_events[0]["details"]["menu_id"], 99)

    def test_is_menus_flow_run_detects_menus_suite(self) -> None:
        import trace_runner

        self.assertTrue(
            trace_runner._is_menus_flow_run(
                ["menu_available", "menu_unavailable", "menu_sold_out", "menu_store_closed"]
            )
        )
        self.assertFalse(trace_runner._is_menus_flow_run(["menu_available", "completed"]))


class FlowReliabilityPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_coupon_retry_skips_api_fault_store_and_continues(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim
        from scenarios import resolve_timing_profile
        from store_sim import HttpApiError

        recorder = RunRecorder.bootstrap()
        calls: list[str] = []
        previous = (
            config.SIM_FAILURE_POLICY,
            config.SIM_PREFLIGHT_STRATEGY,
            config.SIM_STORE_EXPLICIT,
            config.SIM_COUPON_ID,
            getattr(config, "SIM_ACTORS", None),
        )
        original_ensure = trace_runner._ensure_coupon_for_scenario
        original_candidates = trace_runner._trace_store_candidates
        original_store_auth = trace_runner._bootstrap_store_auth
        original_fixtures = trace_runner.user_sim.bootstrap_fixtures
        original_run_completed = trace_runner._run_completed
        attempt = {"count": 0}

        async def fake_ensure_coupon(*args, **kwargs):
            attempt["count"] += 1
            if attempt["count"] >= 2:
                config.SIM_COUPON_ID = 301
                return True
            return False

        def fake_candidates():
            return ["FZY_BAD", "FZY_GOOD"]

        async def fake_store_auth(client, recorder, store_id=None):
            if store_id == "FZY_BAD":
                raise HttpApiError(
                    url="https://example.test/v1/entities/store/login",
                    status_code=500,
                    response_text="server error",
                )
            return store_sim.StoreSession(
                last_mile_token="store-token",
                fainzy_token=None,
                subentity={"id": 2, "setup": True},
                store_id=2,
                token_source="test",
                store_login_id="FZY_GOOD",
            )

        async def fake_fixtures(*args, **kwargs):
            calls.append(str(kwargs.get("subentity_id")))
            return _fixtures()

        async def fake_run_completed(*args, **kwargs):
            calls.append("completed")

        config.SIM_FAILURE_POLICY = "api_only"
        config.SIM_PREFLIGHT_STRATEGY = "auto_recover"
        config.SIM_STORE_EXPLICIT = False
        config.SIM_COUPON_ID = None
        config.SIM_ACTORS = {
            "stores": [{"store_id": "FZY_BAD"}, {"store_id": "FZY_GOOD"}],
            "users": [{"phone": "+100"}],
        }
        trace_runner._ensure_coupon_for_scenario = fake_ensure_coupon
        trace_runner._trace_store_candidates = fake_candidates
        trace_runner._bootstrap_store_auth = fake_store_auth
        trace_runner.user_sim.bootstrap_fixtures = fake_fixtures
        trace_runner._run_completed = fake_run_completed
        try:
            await trace_runner._run_payment_scenario(
                object(),
                scenario="returning_paid_with_coupon",
                user_session=user_sim.UserSession(
                    token="user-token",
                    user_id=13,
                    user={"id": 13},
                    token_source="test",
                ),
                store_session=store_sim.StoreSession(
                    last_mile_token="store-token",
                    fainzy_token=None,
                    subentity={"id": 1, "setup": True},
                    store_id=1,
                    token_source="test",
                    store_login_id="FZY_PRIMARY",
                ),
                fixtures=_fixtures(),
                recorder=recorder,
                timing=resolve_timing_profile("fast"),
                observer=None,
            )
        finally:
            trace_runner._ensure_coupon_for_scenario = original_ensure
            trace_runner._trace_store_candidates = original_candidates
            trace_runner._bootstrap_store_auth = original_store_auth
            trace_runner.user_sim.bootstrap_fixtures = original_fixtures
            trace_runner._run_completed = original_run_completed
            (
                config.SIM_FAILURE_POLICY,
                config.SIM_PREFLIGHT_STRATEGY,
                config.SIM_STORE_EXPLICIT,
                config.SIM_COUPON_ID,
                config.SIM_ACTORS,
            ) = previous

        api_issues = [
            item
            for item in recorder.issues
            if item.get("code") == "coupon_retry_store_api_error"
        ]
        self.assertEqual(len(api_issues), 1)
        self.assertEqual(api_issues[0]["failure_class"], "api_fault")
        self.assertIn("completed", calls)

    async def test_coupon_exhaustion_finishes_unsupported_without_raise(self) -> None:
        import config
        import trace_runner
        import user_sim
        import store_sim
        from scenarios import resolve_timing_profile

        recorder = RunRecorder.bootstrap()
        previous = (
            config.SIM_FAILURE_POLICY,
            config.SIM_PREFLIGHT_STRATEGY,
            config.SIM_STORE_EXPLICIT,
            config.SIM_COUPON_ID,
        )
        original_ensure = trace_runner._ensure_coupon_for_scenario

        async def fake_ensure_coupon(*args, **kwargs):
            return False

        config.SIM_FAILURE_POLICY = "api_only"
        config.SIM_PREFLIGHT_STRATEGY = "auto_recover"
        config.SIM_STORE_EXPLICIT = True
        config.SIM_COUPON_ID = None
        trace_runner._ensure_coupon_for_scenario = fake_ensure_coupon
        try:
            await trace_runner._run_payment_scenario(
                object(),
                scenario="returning_paid_with_coupon",
                user_session=user_sim.UserSession(
                    token="user-token",
                    user_id=13,
                    user={"id": 13},
                    token_source="test",
                ),
                store_session=store_sim.StoreSession(
                    last_mile_token="store-token",
                    fainzy_token=None,
                    subentity={"id": 7, "setup": True},
                    store_id=7,
                    token_source="test",
                ),
                fixtures=_fixtures(),
                recorder=recorder,
                timing=resolve_timing_profile("fast"),
                observer=None,
            )
        finally:
            trace_runner._ensure_coupon_for_scenario = original_ensure
            (
                config.SIM_FAILURE_POLICY,
                config.SIM_PREFLIGHT_STRATEGY,
                config.SIM_STORE_EXPLICIT,
                config.SIM_COUPON_ID,
            ) = previous

        scenario = recorder.scenarios["returning_paid_with_coupon"]
        self.assertEqual(scenario["base_verdict"], "unsupported")
        self.assertEqual(scenario["actual_final_status"], "coupon_missing")
        self.assertIn("coupon", scenario.get("note", "").lower())

    def test_new_user_already_setup_marks_unsupported(self) -> None:
        import trace_runner
        import user_sim

        recorder = RunRecorder.bootstrap()
        trace_runner._run_new_user_setup(
            user_session=user_sim.UserSession(
                token="user-token",
                user_id=13,
                user={"id": 13, "email": "existing@example.com"},
                token_source="user_cached_token",
            ),
            fixtures=_fixtures(),
            recorder=recorder,
        )
        scenario = recorder.scenarios["new_user_setup"]
        self.assertEqual(scenario["base_verdict"], "unsupported")
        self.assertEqual(scenario["actual_final_status"], "account_already_setup")
        issue = next(item for item in recorder.issues if item.get("code") == "new_user_not_created")
        self.assertEqual(issue["failure_class"], "precondition")

    async def test_otp_retry_records_precondition_decision_and_continues(self) -> None:
        import config
        import user_sim
        from user_sim import HttpApiError

        recorder = RunRecorder.bootstrap()
        previous_phone = getattr(config, "USER_PHONE_NUMBER", None)
        previous_token = getattr(config, "USER_LASTMILE_TOKEN", None)
        verify_calls = {"count": 0}

        async def fake_auth_request(client, *, recorder=None, action=None, **kwargs):
            if action == "request_user_otp":
                return {"data": "123456"}
            if action == "verify_user_otp":
                verify_calls["count"] += 1
                if verify_calls["count"] == 1:
                    raise HttpApiError(
                        url="https://example.test/v1/auth/otp/verify/",
                        status_code=400,
                        response_text='{"detail":"invalid otp"}',
                    )
                return {
                    "data": {
                        "setup_complete": True,
                        "is_active": True,
                        "user": {"id": 99},
                    }
                }
            if action == "fetch_user_token":
                return {"data": {"token": "fresh-token", "user": {"id": 99}}}
            raise AssertionError(f"unexpected action {action}")

        config.USER_PHONE_NUMBER = "+2348000000099"
        config.USER_LASTMILE_TOKEN = None
        try:
            with mock.patch.object(user_sim, "_auth_request", fake_auth_request):
                session = await user_sim.bootstrap_auth(object(), recorder, scenario="completed")
        finally:
            if previous_phone is None:
                delattr(config, "USER_PHONE_NUMBER")
            else:
                config.USER_PHONE_NUMBER = previous_phone
            if previous_token is None:
                delattr(config, "USER_LASTMILE_TOKEN")
            else:
                config.USER_LASTMILE_TOKEN = previous_token

        self.assertEqual(verify_calls["count"], 2)
        self.assertEqual(session.token, "fresh-token")
        retry_decisions = [
            item
            for item in recorder.decisions
            if item.get("reason_code") == "otp_retry_after_invalid_or_expired"
        ]
        self.assertEqual(len(retry_decisions), 1)
        self.assertEqual(retry_decisions[0]["failure_class"], "precondition")
        self.assertTrue(retry_decisions[0]["run_continued"])

    def test_artifact_write_preserves_failure_class_and_policy(self) -> None:
        import config
        import json

        previous_policy = config.SIM_FAILURE_POLICY
        config.SIM_FAILURE_POLICY = "api_only"
        recorder = RunRecorder.bootstrap()
        recorder.record_issue(
            severity="warning",
            code="coupon_required",
            message="coupon missing",
            failure_class="precondition",
            scenario="returning_paid_with_coupon",
        )
        recorder.record_decision(
            action="retry_coupon_with_alternate_store",
            status="called",
            reason="coupon_missing_try_next_store",
            message="trying next store",
            failure_class="precondition",
            scenario="returning_paid_with_coupon",
        )
        recorder.start_scenario("returning_paid_with_coupon")
        recorder.finish_scenario(
            "returning_paid_with_coupon",
            verdict="unsupported",
            actual_final_status="coupon_missing",
        )
        try:
            events_path, report_path, _story_path = recorder.write()
            payload = json.loads(events_path.read_text(encoding="utf-8"))
            report_text = report_path.read_text(encoding="utf-8")
        finally:
            config.SIM_FAILURE_POLICY = previous_policy

        self.assertEqual(payload["run"]["config"]["failure_policy"], "api_only")
        self.assertEqual(payload["issues"][0]["failure_class"], "precondition")
        self.assertEqual(payload["decisions"][0]["failure_class"], "precondition")
        self.assertIn("DEGRADED", report_text.upper())

    def test_health_summary_strict_fails_on_precondition_error(self) -> None:
        from health import build_health_summary

        summary = build_health_summary(
            duration_ms=100,
            scenarios=[{"name": "menus", "effective_verdict": "degraded"}],
            orders=[],
            events=[],
            issues=[
                {
                    "severity": "error",
                    "failure_class": "precondition",
                    "code": "menu_missing",
                }
            ],
            failure_policy="strict",
        )
        self.assertEqual(summary["verdict"], "failed")

    async def test_bootstrap_precondition_degrades_in_api_only(self) -> None:
        import config
        import trace_runner
        import user_sim

        recorder = RunRecorder.bootstrap()
        previous_policy = config.SIM_FAILURE_POLICY
        previous_preflight = config.SIM_PREFLIGHT_STRATEGY
        config.SIM_FAILURE_POLICY = "api_only"
        config.SIM_PREFLIGHT_STRATEGY = "auto_recover"

        async def failing_auth(*args, **kwargs):
            raise RuntimeError("fixtures unavailable for planned store")

        originals = trace_runner.user_sim.bootstrap_auth
        trace_runner.user_sim.bootstrap_auth = failing_auth
        try:
            await trace_runner.run(
                recorder=recorder,
                suite=None,
                scenarios=["menu_available"],
                timing_profile="fast",
            )
        finally:
            trace_runner.user_sim.bootstrap_auth = originals
            config.SIM_FAILURE_POLICY = previous_policy
            config.SIM_PREFLIGHT_STRATEGY = previous_preflight

        bootstrap_issues = [
            item for item in recorder.issues if item.get("code") == "trace_bootstrap_precondition"
        ]
        self.assertEqual(len(bootstrap_issues), 1)
        self.assertEqual(bootstrap_issues[0]["failure_class"], "precondition")
        scenario = recorder.scenarios["menu_available"]
        self.assertEqual(scenario["base_verdict"], "unsupported")

    async def test_bootstrap_api_fault_still_raises_in_api_only(self) -> None:
        import config
        import trace_runner

        recorder = RunRecorder.bootstrap()
        previous_policy = config.SIM_FAILURE_POLICY
        previous_preflight = config.SIM_PREFLIGHT_STRATEGY
        config.SIM_FAILURE_POLICY = "api_only"
        config.SIM_PREFLIGHT_STRATEGY = "auto_recover"

        async def failing_auth(*args, **kwargs):
            raise RuntimeError("connection timed out during bootstrap")

        originals = trace_runner.user_sim.bootstrap_auth
        trace_runner.user_sim.bootstrap_auth = failing_auth
        try:
            with self.assertRaises(RuntimeError):
                await trace_runner.run(
                    recorder=recorder,
                    suite=None,
                    scenarios=["menu_available"],
                    timing_profile="fast",
                )
        finally:
            trace_runner.user_sim.bootstrap_auth = originals
            config.SIM_FAILURE_POLICY = previous_policy
            config.SIM_PREFLIGHT_STRATEGY = previous_preflight

    async def test_bootstrap_failure_raises_in_strict_mode(self) -> None:
        import config
        import trace_runner

        recorder = RunRecorder.bootstrap()
        previous_policy = config.SIM_FAILURE_POLICY
        previous_preflight = config.SIM_PREFLIGHT_STRATEGY
        config.SIM_FAILURE_POLICY = "strict"
        config.SIM_PREFLIGHT_STRATEGY = "hard_stop"

        async def failing_auth(*args, **kwargs):
            raise RuntimeError("fixtures unavailable for planned store")

        originals = trace_runner.user_sim.bootstrap_auth
        trace_runner.user_sim.bootstrap_auth = failing_auth
        try:
            with self.assertRaises(RuntimeError):
                await trace_runner.run(
                    recorder=recorder,
                    suite=None,
                    scenarios=["menu_available"],
                    timing_profile="fast",
                )
        finally:
            trace_runner.user_sim.bootstrap_auth = originals
            config.SIM_FAILURE_POLICY = previous_policy
            config.SIM_PREFLIGHT_STRATEGY = previous_preflight


if __name__ == "__main__":
    unittest.main()
