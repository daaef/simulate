# Production Simulator Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a JSON-driven production doctor for the Fainzy ordering system with real-app probes, post-order checks, richer reports, and a complete guidebook.

**Architecture:** Keep the existing async actor model and add small modules for run plans, probes, post-order actions, and health summaries. Wire them into trace/load paths without replacing the proven order lifecycle.

**Tech Stack:** Python 3, `asyncio`, `httpx`, `websockets`, `rich`, `unittest`, markdown run artifacts.

---

### Task 1: JSON Run Plan Parser

**Files:**
- Create: `run_plan.py`
- Modify: `config.py`
- Modify: `__main__.py`
- Test: `tests/test_simulate.py`

- [ ] **Step 1: Write failing tests**

Add tests that load a temporary JSON plan with two users and two stores, validate required GPS fields, and verify actor selection compatibility with existing `sim_actors.json`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_simulate.RunPlanTests -v`
Expected: failure because `run_plan` does not exist.

- [ ] **Step 3: Implement parser**

Create dataclasses for `PlanUser`, `PlanStore`, and `RunPlan`. Accept fields:

- `defaults.user_phone`
- `defaults.store_id`
- `users[].phone`
- `users[].role`
- `users[].lat`
- `users[].lng`
- `users[].orders`
- `stores[].store_id`
- `stores[].subentity_id`
- `stores[].lat`
- `stores[].lng`

- [ ] **Step 4: Wire CLI**

Add `--plan` to CLI. Default remains `sim_actors.json`.

- [ ] **Step 5: Verify**

Run the run-plan tests and full unit test suite.

### Task 2: Health Summary

**Files:**
- Create: `health.py`
- Modify: `reporting.py`
- Test: `tests/test_simulate.py`

- [ ] **Step 1: Write failing tests**

Test status counts, latency percentiles, slow endpoint grouping, websocket match rate, and issue severity counts.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_simulate.HealthSummaryTests -v`
Expected: failure because `health` does not exist.

- [ ] **Step 3: Implement health helpers**

Add pure functions that accept events/issues/orders/scenarios and return JSON-safe summary dictionaries.

- [ ] **Step 4: Render report sections**

Place `Daily Doctor Summary`, `Graphical Summary`, and `Bottlenecks` before the existing technical sections.

- [ ] **Step 5: Verify**

Run report tests and full unit test suite.

### Task 3: Real-App Probes

**Files:**
- Create: `app_probes.py`
- Modify: `trace_runner.py`
- Modify: `__main__.py`
- Modify: `store_sim.py`
- Test: `tests/test_simulate.py`

- [ ] **Step 1: Write failing tests**

Test probe endpoint metadata and that non-critical failures are recorded as issues, not uncaught exceptions.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_simulate.AppProbeTests -v`
Expected: failure because `app_probes` does not exist.

- [ ] **Step 3: Implement probes**

Add helpers for:

- `GET /v1/entities/configs/`
- `POST /v1/biz/product/authentication/?product=rds`
- `GET /v1/biz/pricing/0/?product_name=lastmile&currency=<currency>`
- `GET /v1/core/cards/`
- `GET /v1/core/coupon/`
- `GET /v1/core/orders/?user=<id>`
- `GET /v1/core/orders/?subentity_id=<id>`
- `GET /v1/statistics/subentities/<id>/`
- `GET /v1/statistics/subentities/<id>/top-customers/`

- [ ] **Step 4: Wire probes**

Run user probes during trace bootstrap and store probes during store setup/audit.

- [ ] **Step 5: Verify**

Run probe tests and full unit test suite.

### Task 4: Post-Order Actions

**Files:**
- Create: `post_order_actions.py`
- Modify: `trace_runner.py`
- Modify: `user_sim.py`
- Modify: `scenarios.py`
- Test: `tests/test_simulate.py`

- [ ] **Step 1: Write failing tests**

Test request shapes for generate receipt, submit review, and reorder.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_simulate.PostOrderActionTests -v`
Expected: failure because `post_order_actions` does not exist.

- [ ] **Step 3: Implement actions**

Add receipt, review, and reorder helpers using `request_json`.

- [ ] **Step 4: Wire to completed flows**

After completed scenarios, run receipt/review/reorder probes when enabled.

- [ ] **Step 5: Verify**

Run post-order tests and full unit test suite.

### Task 5: Friendly Presets and Docs

**Files:**
- Modify: `flow_presets.py`
- Modify: `scenarios.py`
- Modify: `ARCHITECTURE.md`
- Create: `SIMULATOR_GUIDE.md`
- Test: `tests/test_simulate.py`

- [ ] **Step 1: Write failing preset tests**

Verify `doctor`, `full`, `receipt-review`, and `store-dashboard` presets resolve.

- [ ] **Step 2: Implement presets**

Map friendly names to existing and new scenarios.

- [ ] **Step 3: Write guidebook**

Document installation, JSON input, commands, scenario catalog, report interpretation, assumptions, limitations, troubleshooting, and rebuild architecture.

- [ ] **Step 4: Verify**

Run compile, unit tests, and CLI help.
