"""SIMULATOR_APPLOGGER — simulator-wide run logger.

Writes structured NDJSON to logs/simulator-runs/<YYYY-MM-DD>/<session-id>.ndjson.
Each record carries an ISO-8601 timestamp with milliseconds and UTC timezone.

Usage::

    logger = SimulatorAppLogger(session_id="abc123", log_dir=Path("logs/simulator-runs"))
    logger.lifecycle("launch", details={"version": "1.0"})
    logger.route("/runs", "page_load")
    logger.action("click", target="#start-btn")
    logger.network("GET", "http://localhost:8080/api/v1/flows", status=200, latency_ms=45)
    logger.console("INFO", "Run started")
    logger.error("TypeError", "Cannot read property", stacktrace="...")
    logger.flow_status("auth-login", "passed")
    logger.stop()
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional


def _now_iso() -> str:
    """ISO-8601 with milliseconds and +00:00 timezone."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+00:00"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SimulatorAppLogger:
    """Write structured NDJSON run events for SIMULATOR_APPLOGGER."""

    def __init__(
        self,
        session_id: str,
        log_dir: Optional[Path] = None,
        *,
        print_live: bool = True,
    ) -> None:
        self.session_id = session_id
        self._print_live = print_live
        self._lock = Lock()

        base = log_dir or (Path(__file__).parent / "logs" / "simulator-runs")
        date_dir = base / _today_str()
        date_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = date_dir / f"{session_id}.ndjson"
        self.date_dir = date_dir

        self._file = open(self.log_path, "a", encoding="utf-8")  # noqa: WPS515
        self._seq = 0
        self._started_at = _now_iso()
        self._flow_results: list[dict[str, Any]] = []

        self._emit(
            event="lifecycle",
            phase="launch",
            details={"session_id": session_id, "pid": os.getpid(), "python": sys.version},
        )
        if print_live:
            self._live(f"[SIMULATOR_APPLOGGER] session={session_id}  log={self.log_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # Public logging API
    # ──────────────────────────────────────────────────────────────────────────

    def lifecycle(self, phase: str, *, details: dict[str, Any] | None = None) -> None:
        """App lifecycle event: launch, ready, shutdown, crash."""
        self._emit(event="lifecycle", phase=phase, details=details)

    def route(self, path: str, action: str = "navigate", *, details: dict[str, Any] | None = None) -> None:
        """Route/page transition."""
        self._emit(event="route", path=path, action=action, details=details)

    def action(
        self,
        kind: str,
        *,
        target: str | None = None,
        value: str | None = None,
        flow: str | None = None,
        step: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """User action: click, type, submit, select."""
        self._emit(
            event="action",
            kind=kind,
            target=target,
            value=value,
            flow=flow,
            step=step,
            details=details,
        )

    def network(
        self,
        method: str,
        url: str,
        *,
        status: int | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
        response_snippet: str | None = None,
        flow: str | None = None,
    ) -> None:
        """Network request/response."""
        ok = status is not None and status < 400
        self._emit(
            event="network",
            method=method.upper(),
            url=url,
            http_status=status,
            latency_ms=latency_ms,
            ok=ok,
            error=error,
            response_snippet=response_snippet[:500] if response_snippet else None,
            flow=flow,
        )

    def console(
        self,
        severity: str,
        message: str,
        *,
        source: str | None = None,
        flow: str | None = None,
    ) -> None:
        """Captured stdout/stderr or browser console output."""
        self._emit(
            event="console",
            severity=severity.upper(),
            message=message,
            source=source,
            flow=flow,
        )

    def error(
        self,
        kind: str,
        message: str,
        *,
        stacktrace: str | None = None,
        flow: str | None = None,
        step: str | None = None,
    ) -> None:
        """Uncaught error, exception, or assertion failure."""
        self._emit(
            event="error",
            kind=kind,
            message=message,
            stacktrace=stacktrace,
            flow=flow,
            step=step,
        )

    def flow_status(
        self,
        flow_id: str,
        status: str,  # passed | failed | blocked
        *,
        step: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
        root_cause: str | None = None,
        reproducibility: str | None = None,
        evidence_ts: str | None = None,
    ) -> None:
        """Per-flow verdict: passed, failed, or blocked."""
        assert status in ("passed", "failed", "blocked"), f"Invalid status: {status}"
        record = {
            "flow_id": flow_id,
            "status": status,
            "step": step,
            "expected": expected,
            "actual": actual,
            "root_cause": root_cause,
            "reproducibility": reproducibility,
            "evidence_ts": evidence_ts or _now_iso(),
        }
        self._flow_results.append(record)
        self._emit(event="flow_status", **record)

    def step_check(
        self,
        flow_id: str,
        step: str,
        *,
        passed: bool,
        expected: str | None = None,
        actual: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Individual step check within a flow."""
        icon = "✓" if passed else "✗"
        if self._print_live:
            status_str = "PASS" if passed else "FAIL"
            self._live(f"  [{status_str}] {flow_id} / {step}")
        self._emit(
            event="step_check",
            flow=flow_id,
            step=step,
            passed=passed,
            expected=expected,
            actual=actual,
            icon=icon,
            details=details,
        )

    def stop(self) -> None:
        """Flush, close the log file, write final lifecycle event."""
        self._emit(event="lifecycle", phase="shutdown", details={"total_flows": len(self._flow_results)})
        self._file.flush()
        self._file.close()
        if self._print_live:
            self._live(f"[SIMULATOR_APPLOGGER] shutdown  log={self.log_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _emit(self, **kwargs: Any) -> None:
        ts = _now_iso()
        self._seq += 1
        record: dict[str, Any] = {"ts": ts, "seq": self._seq, "session": self.session_id}
        record.update({k: v for k, v in kwargs.items() if v is not None})
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    @staticmethod
    def _live(msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}+00:00"
        print(f"{ts}  {msg}", flush=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Accessors for summary generation
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def flow_results(self) -> list[dict[str, Any]]:
        return list(self._flow_results)

    @property
    def started_at(self) -> str:
        return self._started_at
