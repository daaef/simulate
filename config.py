from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _optional_int(key: str) -> int | None:
    raw = os.getenv(key, "").strip()
    return int(raw) if raw else None


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _optional_float(key: str) -> float | None:
    raw = os.getenv(key, "").strip()
    return float(raw) if raw else None


def _bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _csv(key: str) -> list[str]:
    raw = os.getenv(key, "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


LASTMILE_BASE_URL: str = _str("LASTMILE_BASE_URL", "https://lastmile.fainzy.tech").rstrip("/")
FAINZY_BASE_URL: str = _str("FAINZY_BASE_URL", "https://fainzy.tech").rstrip("/")

USER_PHONE_NUMBER: str = _str("USER_PHONE_NUMBER")
USER_LASTMILE_TOKEN: str = _str("USER_LASTMILE_TOKEN")

STORE_ID: str = _str("STORE_ID")
STORE_LASTMILE_TOKEN: str = _str("STORE_LASTMILE_TOKEN")

SUBENTITY_ID: int = _int("SUBENTITY_ID", 1)
USER_ID: int | None = _optional_int("USER_ID")
LOCATION_ID: int | None = _optional_int("LOCATION_ID")
STORE_CURRENCY: str = _str("STORE_CURRENCY", "jpy")

SIM_RUN_MODE: str = _str("SIM_RUN_MODE", "load").lower()
SIM_FLOW: str = _str("SIM_FLOW", "").lower()
SIM_TRACE_SUITE: str = _str("SIM_TRACE_SUITE", "core").lower()
SIM_TRACE_SCENARIOS: list[str] = _csv("SIM_TRACE_SCENARIOS")
SIM_TIMING_PROFILE: str = _str("SIM_TIMING_PROFILE", "fast").lower()

SIM_PAYMENT_MODE: str = _str("SIM_PAYMENT_MODE", "stripe").lower()
SIM_PAYMENT_CASE: str = _str("SIM_PAYMENT_CASE", "paid_no_coupon").lower()
SIM_FREE_ORDER_AMOUNT: float = _float("SIM_FREE_ORDER_AMOUNT", 0.0)
SIM_COUPON_ID: int | None = _optional_int("SIM_COUPON_ID")
SIM_SAVE_CARD: bool = _bool("SIM_SAVE_CARD", False)
STRIPE_SECRET_KEY: str = _str("STRIPE_SECRET_KEY")
STRIPE_TEST_PAYMENT_METHOD: str = _str("STRIPE_TEST_PAYMENT_METHOD", "pm_card_visa")
SIM_RUN_APP_PROBES: bool = _bool("SIM_RUN_APP_PROBES", True)
SIM_RUN_STORE_DASHBOARD_PROBES: bool = _bool("SIM_RUN_STORE_DASHBOARD_PROBES", True)
SIM_RUN_POST_ORDER_ACTIONS: bool = _bool("SIM_RUN_POST_ORDER_ACTIONS", False)
SIM_STRICT_PLAN: bool = _bool("SIM_STRICT_PLAN", False)
SIM_REVIEW_RATING: int = _int("SIM_REVIEW_RATING", 4)
SIM_REVIEW_COMMENT: str = _str("SIM_REVIEW_COMMENT", "Simulator review")
SIM_NEW_USER_FIRST_NAME: str = _str("SIM_NEW_USER_FIRST_NAME", "Fainzy")
SIM_NEW_USER_LAST_NAME: str = _str("SIM_NEW_USER_LAST_NAME", "Simulator")
SIM_NEW_USER_EMAIL: str = _str("SIM_NEW_USER_EMAIL")
SIM_NEW_USER_PASSWORD: str = _str("SIM_NEW_USER_PASSWORD", "Password123!")
SIM_APP_AUTOPILOT: bool = _bool("SIM_APP_AUTOPILOT", True)
SIM_AUTO_SELECT_STORE: bool = _bool("SIM_AUTO_SELECT_STORE", SIM_APP_AUTOPILOT)
SIM_AUTO_SELECT_COUPON: bool = _bool("SIM_AUTO_SELECT_COUPON", SIM_APP_AUTOPILOT)
SIM_SELECTED_COUPON: dict[str, Any] | None = None
SIM_AUTO_PROVISION_FIXTURES: bool = _bool("SIM_AUTO_PROVISION_FIXTURES", True)
SIM_MUTATE_STORE_SETUP: bool = _bool("SIM_MUTATE_STORE_SETUP", False)
SIM_MUTATE_MENU_SETUP: bool = _bool("SIM_MUTATE_MENU_SETUP", False)
SIM_AUTO_TOGGLE_STORE_STATUS: bool = _bool("SIM_AUTO_TOGGLE_STORE_STATUS", SIM_APP_AUTOPILOT)
SIM_STORE_OPEN_STATUS: int = _int("SIM_STORE_OPEN_STATUS", 1)
SIM_STORE_CLOSED_STATUS: int = _int("SIM_STORE_CLOSED_STATUS", 3)
SIM_STORE_SETUP_NAME: str = _str("SIM_STORE_SETUP_NAME", "Fainzy Simulator Store")
SIM_STORE_SETUP_BRANCH: str = _str("SIM_STORE_SETUP_BRANCH", "Simulator")
SIM_STORE_SETUP_DESCRIPTION: str = _str(
    "SIM_STORE_SETUP_DESCRIPTION",
    "Store profile created by simulator setup flow.",
)
SIM_STORE_SETUP_MOBILE: str = _str("SIM_STORE_SETUP_MOBILE", USER_PHONE_NUMBER)
SIM_STORE_SETUP_START_TIME: str = _str("SIM_STORE_SETUP_START_TIME", "07:00")
SIM_STORE_SETUP_CLOSING_TIME: str = _str("SIM_STORE_SETUP_CLOSING_TIME", "23:59")
SIM_STORE_SETUP_STATUS: int = _int("SIM_STORE_SETUP_STATUS", 1)
SIM_STORE_SETUP_ADDRESS: str = _str("SIM_STORE_SETUP_ADDRESS", "Simulator address")
SIM_STORE_SETUP_CITY: str = _str("SIM_STORE_SETUP_CITY", "")
SIM_STORE_SETUP_STATE: str = _str("SIM_STORE_SETUP_STATE", "")
SIM_STORE_SETUP_COUNTRY: str = _str("SIM_STORE_SETUP_COUNTRY", "")
SIM_MENU_CATEGORY_NAME: str = _str("SIM_MENU_CATEGORY_NAME", "Simulator")
SIM_MENU_NAME: str = _str("SIM_MENU_NAME", "Simulator item")
SIM_MENU_DESCRIPTION: str = _str(
    "SIM_MENU_DESCRIPTION",
    "Menu item created by simulator.",
)
SIM_MENU_PRICE: float = _float("SIM_MENU_PRICE", 100.0)
SIM_MENU_INGREDIENTS: str = _str("SIM_MENU_INGREDIENTS", "simulator ingredients")
SIM_MENU_DISCOUNT: float = _float("SIM_MENU_DISCOUNT", 0.0)
SIM_MENU_DISCOUNT_PRICE: float = _float("SIM_MENU_DISCOUNT_PRICE", 0.0)
SIM_LAT: float | None = _optional_float("SIM_LAT")
SIM_LNG: float | None = _optional_float("SIM_LNG")
SIM_LOCATION_RADIUS: int = _int("SIM_LOCATION_RADIUS", 1)

N_USERS: int = _int("N_USERS", 1)
ORDER_INTERVAL_SECONDS: float = _float("ORDER_INTERVAL_SECONDS", 30.0)
REJECT_RATE: float = _float("REJECT_RATE", 0.1)
SIM_ORDERS: int = _int("SIM_ORDERS", 1)
SIM_CONTINUOUS: bool = _bool("SIM_CONTINUOUS", False)

USER_DECISION_POLL_INTERVAL_SECONDS: float = _float(
    "USER_DECISION_POLL_INTERVAL_SECONDS", 5.0
)
USER_DECISION_POLL_MAX_ATTEMPTS: int = _int("USER_DECISION_POLL_MAX_ATTEMPTS", 60)
ORDER_PROCESSING_POLL_INTERVAL_SECONDS: float = _float(
    "ORDER_PROCESSING_POLL_INTERVAL_SECONDS", 5.0
)
ORDER_PROCESSING_POLL_MAX_ATTEMPTS: int = _int("ORDER_PROCESSING_POLL_MAX_ATTEMPTS", 60)
SIM_WEBSOCKET_CONNECT_GRACE_SECONDS: float = _float(
    "SIM_WEBSOCKET_CONNECT_GRACE_SECONDS", 1.0
)
SIM_WEBSOCKET_DRAIN_SECONDS: float = _float("SIM_WEBSOCKET_DRAIN_SECONDS", 3.0)
SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS: float = _float(
    "SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS", 20.0
)

ALL_USERS: bool = False
SIM_STORE_EXPLICIT: bool = False
SIM_ACTORS: dict[str, Any] = {"defaults": {}, "users": [], "stores": []}

# ---------------------------------------------------------------------------
# sim_actors.json loader
# ---------------------------------------------------------------------------

SIM_ACTORS_PATH: Path = Path(__file__).parent / "sim_actors.json"


def actor_gps(actor: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not actor:
        return None, None
    lat = actor.get("lat")
    lng = actor.get("lng")
    gps = actor.get("gps")
    if isinstance(gps, dict):
        lat = lat if lat is not None else gps.get("lat", gps.get("latitude"))
        lng = lng if lng is not None else gps.get("lng", gps.get("longitude"))
    if lat in {None, "", 0, 0.0, "0", "0.0"} or lng in {None, "", 0, 0.0, "0", "0.0"}:
        return None, None
    return float(lat), float(lng)


def _find_actor_user(
    users: list[dict[str, Any]],
    role: str | None,
    phone: str | None = None,
) -> dict[str, Any] | None:
    if role:
        for user in users:
            if str(user.get("role", "")).lower() == role:
                return user
    if phone:
        for user in users:
            if str(user.get("phone", "")) == phone:
                return user
    return users[0] if users else None


def _find_actor_store(
    stores: list[dict[str, Any]],
    store_id: str | None,
) -> dict[str, Any] | None:
    if store_id:
        for store in stores:
            if str(store.get("store_id", "")) == store_id:
                return store
    return stores[0] if stores else None


def apply_actor_selection(
    actors: dict[str, Any],
    *,
    user_role: str | None = None,
    store_id: str | None = None,
) -> None:
    """Apply actor defaults from sim_actors.json to config globals."""
    global USER_PHONE_NUMBER, STORE_ID, SUBENTITY_ID, STORE_CURRENCY, SIM_LAT, SIM_LNG
    global SIM_LOCATION_RADIUS, SIM_COUPON_ID

    defaults: dict[str, Any] = actors.get("defaults", {})
    users: list[dict[str, Any]] = actors.get("users", [])
    stores: list[dict[str, Any]] = actors.get("stores", [])

    requested_user_phone = USER_PHONE_NUMBER or defaults.get("user_phone")
    selected_user = _find_actor_user(
        users,
        user_role,
        str(requested_user_phone) if requested_user_phone else None,
    )
    if selected_user and user_role:
        USER_PHONE_NUMBER = str(selected_user.get("phone") or USER_PHONE_NUMBER)
    elif not USER_PHONE_NUMBER and defaults.get("user_phone"):
        USER_PHONE_NUMBER = str(defaults["user_phone"])
    elif selected_user and not USER_PHONE_NUMBER:
        USER_PHONE_NUMBER = str(selected_user.get("phone") or USER_PHONE_NUMBER)

    user_lat, user_lng = actor_gps(selected_user)
    if user_lat is not None and user_lng is not None:
        SIM_LAT = user_lat
        SIM_LNG = user_lng

    requested_store_id = store_id or STORE_ID or defaults.get("store_id")
    selected_store = _find_actor_store(stores, str(requested_store_id) if requested_store_id else None)
    if selected_store:
        STORE_ID = str(selected_store.get("store_id") or STORE_ID)
        if selected_store.get("subentity_id") is not None:
            SUBENTITY_ID = int(selected_store["subentity_id"])
        if selected_store.get("currency"):
            STORE_CURRENCY = str(selected_store["currency"]).lower()
    elif not STORE_ID and defaults.get("store_id"):
        STORE_ID = str(defaults["store_id"])

    if defaults.get("location_radius") is not None:
        SIM_LOCATION_RADIUS = int(defaults["location_radius"])
    if SIM_COUPON_ID is None and defaults.get("coupon_id") not in {None, ""}:
        SIM_COUPON_ID = int(defaults["coupon_id"])


def _has_plan_value(value: Any) -> bool:
    return value is not None and value != ""


def _plan_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _plan_string(value: Any) -> str:
    return str(value).strip()


def _plan_lower_string(value: Any) -> str:
    return _plan_string(value).lower()


def _plan_scenarios(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [item.strip().lower() for item in str(value).split(",") if item.strip()]


def _apply_plan_value(
    attr: str,
    value: Any,
    *,
    preserve: set[str],
    transform=lambda raw: raw,
) -> None:
    if attr in preserve or not _has_plan_value(value):
        return
    globals()[attr] = transform(value)


def _apply_plan_section(
    section: dict[str, Any],
    mapping: dict[str, tuple[str, Any]],
    *,
    preserve: set[str],
) -> None:
    for key, (attr, transform) in mapping.items():
        _apply_plan_value(attr, section.get(key), preserve=preserve, transform=transform)


def _planned_strict_value(plan: Any, *, preserve: set[str]) -> bool:
    if "SIM_STRICT_PLAN" in preserve:
        return SIM_STRICT_PLAN
    strict_value = getattr(plan, "rules", {}).get("strict_plan")
    if not _has_plan_value(strict_value):
        return SIM_STRICT_PLAN
    return _plan_bool(strict_value)


def apply_plan_defaults(plan: Any, *, preserve: set[str] | None = None) -> None:
    """Apply non-sensitive run-plan defaults to config globals.

    Values in ``preserve`` represent explicit CLI inputs and are not overwritten.
    """
    preserved = set(preserve or set())
    runtime = getattr(plan, "runtime_defaults", {}) or {}
    rules = getattr(plan, "rules", {}) or {}
    fixture_defaults = getattr(plan, "fixture_defaults", {}) or {}
    payment = getattr(plan, "payment_defaults", {}) or {}
    review = getattr(plan, "review_defaults", {}) or {}
    new_user = getattr(plan, "new_user_defaults", {}) or {}

    _apply_plan_section(
        runtime,
        {
            "flow": ("SIM_FLOW", _plan_lower_string),
            "mode": ("SIM_RUN_MODE", _plan_lower_string),
            "trace_suite": ("SIM_TRACE_SUITE", _plan_lower_string),
            "trace_scenarios": ("SIM_TRACE_SCENARIOS", _plan_scenarios),
            "timing_profile": ("SIM_TIMING_PROFILE", _plan_lower_string),
            "users": ("N_USERS", int),
            "orders": ("SIM_ORDERS", int),
            "interval_seconds": ("ORDER_INTERVAL_SECONDS", float),
            "reject_rate": ("REJECT_RATE", float),
            "continuous": ("SIM_CONTINUOUS", _plan_bool),
            "all_users": ("ALL_USERS", _plan_bool),
        },
        preserve=preserved,
    )
    _apply_plan_section(
        rules,
        {
            "strict_plan": ("SIM_STRICT_PLAN", _plan_bool),
            "run_app_probes": ("SIM_RUN_APP_PROBES", _plan_bool),
            "run_store_dashboard_probes": ("SIM_RUN_STORE_DASHBOARD_PROBES", _plan_bool),
            "run_post_order_actions": ("SIM_RUN_POST_ORDER_ACTIONS", _plan_bool),
            "app_autopilot": ("SIM_APP_AUTOPILOT", _plan_bool),
            "auto_select_store": ("SIM_AUTO_SELECT_STORE", _plan_bool),
            "auto_select_coupon": ("SIM_AUTO_SELECT_COUPON", _plan_bool),
            "auto_provision_fixtures": ("SIM_AUTO_PROVISION_FIXTURES", _plan_bool),
            "mutate_store_setup": ("SIM_MUTATE_STORE_SETUP", _plan_bool),
            "mutate_menu_setup": ("SIM_MUTATE_MENU_SETUP", _plan_bool),
            "auto_toggle_store_status": ("SIM_AUTO_TOGGLE_STORE_STATUS", _plan_bool),
            "store_open_status": ("SIM_STORE_OPEN_STATUS", int),
            "store_closed_status": ("SIM_STORE_CLOSED_STATUS", int),
        },
        preserve=preserved,
    )
    _apply_plan_section(
        payment,
        {
            "mode": ("SIM_PAYMENT_MODE", _plan_lower_string),
            "case": ("SIM_PAYMENT_CASE", _plan_lower_string),
            "free_order_amount": ("SIM_FREE_ORDER_AMOUNT", float),
            "coupon_id": ("SIM_COUPON_ID", int),
            "save_card": ("SIM_SAVE_CARD", _plan_bool),
            "test_payment_method": ("STRIPE_TEST_PAYMENT_METHOD", _plan_string),
        },
        preserve=preserved,
    )

    store_setup = fixture_defaults.get("store_setup", {}) if isinstance(fixture_defaults, dict) else {}
    if isinstance(store_setup, dict):
        _apply_plan_section(
            store_setup,
            {
                "name": ("SIM_STORE_SETUP_NAME", _plan_string),
                "branch": ("SIM_STORE_SETUP_BRANCH", _plan_string),
                "description": ("SIM_STORE_SETUP_DESCRIPTION", _plan_string),
                "mobile": ("SIM_STORE_SETUP_MOBILE", _plan_string),
                "start_time": ("SIM_STORE_SETUP_START_TIME", _plan_string),
                "closing_time": ("SIM_STORE_SETUP_CLOSING_TIME", _plan_string),
                "status": ("SIM_STORE_SETUP_STATUS", int),
                "address": ("SIM_STORE_SETUP_ADDRESS", _plan_string),
                "city": ("SIM_STORE_SETUP_CITY", _plan_string),
                "state": ("SIM_STORE_SETUP_STATE", _plan_string),
                "country": ("SIM_STORE_SETUP_COUNTRY", _plan_string),
            },
            preserve=preserved,
        )

    menu = fixture_defaults.get("menu", {}) if isinstance(fixture_defaults, dict) else {}
    if isinstance(menu, dict):
        _apply_plan_section(
            menu,
            {
                "category_name": ("SIM_MENU_CATEGORY_NAME", _plan_string),
                "name": ("SIM_MENU_NAME", _plan_string),
                "description": ("SIM_MENU_DESCRIPTION", _plan_string),
                "price": ("SIM_MENU_PRICE", float),
                "ingredients": ("SIM_MENU_INGREDIENTS", _plan_string),
                "discount": ("SIM_MENU_DISCOUNT", float),
                "discount_price": ("SIM_MENU_DISCOUNT_PRICE", float),
            },
            preserve=preserved,
        )

    _apply_plan_section(
        review,
        {
            "rating": ("SIM_REVIEW_RATING", int),
            "comment": ("SIM_REVIEW_COMMENT", _plan_string),
        },
        preserve=preserved,
    )
    _apply_plan_section(
        new_user,
        {
            "first_name": ("SIM_NEW_USER_FIRST_NAME", _plan_string),
            "last_name": ("SIM_NEW_USER_LAST_NAME", _plan_string),
            "email": ("SIM_NEW_USER_EMAIL", _plan_string),
        },
        preserve=preserved,
    )


def _resolve_sim_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate
    return Path(__file__).parent / candidate


def set_sim_actors_path(path: str | Path) -> None:
    global SIM_ACTORS_PATH
    SIM_ACTORS_PATH = _resolve_sim_path(path)


def load_sim_actors(
    path: str | Path | None = None,
    *,
    preserve: set[str] | None = None,
) -> dict[str, Any]:
    """Load actors from sim_actors.json and apply defaults to config globals.

    Returns ``{"users": [...], "stores": [...]}``.
    If the file does not exist, returns empty lists and leaves globals untouched.
    """
    actor_path = _resolve_sim_path(path) if path is not None else SIM_ACTORS_PATH
    global SIM_ACTORS
    if not actor_path.exists():
        SIM_ACTORS = {"defaults": {}, "users": [], "stores": []}
        return {"users": [], "stores": []}

    from run_plan import PlanValidationError, load_run_plan

    try:
        plan = load_run_plan(actor_path, strict=False)
        plan.validate(strict=_planned_strict_value(plan, preserve=set(preserve or set())))
        apply_plan_defaults(plan, preserve=preserve)
        actors = plan.to_actors()
    except PlanValidationError as exc:
        raise RuntimeError(f"Invalid simulator plan {actor_path}: {exc}") from exc
    SIM_ACTORS = actors
    apply_actor_selection(actors)
    return actors
