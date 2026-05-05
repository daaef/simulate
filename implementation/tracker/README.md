# Implementation Tracker README

## Goal

Plan and design a production-grade web GUI platform for the simulator (run orchestration, live monitoring, reports, stories, events explorer), delivered as a Dockerized app deployable on Contabo VPS behind Nginx, with architecture choices that minimize future major rework.

## Current Status

In progress (implementation)

## Scope

- Produce an approved architecture/design spec for a web-based simulator control plane and UX.
- Produce an implementation plan with phased backend/frontend/infra/testing work.
- Define deployment topology for Docker + Nginx on Contabo VPS.
- Define feature set for operator UX, observability UX, and reporting UX.
- Define security, reliability, scaling, and data-retention decisions needed before implementation.
- Keep the existing CLI simulator as the execution engine for the first web platform version.

## Out of Scope

- Implementing the full web app in this planning phase.
- Replacing simulator business logic with a new engine.
- Modifying real user/store mobile app codebases.
- Destructive data operations in production environments.

## Relevant Files

- `__main__.py`
- `config.py`
- `user_sim.py`
- `store_sim.py`
- `robot_sim.py`
- `trace_runner.py`
- `reporting.py`
- `transport.py`
- `websocket_observer.py`
- `interaction_catalog.py`
- `flow_presets.py`
- `scenarios.py`
- `sim_actors.json`
- `tests/test_simulate.py`
- `ARCHITECTURE.md`
- `app-20260428.full-session-user.md`
- `app-20260430.full-session-user.md`
- `app-20260429.full-session-store.md`
- `app-20260430.full-session-store.md`
- `docs/superpowers/specs/2026-04-30-production-simulator-upgrade-design.md`
- `docs/superpowers/plans/2026-04-30-production-simulator-upgrade.md`
- `docs/superpowers/specs/2026-05-02-simulator-web-gui-platform-design.md`
- `docs/superpowers/plans/2026-05-02-simulator-web-gui-platform.md`

## How to Continue

1. Read `implementation_plan.md`
2. Check open items in `tasks.md`
3. Review the latest entries in `session_log.md`
4. Continue from the first incomplete task

## Validation

- Planning validation:
  - Design spec exists and is internally consistent.
  - Implementation plan exists and maps every major requirement to concrete phases.
  - Tracker task board reflects pending implementation work.
  - Deployment architecture and security assumptions are explicit.

## Known Blockers / Assumptions

- Existing simulator CLI behavior is treated as the execution source of truth for v1 of web orchestration.
- Existing git worktree is already dirty; unrelated files must not be reverted.
- Initial deployment target is a single Contabo VPS with Docker Compose and Nginx reverse proxy.
- V1 architecture is local-first and simple: no mandatory Celery/Redis dependency.
- Planning should optimize for future extensibility (optional multi-worker/queue upgrade, scheduled runs, alerting, long-term artifact retention).
- Some platform choices need explicit user confirmation before implementation (auth model, retention windows, alert channels, storage backend).

## Last Updated

2026-05-03 12:50
