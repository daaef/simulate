from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from .models import RunCreateRequest, RunProfileUpsertRequest

RunArtifactKind = Literal["report", "story", "events"]

_runtime: dict[str, Callable[..., Any]] = {}


def configure_runtime(**callbacks: Callable[..., Any]) -> None:
    _runtime.update(callbacks)


def _callback(name: str) -> Callable[..., Any]:
    callback = _runtime.get(name)
    if callback is None:
        raise RuntimeError(f"Runs runtime callback {name!r} has not been configured")
    return callback


def list_flows() -> dict[str, Any]:
    return _callback("list_flows")()


def list_runs(limit: int, offset: int) -> dict[str, Any]:
    return _callback("list_runs")(limit, offset)


def count_runs() -> dict[str, Any]:
    return _callback("count_runs")()


def dashboard_summary() -> dict[str, Any]:
    return _callback("dashboard_summary")()


def create_run(request: RunCreateRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("create_run")(request, user_id)


def get_run(run_id: int) -> dict[str, Any]:
    return _callback("get_run")(run_id)


def get_run_log(run_id: int, tail: int) -> dict[str, Any]:
    return _callback("get_run_log")(run_id, tail)


def get_run_artifact(
    run_id: int,
    kind: RunArtifactKind,
    offset: int,
    limit: int,
    compact: bool,
) -> dict[str, Any]:
    return _callback("get_run_artifact")(run_id, kind, offset, limit, compact)


def get_run_metrics(run_id: int) -> dict[str, Any]:
    return _callback("get_run_metrics")(run_id)


def cancel_run(run_id: int) -> dict[str, Any]:
    return _callback("cancel_run")(run_id)


def delete_run(run_id: int) -> dict[str, Any]:
    return _callback("delete_run")(run_id)


def list_profiles() -> dict[str, Any]:
    return _callback("list_profiles")()


def create_profile(request: RunProfileUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("create_profile")(request, user_id)


def update_profile(profile_id: int, request: RunProfileUpsertRequest, user_id: int | None) -> dict[str, Any]:
    return _callback("update_profile")(profile_id, request, user_id)


def delete_profile(profile_id: int) -> dict[str, Any]:
    return _callback("delete_profile")(profile_id)


def launch_profile(profile_id: int, user_id: int | None) -> dict[str, Any]:
    return _callback("launch_profile")(profile_id, user_id)


def get_execution_snapshot(run_id: int) -> dict[str, Any]:
    return _callback("get_execution_snapshot")(run_id)


def replay_run(run_id: int, user_id: int | None) -> dict[str, Any]:
    return _callback("replay_run")(run_id, user_id)
