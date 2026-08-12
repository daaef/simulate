#!/usr/bin/env python3
"""Generate skeleton JSON files for all use cases identified in Stage 1 and Stage 2.
This is a one-time bootstrap script; not part of the normal workflow.

Usage:
  python3 generate_skeletons.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # api_docs/

# Internal API use cases (from Stage 1: INTERNAL_USE_CASE_MAP.md)
INTERNAL_USE_CASES = {
    "auth": [
        {
            "useCase": "login_user",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/auth/login"},
            "screen": "Dashboard login",
            "trigger": "User submits login form with credentials",
            "auth": {"header": "n/a", "howObtained": "Session cookie set on successful login"},
            "sensitivePaths": ["params.body.password", "response.user"],
        },
        {
            "useCase": "get_session",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/auth/session"},
            "screen": "Dashboard app load",
            "trigger": "Dashboard checks if user is still logged in",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie from login"},
            "sensitivePaths": ["auth.value", "response.user"],
        },
        {
            "useCase": "get_me",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/auth/me"},
            "screen": "Dashboard app load",
            "trigger": "Dashboard loads current user profile",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie from login"},
            "sensitivePaths": ["auth.value", "response"],
        },
        {
            "useCase": "logout_user",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/auth/logout"},
            "screen": "Dashboard user menu",
            "trigger": "User clicks Logout",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "refresh_token",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/auth/refresh"},
            "screen": "Dashboard background",
            "trigger": "Access token expires, dashboard auto-refreshes",
            "auth": {"header": "Bearer", "howObtained": "Refresh token from previous login"},
            "sensitivePaths": ["params.body.refresh_token", "response.access_token"],
        },
        {
            "useCase": "register_user",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/auth/register"},
            "screen": "Registration page (disabled)",
            "trigger": "User attempts registration",
            "auth": {"header": "n/a", "howObtained": "No auth required for registration"},
            "sensitivePaths": ["params.body.password"],
            "badge": "Currently disabled (returns 403)",
        },
    ],
    "runs": [
        {
            "useCase": "list_flows",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/flows"},
            "screen": "Run creation form",
            "trigger": "Run creation form loads to populate flow dropdown",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "list_runs",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/runs"},
            "screen": "Runs list page",
            "trigger": "Runs list page loads or user refreshes",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "create_run",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/runs"},
            "screen": "Run creation form",
            "trigger": "Operator clicks 'Start Run' after configuring parameters",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value", "params.body"],
        },
        {
            "useCase": "get_run",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/runs/{run_id}"},
            "screen": "Run detail page",
            "trigger": "User clicks into a specific run",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "cancel_run",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/runs/{run_id}/cancel"},
            "screen": "Run detail page",
            "trigger": "Operator clicks 'Cancel' on active run",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value"],
        },
    ],
    "orders": [
        {
            "useCase": "orders_auto_login",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/orders/auto-login"},
            "screen": "Orders panel",
            "trigger": "Orders panel opens, gets token without picking a store yet",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value", "response.token"],
        },
        {
            "useCase": "orders_store_login",
            "endpoint": {"method": "POST", "host": "localhost:8000", "path": "/api/v1/orders/store-login"},
            "screen": "Orders panel store selector",
            "trigger": "Operator selects a store to manage orders",
            "auth": {"header": "simulator_session", "howObtained": "Session cookie"},
            "sensitivePaths": ["auth.value", "response.session.token"],
        },
        {
            "useCase": "orders_lookup",
            "endpoint": {"method": "GET", "host": "localhost:8000", "path": "/api/v1/orders/lookup"},
            "screen": "Orders panel search",
            "trigger": "Operator searches for specific order by ID or reference",
            "auth": {"header": "x-fainzy-token", "howObtained": "Store login token"},
            "sensitivePaths": ["auth.value"],
        },
    ],
}

# External API use cases (from Stage 2: EXTERNAL_USE_CASE_MAP.md)
EXTERNAL_USE_CASES = {
    "auth": [
        {
            "useCase": "otp_send",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/auth/otp/send/"},
            "screen": "User login/registration phone-entry",
            "trigger": "User submits phone number to receive OTP",
            "auth": {"header": "n/a", "howObtained": "No auth required for OTP send"},
            "sensitivePaths": ["params.body.phone_number"],
        },
        {
            "useCase": "otp_verify",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/auth/otp/verify/"},
            "screen": "User login/registration OTP-entry",
            "trigger": "User enters 6-digit OTP code",
            "auth": {"header": "n/a", "howObtained": "No auth required for OTP verify"},
            "sensitivePaths": ["params.body.otp"],
        },
        {
            "useCase": "login_authenticate_user",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/auth/users/auth/"},
            "screen": "User login",
            "trigger": "OTP verified; user login completes",
            "auth": {"header": "n/a", "howObtained": "No auth required for login (return includes token)"},
            "sensitivePaths": ["params.body.password", "response.token"],
        },
        {
            "useCase": "signup_create_user",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/auth/users/create/"},
            "screen": "User registration",
            "trigger": "User completes registration form after OTP verify",
            "auth": {"header": "n/a", "howObtained": "No auth required for signup"},
            "sensitivePaths": ["params.body.password", "params.body.email", "response.token"],
        },
    ],
    "config": [
        {
            "useCase": "fainzy_token",
            "endpoint": {"method": "POST", "host": "fainzy.tech", "path": "/v1/biz/product/authentication/"},
            "screen": "Simulator startup",
            "trigger": "Simulator startup before any simulation flow begins (product-level auth)",
            "auth": {"header": "n/a", "howObtained": "API credentials in query params (product auth)"},
            "sensitivePaths": ["response.token"],
        },
    ],
    "location": [
        {
            "useCase": "map_locations_by_geo",
            "endpoint": {"method": "GET", "host": "fainzy.tech", "path": "/v1/entities/locations/{lng}/{lat}/"},
            "screen": "Location lookup",
            "trigger": "User grants location or enters coordinates for service-area lookup",
            "auth": {"header": "Fainzy-Token", "howObtained": "fainzy_token"},
            "sensitivePaths": ["auth.value"],
        },
    ],
    "stores": [
        {
            "useCase": "home_stores_by_area",
            "endpoint": {"method": "GET", "host": "fainzy.tech", "path": "/v1/entities/subentities/service-area/{a}/"},
            "screen": "Home feed",
            "trigger": "User home feed loads to list stores in service area",
            "auth": {"header": "Fainzy-Token", "howObtained": "fainzy_token"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "store_detail_status_poll",
            "endpoint": {"method": "GET", "host": "fainzy.tech", "path": "/v1/entities/subentities/{id}"},
            "screen": "Store detail page",
            "trigger": "Store page opens or periodic status poll",
            "auth": {"header": "Fainzy-Token", "howObtained": "fainzy_token"},
            "sensitivePaths": ["auth.value"],
        },
    ],
    "menu": [
        {
            "useCase": "store_menu",
            "endpoint": {"method": "GET", "host": "lastmile.fainzy.tech", "path": "/v1/core/subentities/{id}/menu"},
            "screen": "Store menu page",
            "trigger": "Store page opens to display items",
            "auth": {"header": "Authorization", "howObtained": "User login token"},
            "sensitivePaths": ["auth.value"],
        },
        {
            "useCase": "store_categories",
            "endpoint": {"method": "GET", "host": "lastmile.fainzy.tech", "path": "/v1/core/subentities/{id}/categories"},
            "screen": "Store menu page",
            "trigger": "Store page opens (parallel with menu) for category tabs",
            "auth": {"header": "Authorization", "howObtained": "User login token"},
            "sensitivePaths": ["auth.value"],
        },
    ],
    "orders": [
        {
            "useCase": "checkout_place_order",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/core/orders/"},
            "screen": "Checkout page",
            "trigger": "User taps 'Place Order' to finalize purchase",
            "auth": {"header": "Authorization", "howObtained": "User login token"},
            "sensitivePaths": ["auth.value", "response.order_id"],
        },
        {
            "useCase": "free_order_complete",
            "endpoint": {"method": "POST", "host": "lastmile.fainzy.tech", "path": "/v1/core/order/free/"},
            "screen": "Checkout page",
            "trigger": "Order total is zero (full coupon/free), place without payment",
            "auth": {"header": "Authorization", "howObtained": "User login token"},
            "sensitivePaths": ["auth.value", "response.order_id"],
        },
    ],
}

def generate_skeleton(use_case_key: str, part: str, group: str, data: dict) -> dict:
    """Generate a complete skeleton JSON structure for a use case."""
    return {
        "useCase": data["useCase"],
        "group": group,
        "part": part,
        "endpoint": data["endpoint"],
        "usedIn": {
            "screen": data["screen"],
            "chain": ["<file:line citation from Stage 1/2>"],
        },
        "trigger": data["trigger"],
        "params": {
            "path": {},
            "query": {},
            "body": {},
        },
        "auth": {
            "header": data["auth"]["header"],
            "value": None,
            "howObtained": data["auth"]["howObtained"],
        },
        "sensitivePaths": data.get("sensitivePaths", []),
        "alsoTriggeredBy": None,
        "capture": {
            "verifiedAt": None,
            "status": None,
            "tool": "capture_internal.py" if part == "internal" else "capture_external.py",
            "flavor": "development",
        },
        "response": None,
        **({"badge": data["badge"]} if "badge" in data else {}),
    }

def main() -> None:
    root = ROOT

    # Create internal skeletons
    for group, use_cases in INTERNAL_USE_CASES.items():
        group_dir = root / "internal" / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for data in use_cases:
            skeleton = generate_skeleton(data["useCase"], "internal", group, data)
            file_path = group_dir / f"{data['useCase']}.json"
            file_path.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n")
            print(f"✓ {file_path.relative_to(root.parent)}")

    # Create external skeletons
    for group, use_cases in EXTERNAL_USE_CASES.items():
        group_dir = root / "external" / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for data in use_cases:
            skeleton = generate_skeleton(data["useCase"], "external", group, data)
            file_path = group_dir / f"{data['useCase']}.json"
            file_path.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n")
            print(f"✓ {file_path.relative_to(root.parent)}")

    print(f"\nGenerated {len(sum(INTERNAL_USE_CASES.values(), []))} internal + {len(sum(EXTERNAL_USE_CASES.values(), []))} external skeletons.")

if __name__ == "__main__":
    main()
