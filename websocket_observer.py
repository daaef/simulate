"""Websocket observation and validation for simulator runs."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlparse

import websockets
from rich.console import Console

import config
from reporting import RunRecorder

console = Console()


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
        if status is None and item.get("status") is not None:
            status = str(item["status"])

        raw_ref = item.get("order_id") or item.get("order_ref")
        if order_ref is None and raw_ref is not None:
            order_ref = str(raw_ref)

        raw_id = item.get("id") or item.get("order_db_id")
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
        user_id: int,
        store_id: int,
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

    async def start(self) -> None:
        for source, (url, subprotocols) in self.targets.items():
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

    async def _listen(
        self,
        source: str,
        url: str,
        subprotocols: list[str] | None,
    ) -> None:
        while True:
            try:
                async with websockets.connect(
                    url,
                    subprotocols=subprotocols,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:
                    console.print(f"[blue]websocket:[/] connected {source}")
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
        self.recorder.record_websocket(
            source=source,
            raw=raw,
            payload=payload,
            nested=nested,
            order_db_id=order_db_id,
            order_ref=order_ref,
            status=status,
        )


def validate_websocket_events(recorder: RunRecorder) -> None:
    expected = [
        event
        for event in recorder.events
        if event.get("expect_websocket") and event.get("order_db_id") is not None
    ]
    websocket_events = [
        event for event in recorder.events if event.get("category") == "websocket"
    ]
    timeout_ms = int(config.SIM_WEBSOCKET_EVENT_TIMEOUT_SECONDS * 1000)
    early_tolerance_ms = 5000

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
            recorder.record_issue(
                severity="warning",
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
            continue

        first = min(matches, key=lambda item: abs(item["elapsed_ms"] - event["elapsed_ms"]))
        event["websocket_match"] = {
            "matched": False,
            "source": (first.get("details") or {}).get("source", ""),
            "latency_ms": first["elapsed_ms"] - event["elapsed_ms"],
            "websocket_event_id": first["id"],
        }
        recorder.record_issue(
            severity="warning",
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
