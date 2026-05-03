"""Structured run recording and proof-oriented report generation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, TYPE_CHECKING

import config
from health import ascii_bar, build_health_summary
from interaction_catalog import catalogue_payload

if TYPE_CHECKING:
    import user_sim


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_run_folder_name(config_snapshot: dict[str, Any]) -> str:
    """Build descriptive folder name: 20260502T204500-doctor-FZY_926025-user5609"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Determine flow/scenario identifier
    flow = config_snapshot.get("flow") or ""
    trace_scenarios = config_snapshot.get("trace_scenarios") or []
    run_mode = config_snapshot.get("run_mode") or "load"

    if flow:
        flow_part = flow
    elif trace_scenarios:
        # Join multiple scenarios with underscore
        flow_part = "_".join(str(s) for s in trace_scenarios[:3])  # Limit to first 3
        if len(trace_scenarios) > 3:
            flow_part += "_plus"
    else:
        flow_part = run_mode

    # Sanitize flow_part: replace spaces and special chars
    flow_part = flow_part.replace(" ", "_").replace(",", "_")

    # Get store identifier
    store_id = config_snapshot.get("store_id") or ""
    auto_select_store = config_snapshot.get("auto_select_store", False)

    if store_id:
        store_part = store_id
    elif auto_select_store:
        store_part = "auto"
    else:
        store_part = "no-store"

    # Get user phone last 4 digits
    user_phone = config_snapshot.get("user_phone") or ""
    if user_phone:
        # Extract last 4 digits from phone number
        digits_only = "".join(c for c in str(user_phone) if c.isdigit())
        user_part = digits_only[-4:] if len(digits_only) >= 4 else digits_only
        if not user_part:
            user_part = "no-user"
    else:
        user_part = "no-user"

    return f"{timestamp}-{flow_part}-{store_part}-user{user_part}"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _table_row(values: list[Any]) -> str:
    escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
    return "| " + " | ".join(escaped) + " |"


def _to_inline_json(value: Any, *, limit: int = 500) -> str:
    if value is None:
        return ""
    text = json.dumps(_json_safe(value), ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class RunRecorder:
    def __init__(
        self,
        *,
        run_dir: Path,
        config_snapshot: dict[str, Any],
        fixtures_summary: dict[str, Any],
    ) -> None:
        self.run_dir = run_dir
        self.started_at = _utc_now()
        self.started_perf = time.perf_counter()
        self.finished_at: str | None = None
        self.config_snapshot = config_snapshot
        self.fixtures_summary = fixtures_summary
        self.events: list[dict[str, Any]] = []
        self.issues: list[dict[str, Any]] = []
        self.orders: dict[str, dict[str, Any]] = {}
        self.scenarios: dict[str, dict[str, Any]] = {}
        self.identity_context: dict[str, dict[str, Any]] = {
            "user": {
                "id": config.USER_ID,
                "name": "",
                "phone": getattr(config, "USER_PHONE_NUMBER", "") or "",
            },
            "store": {
                "subentity_id": config.SUBENTITY_ID,
                "login_id": config.STORE_ID,
                "name": "",
                "branch": "",
                "phone": "",
            },
        }
        self._next_event_id = 1
        self._next_issue_id = 1

    @classmethod
    def bootstrap(cls) -> "RunRecorder":
        root = Path(__file__).parent / "runs"

        # Build config snapshot first (needed for folder naming)
        config_snapshot = {
            "run_mode": getattr(config, "SIM_RUN_MODE", "load"),
            "flow": getattr(config, "SIM_FLOW", ""),
            "trace_suite": getattr(config, "SIM_TRACE_SUITE", ""),
            "trace_scenarios": getattr(config, "SIM_TRACE_SCENARIOS", []),
            "timing_profile": getattr(config, "SIM_TIMING_PROFILE", "fast"),
            "lastmile_base_url": config.LASTMILE_BASE_URL,
            "fainzy_base_url": config.FAINZY_BASE_URL,
            "payment_mode": config.SIM_PAYMENT_MODE,
            "payment_case": config.SIM_PAYMENT_CASE,
            "stripe_test_payment_method": config.STRIPE_TEST_PAYMENT_METHOD,
            "sim_save_card": config.SIM_SAVE_CARD,
            "sim_coupon_id": config.SIM_COUPON_ID,
            "sim_free_order_amount": config.SIM_FREE_ORDER_AMOUNT,
            "app_autopilot": config.SIM_APP_AUTOPILOT,
            "auto_select_store": config.SIM_AUTO_SELECT_STORE,
            "auto_select_coupon": config.SIM_AUTO_SELECT_COUPON,
            "auto_provision_fixtures": config.SIM_AUTO_PROVISION_FIXTURES,
            "mutate_store_setup": config.SIM_MUTATE_STORE_SETUP,
            "mutate_menu_setup": config.SIM_MUTATE_MENU_SETUP,
            "users": config.N_USERS,
            "orders": config.SIM_ORDERS,
            "continuous": config.SIM_CONTINUOUS,
            "interval_seconds": config.ORDER_INTERVAL_SECONDS,
            "reject_rate": config.REJECT_RATE,
            "user_id": config.USER_ID,
            "user_phone": getattr(config, "USER_PHONE_NUMBER", ""),
            "store_id": config.STORE_ID,
            "subentity_id": config.SUBENTITY_ID,
            "location_id": config.LOCATION_ID,
            "websocket_timeout_seconds": config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS,
            "interaction_catalogue": catalogue_payload(),
        }

        # Build descriptive folder name
        stamp = _build_run_folder_name(config_snapshot)

        return cls(
            run_dir=root / stamp,
            config_snapshot=config_snapshot,
            fixtures_summary={},
        )

    @classmethod
    def create(cls, fixtures: "user_sim.UserFixtures") -> "RunRecorder":
        recorder = cls.bootstrap()
        recorder.set_fixtures(fixtures)
        return recorder

    def set_fixtures(self, fixtures: "user_sim.UserFixtures") -> None:
        self.config_snapshot["user_id"] = fixtures.user_id
        self.config_snapshot["store_id"] = fixtures.store.get("id")
        self.config_snapshot["subentity_id"] = config.SUBENTITY_ID
        self.config_snapshot["location_id"] = fixtures.location.get("id")
        self.set_user_identity(user_id=fixtures.user_id)
        self.set_store_identity(
            subentity_id=fixtures.store.get("id"),
            name=fixtures.store.get("name"),
            branch=fixtures.store.get("branch"),
        )
        self.fixtures_summary = {
            "user_id": fixtures.user_id,
            "user_phone": self.identity_context.get("user", {}).get("phone", ""),
            "store": {
                "id": fixtures.store.get("id"),
                "name": fixtures.store.get("name"),
                "branch": fixtures.store.get("branch"),
                "phone": self.identity_context.get("store", {}).get("phone", ""),
                "currency": fixtures.store.get("currency"),
            },
            "location": {
                "id": fixtures.location.get("id"),
                "name": fixtures.location.get("name"),
                "address": fixtures.location.get("address")
                or fixtures.location.get("address_details"),
            },
            "menu_items_available": len(fixtures.menu_items),
            "currency": fixtures.currency,
        }

    def set_user_identity(
        self,
        *,
        user_id: int | None = None,
        name: str | None = None,
        phone: str | None = None,
        raw_user: dict[str, Any] | None = None,
    ) -> None:
        user = self.identity_context.setdefault("user", {})
        if user_id is not None:
            user["id"] = user_id
        if phone:
            user["phone"] = str(phone)
            self.config_snapshot["user_phone"] = str(phone)
        elif not user.get("phone"):
            user["phone"] = str(self.config_snapshot.get("user_phone") or "")
        resolved_name = name or self._user_name(raw_user)
        if resolved_name:
            user["name"] = resolved_name

    def set_store_identity(
        self,
        *,
        subentity_id: int | None = None,
        login_id: str | None = None,
        name: str | None = None,
        branch: str | None = None,
        phone: str | None = None,
        raw_store: dict[str, Any] | None = None,
    ) -> None:
        store = self.identity_context.setdefault("store", {})
        if subentity_id is not None:
            store["subentity_id"] = subentity_id
            self.config_snapshot["subentity_id"] = subentity_id
        if login_id:
            store["login_id"] = login_id
            self.config_snapshot["store_id"] = login_id
        if name:
            store["name"] = str(name)
        if branch:
            store["branch"] = str(branch)
        if phone:
            store["phone"] = str(phone)
        if raw_store:
            resolved_name = raw_store.get("name")
            resolved_branch = raw_store.get("branch")
            resolved_phone = raw_store.get("mobile_number") or raw_store.get("phone_number")
            if resolved_name and not store.get("name"):
                store["name"] = str(resolved_name)
            if resolved_branch and not store.get("branch"):
                store["branch"] = str(resolved_branch)
            if resolved_phone and not store.get("phone"):
                store["phone"] = str(resolved_phone)

    def _identity_snapshot(self) -> dict[str, Any]:
        user = self.identity_context.get("user", {})
        store = self.identity_context.get("store", {})
        return {
            "user": {
                "id": user.get("id"),
                "name": user.get("name") or "",
                "phone": user.get("phone") or "",
            },
            "store": {
                "subentity_id": store.get("subentity_id"),
                "login_id": store.get("login_id") or "",
                "name": store.get("name") or "",
                "branch": store.get("branch") or "",
                "phone": store.get("phone") or "",
            },
        }

    @staticmethod
    def _user_name(raw_user: dict[str, Any] | None) -> str:
        if not isinstance(raw_user, dict):
            return ""
        full_name = str(raw_user.get("name") or "").strip()
        if full_name:
            return full_name
        first = str(raw_user.get("first_name") or "").strip()
        last = str(raw_user.get("last_name") or "").strip()
        return " ".join(part for part in (first, last) if part).strip()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_perf) * 1000)

    def start_scenario(
        self,
        name: str,
        *,
        expected_final_status: str | None = None,
        note: str | None = None,
    ) -> None:
        scenario = self.scenarios.setdefault(
            name,
            {
                "name": name,
                "started_at": _utc_now(),
                "finished_at": None,
                "expected_final_status": expected_final_status,
                "actual_final_status": None,
                "base_verdict": "running",
                "order_db_id": None,
                "order_ref": None,
                "note": note,
                "identity": self._identity_snapshot(),
            },
        )
        if expected_final_status is not None:
            scenario["expected_final_status"] = expected_final_status
        if note is not None:
            scenario["note"] = note
        if not scenario.get("identity"):
            scenario["identity"] = self._identity_snapshot()

    def finish_scenario(
        self,
        name: str,
        *,
        verdict: str,
        actual_final_status: str | None,
        order_db_id: int | None = None,
        order_ref: str | None = None,
        note: str | None = None,
    ) -> None:
        self.start_scenario(name)
        scenario = self.scenarios[name]
        scenario["finished_at"] = _utc_now()
        scenario["base_verdict"] = verdict
        scenario["actual_final_status"] = actual_final_status
        if order_db_id is not None:
            scenario["order_db_id"] = order_db_id
        if order_ref is not None:
            scenario["order_ref"] = order_ref
        if note is not None:
            scenario["note"] = note

    def record_event(
        self,
        *,
        actor: str,
        action: str,
        category: str = "action",
        ok: bool = True,
        scenario: str | None = None,
        step: str | None = None,
        order_db_id: int | None = None,
        order_ref: str | None = None,
        status: str | None = None,
        expected_status: str | None = None,
        observed_status: str | None = None,
        method: str | None = None,
        endpoint: str | None = None,
        full_url: str | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        body_encoding: str | None = None,
        auth: dict[str, Any] | None = None,
        http_status: int | None = None,
        response_payload: Any = None,
        response_preview: str | None = None,
        latency_ms: int | None = None,
        planned_delay_ms: int | None = None,
        poll_attempt: int | None = None,
        expect_websocket: bool = False,
        track_order: bool = True,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "id": self._next_event_id,
            "ts": _utc_now(),
            "elapsed_ms": self.elapsed_ms(),
            "actor": actor,
            "action": action,
            "category": category,
            "ok": ok,
            "identity": self._identity_snapshot(),
        }
        self._next_event_id += 1
        if scenario is not None:
            event["scenario"] = scenario
            self.start_scenario(scenario)
        if step is not None:
            event["step"] = step
        if order_db_id is not None:
            event["order_db_id"] = order_db_id
        if order_ref is not None:
            event["order_ref"] = order_ref
        if status is not None:
            event["status"] = status
        if expected_status is not None:
            event["expected_status"] = expected_status
        if observed_status is not None:
            event["observed_status"] = observed_status
        if method is not None:
            event["method"] = method
        if endpoint is not None:
            event["endpoint"] = endpoint
        if full_url is not None:
            event["full_url"] = full_url
        if query_params is not None:
            event["query_params"] = _json_safe(query_params)
        if body is not None:
            event["body"] = _json_safe(body)
        if body_encoding is not None:
            event["body_encoding"] = body_encoding
        if auth is not None:
            event["auth"] = _json_safe(auth)
        if http_status is not None:
            event["http_status"] = http_status
        if response_payload is not None:
            event["response_payload"] = _json_safe(response_payload)
        if response_preview is not None:
            event["response_preview"] = response_preview
        if latency_ms is not None:
            event["latency_ms"] = latency_ms
        if planned_delay_ms is not None:
            event["planned_delay_ms"] = planned_delay_ms
        if poll_attempt is not None:
            event["poll_attempt"] = poll_attempt
        if expect_websocket:
            event["expect_websocket"] = True
        if details:
            event["details"] = _json_safe(details)

        self.events.append(event)
        if scenario is not None:
            scenario_record = self.scenarios[scenario]
            if order_db_id is not None and scenario_record.get("order_db_id") is None:
                scenario_record["order_db_id"] = order_db_id
            if order_ref is not None and scenario_record.get("order_ref") is None:
                scenario_record["order_ref"] = order_ref
        if track_order and order_db_id is not None:
            self._touch_order(order_db_id, order_ref=order_ref, event=event)
        return event

    def record_issue(
        self,
        *,
        severity: str,
        code: str,
        message: str,
        actor: str | None = None,
        scenario: str | None = None,
        step: str | None = None,
        order_db_id: int | None = None,
        order_ref: str | None = None,
        related_event_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        issue: dict[str, Any] = {
            "id": self._next_issue_id,
            "ts": _utc_now(),
            "elapsed_ms": self.elapsed_ms(),
            "severity": severity,
            "code": code,
            "message": message,
            "identity": self._identity_snapshot(),
        }
        self._next_issue_id += 1
        if actor is not None:
            issue["actor"] = actor
        if scenario is not None:
            issue["scenario"] = scenario
            self.start_scenario(scenario)
        if step is not None:
            issue["step"] = step
        if order_db_id is not None:
            issue["order_db_id"] = order_db_id
        if order_ref is not None:
            issue["order_ref"] = order_ref
        if related_event_id is not None:
            issue["related_event_id"] = related_event_id
        if details:
            issue["details"] = _json_safe(details)
        self.issues.append(issue)
        return issue

    def record_websocket(
        self,
        *,
        source: str,
        raw: str,
        payload: Any,
        nested: Any,
        order_db_id: int | None,
        order_ref: str | None,
        status: str | None,
    ) -> None:
        scenario = self._scenario_for_order(order_db_id, order_ref)
        self.record_event(
            actor="websocket",
            action="message",
            category="websocket",
            scenario=scenario,
            order_db_id=order_db_id,
            order_ref=order_ref,
            observed_status=status,
            track_order=False,
            details={
                "source": source,
                "payload": payload,
                "message": nested,
                "raw": raw[:2000],
            },
        )

    def _scenario_for_order(
        self,
        order_db_id: int | None,
        order_ref: str | None,
    ) -> str | None:
        for event in reversed(self.events):
            if event.get("scenario") is None:
                continue
            if order_db_id is not None and event.get("order_db_id") == order_db_id:
                return event.get("scenario")
            if order_ref is not None and event.get("order_ref") == order_ref:
                return event.get("scenario")
        return None

    def _touch_order(
        self,
        order_db_id: int,
        *,
        order_ref: str | None,
        event: dict[str, Any],
    ) -> None:
        key = str(order_db_id)
        order = self.orders.setdefault(
            key,
            {
                "order_db_id": order_db_id,
                "order_ref": order_ref,
                "statuses": [],
                "final_status": None,
                "identity": event.get("identity") or self._identity_snapshot(),
            },
        )
        if order_ref and not order.get("order_ref"):
            order["order_ref"] = order_ref
        if not order.get("identity"):
            order["identity"] = event.get("identity") or self._identity_snapshot()
        status = event.get("observed_status") or event.get("status")
        if status:
            statuses = order["statuses"]
            if not statuses or statuses[-1]["status"] != status:
                statuses.append(
                    {
                        "status": status,
                        "actor": event["actor"],
                        "action": event["action"],
                        "scenario": event.get("scenario"),
                        "step": event.get("step"),
                        "elapsed_ms": event["elapsed_ms"],
                    }
                )
            order["final_status"] = status

    def write(self) -> tuple[Path, Path, Path]:
        self.finished_at = _utc_now()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        events_path = self.run_dir / "events.json"
        report_path = self.run_dir / "report.md"
        story_path = self.run_dir / "story.md"
        events_path.write_text(
            json.dumps(
                {
                    "run": {
                        "started_at": self.started_at,
                        "finished_at": self.finished_at,
                        "duration_ms": self.elapsed_ms(),
                        "config": self.config_snapshot,
                        "fixtures": self.fixtures_summary,
                    },
                    "scenarios": list(self.scenarios.values()),
                    "orders": list(self.orders.values()),
                    "events": self.events,
                    "issues": self.issues,
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        report_path.write_text(self._render_markdown(), encoding="utf-8")
        story_path.write_text(self._render_story(), encoding="utf-8")
        return events_path, report_path, story_path

    def _scenario_records(self) -> list[dict[str, Any]]:
        if self.scenarios:
            return list(self.scenarios.values())
        return []

    def _scenario_effective_verdict(self, scenario: dict[str, Any]) -> str:
        base = scenario.get("base_verdict") or "unknown"
        if base == "unsupported":
            return "unsupported"
        expected = scenario.get("expected_final_status")
        actual = scenario.get("actual_final_status")
        if base == "passed" and expected and actual != expected:
            return "blocked"
        issues = self._issues_for_scenario(scenario)
        if any(item.get("severity") == "error" for item in issues):
            return "blocked"
        if any(item.get("severity") == "warning" for item in issues):
            return "degraded"
        return base

    def _issues_for_scenario(self, scenario: dict[str, Any]) -> list[dict[str, Any]]:
        name = scenario["name"]
        order_db_id = scenario.get("order_db_id")
        order_ref = scenario.get("order_ref")
        matches: list[dict[str, Any]] = []
        for issue in self.issues:
            if issue.get("scenario") == name:
                matches.append(issue)
                continue
            if order_db_id is not None and issue.get("order_db_id") == order_db_id:
                matches.append(issue)
                continue
            if order_ref is not None and issue.get("order_ref") == order_ref:
                matches.append(issue)
        return matches

    def _lookup_event(self, event_id: int | None) -> dict[str, Any] | None:
        if event_id is None:
            return None
        for event in self.events:
            if event["id"] == event_id:
                return event
        return None

    def _identity_for_order(self, order: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(order, dict):
            identity = order.get("identity")
            if isinstance(identity, dict):
                return identity
        return self._identity_snapshot()

    def _identity_for_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        identity = scenario.get("identity")
        if isinstance(identity, dict):
            return identity
        order_db_id = scenario.get("order_db_id")
        if order_db_id is not None:
            order = self.orders.get(str(order_db_id))
            if order:
                return self._identity_for_order(order)
        return self._identity_snapshot()

    def _identity_for_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        identity = issue.get("identity")
        if isinstance(identity, dict):
            return identity
        order_db_id = issue.get("order_db_id")
        if order_db_id is not None:
            order = self.orders.get(str(order_db_id))
            if order:
                return self._identity_for_order(order)
        if issue.get("scenario"):
            scenario = self.scenarios.get(str(issue["scenario"]))
            if scenario:
                return self._identity_for_scenario(scenario)
        return self._identity_snapshot()

    @staticmethod
    def _identity_user_text(identity: dict[str, Any]) -> str:
        user = identity.get("user", {}) if isinstance(identity, dict) else {}
        return " / ".join(
            part
            for part in [
                str(user.get("id") or "").strip(),
                str(user.get("name") or "").strip(),
                str(user.get("phone") or "").strip(),
            ]
            if part
        )

    @staticmethod
    def _identity_store_text(identity: dict[str, Any]) -> str:
        store = identity.get("store", {}) if isinstance(identity, dict) else {}
        return " / ".join(
            part
            for part in [
                str(store.get("subentity_id") or "").strip(),
                str(store.get("login_id") or "").strip(),
                str(store.get("name") or "").strip(),
                str(store.get("branch") or "").strip(),
                str(store.get("phone") or "").strip(),
            ]
            if part
        )

    def _render_markdown(self) -> str:
        actor_counts = Counter(event["actor"] for event in self.events)
        terminal = Counter(
            order.get("final_status") or "unknown" for order in self.orders.values()
        )
        scenarios = self._scenario_records()
        lines = [
            "# Fainzy Simulation Run",
            "",
            *self._render_health_sections(),
            "## Summary",
            _table_row(["Metric", "Value"]),
            _table_row(["---", "---"]),
            _table_row(["Started", self.started_at]),
            _table_row(["Finished", self.finished_at or ""]),
            _table_row(["Duration", f"{self.elapsed_ms() / 1000:.1f}s"]),
            _table_row(["Run mode", self.config_snapshot.get("run_mode", "load")]),
            _table_row(["Timing profile", self.config_snapshot.get("timing_profile", "")]),
            _table_row(["Orders", len(self.orders)]),
            _table_row(["Terminal statuses", dict(terminal)]),
            _table_row(["Events", len(self.events)]),
            _table_row(["Issues", len(self.issues)]),
            "",
        ]

        if scenarios:
            lines.extend(
                [
                    "## Scenario Verdicts",
                    _table_row(
                        [
                            "Scenario",
                            "Expected",
                            "Actual",
                            "Verdict",
                            "Order",
                            "User",
                            "Store",
                            "Note",
                        ]
                    ),
                    _table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
                ]
            )
            for scenario in scenarios:
                identity = self._identity_for_scenario(scenario)
                lines.append(
                    _table_row(
                        [
                            scenario["name"],
                            scenario.get("expected_final_status", ""),
                            scenario.get("actual_final_status", ""),
                            self._scenario_effective_verdict(scenario),
                            scenario.get("order_db_id") or scenario.get("order_ref") or "",
                            self._identity_user_text(identity),
                            self._identity_store_text(identity),
                            scenario.get("note", "") or "",
                        ]
                    )
                )
            lines.append("")

        lines.extend(
            [
                "## Order Lifecycle",
                _table_row(["Order ID", "Reference", "Final", "User", "Store", "Status path"]),
                _table_row(["---", "---", "---", "---", "---", "---"]),
            ]
        )
        if self.orders:
            for order in self.orders.values():
                identity = self._identity_for_order(order)
                path = " -> ".join(item["status"] for item in order["statuses"])
                lines.append(
                    _table_row(
                        [
                            order["order_db_id"],
                            order.get("order_ref") or "",
                            order.get("final_status") or "",
                            self._identity_user_text(identity),
                            self._identity_store_text(identity),
                            path,
                        ]
                    )
                )
        else:
            lines.append(_table_row(["none", "", "", "", "", ""]))
        lines.append("")

        lines.extend(
            [
                "## Websocket Assertions",
                _table_row(
                    [
                        "Scenario",
                        "Order",
                        "Status",
                        "Matched",
                        "Source",
                        "Latency",
                        "User",
                        "Store",
                    ]
                ),
                _table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
            ]
        )
        expected_events = [
            event
            for event in self.events
            if event.get("expect_websocket") and event.get("order_db_id") is not None
        ]
        if expected_events:
            for event in expected_events:
                match = event.get("websocket_match") or {}
                identity = event.get("identity") or self._identity_snapshot()
                lines.append(
                    _table_row(
                        [
                            event.get("scenario", ""),
                            event.get("order_db_id", ""),
                            event.get("observed_status")
                            or event.get("status")
                            or event.get("expected_status")
                            or "",
                            "yes" if match.get("matched") else "no",
                            match.get("source", ""),
                            f"{match['latency_ms']}ms" if "latency_ms" in match else "",
                            self._identity_user_text(identity),
                            self._identity_store_text(identity),
                        ]
                    )
                )
        else:
            lines.append(_table_row(["none", "", "", "", "", "", "", ""]))
        lines.append("")

        lines.extend(
            [
                "## Developer Findings",
                _table_row(
                    [
                        "Severity",
                        "Impact",
                        "Scenario",
                        "Code",
                        "Request",
                        "User",
                        "Store",
                        "Message",
                    ]
                ),
                _table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
            ]
        )
        if self.issues:
            for issue in self.issues:
                related = self._lookup_event(issue.get("related_event_id"))
                identity = self._identity_for_issue(issue)
                request = ""
                if related is not None:
                    request = " ".join(
                        part
                        for part in [
                            related.get("method", ""),
                            related.get("endpoint", ""),
                            f"HTTP {related.get('http_status')}"
                            if related.get("http_status") is not None
                            else "",
                        ]
                        if part
                    )
                impact = "blocked" if issue["severity"] == "error" else "degraded"
                lines.append(
                    _table_row(
                        [
                            issue["severity"],
                            impact,
                            issue.get("scenario", ""),
                            issue["code"],
                            request,
                            self._identity_user_text(identity),
                            self._identity_store_text(identity),
                            issue["message"],
                        ]
                    )
                )
        else:
            lines.append(_table_row(["none", "", "", "", "", "", "", ""]))
        lines.append("")

        lines.append("## Technical Trace")
        lines.append("")
        scenario_names = [None, *[item["name"] for item in scenarios]] if scenarios else [None]
        for scenario_name in scenario_names:
            title = scenario_name or "bootstrap"
            lines.append(f"### Scenario `{title}`")
            if scenario_name is None:
                group = [event for event in self.events if event.get("scenario") is None]
            else:
                group = [event for event in self.events if event.get("scenario") == scenario_name]
            if not group:
                lines.append("")
                lines.append("No events were recorded.")
                lines.append("")
                continue
            for index, event in enumerate(group, start=1):
                status_text = event.get("observed_status") or event.get("status") or ""
                request_text = " ".join(
                    part
                    for part in [
                        event.get("method", ""),
                        event.get("full_url", event.get("endpoint", "")),
                    ]
                    if part
                )
                response_bits = []
                if event.get("http_status") is not None:
                    response_bits.append(f"HTTP {event['http_status']}")
                if event.get("response_preview"):
                    response_bits.append(event["response_preview"])
                auth = event.get("auth") or {}
                auth_text = ""
                if auth:
                    auth_text = " / ".join(
                        part
                        for part in [
                            auth.get("header_name", ""),
                            auth.get("scheme", ""),
                            auth.get("source", ""),
                            auth.get("fingerprint", ""),
                            auth.get("preview", ""),
                        ]
                        if part
                    )
                delay_text = ""
                if event.get("planned_delay_ms") is not None:
                    delay_text = f"{event['planned_delay_ms']}ms"
                elif event.get("latency_ms") is not None:
                    delay_text = f"{event['latency_ms']}ms"
                ws_match = event.get("websocket_match") or {}
                websocket_text = ""
                if event.get("expect_websocket"):
                    if ws_match.get("matched"):
                        websocket_text = (
                            f"matched via {ws_match.get('source', 'unknown')} "
                            f"in {ws_match.get('latency_ms', '')}ms"
                        )
                    else:
                        websocket_text = "expected but not matched"

                lines.extend(
                    [
                        f"#### {index}. {event['actor']} :: {event['action']}",
                        _table_row(["Field", "Value"]),
                        _table_row(["---", "---"]),
                        _table_row(["Event id", event["id"]]),
                        _table_row(["Time", f"{event['elapsed_ms'] / 1000:.1f}s"]),
                        _table_row(["Category", event["category"]]),
                        _table_row(["Step", event.get("step", "")]),
                        _table_row(["Order", event.get("order_db_id") or event.get("order_ref") or ""]),
                        _table_row(["Expected status", event.get("expected_status", "")]),
                        _table_row(["Observed status", status_text]),
                        _table_row(["Request", request_text]),
                        _table_row(["Auth proof", auth_text]),
                        _table_row(["Payload", _to_inline_json(event.get("body"))]),
                        _table_row(["Response", " | ".join(part for part in response_bits if part)]),
                        _table_row(["Delay / latency", delay_text]),
                        _table_row(["Websocket proof", websocket_text]),
                        _table_row(["Extra", _to_inline_json(event.get("details"))]),
                        "",
                    ]
                )

        lines.extend(
            [
                "## UI Mapping Appendix",
                "",
                "- `robot_arrived_for_delivery` maps to the user app's Receive Order button in the order details screen, which opens the QR/NFC handoff flow.",
                "- The simulator verifies that a receive code exists before backend completion so the handoff step is proven without inventing a fake customer mutation.",
                "- `completed` is a backend terminal status. The codebase exposes a `CompletedOrderScreen`, but the handoff proof still comes from the receive-code flow and terminal backend state.",
                "",
                "## Actor Events",
                _table_row(["Actor", "Events"]),
                _table_row(["---", "---"]),
            ]
        )
        for actor, count in actor_counts.items():
            lines.append(_table_row([actor, count]))

        lines.extend(
            [
                "",
                "## Fixtures And Config",
                _table_row(["Field", "Value"]),
                _table_row(["---", "---"]),
            ]
        )
        for key, value in {**self.fixtures_summary, **self.config_snapshot}.items():
            lines.append(_table_row([key, value]))

        return "\n".join(lines) + "\n"

    def _health_summary(self) -> dict[str, Any]:
        scenarios = []
        for scenario in self._scenario_records():
            item = dict(scenario)
            item["effective_verdict"] = self._scenario_effective_verdict(scenario)
            scenarios.append(item)
        return build_health_summary(
            duration_ms=self.elapsed_ms(),
            scenarios=scenarios,
            orders=list(self.orders.values()),
            events=self.events,
            issues=self.issues,
        )

    def _render_health_sections(self) -> list[str]:
        summary = self._health_summary()
        issue_counts = summary["issue_counts"]
        http = summary["http"]
        websockets = summary["websockets"]
        order_statuses = summary["order_final_statuses"]
        max_bar = max(
            [
                http["count"],
                websockets["expected"],
                sum(issue_counts.values()),
                summary["order_count"],
                1,
            ]
        )
        lines = [
            "## Daily Doctor Summary",
            _table_row(["Metric", "Value"]),
            _table_row(["---", "---"]),
            _table_row(["Verdict", str(summary["verdict"]).upper()]),
            _table_row(["Duration", f"{summary['duration_seconds']}s"]),
            _table_row(["Scenarios", summary["scenario_count"]]),
            _table_row(["Orders", summary["order_count"]]),
            _table_row(["Order final statuses", order_statuses or "none"]),
            _table_row(["HTTP calls", http["count"]]),
            _table_row(["HTTP status groups", http["status_groups"] or "none"]),
            _table_row(["HTTP latency p50/p95/max", f"{http['latency_ms']['p50']}ms / {http['latency_ms']['p95']}ms / {http['latency_ms']['max']}ms"]),
            _table_row(["Websocket matches", f"{websockets['matched']}/{websockets['expected']} ({websockets['match_rate']:.0%})"]),
            _table_row(["Issues", issue_counts or "none"]),
            "",
            "## Graphical Summary",
            _table_row(["Signal", "Count", "Bar"]),
            _table_row(["---", "---", "---"]),
            _table_row(["Orders", summary["order_count"], ascii_bar(summary["order_count"], maximum=max_bar)]),
            _table_row(["HTTP calls", http["count"], ascii_bar(http["count"], maximum=max_bar)]),
            _table_row(["Expected websocket events", websockets["expected"], ascii_bar(websockets["expected"], maximum=max_bar)]),
            _table_row(["Matched websocket events", websockets["matched"], ascii_bar(websockets["matched"], maximum=max_bar)]),
            _table_row(["Issues", sum(issue_counts.values()), ascii_bar(sum(issue_counts.values()), maximum=max_bar)]),
            "",
            "## Bottlenecks",
            _table_row(["Method", "Endpoint", "Calls", "Errors", "Avg", "P95", "Max"]),
            _table_row(["---", "---", "---", "---", "---", "---", "---"]),
        ]
        if http["endpoints"]:
            for item in http["endpoints"][:10]:
                latency = item["latency_ms"]
                lines.append(
                    _table_row(
                        [
                            item["method"],
                            item["endpoint"],
                            item["count"],
                            item["errors"],
                            f"{latency['avg']}ms",
                            f"{latency['p95']}ms",
                            f"{latency['max']}ms",
                        ]
                    )
                )
        else:
            lines.append(_table_row(["none", "", "", "", "", "", ""]))
        lines.append("")
        return lines

    def _render_story(self) -> str:
        lines = [
            "# Fainzy Simulation Story",
            "",
            "This report explains what the platform did in simple language.",
            "",
        ]
        scenarios = self._scenario_records()
        if not scenarios:
            lines.extend(
                [
                    "## Load Run",
                    "",
                    "This run used load mode, so it mixed multiple actions together instead of walking one fixed story at a time.",
                    "",
                ]
            )
            return "\n".join(lines) + "\n"

        for scenario in scenarios:
            verdict = self._scenario_effective_verdict(scenario)
            order_id = scenario.get("order_ref") or scenario.get("order_db_id") or "unknown order"
            actual = scenario.get("actual_final_status") or "unknown"
            lines.extend(
                [
                    f"## {scenario['name'].replace('_', ' ').title()}",
                    "",
                    f"Order `{order_id}` ended as `{actual}` with a `{verdict}` verdict.",
                    "",
                    self._story_summary_for_scenario(scenario),
                    "",
                    "Problems noticed:",
                ]
            )
            issues = self._issues_for_scenario(scenario)
            if issues:
                for issue in issues:
                    lines.append(f"- {issue['message']}")
            else:
                lines.append("- No problems were detected in this scenario.")
            lines.append("")
        return "\n".join(lines) + "\n"

    def _story_summary_for_scenario(self, scenario: dict[str, Any]) -> str:
        name = scenario["name"]
        if name == "completed":
            return (
                "The customer logged in, placed an order, the store accepted it, "
                "payment completed, the store marked it ready, the robot moved it "
                "through pickup and delivery, the platform exposed a receive code for "
                "handoff, and the order finished successfully."
            )
        if name == "rejected":
            return (
                "The customer placed an order, but the store rejected it before payment, "
                "so the order stopped early and no delivery flow should continue."
            )
        if name == "cancelled":
            return (
                "The customer placed an order and then cancelled it while it was still "
                "waiting for store action, so the platform should stop before payment "
                "or preparation begins."
            )
        if name == "auto_cancel":
            return (
                "The simulator intentionally left the order untouched to see whether the "
                "backend would cancel it on its own. This scenario is diagnostic and does "
                "not count as a core failure when the backend does not support it."
            )
        return "This scenario ran with a custom flow."
