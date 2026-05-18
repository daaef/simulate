"""Session-doc-only probe contracts and helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ALLOWED_SESSION_DOCS = (
    "app-20260428.full-session-user.md",
    "app-20260430.full-session-user.md",
    "app-20260517.full-session-user.md",
    "app-20260429.full-session-store.md",
    "app-20260430.full-session-store.md",
)

SAVED_CARDS_EMPTY_LIST_KEYS = ("object", "data", "has_more", "url")
SAVED_CARDS_NONEMPTY_ITEM_KEYS = ("id", "object")


def _preflight(
    *,
    field: str,
    reason_code: str,
    message: str,
    source_doc: str,
    source_phase: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "reason_code": reason_code,
        "message": message,
        "source_doc": source_doc,
        "source_phase": source_phase,
    }


def _variant(
    *,
    source_doc: str,
    source_phase: str,
    request_context: dict[str, Any],
    http_status: int,
    envelope_keys: tuple[str, ...],
    container_path: tuple[str, ...] | None = None,
    container_required_keys: tuple[str, ...] = (),
    list_path: tuple[str, ...] | None = None,
    list_item_required_keys: tuple[str, ...] = (),
    list_allow_empty: bool = True,
    list_state: str = "any",
    scalar_path: tuple[str, ...] | None = None,
    scalar_kind: str | None = None,
) -> dict[str, Any]:
    return {
        "source_doc": source_doc,
        "source_phase": source_phase,
        "request_context": request_context,
        "allowed_http_statuses": (http_status,),
        "envelope_keys": envelope_keys,
        "container_path": container_path,
        "container_required_keys": container_required_keys,
        "list_path": list_path,
        "list_item_required_keys": list_item_required_keys,
        "list_allow_empty": list_allow_empty,
        "list_state": list_state,
        "scalar_path": scalar_path,
        "scalar_kind": scalar_kind,
    }


PROBE_CONTRACTS: dict[str, dict[str, Any]] = {
    "global_config": {
        "method": "GET",
        "base": "fainzy",
        "endpoint": "/v1/entities/configs/",
        "preflight": (),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "supported_currencies",
                    "lastmile_user_terms_and_conditions",
                    "staff_terms_and_conditions",
                ),
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "supported_currencies",
                    "lastmile_user_terms_and_conditions",
                    "staff_terms_and_conditions",
                ),
            ),
            _variant(
                source_doc="app-20260517.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "supported_currencies",
                    "lastmile_user_terms_and_conditions",
                    "staff_terms_and_conditions",
                ),
            ),
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store setup bootstrap",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "supported_currencies",
                    "lastmile_user_terms_and_conditions",
                    "staff_terms_and_conditions",
                ),
            ),
        ),
    },
    "product_auth": {
        "method": "POST",
        "base": "fainzy",
        "endpoint": "/v1/biz/product/authentication/",
        "preflight": (),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={"params": {"product": "rds"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                scalar_path=("data",),
                scalar_kind="string",
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={"params": {"product": "rds"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                scalar_path=("data",),
                scalar_kind="string",
            ),
            _variant(
                source_doc="app-20260517.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
                request_context={"params": {"product": "rds"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                scalar_path=("data",),
                scalar_kind="string",
            ),
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store setup bootstrap",
                request_context={"params": {"product": "rds"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                scalar_path=("data",),
                scalar_kind="string",
            ),
        ),
    },
    "pricing": {
        "method": "GET",
        "base": "fainzy",
        "endpoint": "/v1/biz/pricing/0/",
        "preflight": (
            _preflight(
                field="currency",
                reason_code="missing_currency",
                message="Pricing was skipped because currency is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
            ),
            _preflight(
                field="auth_token",
                reason_code="missing_product_auth",
                message="Pricing was skipped because product authentication is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 3 - Config + Product Auth",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={"params": {"product_name": "lastmile", "currency": "jpy"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "id",
                    "name",
                    "currency",
                    "cost_per_order",
                    "platform_fee",
                    "delivery_fee",
                    "vat",
                ),
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={"params": {"product_name": "lastmile", "currency": "jpy"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "id",
                    "name",
                    "currency",
                    "cost_per_order",
                    "platform_fee",
                    "delivery_fee",
                    "vat",
                ),
            ),
            _variant(
                source_doc="app-20260517.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={"params": {"product_name": "lastmile", "currency": "jpy"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "id",
                    "name",
                    "currency",
                    "cost_per_order",
                    "platform_fee",
                    "delivery_fee",
                    "vat",
                ),
            ),
            _variant(
                source_doc="app-20260430.full-session-store.md",
                source_phase="CheckoutBloc.LoadOrderCosts",
                request_context={"params": {"product_name": "lastmile", "currency": "jpy"}},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "id",
                    "name",
                    "currency",
                    "cost_per_order",
                    "platform_fee",
                    "delivery_fee",
                    "vat",
                ),
            ),
        ),
    },
    "saved_cards": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/core/cards/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_user_token",
                message="Saved cards were skipped because user authentication is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=SAVED_CARDS_EMPTY_LIST_KEYS,
                list_path=("data", "data"),
                list_allow_empty=True,
                list_state="empty",
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=SAVED_CARDS_EMPTY_LIST_KEYS,
                list_path=("data", "data"),
                list_allow_empty=True,
                list_state="empty",
            ),
            _variant(
                source_doc="app-20260517.full-session-user.md",
                source_phase="Phase 15 - Checkout Init",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=SAVED_CARDS_EMPTY_LIST_KEYS,
                list_path=("data", "data"),
                list_item_required_keys=SAVED_CARDS_NONEMPTY_ITEM_KEYS,
                list_allow_empty=False,
                list_state="nonempty",
            ),
            _variant(
                source_doc="app-20260430.full-session-store.md",
                source_phase="CheckoutBloc.LoadSavedCards",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=SAVED_CARDS_EMPTY_LIST_KEYS,
                list_path=("data", "data"),
                list_allow_empty=True,
                list_state="empty",
            ),
        ),
    },
    "coupons": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/core/coupon/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_user_token",
                message="Coupons were skipped because user authentication is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 16 - Coupon Modal + Selection",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 16 - Coupon Modal + Selection",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_item_required_keys=("id", "code", "config_details", "is_valid"),
                list_allow_empty=False,
                list_state="nonempty",
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 16 - Coupon Modal + Selection",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_item_required_keys=("id", "code", "config_details", "is_valid"),
                list_allow_empty=False,
                list_state="nonempty",
            ),
            _variant(
                source_doc="app-20260430.full-session-store.md",
                source_phase="CheckoutBloc.LoadCoupons",
                request_context={},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_item_required_keys=("id", "code", "config_details", "is_valid"),
                list_allow_empty=False,
                list_state="nonempty",
            ),
        ),
    },
    "user_active_orders": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/core/orders/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_user_token",
                message="Active orders were skipped because user authentication is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 11 - Home Feed + Active Orders",
            ),
            _preflight(
                field="user_id",
                reason_code="missing_user_id",
                message="Active orders were skipped because user_id is missing.",
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 11 - Home Feed + Active Orders",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260428.full-session-user.md",
                source_phase="Phase 11 - Home Feed + Active Orders",
                request_context={"params": {"user": 27}},
                http_status=201,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_allow_empty=True,
                list_state="empty",
            ),
            _variant(
                source_doc="app-20260430.full-session-user.md",
                source_phase="Phase 11 - Home Feed + Active Orders",
                request_context={"params": {"user": 32}},
                http_status=201,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_allow_empty=True,
                list_state="empty",
            ),
            _variant(
                source_doc="app-20260517.full-session-user.md",
                source_phase="Phase 11 - Home Feed + Active Orders",
                request_context={"params": {"user": 37}},
                http_status=201,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_item_required_keys=("id", "user", "code", "order_id", "restaurant"),
                list_allow_empty=False,
                list_state="nonempty",
            ),
            _variant(
                source_doc="app-20260430.full-session-store.md",
                source_phase="ActiveOrdersBloc.FetchActiveOrders",
                request_context={"params": {"user": 30}},
                http_status=201,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_allow_empty=True,
                list_state="empty",
            ),
        ),
    },
    "store_orders": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/core/orders/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_store_token",
                message="Store orders were skipped because store authentication is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
            _preflight(
                field="subentity_id",
                reason_code="missing_subentity_id",
                message="Store orders were skipped because subentity_id is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="API 19 - Store orders",
                request_context={"params": {"subentity_id": 7}},
                http_status=201,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_allow_empty=True,
                list_state="empty",
            ),
        ),
    },
    "store_statistics": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/statistics/subentities/{subentity_id}/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_store_token",
                message="Store statistics were skipped because store authentication is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
            _preflight(
                field="subentity_id",
                reason_code="missing_subentity_id",
                message="Store statistics were skipped because subentity_id is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="API 21/API26 - Store statistics not found",
                request_context={"params": {}, "subentity_id": 7},
                http_status=404,
                envelope_keys=("status", "message"),
            ),
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="API 42 - Store statistics success",
                request_context={"params": {}, "subentity_id": 7},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                container_path=("data",),
                container_required_keys=(
                    "id",
                    "subentity_id",
                    "total_orders",
                    "total_pending_orders",
                    "total_completed_orders",
                    "total_revenue",
                ),
            ),
        ),
    },
    "top_customers": {
        "method": "GET",
        "base": "lastmile",
        "endpoint": "/v1/statistics/subentities/{subentity_id}/top-customers/",
        "preflight": (
            _preflight(
                field="auth_token",
                reason_code="missing_store_token",
                message="Top customers were skipped because store authentication is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
            _preflight(
                field="subentity_id",
                reason_code="missing_subentity_id",
                message="Top customers were skipped because subentity_id is missing.",
                source_doc="app-20260429.full-session-store.md",
                source_phase="Store dashboard",
            ),
        ),
        "variants": (
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="API 20/API27 - Top customers not found",
                request_context={"params": {}, "subentity_id": 7},
                http_status=404,
                envelope_keys=("status", "message"),
            ),
            _variant(
                source_doc="app-20260429.full-session-store.md",
                source_phase="API 43 - Top customers success",
                request_context={"params": {}, "subentity_id": 7},
                http_status=200,
                envelope_keys=("status", "message", "data"),
                list_path=("data",),
                list_item_required_keys=(
                    "id",
                    "phone_number",
                    "email",
                    "first_name",
                    "last_name",
                    "is_active",
                ),
                list_allow_empty=False,
                list_state="nonempty",
            ),
        ),
    },
}


def _copy(value: Any) -> Any:
    return deepcopy(value)


def probe_contract(name: str) -> dict[str, Any] | None:
    contract = PROBE_CONTRACTS.get(name)
    return _copy(contract) if contract else None


def reference_for_probe(name: str) -> dict[str, Any] | None:
    contract = PROBE_CONTRACTS.get(name)
    if not contract:
        return None
    variants = contract.get("variants") or ()
    if not variants:
        return {
            "method": contract.get("method"),
            "base": contract.get("base"),
            "endpoint": contract.get("endpoint"),
            "source_doc": None,
            "source_phase": None,
            "expected_envelope_keys": (),
            "allowed_http_statuses": (),
        }
    first = variants[0]
    return {
        "method": contract.get("method"),
        "base": contract.get("base"),
        "endpoint": contract.get("endpoint"),
        "source_doc": first.get("source_doc"),
        "source_phase": first.get("source_phase"),
        "expected_envelope_keys": tuple(first.get("envelope_keys") or ()),
        "allowed_http_statuses": tuple(first.get("allowed_http_statuses") or ()),
    }


def session_reference_details(spec_name: str) -> dict[str, Any]:
    contract = probe_contract(spec_name)
    if not contract:
        return {}
    preflight = contract.get("preflight") or ()
    variants = contract.get("variants") or ()
    return {
        "session_reference": {
            "contract_mode": "doc_only",
            "allowed_source_docs": list(ALLOWED_SESSION_DOCS),
            "method": contract.get("method"),
            "base": contract.get("base"),
            "endpoint": contract.get("endpoint"),
            "preflight": [
                {
                    "field": requirement.get("field"),
                    "reason_code": requirement.get("reason_code"),
                    "source_doc": requirement.get("source_doc"),
                    "source_phase": requirement.get("source_phase"),
                }
                for requirement in preflight
            ],
            "variants": [
                {
                    "source_doc": variant.get("source_doc"),
                    "source_phase": variant.get("source_phase"),
                    "allowed_http_statuses": list(variant.get("allowed_http_statuses") or ()),
                    "envelope_keys": list(variant.get("envelope_keys") or ()),
                    "request_context": _copy(variant.get("request_context") or {}),
                    "container_path": list(variant.get("container_path") or ()),
                    "container_required_keys": list(variant.get("container_required_keys") or ()),
                    "list_path": list(variant.get("list_path") or ()),
                    "list_item_required_keys": list(variant.get("list_item_required_keys") or ()),
                    "list_allow_empty": bool(variant.get("list_allow_empty", True)),
                    "list_state": variant.get("list_state") or "any",
                    "scalar_path": list(variant.get("scalar_path") or ()),
                    "scalar_kind": variant.get("scalar_kind"),
                }
                for variant in variants
            ],
            "missing_sample_policy": {
                "status": "skipped",
                "reason_code": "missing_reference_sample",
                "next_action": "request_sample_from_user",
            },
        }
    }


def contract_integrity_issues() -> list[str]:
    issues: list[str] = []
    for probe_name, contract in PROBE_CONTRACTS.items():
        for requirement in contract.get("preflight") or ():
            source_doc = requirement.get("source_doc")
            source_phase = requirement.get("source_phase")
            if source_doc not in ALLOWED_SESSION_DOCS:
                issues.append(
                    f"{probe_name}: preflight source_doc {source_doc!r} is outside allowed docs."
                )
            if not isinstance(source_phase, str) or not source_phase.strip():
                issues.append(f"{probe_name}: preflight entry missing source_phase.")
        for variant in contract.get("variants") or ():
            source_doc = variant.get("source_doc")
            source_phase = variant.get("source_phase")
            if source_doc not in ALLOWED_SESSION_DOCS:
                issues.append(
                    f"{probe_name}: variant source_doc {source_doc!r} is outside allowed docs."
                )
            if not isinstance(source_phase, str) or not source_phase.strip():
                issues.append(f"{probe_name}: variant entry missing source_phase.")
    return issues
