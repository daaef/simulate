from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Literal

from decision_reasons import is_informational_decision_reason
from session_flow_labels import flow_label_for
from ..event_failure import is_metric_failed_event
from ..runs import service as runs_service


FindingBucket = Literal["critical", "operational"]

CRITICAL_FINDINGS_CAP = 10
OPERATIONAL_FINDINGS_CAP = 25
ARTIFACT_ISSUES_SCAN_LIMIT = 24

ACTOR_KEYS = ("user", "store", "robot")
CRITICAL_ISSUE_CODES = frozenset(
    {
        "websocket_event_missing",
        "websocket_event_late",
    }
)
NON_SERVER_FAILURE_CODE_PARTS = (
    "missing_",
    "coupon",
    "saved_card",
    "card",
    "token",
    "customer_id",
    "user_id",
    "subentity_id",
    "validation",
    "required",
    "unauthorized",
    "forbidden",
    "not_found",
)
SERVER_FAILURE_CODE_PARTS = (
    "http_error",
    "connection_error",
    "timeout",
    "unavailable",
    "websocket_connection_error",
    "server_error",
    "gateway",
    "bad_gateway",
)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _lower(value: Any) -> str:
    return _str(value).strip().lower()


def _is_failed_event(event: dict[str, Any]) -> bool:
    if _lower(event.get("category")) == "decision" and is_informational_decision_reason(
        status=event.get("status"),
        reason_code=event.get("reason_code"),
    ):
        return False

    if event.get("ok") is False:
        return True

    status = _lower(event.get("status"))
    if status in {"failed", "error", "rejected", "blocked"}:
        return True

    http_status = event.get("http_status") or event.get("status_code")
    try:
        if http_status is not None and int(http_status) >= 400:
            return True
    except (TypeError, ValueError):
        pass

    return False


def _is_server_api_failure_event(event: dict[str, Any]) -> bool:
    if _lower(event.get("category")) == "decision" and is_informational_decision_reason(
        status=event.get("status"),
        reason_code=event.get("reason_code"),
    ):
        return False

    try:
        http_status = event.get("http_status") or event.get("status_code")
        if http_status is not None and int(http_status) >= 500:
            return True
    except (TypeError, ValueError):
        pass

    code = _lower(event.get("code") or event.get("reason_code"))
    action = _lower(event.get("action"))
    message = _lower(_event_message(event))
    category = _lower(event.get("category"))

    if "websocket_connection_error" in code:
        return True
    if category == "websocket" and ("connection" in message or "connect" in action):
        return True
    if any(part in code for part in SERVER_FAILURE_CODE_PARTS):
        return True
    if "connection" in message or "timed out" in message or "timeout" in message:
        return True
    if "api unavailable" in message or "service unavailable" in message:
        return True
    return False


def _is_server_api_failure_issue(issue: dict[str, Any]) -> bool:
    try:
        details = issue.get("details")
        if isinstance(details, dict):
            http_status = details.get("http_status") or details.get("status_code")
            if http_status is not None and int(http_status) >= 500:
                return True
    except (TypeError, ValueError):
        pass

    code = _lower(issue.get("code"))
    message = _lower(issue.get("message"))

    if any(part in code for part in NON_SERVER_FAILURE_CODE_PARTS):
        return False
    if any(part in message for part in ("missing token", "saved card", "no coupon", "coupon", "customer id", "not available for this user")):
        return False
    if any(part in code for part in SERVER_FAILURE_CODE_PARTS):
        return True
    if "websocket_connection_error" in code:
        return True
    if "server error" in message or "api unavailable" in message or "service unavailable" in message:
        return True
    if "timeout" in message or "timed out" in message or "connection" in message:
        return True
    return False


def _finding_bucket_issue(issue: dict[str, Any]) -> FindingBucket:
    code = _lower(issue.get("code"))

    if code in CRITICAL_ISSUE_CODES:
        return "critical"

    details = issue.get("details")
    if isinstance(details, dict) and code.startswith("websocket_gate_"):
        enforced = details.get("enforced")
        if enforced is False:
            return "operational"
        if enforced is True:
            return "critical"

    if _is_server_api_failure_issue(issue):
        return "critical"

    return "operational"


def _http_status_value(event: dict[str, Any] | None, details: dict[str, Any]) -> int | None:
    for source in (event or {}, details):
        raw = source.get("http_status") or source.get("status_code")
        try:
            if raw is not None:
                return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _preceding_steps(
    events: list[dict[str, Any]],
    *,
    related_event: dict[str, Any] | None,
    actor: str | None,
    flow: str | None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if related_event is None:
        return []

    related_id = related_event.get("id")
    actor_key = _lower(actor or related_event.get("actor"))
    flow_key = _lower(flow or related_event.get("scenario"))
    preceding: list[dict[str, Any]] = []

    for event in events:
        try:
            event_id = int(event.get("id"))
        except (TypeError, ValueError):
            continue
        try:
            if related_id is not None and event_id >= int(related_id):
                continue
        except (TypeError, ValueError):
            continue
        if actor_key and _event_actor(event) != actor_key:
            continue
        if flow_key and _lower(event.get("scenario")) != flow_key:
            continue
        endpoint = _event_endpoint(event) or None
        action = _event_action(event)
        if not endpoint and not action:
            continue
        preceding.append(
            {
                "at": _event_timestamp(event) or None,
                "action": action,
                "step": _str(event.get("step")) or None,
                "endpoint": endpoint,
                "ok": event.get("ok") if event.get("ok") is not None else not _is_failed_event(event),
            }
        )

    return preceding[-limit:]


def _issue_context_fields(
    *,
    issue: dict[str, Any] | None,
    related_event: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    details = issue.get("details") if issue and isinstance(issue.get("details"), dict) else {}
    flow = _str(issue.get("scenario") if issue else None) or _str((related_event or {}).get("scenario")) or None
    step = _str(issue.get("step") if issue else None) or _str((related_event or {}).get("step")) or None
    action = _str((related_event or {}).get("action")) or None
    flow_label = flow_label_for(step=step, action=action or step)
    order_ref = issue.get("order_ref") if issue else None
    if order_ref is None and related_event is not None:
        order_ref = related_event.get("order_ref")
    http_status = _http_status_value(related_event, details)
    preceding = _preceding_steps(
        events,
        related_event=related_event,
        actor=issue.get("actor") if issue else (related_event or {}).get("actor"),
        flow=flow,
    )
    fields: dict[str, Any] = {
        "flow": flow or None,
        "step": step or None,
        "method": (related_event or {}).get("method"),
        "http_status": http_status,
        "order_ref": order_ref,
        "preceding_steps": preceding,
    }
    if flow_label:
        fields["flow_label"] = flow_label
    return fields


def _issue_row_from_artifact(
    issue: dict[str, Any],
    event_by_id: dict[int, dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    related_event = None
    try:
        related_event = event_by_id.get(int(issue.get("related_event_id")))
    except (TypeError, ValueError):
        related_event = None
    details = issue.get("details") if isinstance(issue.get("details"), dict) else {}
    route = (
        _event_endpoint(related_event or {})
        or _str(details.get("endpoint") or details.get("path") or details.get("url") or details.get("full_url"))
        or None
    )
    row = {
        "severity": issue.get("severity") or "warning",
        "code": issue.get("code") or "issue",
        "message": issue.get("message") or "Recorded issue",
        "actor": issue.get("actor"),
        "at": issue.get("ts"),
        "route": route,
    }
    row.update(_issue_context_fields(issue=issue, related_event=related_event, events=events))
    return row


def _issue_row_from_event(event: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    action = _str(event.get("action") or event.get("category") or "failed_event")
    step = _str(event.get("step")) or None
    flow = _str(event.get("scenario")) or None
    flow_label = flow_label_for(step=step, action=action)
    row = {
        "severity": "error",
        "code": action,
        "message": _event_message(event) or _event_endpoint(event) or "Failed event",
        "actor": event.get("actor"),
        "at": _event_timestamp(event),
        "route": _event_endpoint(event) or None,
        "flow": flow,
        "step": step,
        "method": event.get("method"),
        "http_status": _http_status_value(event, {}),
        "order_ref": event.get("order_ref"),
        "preceding_steps": _preceding_steps(
            events,
            related_event=event,
            actor=_str(event.get("actor")) or None,
            flow=flow,
        ),
    }
    if flow_label:
        row["flow_label"] = flow_label
    return row


def _event_timestamp(event: dict[str, Any]) -> str:
    return _str(event.get("ts") or event.get("timestamp") or event.get("created_at"))


def _event_actor(event: dict[str, Any]) -> str:
    return _lower(event.get("actor") or event.get("category") or "unknown")


def _event_action(event: dict[str, Any]) -> str:
    return _str(event.get("action") or event.get("step") or event.get("method") or "event")


def _event_endpoint(event: dict[str, Any]) -> str:
    return _str(
        event.get("endpoint")
        or event.get("path")
        or event.get("url")
        or event.get("full_url")
    )


def _event_message(event: dict[str, Any]) -> str:
    if event.get("response_preview"):
        return _str(event.get("response_preview"))
    if event.get("message"):
        return _str(event.get("message"))
    if event.get("details"):
        details = event.get("details")
        if isinstance(details, dict):
            if details.get("message"):
                return _str(details.get("message"))
            if details.get("source"):
                return f"source={details.get('source')}"
        return _str(details)
    return ""


def _extract_artifact_events(artifact_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    content = artifact_payload.get("content")

    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)], [], {}

    if isinstance(content, dict):
        events = [item for item in _as_list(content.get("events")) if isinstance(item, dict)]
        issues = [item for item in _as_list(content.get("issues")) if isinstance(item, dict)]
        run_meta = _as_dict(content.get("run"))
        return events, issues, run_meta

    return [], [], {}


def _load_latest_run() -> dict[str, Any] | None:
    payload = runs_service.list_runs(1, 0)
    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list) or not runs:
        return None
    run = runs[0]
    return run if isinstance(run, dict) else None


def _load_metrics(run_id: int) -> dict[str, Any] | None:
    try:
        payload = runs_service.get_run_metrics(run_id)
    except Exception:
        return None

    if not isinstance(payload, dict) or not payload.get("available"):
        return None

    metrics = payload.get("metrics")
    return metrics if isinstance(metrics, dict) else None


def _load_events(run_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        artifact = runs_service.get_run_artifact(run_id, "events", 0, 2000, False)
    except Exception:
        return [], [], {}

    if not isinstance(artifact, dict) or not artifact.get("available"):
        return [], [], {}

    return _extract_artifact_events(artifact)


def _duration_seconds(run: dict[str, Any], run_meta: dict[str, Any]) -> float | None:
    if isinstance(run_meta.get("duration_ms"), (int, float)):
        return round(float(run_meta["duration_ms"]) / 1000, 2)

    started = run.get("started_at") or run.get("created_at")
    finished = run.get("finished_at")
    if not started or not finished:
        return None

    try:
        start_dt = datetime.fromisoformat(_str(started).replace("Z", "+00:00"))
        finish_dt = datetime.fromisoformat(_str(finished).replace("Z", "+00:00"))
        return round((finish_dt - start_dt).total_seconds(), 2)
    except Exception:
        return None


def _actor_identity(actor: str, run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        identity = event.get("identity")
        if not isinstance(identity, dict):
            continue
        actor_identity = identity.get(actor)
        if isinstance(actor_identity, dict) and actor_identity:
            return actor_identity

    if actor == "user":
        return {
            "id": None,
            "name": run.get("user_name"),
            "phone": run.get("phone"),
        }

    if actor == "store":
        return {
            "id": run.get("store_id"),
            "name": run.get("store_name"),
            "phone": run.get("store_phone"),
        }

    return {
        "id": None,
        "name": None,
        "phone": None,
    }


def _actor_summary(actor: str, run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    actor_events = [
        event
        for event in events
        if _event_actor(event) == actor or _event_actor(event).startswith(f"{actor}:")
    ]

    failed = [event for event in actor_events if _is_server_api_failure_event(event)]
    latest = actor_events[-1] if actor_events else None

    return {
        "key": actor,
        "label": actor.title(),
        "identity": _actor_identity(actor, run, events),
        "events": len(actor_events),
        "failed_events": len(failed),
        "latest_action": _event_action(latest) if latest else None,
        "latest_status": latest.get("status") if latest else None,
        "latest_at": _event_timestamp(latest) if latest else None,
    }


def _is_http_event(event: dict[str, Any]) -> bool:
    return bool(event.get("method") and _event_endpoint(event))


def _is_websocket_event(event: dict[str, Any]) -> bool:
    actor = _event_actor(event)
    category = _lower(event.get("category"))
    action = _lower(event.get("action"))
    return actor == "websocket" or category == "websocket" or "websocket" in action


def _http_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    http_events = [event for event in events if _is_http_event(event)]
    failed = [event for event in http_events if _is_server_api_failure_event(event)]

    status_groups = {
        "2xx": 0,
        "3xx": 0,
        "4xx": 0,
        "5xx": 0,
        "unknown": 0,
    }
    latencies: list[float] = []
    endpoint_counter: Counter[str] = Counter()
    failed_endpoint_counter: Counter[str] = Counter()

    slowest: dict[str, Any] | None = None

    for event in http_events:
        endpoint = _event_endpoint(event) or "unknown"
        endpoint_counter[endpoint] += 1

        if _is_server_api_failure_event(event):
            failed_endpoint_counter[endpoint] += 1

        status_value = event.get("http_status") or event.get("status_code")
        try:
            status = int(status_value)
            if 200 <= status <= 299:
                status_groups["2xx"] += 1
            elif 300 <= status <= 399:
                status_groups["3xx"] += 1
            elif 400 <= status <= 499:
                status_groups["4xx"] += 1
            elif status >= 500:
                status_groups["5xx"] += 1
            else:
                status_groups["unknown"] += 1
        except (TypeError, ValueError):
            status_groups["unknown"] += 1

        latency = event.get("latency_ms") or event.get("duration_ms")
        try:
            latency_value = float(latency)
            latencies.append(latency_value)
            if slowest is None or latency_value > float(slowest.get("latency_ms") or 0):
                slowest = {
                    "endpoint": endpoint,
                    "method": event.get("method"),
                    "status": status_value,
                    "latency_ms": latency_value,
                }
        except (TypeError, ValueError):
            pass

    return {
        "total": len(http_events),
        "failed": len(failed),
        "success": max(0, len(http_events) - len(failed)),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "status_groups": status_groups,
        "slowest": slowest,
        "top_endpoints": [
            {"endpoint": endpoint, "count": count}
            for endpoint, count in endpoint_counter.most_common(6)
        ],
        "top_failed_endpoints": [
            {"endpoint": endpoint, "count": count}
            for endpoint, count in failed_endpoint_counter.most_common(6)
        ],
    }


def _websocket_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    websocket_events = [event for event in events if _is_websocket_event(event)]
    expected_events = [event for event in events if event.get("expect_websocket")]

    matched = 0
    missed = 0
    for event in expected_events:
        match = event.get("websocket_match")
        if isinstance(match, dict) and match.get("matched"):
            matched += 1
        else:
            missed += 1

    sources: Counter[str] = Counter()
    for event in websocket_events:
        details = event.get("details")
        source = ""
        if isinstance(details, dict):
            source = _str(details.get("source"))
        sources[source or "websocket"] += 1

    latest = websocket_events[-1] if websocket_events else None

    return {
        "total": len(websocket_events),
        "expected": len(expected_events),
        "matched": matched,
        "missed": missed,
        "sources": [{"source": source, "count": count} for source, count in sources.most_common()],
        "latest": {
            "at": _event_timestamp(latest),
            "action": _event_action(latest),
            "status": latest.get("observed_status") or latest.get("status"),
            "message": _event_message(latest),
        } if latest else None,
    }


def _build_lifecycle(events: list[dict[str, Any]], run: dict[str, Any]) -> list[dict[str, Any]]:
    important: list[dict[str, Any]] = []

    for event in events:
        action = _lower(event.get("action"))
        category = _lower(event.get("category"))
        step = _lower(event.get("step"))
        endpoint = _lower(_event_endpoint(event))

        keep = (
            "login" in action
            or "store" in action
            or "menu" in action
            or "order" in action
            or "payment" in action
            or "stripe" in action
            or "robot" in action
            or "websocket" in action
            or "websocket" in category
            or "create" in step
            or "confirm" in step
            or "order" in endpoint
            or "payment" in endpoint
        )

        if keep:
            important.append(event)

    if not important and events:
        important = events[:8]

    lifecycle = [
        {
            "at": run.get("created_at"),
            "actor": "system",
            "label": "Run created",
            "status": run.get("status"),
            "ok": True,
        }
    ]

    for event in important[:12]:
        lifecycle.append(
            {
                "at": _event_timestamp(event),
                "actor": event.get("actor") or event.get("category") or "event",
                "label": _event_action(event),
                "status": event.get("observed_status") or event.get("status") or event.get("http_status"),
                "ok": not _is_failed_event(event),
                "endpoint": _event_endpoint(event) or None,
                "latency_ms": event.get("latency_ms") or event.get("duration_ms"),
            }
        )

    if run.get("finished_at"):
        lifecycle.append(
            {
                "at": run.get("finished_at"),
                "actor": "system",
                "label": "Run finished",
                "status": run.get("status"),
                "ok": _lower(run.get("status")) == "succeeded",
            }
        )

    return lifecycle


def _event_id(event: dict[str, Any]) -> int | None:
    try:
        return int(event.get("id"))
    except (TypeError, ValueError):
        return None


def _related_event_id(issue: dict[str, Any]) -> int | None:
    try:
        return int(issue.get("related_event_id"))
    except (TypeError, ValueError):
        return None


def _build_findings(
    events: list[dict[str, Any]],
    artifact_issues: list[dict[str, Any]],
    run: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    critical: list[dict[str, Any]] = []
    operational: list[dict[str, Any]] = []
    event_by_id: dict[int, dict[str, Any]] = {}
    represented_event_ids: set[int] = set()

    for event in events:
        event_id = _event_id(event)
        if event_id is not None:
            event_by_id[event_id] = event

    for issue in artifact_issues[:ARTIFACT_ISSUES_SCAN_LIMIT]:
        try:
            related_id = _related_event_id(issue)
            if related_id is not None:
                represented_event_ids.add(related_id)
            row = _issue_row_from_artifact(issue, event_by_id, events)
            if _finding_bucket_issue(issue) == "critical":
                critical.append(row)
            else:
                operational.append(row)
        except Exception:
            continue

    for event in events:
        if len(critical) >= CRITICAL_FINDINGS_CAP:
            break
        event_id = _event_id(event)
        if event_id is not None and event_id in represented_event_ids:
            continue
        try:
            if not _is_server_api_failure_event(event):
                continue
            critical.append(_issue_row_from_event(event, events))
            if event_id is not None:
                represented_event_ids.add(event_id)
        except Exception:
            continue

    for event in events:
        if len(operational) >= OPERATIONAL_FINDINGS_CAP:
            break
        event_id = _event_id(event)
        if event_id is not None and event_id in represented_event_ids:
            continue
        try:
            if not is_metric_failed_event(event):
                continue
            if _is_server_api_failure_event(event):
                continue
            operational.append(_issue_row_from_event(event, events))
            if event_id is not None:
                represented_event_ids.add(event_id)
        except Exception:
            continue

    if run.get("error") and _is_server_api_failure_issue({"code": "run_error", "message": _str(run.get("error"))}):
        critical.insert(
            0,
            {
                "severity": "error",
                "code": "run_error",
                "message": run.get("error"),
                "actor": "system",
                "at": run.get("finished_at") or run.get("created_at"),
                "route": None,
                "flow": None,
                "step": None,
                "method": None,
                "http_status": None,
                "order_ref": None,
                "preceding_steps": [],
            },
        )

    return {
        "critical": critical[:CRITICAL_FINDINGS_CAP],
        "operational": operational[:OPERATIONAL_FINDINGS_CAP],
    }


def _issues(events: list[dict[str, Any]], artifact_issues: list[dict[str, Any]], run: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible alias: critical findings only."""
    return _build_findings(events, artifact_issues, run)["critical"]


def _derived_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [event for event in events if is_metric_failed_event(event)]
    http_events = [event for event in events if _is_http_event(event)]
    websocket_events = [event for event in events if _is_websocket_event(event)]

    top_actors = Counter(_event_actor(event) or "unknown" for event in events)
    # Align action keys with `_event_metrics` in `main.py` (raw `action` field, else "unknown").
    action_totals = Counter(str(event.get("action") or "unknown") for event in events)

    latencies = []
    for event in http_events:
        latency = event.get("latency_ms") or event.get("duration_ms")
        try:
            latencies.append(float(latency))
        except (TypeError, ValueError):
            pass

    action_counts = [
        {"action": name, "count": count}
        for name, count in sorted(action_totals.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "total_events": len(events),
        "failed_events": len(failed),
        "http_calls": len(http_events),
        "websocket_events": len(websocket_events),
        "avg_http_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "top_actors": dict(top_actors.most_common(10)),
        "top_actions": dict(action_totals.most_common(10)),
        "action_counts": action_counts,
    }


def latest_run_overview() -> dict[str, Any]:
    run = _load_latest_run()
    if run is None:
        return {
            "run": None,
            "metrics": None,
            "actors": {},
            "protocols": {
                "http": {},
                "websocket": {},
            },
            "lifecycle": [],
            "issues": [],
            "findings": {"critical": [], "operational": []},
            "run_meta": {},
        }

    return _build_overview_payload(run)


def run_overview(run_id: int) -> dict[str, Any]:
    run = runs_service.get_run(run_id)
    return _build_overview_payload(run)


def _build_overview_payload(run: dict[str, Any]) -> dict[str, Any]:
    run_id = int(run["id"])
    events, artifact_issues, run_meta = _load_events(run_id)
    metrics = _load_metrics(run_id) or _derived_metrics(events)

    findings = _build_findings(events, artifact_issues, run)

    return {
        "run": {
            **run,
            "duration_seconds": _duration_seconds(run, run_meta),
        },
        "metrics": metrics,
        "actors": {
            actor: _actor_summary(actor, run, events)
            for actor in ACTOR_KEYS
        },
        "protocols": {
            "http": _http_summary(events),
            "websocket": _websocket_summary(events),
        },
        "lifecycle": _build_lifecycle(events, run),
        "findings": findings,
        "issues": findings["critical"],
        "run_meta": run_meta,
    }
