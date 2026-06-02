"""Websocket observation and validation for simulator runs."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlparse

import websockets
from rich.console import Console

import config
from reporting import RunRecorder

console = Console()
REQUIRED_WEBSOCKET_SOURCES = frozenset({"user_orders", "store_orders", "store_stats"})


def _websocket_root() -> str:
    parsed = urlparse(config.LASTMILE_BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


def _decode_json(raw: str) -> Any:
    return json.loads(raw)


def _nested_message(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if isinstance(message, str):
        return _decode_json(message)
    if isinstance(message, dict):
        return message
    return None


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _extract_order_fields(payload: Any, nested: Any) -> tuple[int | None, str | None, str | None]:
    order_db_id: int | None = None
    order_ref: str | None = None
    status: str | None = None

    for item in _walk_dicts(nested if nested is not None else payload):
        if status is None:
            raw_status = (
                item.get("status")
                or item.get("order_status")
                or item.get("state")
            )
            if raw_status is not None:
                status = str(raw_status)

        raw_ref = (
            item.get("order_id")
            or item.get("order_ref")
            or item.get("orderId")
            or item.get("reference")
        )
        if order_ref is None and raw_ref is not None:
            order_ref = str(raw_ref)

        raw_id = (
            item.get("id")
            or item.get("order_db_id")
            or item.get("order_id_int")
            or item.get("orderIdInt")
        )
        if order_db_id is None and raw_id is not None:
            try:
                order_db_id = int(raw_id)
            except (TypeError, ValueError):
                pass

        if order_db_id is not None and order_ref is not None and status is not None:
            break

    return order_db_id, order_ref, status


class WebsocketObserver:
    def __init__(
        self,
        *,
        recorder: RunRecorder,
        user_id: int | str,
        store_id: int | str,
    ) -> None:
        self.recorder = recorder
        root = _websocket_root()
        self.targets = {
            "user_orders": (f"{root}/ws/soc/{user_id}/", ["websocket"]),
            "store_orders": (f"{root}/ws/soc/store_{store_id}/", None),
            "store_stats": (f"{root}/ws/soc/store_statistics_{store_id}/", None),
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._connection_errors: dict[str, int] = {}
        self._event_lock = asyncio.Lock()
        self._event_notifier = asyncio.Event()
        self._coverage_notifier = asyncio.Event()
        self._order_events: list[dict[str, Any]] = []
        self.coverage = {
            "user_orders": {
                "status": "not_started",
                "reason": None,
                "messages": 0,
                "url": self.targets["user_orders"][0],
            },
            "store_orders": {
                "status": "not_started",
                "reason": None,
                "messages": 0,
                "url": self.targets["store_orders"][0],
            },
            "store_stats": {
                "status": "not_started",
                "reason": None,
                "messages": 0,
                "url": self.targets["store_stats"][0],
            },
            "expected_order_events": 0,
            "matched_order_events": 0,
            "missed_order_events": 0,
        }

    def required_sources(self) -> set[str]:
        return set(REQUIRED_WEBSOCKET_SOURCES)

    def connected_sources(self, sources: set[str] | None = None) -> set[str]:
        required = set(sources or REQUIRED_WEBSOCKET_SOURCES)
        return {
            source
            for source in required
            if self.coverage.get(source, {}).get("status") == "connected"
        }

    def missing_sources(self, sources: set[str] | None = None) -> set[str]:
        required = set(sources or REQUIRED_WEBSOCKET_SOURCES)
        return required.difference(self.connected_sources(required))

    def _set_source_status(self, source: str, *, status: str, reason: str | None = None) -> None:
        if source not in self.coverage:
            return
        self.coverage[source]["status"] = status
        self.coverage[source]["reason"] = reason
        self._coverage_notifier.set()

    async def wait_for_order_status(
        self,
        *,
        order_db_id: int | None,
        order_ref: str | None,
        status: str,
        sources: set[str] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS)
        )
        expected_sources = set(sources or {"user_orders", "store_orders"})
        deadline = time.monotonic() + max(timeout, 0.1)

        if not order_db_id and not order_ref:
            raise RuntimeError("websocket gate requires order_db_id or order_ref")

        cursor = 0
        while True:
            async with self._event_lock:
                batch = self._order_events[cursor:]
                cursor = len(self._order_events)
            for event in batch:
                if expected_sources and event.get("source") not in expected_sources:
                    continue
                event_status = str(event.get("status") or "").strip().lower()
                if event_status != status.strip().lower():
                    continue
                if order_db_id is not None and event.get("order_db_id") == int(order_db_id):
                    return event
                if order_ref is not None and str(event.get("order_ref") or "") == str(order_ref):
                    return event

            if expected_sources:
                failed_sources = {
                    source
                    for source in expected_sources
                    if self.coverage.get(source, {}).get("status") == "failed"
                }
                if failed_sources == expected_sources:
                    raise RuntimeError(
                        "websocket_gate_source_unavailable:"
                        f" status={status} sources={sorted(expected_sources)}"
                    )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    "websocket_gate_timeout:"
                    f" status={status} order_db_id={order_db_id} order_ref={order_ref}"
                )
            self._event_notifier.clear()
            try:
                await asyncio.wait_for(self._event_notifier.wait(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    "websocket_gate_timeout:"
                    f" status={status} order_db_id={order_db_id} order_ref={order_ref}"
                ) from exc

    async def start(self) -> None:
        for source, (url, subprotocols) in self.targets.items():
            self._set_source_status(source, status="connecting")
            self._tasks.append(
                asyncio.create_task(self._listen(source, url, subprotocols))
            )

        if config.SIM_WEBSOCKET_CONNECT_GRACE_SECONDS > 0:
            await asyncio.sleep(config.SIM_WEBSOCKET_CONNECT_GRACE_SECONDS)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def coverage_summary(self) -> dict[str, Any]:
        return self.coverage

    async def wait_for_sources_connected(
        self,
        *,
        sources: set[str] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        required = set(sources or REQUIRED_WEBSOCKET_SOURCES)
        timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS)
        )
        deadline = time.monotonic() + max(timeout, 0.1)

        while True:
            missing = self.missing_sources(required)
            if not missing:
                return {
                    "required_sources": sorted(required),
                    "connected_sources": sorted(self.connected_sources(required)),
                    "coverage": {name: self.coverage.get(name, {}) for name in sorted(required)},
                }

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                statuses = {
                    source: (self.coverage.get(source) or {}).get("status")
                    for source in sorted(required)
                }
                raise RuntimeError(
                    "websocket_sources_timeout:"
                    f" required={sorted(required)} missing={sorted(missing)} statuses={statuses}"
                )
            self._coverage_notifier.clear()
            try:
                await asyncio.wait_for(self._coverage_notifier.wait(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                statuses = {
                    source: (self.coverage.get(source) or {}).get("status")
                    for source in sorted(required)
                }
                raise RuntimeError(
                    "websocket_sources_timeout:"
                    f" required={sorted(required)} missing={sorted(missing)} statuses={statuses}"
                ) from exc

    async def monitor_required_sources(
        self,
        *,
        sources: set[str] | None = None,
        retry_window_seconds: float | None = None,
    ) -> None:
        required = set(sources or REQUIRED_WEBSOCKET_SOURCES)
        retry_window = (
            float(retry_window_seconds)
            if retry_window_seconds is not None
            else float(config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS)
        )
        retry_window = max(0.1, retry_window)
        outage_started: float | None = None
        initial_missing = sorted(self.missing_sources(required))

        while True:
            missing = self.missing_sources(required)
            if not missing:
                if outage_started is not None:
                    self.recorder.record_event(
                        actor="websocket",
                        action="websocket_required_sources_recovered",
                        category="websocket_gate",
                        details={
                            "required_sources": sorted(required),
                            "retry_window_seconds": retry_window,
                        },
                        track_order=False,
                    )
                outage_started = None
            else:
                if outage_started is None:
                    outage_started = time.monotonic()
                    self.recorder.record_event(
                        actor="websocket",
                        action="websocket_required_sources_degraded",
                        category="websocket_gate",
                        details={
                            "required_sources": sorted(required),
                            "missing_sources": sorted(missing),
                            "retry_window_seconds": retry_window,
                            "initial_missing_sources": initial_missing,
                        },
                        track_order=False,
                    )
                elapsed = time.monotonic() - outage_started
                if elapsed >= retry_window:
                    statuses = {
                        source: (self.coverage.get(source) or {}).get("status")
                        for source in sorted(required)
                    }
                    raise RuntimeError(
                        "websocket_required_sources_timeout:"
                        f" required={sorted(required)} missing={sorted(missing)} "
                        f"retry_window_seconds={retry_window} statuses={statuses}"
                    )

            self._coverage_notifier.clear()
            try:
                await asyncio.wait_for(self._coverage_notifier.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

    async def _listen(
        self,
        source: str,
        url: str,
        subprotocols: list[str] | None,
    ) -> None:
        while True:
            try:
                if self.coverage.get(source, {}).get("status") != "connected":
                    self._set_source_status(source, status="connecting")
                async with websockets.connect(
                    url,
                    subprotocols=subprotocols,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:
                    console.print(f"[blue]websocket:[/] connected {source}")
                    self._set_source_status(source, status="connected")
                    self.recorder.record_event(
                        actor="websocket",
                        action="connected",
                        category="websocket_lifecycle",
                        details={"source": source, "url": url},
                    )
                    async for raw in websocket:
                        await self._handle_message(source, str(raw))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                count = self._connection_errors.get(source, 0) + 1
                self._connection_errors[source] = count
                self._set_source_status(source, status="failed", reason=str(exc))
                if count <= 3:
                    self.recorder.record_issue(
                        severity="warning",
                        code="websocket_connection_error",
                        actor="websocket",
                        message=f"{source} websocket connection failed: {exc}",
                        details={"source": source, "url": url},
                    )
                await asyncio.sleep(5)

    async def _handle_message(self, source: str, raw: str) -> None:
        try:
            payload = _decode_json(raw)
        except json.JSONDecodeError as exc:
            self.recorder.record_issue(
                severity="warning",
                code="websocket_malformed_json",
                actor="websocket",
                message=f"{source} websocket emitted malformed JSON: {exc}",
                details={"source": source, "raw": raw[:1000]},
            )
            return
        if source in self.coverage:
            self.coverage[source]["messages"] += 1
        try:
            nested = _nested_message(payload)
        except json.JSONDecodeError as exc:
            self.recorder.record_issue(
                severity="warning",
                code="websocket_malformed_message",
                actor="websocket",
                message=f"{source} websocket message field was malformed JSON: {exc}",
                details={"source": source, "payload": payload},
            )
            nested = None

        if source == "store_stats":
            order_db_id, order_ref, status = None, None, None
        else:
            order_db_id, order_ref, status = _extract_order_fields(payload, nested)
            if status and order_db_id is None and not order_ref:
                self.recorder.record_issue(
                    severity="warning",
                    code="websocket_gate_unattributed_event",
                    actor="websocket",
                    message=(
                        f"{source} websocket contained status={status} "
                        "without order_db_id/order_ref."
                    ),
                    details={"source": source, "payload": payload, "nested": nested},
                )
        self.recorder.record_websocket(
            source=source,
            raw=raw,
            payload=payload,
            nested=nested,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=status,
        )
        if source != "store_stats" and status and (order_db_id is not None or order_ref):
            gate_event = {
                "source": source,
                "status": str(status),
                "order_db_id": order_db_id,
                "order_ref": order_ref,
            }
            async with self._event_lock:
                self._order_events.append(gate_event)
            self._event_notifier.set()


def _unsupported_lifecycle_order_ids(recorder: RunRecorder) -> set[int]:
    skip: set[int] = set()
    for scenario in getattr(recorder, "scenarios", {}).values():
        if not isinstance(scenario, dict):
            continue
        if str(scenario.get("base_verdict") or "").strip().lower() != "unsupported":
            continue
        order_db_id = scenario.get("order_db_id")
        if order_db_id is None:
            continue
        try:
            skip.add(int(order_db_id))
        except (TypeError, ValueError):
            continue
    return skip


def validate_websocket_events(
    recorder: RunRecorder,
    *,
    strict: bool = False,
    require_lifecycle_proof: bool = False,
) -> dict[str, Any]:
    expected = [
        event
        for event in recorder.events
        if event.get("expect_websocket") and event.get("order_db_id") is not None
    ]
    websocket_events = [
        event for event in recorder.events if event.get("category") == "websocket"
    ]
    websocket_gate_events = [
        event
        for event in recorder.events
        if event.get("category") == "websocket_gate"
        and event.get("order_db_id") is not None
        and str(event.get("action") or "").endswith("_ok")
    ]
    skip_lifecycle_order_ids = _unsupported_lifecycle_order_ids(recorder)
    coverage = getattr(recorder, "websocket_coverage", None)
    if isinstance(coverage, dict):
        coverage["expected_order_events"] = len(expected)
    timeout_ms = int(config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS * 1000)
    early_tolerance_ms = 5000
    missing_count = 0
    late_count = 0
    lifecycle_missing_count = 0
    blocking_failures = 0
    issue_severity = "error" if strict else "warning"

    def _ws_matches(order_id: int, order_ref: str | None, status: str) -> list[dict[str, Any]]:
        normalized = str(status or "").strip().lower()
        if not normalized:
            return []
        matches = [
            ws
            for ws in websocket_events
            if str(ws.get("observed_status") or ws.get("status") or "").strip().lower()
            == normalized
            and (
                ws.get("order_db_id") == order_id
                or (order_ref is not None and ws.get("order_ref") == order_ref)
            )
        ]
        if matches:
            return matches
        return [
            gate
            for gate in websocket_gate_events
            if str(gate.get("observed_status") or gate.get("status") or "").strip().lower()
            == normalized
            and (
                gate.get("order_db_id") == order_id
                or (order_ref is not None and gate.get("order_ref") == order_ref)
            )
        ]

    for event in expected:
        order_id = event["order_db_id"]
        order_ref = event.get("order_ref")
        status = event.get("observed_status") or event.get("status") or event.get("expected_status")
        matches = [
            ws
            for ws in websocket_events
            if (ws.get("observed_status") or ws.get("status")) == status
            and (
                ws.get("order_db_id") == order_id
                or (order_ref is not None and ws.get("order_ref") == order_ref)
            )
        ]
        if not matches:
            event["websocket_match"] = {
                "matched": False,
                "source": "",
            }
            coverage = getattr(recorder, "websocket_coverage", None)
            if isinstance(coverage, dict):
                coverage["missed_order_events"] = coverage.get("missed_order_events", 0) + 1
            missing_count += 1
            recorder.record_issue(
                severity=issue_severity,
                code="websocket_event_missing",
                actor="websocket",
                scenario=event.get("scenario"),
                step=event.get("step"),
                order_db_id=order_id,
                order_ref=event.get("order_ref"),
                related_event_id=event.get("id"),
                message=f"No websocket event observed for status {status}",
                details={"expected_event": event},
            )
            if strict:
                blocking_failures += 1
            continue

        in_window = [
            ws
            for ws in matches
            if event["elapsed_ms"] - early_tolerance_ms
            <= ws["elapsed_ms"]
            <= event["elapsed_ms"] + timeout_ms
        ]
        if in_window:
            best = min(in_window, key=lambda item: abs(item["elapsed_ms"] - event["elapsed_ms"]))
            event["websocket_match"] = {
                "matched": True,
                "source": (best.get("details") or {}).get("source", ""),
                "latency_ms": best["elapsed_ms"] - event["elapsed_ms"],
                "websocket_event_id": best["id"],
            }
            coverage = getattr(recorder, "websocket_coverage", None)
            if isinstance(coverage, dict):
                coverage["matched_order_events"] = coverage.get("matched_order_events", 0) + 1
            continue

        first = min(matches, key=lambda item: abs(item["elapsed_ms"] - event["elapsed_ms"]))
        event["websocket_match"] = {
            "matched": False,
            "source": (first.get("details") or {}).get("source", ""),
            "latency_ms": first["elapsed_ms"] - event["elapsed_ms"],
            "websocket_event_id": first["id"],
        }
        coverage = getattr(recorder, "websocket_coverage", None)
        if isinstance(coverage, dict):
            coverage["missed_order_events"] = coverage.get("missed_order_events", 0) + 1
        late_count += 1
        recorder.record_issue(
            severity=issue_severity,
            code="websocket_event_late",
            actor="websocket",
            scenario=event.get("scenario"),
            step=event.get("step"),
            order_db_id=order_id,
            order_ref=event.get("order_ref"),
            related_event_id=event.get("id"),
            message=f"Websocket event for status {status} arrived outside timeout window",
            details={"expected_event": event, "observed_event": first},
        )
        if strict:
            blocking_failures += 1

    if require_lifecycle_proof:
        for order in recorder.orders.values():
            if not isinstance(order, dict) or order.get("order_db_id") is None:
                continue
            order_db_id = int(order["order_db_id"])
            if order_db_id in skip_lifecycle_order_ids:
                continue
            order_ref = (
                str(order.get("order_ref"))
                if order.get("order_ref") not in {None, ""}
                else None
            )
            final_status = str(order.get("final_status") or "").strip().lower()
            driven_statuses = {
                str(
                    event.get("observed_status")
                    or event.get("status")
                    or event.get("expected_status")
                    or ""
                ).strip().lower()
                for event in recorder.events
                if event.get("expect_websocket")
                and event.get("order_db_id") == order_db_id
            }
            required_statuses = {status for status in driven_statuses if status}
            required_statuses.add("pending")
            if final_status:
                required_statuses.add(final_status)

            for required_status in sorted(required_statuses):
                if _ws_matches(order_db_id, order_ref, required_status):
                    continue
                lifecycle_missing_count += 1
                if required_status == "pending":
                    code = "websocket_lifecycle_pending_missing"
                elif required_status == final_status:
                    code = "websocket_lifecycle_terminal_missing"
                else:
                    code = "websocket_lifecycle_intermediate_missing"
                recorder.record_issue(
                    severity=issue_severity,
                    code=code,
                    actor="websocket",
                    scenario="simulation_cleanup",
                    step="websocket_lifecycle_proof",
                    order_db_id=order_db_id,
                    order_ref=order_ref,
                    message=(
                        "Websocket lifecycle proof missing for "
                        f"order {order_db_id} status={required_status}."
                    ),
                    details={
                        "required_status": required_status,
                        "final_status": final_status or None,
                        "order_ref": order_ref,
                    },
                )
                if strict:
                    blocking_failures += 1

    return {
        "expected_events": len(expected),
        "missing_events": missing_count,
        "late_events": late_count,
        "lifecycle_missing_events": lifecycle_missing_count,
        "blocking_failures": blocking_failures,
    }
