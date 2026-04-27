from __future__ import annotations

import os
from pathlib import Path
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
SIM_TRACE_SUITE: str = _str("SIM_TRACE_SUITE", "core").lower()
SIM_TRACE_SCENARIOS: list[str] = _csv("SIM_TRACE_SCENARIOS")
SIM_TIMING_PROFILE: str = _str("SIM_TIMING_PROFILE", "fast").lower()

SIM_PAYMENT_MODE: str = _str("SIM_PAYMENT_MODE", "stripe").lower()
SIM_FREE_ORDER_AMOUNT: float = _float("SIM_FREE_ORDER_AMOUNT", 0.0)
SIM_COUPON_ID: int | None = _optional_int("SIM_COUPON_ID")
SIM_SAVE_CARD: bool = _bool("SIM_SAVE_CARD", False)
STRIPE_SECRET_KEY: str = _str("STRIPE_SECRET_KEY")
STRIPE_TEST_PAYMENT_METHOD: str = _str("STRIPE_TEST_PAYMENT_METHOD", "pm_card_visa")
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
