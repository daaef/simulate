"""Allowed UI actions and contract rules for Fainzy simulations."""

from __future__ import annotations

from typing import Any


MENU_AVAILABLE = "available"
MENU_UNAVAILABLE = "unavailable"
MENU_SOLD_OUT = "sold_out"
MENU_STATUSES = (MENU_AVAILABLE, MENU_UNAVAILABLE, MENU_SOLD_OUT)
LEGACY_AVAILABLE_STATUSES = ("1", 1)

USER_PHONE_COUNTRIES = ("JP", "NG", "IN", "GB", "US")
STORE_PHONE_COUNTRIES = ("US", "NG", "GH", "GB", "CA", "JP")
STORE_CURRENCY_FALLBACKS = ("USD", "EUR", "GBP", "NGN", "GHS", "JPY")
WORKING_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LOCATION_RADII_KM = (1, 2, 3, 4, 5)

USER_ROOT_TABS = ("Home", "Carts", "My Orders", "Notifications", "Account")
USER_HOME_TABS = ("All Stores", "Offers")
PAYMENT_METHODS = ("newCard", "savedCard")
PAYMENT_CASES = (
    "paid_no_coupon",
    "paid_with_coupon",
    "free_with_coupon",
)

STORE_ROOT_TABS = ("Home", "Orders", "Menus", "Store")
STORE_QUICK_ACTIONS = ("Manage Menus", "View Orders", "Store Settings")
STORE_STATUS_VALUES = ("open", "closed")
STORE_MENU_FILTERS = ("All",)
STORE_DISCOUNT_TYPES = ("percentage", "value")
STORE_SIDE_DEFAULT_OPTIONS = ("without price", "with price")
STORE_ORDER_TABS = ("Active", "Pending", "Completed", "Cancelled", "Rejected", "All")
STORE_ORDER_GRID_COLUMNS = (2, 3, 4)

ROBOT_STATUS_SEQUENCE = (
    "enroute_pickup",
    "robot_arrived_for_pickup",
    "enroute_delivery",
    "robot_arrived_for_delivery",
    "completed",
)


def normalise_menu_status(status: Any) -> str:
    if status in LEGACY_AVAILABLE_STATUSES:
        return "legacy_available"
    if isinstance(status, str):
        value = status.strip()
        if value in MENU_STATUSES:
            return value
    return "unknown"


def user_can_add_menu_item(status: Any, *, store_is_open: bool) -> bool:
    return store_is_open and status == MENU_AVAILABLE


def user_menu_block_reason(status: Any, *, store_is_open: bool) -> str | None:
    if user_can_add_menu_item(status, store_is_open=store_is_open):
        return None
    if not store_is_open:
        return "store_closed"
    if status in {MENU_UNAVAILABLE, MENU_SOLD_OUT}:
        return "item_sold_out_or_unavailable"
    if status in LEGACY_AVAILABLE_STATUSES:
        return "legacy_status_not_user_addable"
    return "unknown_menu_status"


def store_counts_menu_available(status: Any) -> bool:
    return status == MENU_AVAILABLE or status in LEGACY_AVAILABLE_STATUSES


def catalogue_payload() -> dict[str, Any]:
    return {
        "user": {
            "auth_phone_countries": USER_PHONE_COUNTRIES,
            "location_radius_km": LOCATION_RADII_KM,
            "root_tabs": USER_ROOT_TABS,
            "home_tabs": USER_HOME_TABS,
            "payment_methods": PAYMENT_METHODS,
            "payment_cases": PAYMENT_CASES,
        },
        "store": {
            "phone_countries": STORE_PHONE_COUNTRIES,
            "currency_fallbacks": STORE_CURRENCY_FALLBACKS,
            "working_days": WORKING_DAYS,
            "root_tabs": STORE_ROOT_TABS,
            "quick_actions": STORE_QUICK_ACTIONS,
            "status_values": STORE_STATUS_VALUES,
            "menu_statuses": MENU_STATUSES,
            "menu_filters": STORE_MENU_FILTERS,
            "discount_types": STORE_DISCOUNT_TYPES,
            "side_default_options": STORE_SIDE_DEFAULT_OPTIONS,
            "order_tabs": STORE_ORDER_TABS,
            "order_grid_columns": STORE_ORDER_GRID_COLUMNS,
        },
        "robot": {
            "status_sequence": ROBOT_STATUS_SEQUENCE,
        },
        "contracts": {
            "user_add_to_cart": (
                "store must be open and menu.status must equal 'available'"
            ),
            "legacy_status_risk": (
                "store grid counts status '1' as available, but user app only "
                "accepts status 'available'"
            ),
            "unavailable_user_message": (
                "user app blocks unavailable and sold_out with the same sold-out text"
            ),
        },
    }
