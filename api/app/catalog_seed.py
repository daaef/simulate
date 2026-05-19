"""Idempotent catalog run profiles and schedule templates.

Set SIM_SKIP_CATALOG_SEED=1 to disable seeding (tests or air-gapped installs).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

PROFILE_SPECS: list[dict[str, Any]] = [
    {
        "catalog_slug": "api-sweep-max",
        "name": "API sweep max",
        "description": "Maximum single-run trace/API sweep: full suite plus explicit completed/rejected/cancelled/auto-cancel scenarios with websocket gates enforced.",
        "flow": "full",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "trace",
        "suite": "full",
        "scenarios": [
            "completed",
            "rejected",
            "cancelled",
            "auto_cancel",
        ],
        "post_order_actions": True,
        "enforce_websocket_gates": True,
        "strict_plan": False,
        "skip_app_probes": False,
        "skip_store_dashboard_probes": False,
        "no_auto_provision": False,
    },
    {
        "catalog_slug": "bounded-load-smoke",
        "name": "Bounded load smoke",
        "description": "Low-volume load smoke with guaranteed accepted baseline (>=1 completed) before reject/cancel tail checks.",
        "flow": "load",
        "plan": "sim_actors.json",
        "timing": "fast",
        "mode": "load",
        "suite": None,
        "scenarios": [],
        "users": 2,
        "orders": 3,
        "interval": 2.0,
        "reject": 0.35,
        "extra_args": [
            "--bounded-load-smoke-policy",
            "--bounded-baseline-min-completed",
            "1",
            "--bounded-baseline-max-attempts",
            "3",
            "--bounded-tail-cancel-rate",
            "0.15",
        ],
        "enforce_websocket_gates": False,
    },
]

# schedule spec keys:
# - catalog_slug
# - profile_catalog_slug
# - title
# - description
# - period / repeat / stop_rule / runs_per_period / all_day / run_slots / timezone
# - status
SCHEDULE_SPECS: list[dict[str, Any]] = [
    {
        "catalog_slug": "catalog-bounded-load-smoke-utc-0800",
        "profile_catalog_slug": "bounded-load-smoke",
        "title": "Catalog: Bounded load smoke (08:00 UTC daily, paused)",
        "description": "Paused template — resume in Schedules to enable automatic runs.",
        "period": "daily",
        "repeat": "daily",
        "stop_rule": "never",
        "runs_per_period": 1,
        "all_day": False,
        "run_slots": [{"time": "08:00"}],
        "timezone": "UTC",
        "status": "paused",
    },
    {
        "catalog_slug": "catalog-api-sweep-max-utc-3x-daily",
        "profile_catalog_slug": "api-sweep-max",
        "title": "Catalog: API sweep max (06:00 / 14:00 / 20:00 UTC daily, active)",
        "description": "Active baseline — runs a broad trace/API sweep three times daily.",
        "period": "daily",
        "repeat": "daily",
        "stop_rule": "never",
        "runs_per_period": 3,
        "all_day": False,
        "run_slots": [{"time": "06:00"}, {"time": "14:00"}, {"time": "20:00"}],
        "timezone": "UTC",
        "status": "active",
    },
]

ACTIVE_CATALOG_PROFILE_SLUGS = {spec["catalog_slug"] for spec in PROFILE_SPECS}
ACTIVE_CATALOG_SCHEDULE_SLUGS = {spec["catalog_slug"] for spec in SCHEDULE_SPECS}


def catalog_seed_skip_requested() -> bool:
    return os.getenv("SIM_SKIP_CATALOG_SEED", "").strip().lower() in {"1", "true", "yes"}


def _anchor_start_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()


def _profile_row_values(spec: dict[str, Any], now: str) -> dict[str, Any]:
    return {
        "catalog_slug": spec["catalog_slug"],
        "catalog_managed": 1,
        "status": "active",
        "archived_at": None,
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
        row = conn.execute("SELECT id, catalog_managed FROM run_profiles WHERE catalog_slug = ?", (slug,)).fetchone()
        v = _profile_row_values(spec, now)
        if row:
            if not bool(row["catalog_managed"]):
                continue
            conn.execute(
                """
                UPDATE run_profiles SET
                    status = ?, archived_at = ?, catalog_managed = ?,
                    name = ?, description = ?, flow = ?, plan = ?, timing = ?, mode = ?, suite = ?, scenarios = ?,
                    store_id = ?, phone = ?, all_users = ?, strict_plan = ?, skip_app_probes = ?,
                    skip_store_dashboard_probes = ?, no_auto_provision = ?, enforce_websocket_gates = ?,
                    post_order_actions = ?, users = ?, orders = ?, interval = ?, reject = ?, continuous = ?,
                    extra_args = ?, updated_at = ?
                WHERE catalog_slug = ?
                """,
                (
                    v["status"],
                    v["archived_at"],
                    v["catalog_managed"],
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
                    extra_args, status, archived_at, created_at, updated_at, catalog_slug, catalog_managed
                ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    v["status"],
                    v["archived_at"],
                    v["created_at"],
                    v["updated_at"],
                    slug,
                    v["catalog_managed"],
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
                cursor.execute("SELECT id, catalog_managed FROM run_profiles WHERE catalog_slug = %s", (slug,))
                exists = cursor.fetchone()
                if exists:
                    if not bool(exists[1]):
                        continue
                    cursor.execute(
                        """
                        UPDATE run_profiles SET
                            status = %s, archived_at = %s, catalog_managed = %s,
                            name = %s, description = %s, flow = %s, plan = %s, timing = %s, mode = %s, suite = %s,
                            scenarios = %s::jsonb, store_id = %s, phone = %s, all_users = %s, strict_plan = %s,
                            skip_app_probes = %s, skip_store_dashboard_probes = %s, no_auto_provision = %s,
                            enforce_websocket_gates = %s, post_order_actions = %s, users = %s, orders = %s,
                            interval = %s, reject = %s, continuous = %s, extra_args = %s::jsonb, updated_at = %s
                        WHERE catalog_slug = %s
                        """,
                        (
                            v["status"],
                            v["archived_at"],
                            bool(v["catalog_managed"]),
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
                            extra_args, status, archived_at, created_at, updated_at, catalog_slug, catalog_managed
                        ) VALUES (
                            NULL, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s
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
                            v["status"],
                            v["archived_at"],
                            v["created_at"],
                            v["updated_at"],
                            slug,
                            bool(v["catalog_managed"]),
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def _profile_id_for_catalog_slug(m: Any, slug: str) -> int | None:
    if m.USE_POSTGRES:
        conn = m._get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM run_profiles WHERE catalog_slug = %s AND catalog_managed = TRUE AND status <> %s",
                    (slug, "archived"),
                )
                row = cursor.fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else None
    with m.DB_LOCK, m._db() as conn:
        row = conn.execute(
            "SELECT id FROM run_profiles WHERE catalog_slug = ? AND catalog_managed = 1 AND status <> ?",
            (slug, "archived"),
        ).fetchone()
    return int(row["id"]) if row else None


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
    for spec in SCHEDULE_SPECS:
        sched_slug = str(spec["catalog_slug"])
        prof_slug = str(spec["profile_catalog_slug"])
        profile_id = _profile_id_for_catalog_slug(m, prof_slug)
        existing_id = _schedule_id_for_catalog_slug(m, sched_slug)
        if existing_id is not None:
            existing = m._get_schedule(existing_id)
            if not bool(existing.get("catalog_managed")):
                continue
        if profile_id is None:
            continue
        req = ScheduleUpsertRequest(
            name=str(spec["title"]),
            description=str(spec.get("description") or ""),
            schedule_type="simple",
            profile_id=profile_id,
            anchor_start_at=anchor,
            period=str(spec.get("period") or "daily"),
            stop_rule=str(spec.get("stop_rule") or "never"),
            repeat=str(spec.get("repeat") or "daily"),
            runs_per_period=max(1, int(spec.get("runs_per_period") or 1)),
            all_day=bool(spec.get("all_day")),
            run_slots=[dict(slot) for slot in (spec.get("run_slots") or [{"time": "08:00"}])],
            timezone=str(spec.get("timezone") or "UTC"),
            cadence="daily",
            campaign_steps=[],
        )
        status = str(spec.get("status") or "paused")
        if existing_id is not None:
            m._update_schedule(existing_id, req, None)
            m._persist_schedule_catalog_slug(existing_id, sched_slug)
            m._set_schedule_status(existing_id, status)
        else:
            created = m._create_schedule(req, None)
            sid = int(created["schedule"]["id"])
            m._persist_schedule_catalog_slug(sid, sched_slug)
            m._set_schedule_status(sid, status)


def _prune_retired_catalog(m: Any) -> None:
    """Retire catalog rows removed from PROFILE_SPECS / SCHEDULE_SPECS."""
    active_profiles = ACTIVE_CATALOG_PROFILE_SLUGS
    active_schedules = ACTIVE_CATALOG_SCHEDULE_SLUGS
    now = m._utc_now()

    if m.USE_POSTGRES:
        conn = m._get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, catalog_slug FROM run_profiles
                    WHERE catalog_slug IS NOT NULL AND catalog_managed = TRUE
                    """
                )
                for row_id, slug in cursor.fetchall():
                    if slug not in active_profiles:
                        cursor.execute(
                            "UPDATE run_profiles SET catalog_slug = NULL, updated_at = %s WHERE id = %s",
                            (now, row_id),
                        )
                cursor.execute(
                    """
                    SELECT id, catalog_slug FROM schedules
                    WHERE catalog_slug IS NOT NULL AND catalog_managed = TRUE
                    """
                )
                for row_id, slug in cursor.fetchall():
                    if slug not in active_schedules:
                        m._set_schedule_status(int(row_id), "disabled")
            conn.commit()
        finally:
            conn.close()
        return

    with m.DB_LOCK, m._db() as conn:
        rows = conn.execute(
            "SELECT id, catalog_slug FROM run_profiles WHERE catalog_slug IS NOT NULL AND catalog_managed = 1"
        ).fetchall()
        for row in rows:
            slug = row["catalog_slug"]
            if slug not in active_profiles:
                conn.execute(
                    "UPDATE run_profiles SET catalog_slug = NULL, updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
        sched_rows = conn.execute(
            "SELECT id, catalog_slug FROM schedules WHERE catalog_slug IS NOT NULL AND catalog_managed = 1"
        ).fetchall()
        conn.commit()

    for row in sched_rows:
        slug = row["catalog_slug"]
        if slug not in active_schedules:
            m._set_schedule_status(int(row["id"]), "disabled")


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
            conn.commit()
    _ensure_schedules(m)
    _prune_retired_catalog(m)
