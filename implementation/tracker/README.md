# Implementation Tracker README

## Mission alignment (observability)

The shipped product’s **primary mission** is operator observability: owners and developers should quickly know whether the **control plane** is up (`/healthz`), whether **recent simulations** succeeded or failed, and which **doctor/trace/load** flow to run for proof. Canonical vocabulary (**Up / Degraded / Down**), `/healthz` limitations, flow ladder, GUI semantics, and email footers live in **`README.md`** and **`SIMULATOR_GUIDE.md`** (sections *Operator observability* and *Operator GUI (web)*). Tracker work should not regress **scheduling, GitHub webhooks, run launch semantics, or profiles** without explicit owner sign-off—prefer clearer labels, docs, and read-only summaries.

## Goal

Keep simulator behavior operationally truthful while adding a deliberate `place-order` trace flow for manual store-app testing. Standard simulator flows must still close every created order to `completed`, `rejected`, or `cancelled`; only `place_order` may intentionally seed pending orders, and that exception must be explicit in artifacts and validation.

## Current Status

Implemented (Phase 36 Pending Order Trace Flow). Verification caveat: full Python suite currently has one unrelated midnight-edge schedule test failure, `SchedulesApiTests.test_new_contract_schedule_shifts_into_run_window`.

## Scope

- Add `place-order` as a CLI/API/web trace preset for seeding pending orders.
- Reuse `orders` / `--orders` only for this flow, capped at 10 orders.
- Require websocket proof that each seeded order reached `pending`.
- Add an explicit non-terminal exception for `place_order` while preserving terminal-order enforcement for all other flows.
- Enforce one global contract across all standard simulator flows/modes: created orders must end terminal.
- Remove payment/store context leakage so payment requests always target the correct store context.
- Add end-of-run lifecycle finalization (natural-settle wait, cleanup attempts, terminal re-check).
- Convert unresolved non-terminal orders into hard run failures (independent of `failure_policy`).
- Make websocket lifecycle proof strict for order-producing runs.
- Keep run artifacts (`events.json`, `report.md`, `story.md`) aligned with the true final run outcome.

## Out of Scope

- Replacing simulator architecture, flow presets, or CLI launcher shape.
- Changing mobile app codebases.
- Adding broad or hidden bypasses that allow open orders to pass outside `place_order`.
- Any non-related UX redesign work.

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
- `stripe_sim.py`
- `interaction_catalog.py`
- `flow_presets.py`
- `scenarios.py`
- `sim_actors.json`
- `tests/test_simulate.py`
- `tests/test_web_api.py`
- `web/src/app/(app)/runs/page.tsx`
- `web/src/components/runs/RunLaunchPanel.tsx`
- `web/src/lib/api.ts`
- `web/src/lib/run-command-preview.ts`
- `web/src/lib/run-launcher-config.ts`
- `web/src/lib/run-impact-explainer.ts`
- `ARCHITECTURE.md`
- `app-20260428.full-session-user.md`
- `app-20260430.full-session-user.md`
- `app-20260429.full-session-store.md`
- `app-20260430.full-session-store.md`
- `docs/superpowers/specs/2026-04-30-production-simulator-upgrade-design.md`
- `docs/superpowers/plans/2026-04-30-production-simulator-upgrade.md`
- `docs/superpowers/specs/2026-05-02-simulator-web-gui-platform-design.md`
- `docs/superpowers/plans/2026-05-02-simulator-web-gui-platform.md`
- `docs/superpowers/specs/2026-05-06-simulator-operations-platform-redesign.md`
- `docs/superpowers/plans/2026-05-06-simulator-operations-platform-redesign.md`
- `docs/superpowers/specs/2026-05-06-plan-backed-simulator-config-design.md`
- `docs/superpowers/plans/2026-05-06-plan-backed-simulator-config.md`
- `docs/superpowers/specs/2026-05-19-config-load-ux-and-runtime-alignment-design.md`
- `docs/superpowers/plans/2026-05-19-config-load-ux-and-runtime-alignment.md`
- `api/app/main.py`
- `.env`

## How to Continue

1. Read `implementation_plan.md`
2. Check open items in `tasks.md`
3. Review the latest entries in `session_log.md`
4. Continue from the first incomplete task

## Validation

- Runtime validation:
  - Any created order ends as `completed`, `rejected`, or `cancelled`.
  - Non-terminal states (`pending`, `payment_processing`, `order_processing`, `ready`, robot transit states) force failure after cleanup attempts.
  - Websocket lifecycle proof failures are run-failing for order-producing runs.
- Regression validation:
  - Payment requests use the correct per-order store context after coupon-recovery paths.
  - Trace and load paths both enforce the same terminal-order contract.

## Known Blockers / Assumptions

- Existing simulator CLI behavior is treated as the execution source of truth for v1 of web orchestration.
- Global contract supersedes permissive scenario success when orders are left open, except the explicitly documented `place_order` scenario whose purpose is pending-order seeding.
- Existing git worktree is already dirty; unrelated files must not be reverted.
- Initial deployment target is a single Contabo VPS with Docker Compose and Nginx reverse proxy.
- V1 architecture is local-first and simple: no mandatory Celery/Redis dependency.
- Planning should optimize for future extensibility (optional multi-worker/queue upgrade, scheduled runs, alerting, long-term artifact retention).
- The redesign spec and redesign implementation plan are both approved; current work starts with backend-owned auth and route-first migration.
- CLI command syntax must remain compatible; non-sensitive plan defaults are additive and must not remove `.env` fallback behavior.
- Web run deletion must hard-delete only the selected run's own log/artifacts; shared GUI log directories and unrelated run artifacts must survive.
- Secrets, tokens, and passwords remain out of JSON plans.
- Local `.env` may contain real secrets; do not print or move secret values into tracked docs or plan JSON.

## Last Updated

2026-06-02 00:04
