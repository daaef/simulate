import pathlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

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


class RunPlanTests(unittest.TestCase):
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

        self.assertEqual(store_login_calls, ["FZY_BAD", "FZY_GOOD"])
        self.assertEqual(recorder.fixtures_summary["store"]["id"], 2)


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

    def test_ascii_bar_uses_proportional_width(self) -> None:
        from health import ascii_bar

        self.assertEqual(ascii_bar(5, maximum=10, width=10), "#####-----")
        self.assertEqual(ascii_bar(0, maximum=0, width=6), "------")


class AppProbeTests(unittest.IsolatedAsyncioTestCase):
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
        from app_probes import ProbeSpec, run_probe
        from transport import RequestError

        recorder = RunRecorder.bootstrap()

        async def failing_request(*args, **kwargs):
            event = recorder.record_event(
                actor="probe",
                action="failing_probe",
                category="probe",
                ok=False,
                track_order=False,
            )
            raise RequestError("boom", event=event)

        result = await run_probe(
            object(),
            recorder=recorder,
            spec=ProbeSpec(
                name="failing_probe",
                actor="user",
                action="failing_probe",
                method="GET",
                base="lastmile",
                endpoint="/v1/example/",
            ),
            request_func=failing_request,
        )

        self.assertIsNone(result)
        self.assertEqual(recorder.issues[0]["code"], "probe_failed")
        self.assertIn("failing_probe", recorder.issues[0]["message"])


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


if __name__ == "__main__":
    unittest.main()
