from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock
from io import BytesIO
from urllib import error as urllib_error

from fastapi import HTTPException

from api.app.orders import routes, service


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OrdersServiceTests(unittest.TestCase):
    def test_list_stores_reads_default_and_stores_from_sim_actors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = pathlib.Path(tmpdir) / "sim_actors.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "defaults": {"store_id": "FZY_DEFAULT"},
                        "stores": [
                            {
                                "store_id": "FZY_DEFAULT",
                                "subentity_id": 7,
                                "name": "Default Store",
                                "branch": "Main",
                                "currency": "jpy",
                            },
                            {
                                "store_id": "FZY_OTHER",
                                "subentity_id": 6,
                                "name": "Other Store",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(service, "_sim_actors_path", return_value=plan_path):
                payload = service.list_stores()

        self.assertEqual(payload["default_store_id"], "FZY_DEFAULT")
        self.assertEqual([item["store_id"] for item in payload["stores"]], ["FZY_DEFAULT", "FZY_OTHER"])
        self.assertTrue(payload["stores"][0]["is_default"])
        self.assertFalse(payload["stores"][1]["is_default"])

    def test_login_store_uses_product_auth_token_for_lastmile_and_extracts_session(self) -> None:
        seen: list[dict[str, object]] = []

        def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
            entry = {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "timeout": timeout,
            }
            if request.data:
                entry["body"] = json.loads(request.data.decode("utf-8"))
            seen.append(entry)
            if "/v1/biz/product/authentication/" in request.full_url:
                return _FakeResponse({"data": "lastmile-token"})
            return _FakeResponse(
                {
                    "data": {
                        "token": "store-profile-token",
                        "subentity": {
                            "id": 7,
                            "name": "Ask Me",
                            "branch": "Jos",
                            "currency": "jpy",
                        },
                    }
                }
            )

        with mock.patch.object(service.urllib_request, "urlopen", side_effect=fake_urlopen):
            payload = service.login_store("fzy_926025")

        self.assertEqual(payload["token"], "lastmile-token")
        self.assertEqual(payload["store_profile_token"], "store-profile-token")
        self.assertEqual(payload["store_id"], "FZY_926025")
        self.assertEqual(payload["subentity_id"], 7)
        self.assertEqual(payload["store_name"], "Ask Me")
        self.assertIn("/v1/biz/product/authentication/", str(seen[0]["url"]))
        self.assertIn("product=rds", str(seen[0]["url"]))
        self.assertEqual(seen[1]["body"], {"store_id": "FZY_926025"})
        self.assertEqual(seen[1]["headers"].get("Store-request"), "FZY_926025")
        self.assertIn("Fainzy-Simulator", str(seen[1]["headers"].get("User-agent", "")))
        self.assertIn("/v1/entities/store/login", str(seen[1]["url"]))

    def test_fetch_by_query_falls_back_from_numeric_id_to_numeric_reference(self) -> None:
        with (
            mock.patch.object(service, "fetch_by_numeric_id", return_value=None) as fetch_id,
            mock.patch.object(service, "fetch_by_reference", return_value={"id": 42, "order_id": "#156382"}) as fetch_ref,
        ):
            order = service.fetch_by_query("156382", token="store-token", subentity_id=7)

        self.assertEqual(order, {"id": 42, "order_id": "#156382"})
        fetch_id.assert_called_once_with(156382, token="store-token")
        fetch_ref.assert_called_once_with("#156382", token="store-token", subentity_id=7)

    def test_fetch_by_query_uses_reference_for_hash_input(self) -> None:
        with (
            mock.patch.object(service, "fetch_by_numeric_id") as fetch_id,
            mock.patch.object(service, "fetch_by_reference", return_value={"id": 42, "order_id": "#156382"}) as fetch_ref,
        ):
            order = service.fetch_by_query("#156382", token="store-token", subentity_id=7)

        self.assertEqual(order, {"id": 42, "order_id": "#156382"})
        fetch_id.assert_not_called()
        fetch_ref.assert_called_once_with("#156382", token="store-token", subentity_id=7)

    def test_update_status_sends_fainzy_token_header(self) -> None:
        seen: dict[str, object] = {}

        def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
            seen["url"] = request.full_url
            seen["headers"] = dict(request.header_items())
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["method"] = request.get_method()
            return _FakeResponse({"ok": True})

        with mock.patch.object(service.urllib_request, "urlopen", side_effect=fake_urlopen):
            service.update_status(1850, "ready", token="store-token")

        self.assertEqual(seen["method"], "PATCH")
        self.assertEqual(seen["headers"].get("Fainzy-token"), "store-token")
        self.assertEqual(seen["body"], {"status": "ready"})
        self.assertIn("order_id=1850", str(seen["url"]))


class OrdersRoutesTests(unittest.TestCase):
    def test_store_login_maps_upstream_auth_failure_to_store_login_error(self) -> None:
        blocked = urllib_error.HTTPError(
            url="https://fainzy.tech/v1/entities/store/login",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )

        with mock.patch.object(service, "login_store", side_effect=blocked):
            with self.assertRaises(HTTPException) as raised:
                routes.login_store(
                    routes.StoreLoginRequest(store_id="FZY_926025"),
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("Store login", str(raised.exception.detail))
        self.assertNotIn("token was rejected", str(raised.exception.detail))

    def test_lookup_order_requires_fainzy_token(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            routes.lookup_order(
                query="156382",
                subentity_id=7,
                x_fainzy_token=None,
                current_user={"role": "operator"},
            )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("Fainzy token", str(raised.exception.detail))

    def test_lookup_order_missing_result_mentions_selected_store(self) -> None:
        with mock.patch.object(service, "fetch_by_query", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="#164235",
                    subentity_id=7,
                    x_fainzy_token="store-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 404)
        detail = str(raised.exception.detail)
        self.assertIn("selected store", detail.lower())
        self.assertIn("owns this order", detail.lower())

    def test_lookup_order_maps_stale_token_to_auth_error(self) -> None:
        stale = urllib_error.HTTPError(
            url="https://lastmile.fainzy.tech/v1/core/orders/",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with mock.patch.object(service, "fetch_by_query", side_effect=stale):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="156382",
                    subentity_id=7,
                    x_fainzy_token="stale-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("sign in again", str(raised.exception.detail).lower())

    def test_lookup_order_maps_lastmile_invalid_token_400_to_auth_error(self) -> None:
        invalid = urllib_error.HTTPError(
            url="https://lastmile.fainzy.tech/v1/core/orders/",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"status":"error","message":"please provide a valid token"}'),
        )

        with mock.patch.object(service, "fetch_by_query", side_effect=invalid):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="#164235",
                    subentity_id=7,
                    x_fainzy_token="store-profile-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("sign in again", str(raised.exception.detail).lower())

    def test_lookup_order_maps_lastmile_invalid_reference_400_to_not_found(self) -> None:
        bad_reference = urllib_error.HTTPError(
            url="https://lastmile.fainzy.tech/v1/core/orders/",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"status":"error","message":"invalid reference_code"}'),
        )

        with mock.patch.object(service, "fetch_by_query", side_effect=bad_reference):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="not-a-real-ref",
                    subentity_id=7,
                    x_fainzy_token="store-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("no matching order", str(raised.exception.detail).lower())

    def test_lookup_order_maps_lastmile_server_error_to_gateway_error(self) -> None:
        upstream_failure = urllib_error.HTTPError(
            url="https://lastmile.fainzy.tech/v1/core/orders/",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=BytesIO(b"{}"),
        )

        with mock.patch.object(service, "fetch_by_query", side_effect=upstream_failure):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="156382",
                    subentity_id=7,
                    x_fainzy_token="store-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 502)

    def test_lookup_order_maps_lastmile_timeout_to_504(self) -> None:
        with mock.patch.object(
            service,
            "fetch_by_query",
            side_effect=urllib_error.URLError("timed out"),
        ):
            with self.assertRaises(HTTPException) as raised:
                routes.lookup_order(
                    query="156382",
                    subentity_id=7,
                    x_fainzy_token="store-token",
                    current_user={"role": "operator"},
                )

        self.assertEqual(raised.exception.status_code, 504)
        self.assertIn("took too long", str(raised.exception.detail).lower())


if __name__ == "__main__":
    unittest.main()
