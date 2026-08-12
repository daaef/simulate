#!/usr/bin/env python3
"""Generate ALL skeleton JSON files for routes identified in Stages 1 and 2.
This reads from INTERNAL_USE_CASE_MAP.md and EXTERNAL_USE_CASE_MAP.md.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # api_docs/

# Complete internal API mapping from Stage 1 (90 total)
INTERNAL_ROUTES = {
    "auth": [
        ("login_user", "POST", "/api/v1/auth/login", "Dashboard login", "User submits login form", "n/a", "Session set on successful login"),
        ("logout_user", "POST", "/api/v1/auth/logout", "Dashboard user menu", "User clicks Logout", "simulator_session", "Session cookie from login"),
        ("refresh_token", "POST", "/api/v1/auth/refresh", "Dashboard background", "Access token expires", "Bearer", "Refresh token"),
        ("get_session", "GET", "/api/v1/auth/session", "Dashboard app load", "Dashboard checks session", "simulator_session", "Session cookie"),
        ("get_me", "GET", "/api/v1/auth/me", "Dashboard app load", "Dashboard loads user profile", "simulator_session", "Session cookie"),
        ("register_user", "POST", "/api/v1/auth/register", "Registration page", "User attempts registration", "n/a", "No auth"),
    ],
    "admin": [
        ("list_users", "GET", "/api/v1/admin/users", "Admin dashboard", "Admin dashboard loads", "simulator_session", "Session cookie"),
        ("create_user", "POST", "/api/v1/admin/users", "Admin panel", "Admin creates user", "simulator_session", "Session cookie"),
        ("update_user", "PUT", "/api/v1/admin/users/{user_id}", "Admin panel", "Admin edits user", "simulator_session", "Session cookie"),
        ("delete_user", "DELETE", "/api/v1/admin/users/{user_id}", "Admin panel", "Admin deletes user", "simulator_session", "Session cookie"),
        ("reset_user_password", "POST", "/api/v1/admin/users/{user_id}/reset-password", "Admin panel", "Admin resets password", "simulator_session", "Session cookie"),
    ],
    "runs": [
        ("list_flows", "GET", "/api/v1/flows", "Run creation form", "Form loads flow dropdown", "simulator_session", "Session cookie"),
        ("list_runs", "GET", "/api/v1/runs", "Runs list page", "List page loads", "simulator_session", "Session cookie"),
        ("get_runs_count", "GET", "/api/v1/runs/count", "Dashboard", "Dashboard summary loads", "simulator_session", "Session cookie"),
        ("get_dashboard_summary", "GET", "/api/v1/dashboard/summary", "Dashboard home", "Dashboard home loads", "simulator_session", "Session cookie"),
        ("create_run", "POST", "/api/v1/runs", "Run creation", "Operator starts run", "simulator_session", "Session cookie"),
        ("get_run", "GET", "/api/v1/runs/{run_id}", "Run detail page", "Detail page loads", "simulator_session", "Session cookie"),
        ("cancel_run", "POST", "/api/v1/runs/{run_id}/cancel", "Run detail", "Operator cancels run", "simulator_session", "Session cookie"),
        ("delete_run", "DELETE", "/api/v1/runs/{run_id}", "Runs list", "Operator deletes run", "simulator_session", "Session cookie"),
        ("restore_run", "POST", "/api/v1/runs/{run_id}/restore", "Archives", "Operator restores run", "simulator_session", "Session cookie"),
        ("get_run_log", "GET", "/api/v1/runs/{run_id}/log", "Run detail logs", "Logs tab opens", "simulator_session", "Session cookie"),
        ("get_run_artifacts", "GET", "/api/v1/runs/{run_id}/artifacts/{kind}", "Run detail", "Report/Story/Events tab", "simulator_session", "Session cookie"),
        ("get_run_metrics", "GET", "/api/v1/runs/{run_id}/metrics", "Run detail metrics", "Metrics tab opens", "simulator_session", "Session cookie"),
        ("get_execution_snapshot", "GET", "/api/v1/runs/{run_id}/execution-snapshot", "Run detail snapshot", "Snapshot tab opens", "simulator_session", "Session cookie"),
        ("replay_run", "POST", "/api/v1/runs/{run_id}/replay", "Run detail", "Operator replays run", "simulator_session", "Session cookie"),
    ],
    "run_profiles": [
        ("list_run_profiles", "GET", "/api/v1/run-profiles", "Profiles page", "Profiles page loads", "simulator_session", "Session cookie"),
        ("create_run_profile", "POST", "/api/v1/run-profiles", "Profiles page", "Operator saves profile", "simulator_session", "Session cookie"),
        ("update_run_profile", "PUT", "/api/v1/run-profiles/{profile_id}", "Profiles page", "Operator edits profile", "simulator_session", "Session cookie"),
        ("delete_run_profile", "DELETE", "/api/v1/run-profiles/{profile_id}", "Profiles page", "Operator deletes profile", "simulator_session", "Session cookie"),
        ("restore_run_profile", "POST", "/api/v1/run-profiles/{profile_id}/restore", "Archives", "Operator restores profile", "simulator_session", "Session cookie"),
        ("launch_run_profile", "POST", "/api/v1/run-profiles/{profile_id}/launch", "Profiles page", "Operator launches profile", "simulator_session", "Session cookie"),
    ],
    "archives": [
        ("get_archive_summary", "GET", "/api/v1/archives/summary", "Archives page", "Archives page loads", "simulator_session", "Session cookie"),
        ("list_archived_runs", "GET", "/api/v1/archives/runs", "Archives runs tab", "Archived runs list", "simulator_session", "Session cookie"),
        ("list_archived_profiles", "GET", "/api/v1/archives/profiles", "Archives profiles tab", "Archived profiles list", "simulator_session", "Session cookie"),
        ("list_archived_schedules", "GET", "/api/v1/archives/schedules", "Archives schedules tab", "Archived schedules list", "simulator_session", "Session cookie"),
        ("list_archived_integration_mappings", "GET", "/api/v1/archives/integration-mappings", "Archives mappings tab", "Archived mappings list", "simulator_session", "Session cookie"),
        ("purge_run", "POST", "/api/v1/archives/runs/{run_id}/purge", "Archives runs", "Operator purges run", "simulator_session", "Session cookie"),
        ("purge_profile", "POST", "/api/v1/archives/profiles/{profile_id}/purge", "Archives profiles", "Operator purges profile", "simulator_session", "Session cookie"),
        ("purge_schedule", "POST", "/api/v1/archives/schedules/{schedule_id}/purge", "Archives schedules", "Operator purges schedule", "simulator_session", "Session cookie"),
        ("purge_integration_mapping", "POST", "/api/v1/archives/integration-mappings/{mapping_id}/purge", "Archives mappings", "Operator purges mapping", "simulator_session", "Session cookie"),
    ],
    "retention": [
        ("get_retention_summary", "GET", "/api/v1/retention/summary", "Retention settings", "Settings page loads", "simulator_session", "Session cookie"),
    ],
    "schedules": [
        ("list_schedules", "GET", "/api/v1/schedules", "Schedules page", "Schedules page loads", "simulator_session", "Session cookie"),
        ("get_schedule_summary", "GET", "/api/v1/schedules/summary", "Dashboard", "Dashboard loads summary", "simulator_session", "Session cookie"),
        ("create_schedule", "POST", "/api/v1/schedules", "Schedules page", "Operator creates schedule", "simulator_session", "Session cookie"),
        ("update_schedule", "PUT", "/api/v1/schedules/{schedule_id}", "Schedules page", "Operator edits schedule", "simulator_session", "Session cookie"),
        ("trigger_schedule", "POST", "/api/v1/schedules/{schedule_id}/trigger", "Schedules page", "Operator triggers schedule", "simulator_session", "Session cookie"),
        ("pause_schedule", "POST", "/api/v1/schedules/{schedule_id}/pause", "Schedules page", "Operator pauses schedule", "simulator_session", "Session cookie"),
        ("resume_schedule", "POST", "/api/v1/schedules/{schedule_id}/resume", "Schedules page", "Operator resumes schedule", "simulator_session", "Session cookie"),
        ("disable_schedule", "POST", "/api/v1/schedules/{schedule_id}/disable", "Schedules page", "Operator disables schedule", "simulator_session", "Session cookie"),
        ("delete_schedule", "POST", "/api/v1/schedules/{schedule_id}/delete", "Schedules page", "Operator deletes schedule", "simulator_session", "Session cookie"),
        ("restore_schedule", "POST", "/api/v1/schedules/{schedule_id}/restore", "Archives", "Operator restores schedule", "simulator_session", "Session cookie"),
    ],
    "subentities": [
        ("list_subentities", "GET", "/api/v1/subentities", "Orders/simulation config", "Store list loads", "simulator_session", "Session cookie"),
        ("search_subentities", "GET", "/api/v1/subentities/search", "Orders/simulation config", "Store search runs", "simulator_session", "Session cookie"),
    ],
    "alerts": [
        ("list_alerts", "GET", "/api/v1/alerts", "Dashboard alerts", "Alerts panel loads", "simulator_session", "Session cookie"),
    ],
    "simulation_plans": [
        ("list_simulation_plans", "GET", "/api/v1/simulation-plans", "Plans page", "Plans page loads", "simulator_session", "Session cookie"),
        ("get_simulation_plan", "GET", "/api/v1/simulation-plans/{plan_id}", "Plans page", "Plan detail loads", "simulator_session", "Session cookie"),
        ("create_simulation_plan", "POST", "/api/v1/simulation-plans", "Plans page", "Operator creates plan", "simulator_session", "Session cookie"),
        ("update_simulation_plan", "PUT", "/api/v1/simulation-plans/{plan_id}", "Plans page", "Operator edits plan", "simulator_session", "Session cookie"),
        ("delete_simulation_plan", "DELETE", "/api/v1/simulation-plans/{plan_id}", "Plans page", "Operator deletes plan", "simulator_session", "Session cookie"),
    ],
    "system": [
        ("get_system_timezones", "GET", "/api/v1/system/timezones", "System settings", "Settings load", "simulator_session", "Session cookie"),
        ("update_system_timezones", "PUT", "/api/v1/system/timezones", "System settings", "Admin updates timezone", "simulator_session", "Session cookie"),
        ("get_system_email", "GET", "/api/v1/system/email", "Email settings", "Email settings load", "simulator_session", "Session cookie"),
        ("update_system_email", "PUT", "/api/v1/system/email", "Email settings", "Admin updates email", "simulator_session", "Session cookie"),
        ("test_system_email", "POST", "/api/v1/system/email/test", "Email settings", "Admin sends test", "simulator_session", "Session cookie"),
        ("get_system_retention", "GET", "/api/v1/system/retention", "Retention settings", "Settings load", "simulator_session", "Session cookie"),
        ("update_system_retention", "PUT", "/api/v1/system/retention", "Retention settings", "Admin updates policy", "simulator_session", "Session cookie"),
    ],
    "integrations": [
        ("github_deployment_complete_webhook", "POST", "/api/v1/integrations/github/deployment-complete", "GitHub webhook", "Deployment webhook fires", "n/a", "GitHub webhook signature"),
        ("list_github_mappings", "GET", "/api/v1/integrations/github/mappings", "Integrations page", "Mappings list loads", "simulator_session", "Session cookie"),
        ("create_github_mapping", "POST", "/api/v1/integrations/github/mappings", "Integrations page", "Admin creates mapping", "simulator_session", "Session cookie"),
        ("delete_github_mapping", "DELETE", "/api/v1/integrations/github/mappings/{mapping_id}", "Integrations page", "Admin deletes mapping", "simulator_session", "Session cookie"),
        ("restore_github_mapping", "POST", "/api/v1/integrations/github/mappings/{mapping_id}/restore", "Archives", "Admin restores mapping", "simulator_session", "Session cookie"),
        ("list_github_triggers", "GET", "/api/v1/integrations/github/triggers", "Integrations page", "Triggers list loads", "simulator_session", "Session cookie"),
        ("list_github_projects", "GET", "/api/v1/integrations/github/projects", "Integrations page", "Projects list loads", "simulator_session", "Session cookie"),
        ("create_github_project", "POST", "/api/v1/integrations/github/projects", "Integrations page", "Admin registers repo", "simulator_session", "Session cookie"),
        ("rotate_github_project_secret", "POST", "/api/v1/integrations/github/projects/{project}/rotate-secret", "Integrations page", "Admin rotates secret", "simulator_session", "Session cookie"),
        ("update_github_project_repositories", "PATCH", "/api/v1/integrations/github/projects/{project}/repositories", "Integrations page", "Admin updates repos", "simulator_session", "Session cookie"),
        ("delete_github_project", "DELETE", "/api/v1/integrations/github/projects/{project}", "Integrations page", "Admin deletes project", "simulator_session", "Session cookie"),
    ],
    "orders": [
        ("orders_auto_login", "GET", "/api/v1/orders/auto-login", "Orders panel", "Panel opens", "simulator_session", "Session cookie"),
        ("orders_get_config", "GET", "/api/v1/orders/config", "Orders panel", "Panel loads config", "simulator_session", "Session cookie"),
        ("orders_list_stores", "GET", "/api/v1/orders/stores", "Orders store selector", "Store dropdown loads", "simulator_session", "Session cookie"),
        ("orders_store_login", "POST", "/api/v1/orders/store-login", "Orders store selector", "Operator selects store", "simulator_session", "Session cookie"),
        ("orders_lookup", "GET", "/api/v1/orders/lookup", "Orders search", "Operator searches order", "x-fainzy-token", "Store login token"),
        ("orders_list", "GET", "/api/v1/orders/list", "Orders list", "Order list loads", "x-fainzy-token", "Store login token"),
        ("orders_store_stats", "GET", "/api/v1/orders/store-stats", "Orders stats", "Stats tab loads", "x-fainzy-token", "Store login token"),
        ("orders_customer_stats", "GET", "/api/v1/orders/customer-stats", "Orders stats", "Customer stats load", "x-fainzy-token", "Store login token"),
        ("orders_customer_search", "GET", "/api/v1/orders/customers/search", "Orders search", "Customer search runs", "x-fainzy-token", "Store login token"),
        ("orders_update_status", "PATCH", "/api/v1/orders/status", "Orders panel", "Operator updates status", "x-fainzy-token", "Store login token"),
    ],
    "overview": [
        ("get_latest_run_overview", "GET", "/api/v1/overview/latest-run", "Dashboard home", "Dashboard loads overview", "simulator_session", "Session cookie"),
        ("get_socket_status", "GET", "/api/v1/overview/socket-status", "Dashboard socket monitor", "Socket status loads", "simulator_session", "Session cookie"),
        ("get_run_overview", "GET", "/api/v1/overview/runs/{run_id}", "Run detail overview", "Overview loads", "simulator_session", "Session cookie"),
    ],
}

# Complete external API mapping from Stage 2
EXTERNAL_ROUTES = {
    "auth": [
        ("otp_send", "POST", "lastmile.fainzy.tech", "/v1/auth/otp/send/", "Login/registration", "User submits phone", "n/a", "No auth"),
        ("otp_verify", "POST", "lastmile.fainzy.tech", "/v1/auth/otp/verify/", "Login/registration", "User enters OTP", "n/a", "No auth"),
        ("login_authenticate_user", "POST", "lastmile.fainzy.tech", "/v1/auth/users/auth/", "Login", "OTP verified", "n/a", "No auth (return includes token)"),
        ("signup_create_user", "POST", "lastmile.fainzy.tech", "/v1/auth/users/create/", "Registration", "Registration completes", "n/a", "No auth"),
    ],
    "config": [
        ("fainzy_token", "POST", "fainzy.tech", "/v1/biz/product/authentication/", "Simulator startup", "Startup begins", "n/a", "API credentials"),
    ],
    "location": [
        ("map_locations_by_geo", "GET", "fainzy.tech", "/v1/entities/locations/{lng}/{lat}/", "Location lookup", "User/simulator looks up area", "Fainzy-Token", "fainzy_token"),
    ],
    "stores": [
        ("home_stores_by_area", "GET", "fainzy.tech", "/v1/entities/subentities/service-area/{a}/", "Home feed", "Feed loads stores", "Fainzy-Token", "fainzy_token"),
        ("store_detail_status_poll", "GET", "fainzy.tech", "/v1/entities/subentities/{id}", "Store detail", "Store page loads", "Fainzy-Token", "fainzy_token"),
        ("store_update_status", "PATCH", "fainzy.tech", "/v1/entities/subentities/{id}", "Store settings", "Store status changes", "Fainzy-Token", "fainzy_token"),
    ],
    "menu": [
        ("store_menu", "GET", "lastmile.fainzy.tech", "/v1/core/subentities/{id}/menu", "Store menu", "Menu loads", "Authorization", "User login token"),
        ("store_categories", "GET", "lastmile.fainzy.tech", "/v1/core/subentities/{id}/categories", "Store menu", "Categories load", "Authorization", "User login token"),
        ("item_sides", "GET", "lastmile.fainzy.tech", "/v1/core/subentities/{id}/menu/{menuId}/sides", "Item details", "Item details open", "Authorization", "User login token"),
    ],
    "orders": [
        ("checkout_place_order", "POST", "lastmile.fainzy.tech", "/v1/core/orders/", "Checkout", "Place order tapped", "Authorization", "User login token"),
        ("free_order_complete", "POST", "lastmile.fainzy.tech", "/v1/core/order/free/", "Checkout", "Free order placed", "Authorization", "User login token"),
        ("order_details_poll", "GET", "lastmile.fainzy.tech", "/v1/core/orders/?order_id=", "Order details", "Order details loaded", "Authorization", "User login token"),
        ("order_cancel_update", "PATCH", "lastmile.fainzy.tech", "/v1/core/orders/", "Order details", "Order cancelled", "Authorization", "User login token"),
    ],
}

def generate_skeleton(use_case: str, group: str, part: str, method: str, host: str, path: str, screen: str, trigger: str, auth_header: str, auth_source: str) -> dict:
    """Generate skeleton JSON for a use case."""
    return {
        "useCase": use_case,
        "group": group,
        "part": part,
        "endpoint": {"method": method, "host": host, "path": path},
        "usedIn": {"screen": screen, "chain": [f"{method} {path} → call site verified in Stage 1/2"]},
        "trigger": trigger,
        "params": {"path": {}, "query": {}, "body": {}},
        "auth": {"header": auth_header, "value": None, "howObtained": auth_source},
        "sensitivePaths": [],
        "alsoTriggeredBy": None,
        "capture": {
            "verifiedAt": None,
            "status": None,
            "tool": "capture_internal.py" if part == "internal" else "capture_external.py",
            "flavor": "development",
        },
        "response": None,
    }

def main() -> None:
    root = ROOT
    total_internal = 0
    total_external = 0

    # Generate internal skeletons (overwriting existing)
    for group, routes in INTERNAL_ROUTES.items():
        group_dir = root / "internal" / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for use_case, method, path, screen, trigger, auth_header, auth_source in routes:
            skeleton = generate_skeleton(use_case, group, "internal", method, "localhost:8000", path, screen, trigger, auth_header, auth_source)
            file_path = group_dir / f"{use_case}.json"
            file_path.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n")
            total_internal += 1

    # Generate external skeletons (overwriting existing)
    for group, routes in EXTERNAL_ROUTES.items():
        group_dir = root / "external" / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for use_case, method, host, path, screen, trigger, auth_header, auth_source in routes:
            skeleton = generate_skeleton(use_case, group, "external", method, host, path, screen, trigger, auth_header, auth_source)
            file_path = group_dir / f"{use_case}.json"
            file_path.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n")
            total_external += 1

    print(f"✓ Generated {total_internal} internal + {total_external} external skeleton files")

if __name__ == "__main__":
    main()
