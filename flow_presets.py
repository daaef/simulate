"""Simple named simulation flows for the CLI."""

from __future__ import annotations

from typing import Any

from scenarios import TRACE_SCENARIOS, TRACE_SUITES


FLOW_PRESETS: dict[str, dict[str, Any]] = {
    "load": {
        "mode": "load",
    },
    "menus": {
        "mode": "trace",
        "suite": "menus",
    },
    "new-user": {
        "mode": "trace",
        "scenarios": ["new_user_setup"],
        "user_role": "new_user",
    },
    "paid-no-coupon": {
        "mode": "trace",
        "scenarios": ["returning_paid_no_coupon"],
        "payment_mode": "stripe",
        "payment_case": "paid_no_coupon",
        "coupon_id": None,
    },
    "paid-coupon": {
        "mode": "trace",
        "scenarios": ["returning_paid_with_coupon"],
        "payment_mode": "stripe",
        "payment_case": "paid_with_coupon",
        "coupon_required": True,
    },
    "free-coupon": {
        "mode": "trace",
        "scenarios": ["returning_free_with_coupon"],
        "payment_mode": "free",
        "payment_case": "free_with_coupon",
        "free_order_amount": 0.0,
        "coupon_required": True,
    },
    "store-setup": {
        "mode": "trace",
        "scenarios": ["store_first_setup"],
    },
    "store-accept": {
        "mode": "trace",
        "scenarios": ["store_accept"],
        "payment_mode": "stripe",
        "payment_case": "paid_no_coupon",
        "coupon_id": None,
    },
    "store-reject": {
        "mode": "trace",
        "scenarios": ["store_reject"],
    },
    "robot-complete": {
        "mode": "trace",
        "scenarios": ["robot_complete"],
        "payment_mode": "stripe",
        "payment_case": "paid_no_coupon",
        "coupon_id": None,
    },
    "payments": {
        "mode": "trace",
        "suite": "payments",
    },
    "audit": {
        "mode": "trace",
        "suite": "audit",
    },
    "doctor": {
        "mode": "trace",
        "suite": "doctor",
    },
    "full": {
        "mode": "trace",
        "suite": "full",
    },
    "receipt-review": {
        "mode": "trace",
        "scenarios": ["receipt_review_reorder"],
        "payment_mode": "stripe",
        "payment_case": "paid_no_coupon",
        "coupon_id": None,
        "post_order_actions": True,
    },
    "store-dashboard": {
        "mode": "trace",
        "scenarios": ["store_dashboard"],
    },
}

FLOW_ALIASES = {
    "paid": "paid-no-coupon",
    "coupon": "paid-coupon",
    "free": "free-coupon",
    "new_user": "new-user",
    "store_setup": "store-setup",
    "store_accept": "store-accept",
    "store_reject": "store-reject",
    "robot": "robot-complete",
    "daily": "doctor",
    "doctor": "doctor",
    "receipt_review": "receipt-review",
    "receipt-review-reorder": "receipt-review",
    "dashboard": "store-dashboard",
}


FLOW_OPTIONAL_FLAGS: dict[str, list[str]] = {
    "trace": [
        "timing",
        "store_id",
        "phone",
        "suite",
        "scenarios",
        "strict_plan",
        "skip_app_probes",
        "skip_store_dashboard_probes",
        "no_auto_provision",
        "enforce_websocket_gates",
        "post_order_actions",
        "all_users",
        "extra_args",
    ],
    "load": [
        "timing",
        "store_id",
        "phone",
        "all_users",
        "users",
        "orders",
        "interval",
        "reject",
        "continuous",
        "strict_plan",
        "skip_app_probes",
        "skip_store_dashboard_probes",
        "no_auto_provision",
        "enforce_websocket_gates",
        "post_order_actions",
        "extra_args",
    ],
}


def normalise_flow(name: str | None) -> str:
    key = (name or "").strip().lower().replace("_", "-")
    return FLOW_ALIASES.get(key, key)


def resolve_flow(name: str | None) -> dict[str, Any] | None:
    key = normalise_flow(name)
    if not key:
        return None
    preset = FLOW_PRESETS.get(key)
    if preset is None:
        expected = ", ".join(sorted(FLOW_PRESETS))
        raise RuntimeError(f"Unsupported flow {name!r}. Expected one of {expected}.")
    return {"name": key, **preset}


def flow_capabilities() -> dict[str, dict[str, Any]]:
    capabilities: dict[str, dict[str, Any]] = {}
    for flow_name, preset in sorted(FLOW_PRESETS.items()):
        resolved_mode = str(preset.get("mode", "trace"))
        default_suite = str(preset.get("suite") or "") or None
        default_scenarios = [str(item) for item in preset.get("scenarios", [])]
        capabilities[flow_name] = {
            "flow": flow_name,
            "resolved_mode": resolved_mode,
            "default_suite": default_suite,
            "default_scenarios": default_scenarios,
            "allowed_optional_flags": list(FLOW_OPTIONAL_FLAGS.get(resolved_mode, [])),
            "available_suites": sorted(TRACE_SUITES.keys()) if resolved_mode == "trace" else [],
            "available_scenarios": list(TRACE_SCENARIOS) if resolved_mode == "trace" else [],
        }
    return capabilities
