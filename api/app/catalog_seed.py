"""Idempotent catalog run profiles and paused schedule templates.

Set SIM_SKIP_CATALOG_SEED=1 to disable seeding (tests or air-gapped installs).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

PROFILE_SPECS: list[dict[str, Any]] = [
    {
        "catalog_slug": "daily-doctor",
        "name": "Daily doctor",
        "description": "Default production health sweep (doctor suite, fast timing). Typical cost: full doctor trace.",
        "flow": "doctor",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "doctor",
        "scenarios": [],
        "enforce_websocket_gates": False,
    },
    {
        "catalog_slug": "gates-on-doctor",
        "name": "Gates-on doctor",
        "description": "Same coverage as Daily doctor with websocket gates enforced. Higher fidelity, may fail if WS path is degraded.",
        "flow": "doctor",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "doctor",
        "scenarios": [],
        "enforce_websocket_gates": True,
    },
    {
        "catalog_slug": "core-trace",
        "name": "Core trace",
        "description": "Fast proof of completed, rejected, and cancelled paths (core suite). Lower cost than full doctor.",
        "flow": "doctor",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "core",
        "scenarios": [],
        "enforce_websocket_gates": False,
    },
    {
        "catalog_slug": "bounded-load-smoke",
        "name": "Bounded load smoke",
        "description": "Low-volume load smoke (2 users, 3 orders, 2s interval). Short runtime; still hits load-mode paths.",
        "flow": "load",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "load",
        "suite": None,
        "scenarios": [],
        "users": 2,
        "orders": 3,
        "interval": 2.0,
        "reject": 0.1,
        "enforce_websocket_gates": False,
    },
    {
        "catalog_slug": "menu-gates",
        "name": "Menu gates",
        "description": "Menu-state trace (available, unavailable, sold out, store closed). Medium cost vs core trace.",
        "flow": "menus",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "menus",
        "scenarios": [],
        "enforce_websocket_gates": False,
    },
    {
        "catalog_slug": "weekly-full",
        "name": "Weekly full",
        "description": "Broadest standard trace suite (full). Use for weekly depth checks; longest runtime in this catalog.",
        "flow": "full",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "full",
        "scenarios": [],
        "enforce_websocket_gates": False,
    },
]

# schedule_catalog_slug -> profile_catalog_slug, schedule title
SCHEDULE_SPECS: list[tuple[str, str, str]] = [
    (
        "catalog-daily-doctor-utc-0800",
        "daily-doctor",
        "Catalog: Daily doctor (08:00 UTC daily, paused)",
    ),
    (
        "catalog-gates-on-doctor-utc-0800",
        "gates-on-doctor",
        "Catalog: Gates-on doctor (08:00 UTC daily, paused)",
    ),
    (
        "catalog-core-trace-utc-0800",
        "core-trace",
        "Catalog: Core trace (08:00 UTC daily, paused)",
    ),
    (
        "catalog-bounded-load-smoke-utc-0800",
        "bounded-load-smoke",
        "Catalog: Bounded load smoke (08:00 UTC daily, paused)",
    ),
    (
        "catalog-menu-gates-utc-0800",
        "menu-gates",
        "Catalog: Menu gates (08:00 UTC daily, paused)",
    ),
    (
        "catalog-weekly-full-utc-0800",
        "weekly-full",
        "Catalog: Weekly full (08:00 UTC daily, paused)",
    ),
]


def catalog_seed_skip_requested() -> bool:
    return os.getenv("SIM_SKIP_CATALOG_SEED", "").strip().lower() in {"1", "true", "yes"}


def _anchor_start_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()


def _profile_row_values(spec: dict[str, Any], now: str) -> dict[str, Any]:
    return {
        "catalog_slug": spec["catalog_slug"],
        "name": spec["name"],
        "description": spec.get("description"),
        "flow": spec["flow"],
        "plan": spec["plan"],
        "timing": spec["timing"],
        "mode": spec.get("mode"),
        "suite": spec.get("suite"),
        "scenarios": json.dumps(spec.get("scenarios") or []),
        "store_id": spec.get("store_id"),
        "phone": spec.get("phone"),
        "all_users": int(bool(spec.get("all_users"))),
        "strict_plan": int(bool(spec.get("strict_plan"))),
        "skip_app_probes": int(bool(spec.get("skip_app_probes"))),
        "skip_store_dashboard_probes": int(bool(spec.get("skip_store_dashboard_probes"))),
        "no_auto_provision": int(bool(spec.get("no_auto_provision"))),
        "enforce_websocket_gates": int(bool(spec.get("enforce_websocket_gates"))),
        "post_order_actions": spec.get("post_order_actions"),
        "users": spec.get("users"),
        "orders": spec.get("orders"),
        "interval": spec.get("interval"),
        "reject": spec.get("reject"),
        "continuous": int(bool(spec.get("continuous"))),
        "extra_args": json.dumps(spec.get("extra_args") or []),
        "created_at": now,
        "updated_at": now,
    }


def _upsert_profiles_sqlite(conn: Any, now: str) -> None:
    for spec in PROFILE_SPECS:
        slug = spec["catalog_slug"]
        row = conn.execute("SELECT id FROM run_profiles WHERE catalog_slug = ?", (slug,)).fetchone()
        v = _profile_row_values(spec, now)
        if row:
            conn.execute(
                """
                UPDATE run_profiles SET
                    name = ?, description = ?, flow = ?, plan = ?, timing = ?, mode = ?, suite = ?, scenarios = ?,
                    store_id = ?, phone = ?, all_users = ?, strict_plan = ?, skip_app_probes = ?,
                    skip_store_dashboard_probes = ?, no_auto_provision = ?, enforce_websocket_gates = ?,
                    post_order_actions = ?, users = ?, orders = ?, interval = ?, reject = ?, continuous = ?,
                    extra_args = ?, updated_at = ?
                WHERE catalog_slug = ?
                """,
                (
                    v["name"],
                    v["description"],
                    v["flow"],
                    v["plan"],
                    v["timing"],
                    v["mode"],
                    v["suite"],
                    v["scenarios"],
                    v["store_id"],
                    v["phone"],
                    v["all_users"],
                    v["strict_plan"],
                    v["skip_app_probes"],
                    v["skip_store_dashboard_probes"],
                    v["no_auto_provision"],
                    v["enforce_websocket_gates"],
                    v["post_order_actions"],
                    v["users"],
                    v["orders"],
                    v["interval"],
                    v["reject"],
                    v["continuous"],
                    v["extra_args"],
                    v["updated_at"],
                    slug,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO run_profiles (
                    user_id, name, description, flow, plan, timing, mode, suite, scenarios, store_id, phone,
                    all_users, strict_plan, skip_app_probes, skip_store_dashboard_probes, no_auto_provision,
                    enforce_websocket_gates, post_order_actions, users, orders, interval, reject, continuous,
                    extra_args, created_at, updated_at, catalog_slug
                ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    v["name"],
                    v["description"],
                    v["flow"],
                    v["plan"],
                    v["timing"],
                    v["mode"],
                    v["suite"],
                    v["scenarios"],
                    v["store_id"],
                    v["phone"],
                    v["all_users"],
                    v["strict_plan"],
                    v["skip_app_probes"],
                    v["skip_store_dashboard_probes"],
                    v["no_auto_provision"],
                    v["enforce_websocket_gates"],
                    v["post_order_actions"],
                    v["users"],
                    v["orders"],
                    v["interval"],
                    v["reject"],
                    v["continuous"],
                    v["extra_args"],
                    v["created_at"],
                    v["updated_at"],
                    slug,
                ),
            )


def _upsert_profiles_postgres(now: str) -> None:
    from api.app.main import _get_db_connection

    conn = _get_db_connection()
    try:
        with conn.cursor() as cursor:
            for spec in PROFILE_SPECS:
                slug = spec["catalog_slug"]
                v = _profile_row_values(spec, now)
                cursor.execute("SELECT id FROM run_profiles WHERE catalog_slug = %s", (slug,))
                exists = cursor.fetchone()
                if exists:
                    cursor.execute(
                        """
                        UPDATE run_profiles SET
                            name = %s, description = %s, flow = %s, plan = %s, timing = %s, mode = %s, suite = %s,
                            scenarios = %s::jsonb, store_id = %s, phone = %s, all_users = %s, strict_plan = %s,
                            skip_app_probes = %s, skip_store_dashboard_probes = %s, no_auto_provision = %s,
                            enforce_websocket_gates = %s, post_order_actions = %s, users = %s, orders = %s,
                            interval = %s, reject = %s, continuous = %s, extra_args = %s::jsonb, updated_at = %s
                        WHERE catalog_slug = %s
                        """,
                        (
                            v["name"],
                            v["description"],
                            v["flow"],
                            v["plan"],
                            v["timing"],
                            v["mode"],
                            v["suite"],
                            v["scenarios"],
                            v["store_id"],
                            v["phone"],
                            bool(v["all_users"]),
                            bool(v["strict_plan"]),
                            bool(v["skip_app_probes"]),
                            bool(v["skip_store_dashboard_probes"]),
                            bool(v["no_auto_provision"]),
                            bool(v["enforce_websocket_gates"]),
                            v["post_order_actions"],
                            v["users"],
                            v["orders"],
                            v["interval"],
                            v["reject"],
                            bool(v["continuous"]),
                            v["extra_args"],
                            v["updated_at"],
                            slug,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO run_profiles (
                            user_id, name, description, flow, plan, timing, mode, suite, scenarios, store_id, phone,
                            all_users, strict_plan, skip_app_probes, skip_store_dashboard_probes, no_auto_provision,
                            enforce_websocket_gates, post_order_actions, users, orders, interval, reject, continuous,
                            extra_args, created_at, updated_at, catalog_slug
                        ) VALUES (
                            NULL, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s::jsonb, %s, %s, %s
                        )
                        """,
                        (
                            v["name"],
                            v["description"],
                            v["flow"],
                            v["plan"],
                            v["timing"],
                            v["mode"],
                            v["suite"],
                            v["scenarios"],
                            v["store_id"],
                            v["phone"],
                            bool(v["all_users"]),
                            bool(v["strict_plan"]),
                            bool(v["skip_app_probes"]),
                            bool(v["skip_store_dashboard_probes"]),
                            bool(v["no_auto_provision"]),
                            bool(v["enforce_websocket_gates"]),
                            v["post_order_actions"],
                            v["users"],
                            v["orders"],
                            v["interval"],
                            v["reject"],
                            bool(v["continuous"]),
                            v["extra_args"],
                            v["created_at"],
                            v["updated_at"],
                            slug,
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def _profile_id_for_catalog_slug(m: Any, slug: str) -> int:
    if m.USE_POSTGRES:
        conn = m._get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM run_profiles WHERE catalog_slug = %s", (slug,))
                row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            raise RuntimeError(f"Catalog profile {slug!r} missing after seed upsert.")
        return int(row[0])
    with m.DB_LOCK, m._db() as conn:
        row = conn.execute("SELECT id FROM run_profiles WHERE catalog_slug = ?", (slug,)).fetchone()
    if not row:
        raise RuntimeError(f"Catalog profile {slug!r} missing after seed upsert.")
    return int(row["id"])


def _schedule_id_for_catalog_slug(m: Any, slug: str) -> int | None:
    if m.USE_POSTGRES:
        conn = m._get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM schedules WHERE catalog_slug = %s", (slug,))
                row = cursor.fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else None
    with m.DB_LOCK, m._db() as conn:
        row = conn.execute("SELECT id FROM schedules WHERE catalog_slug = ?", (slug,)).fetchone()
    return int(row["id"]) if row else None


def _ensure_schedules(m: Any) -> None:
    from api.app.schedules.models import ScheduleUpsertRequest

    anchor = _anchor_start_iso()
    desc = "Paused template — resume in Schedules to enable automatic runs."
    for sched_slug, prof_slug, title in SCHEDULE_SPECS:
        profile_id = _profile_id_for_catalog_slug(m, prof_slug)
        existing_id = _schedule_id_for_catalog_slug(m, sched_slug)
        req = ScheduleUpsertRequest(
            name=title,
            description=desc,
            schedule_type="simple",
            profile_id=profile_id,
            anchor_start_at=anchor,
            period="daily",
            stop_rule="never",
            repeat="daily",
            runs_per_period=1,
            all_day=False,
            run_slots=[{"time": "08:00"}],
            timezone="UTC",
            cadence="daily",
            campaign_steps=[],
        )
        if existing_id is not None:
            m._update_schedule(existing_id, req, None)
            m._persist_schedule_catalog_slug(existing_id, sched_slug)
            m._set_schedule_status(existing_id, "paused")
        else:
            created = m._create_schedule(req, None)
            sid = int(created["schedule"]["id"])
            m._persist_schedule_catalog_slug(sid, sched_slug)
            m._set_schedule_status(sid, "paused")


def ensure_catalog_seed() -> None:
    if catalog_seed_skip_requested():
        return
    from api.app import main as m

    now = m._utc_now()
    if m.USE_POSTGRES:
        _upsert_profiles_postgres(now)
    else:
        with m.DB_LOCK, m._db() as conn:
            _upsert_profiles_sqlite(conn, now)
    _ensure_schedules(m)
