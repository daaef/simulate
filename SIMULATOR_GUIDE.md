# Fainzy Simulator Guidebook

This simulator is a daily doctor for the ordering platform. It simulates user app, store app, and robot behavior; continuously checks HTTP and websocket paths; and writes operator-friendly reports plus full technical evidence.

## 1) Inputs and Outputs

Required operator inputs:

- `.env` for environment URLs and secrets.
- A plan JSON (default `sim_actors.json`) with users (phone + delivery GPS) and stores (`store_id`, optional metadata).

Generated artifacts per run:

- `runs/<timestamp>/events.json`: complete event ledger.
- `runs/<timestamp>/report.md`: summary + bottlenecks + tabled findings + technical trace.
- `runs/<timestamp>/story.md`: narrative scenario summary.

## 2) Validated Command Matrix

All rows below are supported flow presets exposed by CLI help.

| Flow Preset | Resolved Mode/Suite/Scenarios | What It Tests | Required Prerequisites | Key Optional Flags | Artifacts |
| --- | --- | --- | --- | --- | --- |
| `doctor` | `trace` + suite `doctor` | Daily core health: app bootstrap, setup/dashboard, menus, paid flow, accept/reject, robot complete, receipt/review/reorder | Valid user/store in plan; Stripe key for paid path unless paid path is converted to free by coupon coverage | `--timing`, `--store`, `--phone`, `--plan`, `--strict-plan`, `--no-auto-provision`, `--skip-app-probes`, `--skip-store-dashboard-probes` | `events.json`, `report.md`, `story.md` |
| `full` | `trace` + suite `full` | Broadest suite: includes new-user and coupon variants in addition to doctor coverage | Same as `doctor`, plus coupon availability for coupon scenarios (or auto-select coupon enabled) | Same as `doctor` | Same |
| `audit` | `trace` + suite `audit` | Full app/store/menus/payments/post-order verification with scenario granularity | Same as `full` | Same as `doctor` | Same |
| `payments` | `trace` + suite `payments` | Paid no-coupon, paid with coupon, free with coupon payment routing | Stripe for paid branches; coupon for coupon branches (or auto-select coupon) | `--timing`, `--phone`, `--store`, `--no-auto-provision` | Same |
| `menus` | `trace` + suite `menus` | Menu availability behavior (available/unavailable/sold-out/store-closed) | Valid fixtures (store + menu); auto-provision can repair missing setup/menu | `--timing`, `--store`, `--no-auto-provision` | Same |
| `new-user` | `trace` + scenario `new_user_setup` | OTP + create-user path and first-time setup assertions | Phone in plan not fully onboarded (or backend forcing create path) | `--phone`, `--timing`, `--store`, `--no-auto-provision` | Same |
| `paid-no-coupon` | `trace` + scenario `returning_paid_no_coupon` | Standard paid checkout route | Stripe key and valid fixtures | `--timing`, `--phone`, `--store`, `--post-order-actions` | Same |
| `paid-coupon` | `trace` + scenario `returning_paid_with_coupon` | Coupon checkout path with paid endpoint unless coupon fully covers total | Coupon configured/available (or auto-select coupon enabled) | `--timing`, `--phone`, `--store`, `--no-auto-provision` | Same |
| `free-coupon` | `trace` + scenario `returning_free_with_coupon` | Coupon path targeting free-order behavior | Coupon configured/available (or auto-select coupon enabled) | `--timing`, `--phone`, `--store`, `--no-auto-provision` | Same |
| `store-setup` | `trace` + scenario `store_first_setup` | Store setup/profile patch, store open/restore, category/menu readiness | Store auth must succeed | `--store`, `--timing`, `--no-auto-provision` | Same |
| `store-dashboard` | `trace` + scenario `store_dashboard` | Store-side probes: orders, statistics, top customers | Store auth must succeed | `--store`, `--timing`, `--skip-store-dashboard-probes` | Same |
| `store-accept` | `trace` + scenario `store_accept` | One completed order framed as accept behavior | Stripe key unless payment route becomes free | `--timing`, `--store`, `--phone` | Same |
| `store-reject` | `trace` + scenario `store_reject` | One rejected order framed as reject behavior | Valid fixtures | `--timing`, `--store`, `--phone` | Same |
| `robot-complete` | `trace` + scenario `robot_complete` | End-to-end robot status progression to completed | Valid fixtures; Stripe key unless free payment path applies | `--timing`, `--store`, `--phone` | Same |
| `receipt-review` | `trace` + scenario `receipt_review_reorder` | Completed order + receipt + review + reorder actions | Completed order path must succeed | `--timing`, `--store`, `--phone`, `--post-order-actions` | Same |
| `load` | `load` | Concurrent users/stores/robots, repeated order traffic, performance and stability | Plan with usable users/stores; Stripe for paid runs | `--users`, `--orders`, `--interval`, `--reject`, `--continuous`, `--all-users`, `--store`, `--phone`, `--no-auto-provision` | Same |

### Exhaustive Command Combination Catalog (Supported Practical Set)

This section enumerates every supported command family and value set (flow presets, suites, scenarios, and load variants) with descriptions. It is exhaustive for practical operator usage and CLI-supported values; it intentionally avoids infinite cartesian expansion of unrelated flag permutations.

#### A) Every Flow Preset Command

| Command | Description |
| --- | --- |
| `python3 -m simulate doctor --plan sim_actors.json` | Daily recommended trace suite. |
| `python3 -m simulate full --plan sim_actors.json` | Widest trace suite including new-user and coupon branches. |
| `python3 -m simulate audit --plan sim_actors.json` | Broad audit suite with scenario-level verification. |
| `python3 -m simulate payments --plan sim_actors.json` | Payment-only suite (paid/coupon/free-coupon). |
| `python3 -m simulate menus --plan sim_actors.json` | Menu behavior suite (available/unavailable/sold-out/store-closed). |
| `python3 -m simulate new-user --plan sim_actors.json` | Runs only new-user setup path. |
| `python3 -m simulate paid-no-coupon --plan sim_actors.json` | Runs paid checkout without coupon. |
| `python3 -m simulate paid-coupon --plan sim_actors.json` | Runs paid checkout with coupon path. |
| `python3 -m simulate free-coupon --plan sim_actors.json` | Runs free-with-coupon path. |
| `python3 -m simulate store-setup --plan sim_actors.json` | Runs store setup/update/menu readiness path. |
| `python3 -m simulate store-dashboard --plan sim_actors.json` | Runs store dashboard probe path. |
| `python3 -m simulate store-accept --plan sim_actors.json` | Runs accept-focused completed-order path. |
| `python3 -m simulate store-reject --plan sim_actors.json` | Runs reject-focused order path. |
| `python3 -m simulate robot-complete --plan sim_actors.json` | Runs robot completion lifecycle path. |
| `python3 -m simulate receipt-review --plan sim_actors.json` | Runs completed order + receipt/review/reorder path. |
| `python3 -m simulate load --plan sim_actors.json` | Runs concurrent load-mode simulation. |

#### B) Every Trace Suite Command

| Command | Description |
| --- | --- |
| `python3 -m simulate --mode trace --suite core --plan sim_actors.json` | Core completed/rejected/cancelled suite. |
| `python3 -m simulate --mode trace --suite payments --plan sim_actors.json` | All payment permutations suite. |
| `python3 -m simulate --mode trace --suite menus --plan sim_actors.json` | Menu-state gating suite. |
| `python3 -m simulate --mode trace --suite store --plan sim_actors.json` | Store setup + accept + reject suite. |
| `python3 -m simulate --mode trace --suite audit --plan sim_actors.json` | Broad audit suite. |
| `python3 -m simulate --mode trace --suite doctor --plan sim_actors.json` | Daily doctor suite. |
| `python3 -m simulate --mode trace --suite full --plan sim_actors.json` | Maximal full suite. |

#### C) Every Trace Scenario Command

| Command | Description |
| --- | --- |
| `python3 -m simulate --mode trace --scenario completed --plan sim_actors.json` | End-to-end successful order flow. |
| `python3 -m simulate --mode trace --scenario rejected --plan sim_actors.json` | Store reject flow. |
| `python3 -m simulate --mode trace --scenario cancelled --plan sim_actors.json` | User cancel flow. |
| `python3 -m simulate --mode trace --scenario auto_cancel --plan sim_actors.json` | Backend auto-cancel diagnostic flow. |
| `python3 -m simulate --mode trace --scenario new_user_setup --plan sim_actors.json` | New-user setup flow. |
| `python3 -m simulate --mode trace --scenario returning_paid_no_coupon --plan sim_actors.json` | Returning paid, no coupon flow. |
| `python3 -m simulate --mode trace --scenario returning_paid_with_coupon --plan sim_actors.json` | Returning paid with coupon flow. |
| `python3 -m simulate --mode trace --scenario returning_free_with_coupon --plan sim_actors.json` | Returning free-with-coupon flow. |
| `python3 -m simulate --mode trace --scenario menu_available --plan sim_actors.json` | Menu available state check. |
| `python3 -m simulate --mode trace --scenario menu_unavailable --plan sim_actors.json` | Menu unavailable state check. |
| `python3 -m simulate --mode trace --scenario menu_sold_out --plan sim_actors.json` | Menu sold-out state check. |
| `python3 -m simulate --mode trace --scenario menu_store_closed --plan sim_actors.json` | Menu/store-closed state check. |
| `python3 -m simulate --mode trace --scenario store_first_setup --plan sim_actors.json` | Store first setup flow. |
| `python3 -m simulate --mode trace --scenario store_accept --plan sim_actors.json` | Store accept flow. |
| `python3 -m simulate --mode trace --scenario store_reject --plan sim_actors.json` | Store reject flow. |
| `python3 -m simulate --mode trace --scenario robot_complete --plan sim_actors.json` | Robot completion flow. |
| `python3 -m simulate --mode trace --scenario app_bootstrap --plan sim_actors.json` | User app bootstrap probes flow. |
| `python3 -m simulate --mode trace --scenario store_dashboard --plan sim_actors.json` | Store dashboard probes flow. |
| `python3 -m simulate --mode trace --scenario receipt_review_reorder --plan sim_actors.json` | Receipt/review/reorder flow. |

Multiple-scenario explicit combinations:

- `python3 -m simulate --mode trace --scenario completed --scenario rejected --plan sim_actors.json`: runs listed scenarios in order.
- `python3 -m simulate --mode trace --scenario app_bootstrap --scenario store_dashboard --scenario receipt_review_reorder --plan sim_actors.json`: probes + post-order focused run.

#### D) Load Command Combinations

| Command | Description |
| --- | --- |
| `python3 -m simulate load --plan sim_actors.json --users 1 --orders 1` | Minimal bounded load smoke test. |
| `python3 -m simulate load --plan sim_actors.json --all-users --users 10 --orders 100 --interval 3 --reject 0.1` | Concurrent bounded multi-user load. |
| `python3 -m simulate load --plan sim_actors.json --all-users --users 10 --continuous --interval 10` | Continuous load until manual stop. |
| `python3 -m simulate load --plan sim_actors.json --store FZY_926025 --users 5 --orders 50` | Bounded load pinned to one store. |
| `python3 -m simulate load --plan sim_actors.json --phone +2348166675609 --users 3 --orders 30` | Bounded load pinned to one user phone. |
| `python3 -m simulate load --plan sim_actors.json --strict-plan --users 5 --orders 20` | Enforces strict plan validation before load. |
| `python3 -m simulate load --plan sim_actors.json --no-auto-provision --users 3 --orders 10` | Load test without setup/menu auto-repair. |
| `python3 -m simulate load --plan sim_actors.json --skip-app-probes --skip-store-dashboard-probes --users 5 --orders 40` | Load focused on core ordering paths with probes disabled. |

#### E) Universal Modifiers and Meanings

| Combination | Description |
| --- | --- |
| `... --timing fast` | Uses fast deterministic trace delays. |
| `... --timing realistic` | Uses realistic deterministic trace delays. |
| `... --store <STORE_ID>` | Forces explicit store; disables store fallback autopilot. |
| `... --phone <PHONE>` | Forces explicit user phone selection. |
| `... --strict-plan` | Requires full plan quality gate (user GPS + store IDs). |
| `... --no-auto-provision` | Disables automatic setup/category/menu repair. |
| `... --skip-app-probes` | Disables user-side app probes. |
| `... --skip-store-dashboard-probes` | Disables store dashboard probes. |
| `... --post-order-actions` | Forces receipt/review/reorder after completed orders. |

### Supported/Unsupported Combination Rules

Supported and meaningful:

- `python3 -m simulate doctor --plan sim_actors.json --timing fast`
- `python3 -m simulate load --plan sim_actors.json --all-users --users 10 --orders 100 --interval 2`
- `python3 -m simulate --mode trace --suite doctor --timing realistic`
- `python3 -m simulate --mode trace --scenario completed --scenario rejected`

Validated incompatibilities and behavior constraints:

- `trace` + `--continuous` is invalid and fails validation.
- Coupon scenarios fail fast when both are true: no `SIM_COUPON_ID` and `SIM_AUTO_SELECT_COUPON=false`.
- `--users`, `--orders`, `--interval`, `--reject`, `--all-users`, `--continuous` are load-mode controls; in trace they do not change scenario logic.
- `--suite` / `--scenario` are trace controls; in load they do not alter load orchestration.
- `--store` sets explicit store mode; with explicit store, auto store fallback is disabled.
- `--no-auto-provision` disables auto-provision path (`SIM_AUTO_PROVISION_FIXTURES=false`) for that run.

## 3) Detailed Command Reference

### 3.1 `python3 -m simulate <flow> ...`

Use this for operator-first runs. `<flow>` maps to one preset from the matrix above.

When to use:

- You want app-like behavior with minimal CLI complexity.
- You need a repeatable named audit path (`doctor`, `full`, `load`, etc.).

What it tests:

- Exactly what the selected preset maps to (mode + suite/scenario + payment defaults).

Expected outcomes:

- Successful run writes all three artifacts and prints run paths.
- On functional failures, run still writes artifacts and exits with findings.

Common failure signatures:

- `No active delivery locations were returned`: delivery GPS/radius issue.
- `No usable store candidate could serve this simulation`: all candidate stores failed setup/fixtures.
- `SIM_COUPON_ID is required for coupon flows`: auto coupon selection disabled and no configured coupon.
- `STRIPE_SECRET_KEY is required`: paid flow selected without Stripe secret.

### 3.2 `python3 -m simulate --mode trace --suite <suite> ...`

Use this when you want deterministic suite-level coverage without using a flow alias.

When to use:

- You want direct suite control (`core`, `payments`, `menus`, `store`, `doctor`, `audit`, `full`).

What it tests:

- Ordered scenario list defined in `scenarios.TRACE_SUITES`.

Expected outcomes:

- Each scenario produces a verdict row in report.
- Technical trace shows endpoint-level evidence per scenario.

Common failure signatures:

- Setup/menu gating failures if auto-provision is off and fixtures are missing.
- Websocket assertion warnings for missing expected status events.

### 3.3 `python3 -m simulate --mode trace --scenario <scenario> ...`

Use this for targeted diagnostics. Repeat `--scenario` to chain multiple explicit scenarios.

When to use:

- You need one narrow behavior proof (for example only `store_reject`).

What it tests:

- Only listed scenarios in declaration order, de-duplicated.

Expected outcomes:

- Report focuses only on selected scenarios.
- Useful for quick backend regression confirmation.

Common failure signatures:

- Scenario-specific prerequisites missing (coupon/Stripe/setup/menu).
- Unexpected final status mismatch (reported as blocked/degraded verdict).

### 3.4 `python3 -m simulate --mode load ...`

Use this for concurrency and durability testing.

When to use:

- You want to simulate many users and stores placing orders over time.

What it tests:

- Multi-worker auth/bootstrap + repeated ordering + store/robot listeners + websocket matching under load.

Expected outcomes:

- Bounded mode stops after requested orders.
- Continuous mode runs until interrupted.

Common failure signatures:

- Missing users/stores in plan.
- Backend throttling/timeouts under aggressive intervals.
- Setup/menu preflight disabled while fixture prerequisites are absent.

## 4) Parameter Reference

| Flag | Type | Default | Effect | Constraints / Interactions |
| --- | --- | --- | --- | --- |
| `--mode` | `load` or `trace` | from env (`SIM_RUN_MODE`) | Selects orchestration model | `trace` rejects `--continuous` |
| `--suite` | string | from env (`SIM_TRACE_SUITE`) | Selects trace suite | Trace-mode only |
| `--scenario` | repeatable string | none | Appends explicit trace scenarios | Trace-mode only; invalid names fail |
| `--timing` | `fast` or `realistic` | `fast` | Controls deterministic delays in trace | Does not throttle load worker creation |
| `--users` | int | `1` | User worker count for load | Must be `>=1` in load |
| `--orders` | int | `1` | Total orders in bounded load | Must be `>=1` in load unless `--continuous` |
| `--interval` | float seconds | `30.0` | Delay between user order attempts in load | Load-mode control |
| `--reject` | float `0..1` | `0.1` | Probabilistic store rejection rate in load | Must be between `0` and `1` |
| `--continuous` | boolean | `false` | Infinite load run | Invalid in trace |
| `--phone` | string | none | Overrides selected user phone | Should exist in plan for deterministic selection |
| `--store` | string | none | Forces a specific store ID | Disables store fallback behavior by marking explicit store |
| `--all-users` | boolean | `false` | In load, auth and run all plan users | Load-mode control |
| `--plan` | path | `sim_actors.json` | Run plan JSON path | Relative paths resolve from current cwd first |
| `--strict-plan` | boolean | `false` | Enforces user GPS + store IDs at load time | Fails fast on missing required plan fields |
| `--skip-app-probes` | boolean | `false` | Disables user-side non-order probes | Affects `app_bootstrap`/doctor/full/audit evidence depth |
| `--skip-store-dashboard-probes` | boolean | `false` | Disables store dashboard probes | Affects `store_dashboard` coverage |
| `--post-order-actions` | boolean | env default | Enables receipt/review/reorder after completed orders | Can create real review/receipt records |
| `--no-auto-provision` | boolean | `false` | Disables automatic setup/category/menu repair path | Sets `SIM_AUTO_PROVISION_FIXTURES=false` for run |

## 5) What We Test (Coverage Map)

### User-app probes (`app_probes.py`)

- `GET /v1/entities/configs/`
- `POST /v1/biz/product/authentication/?product=rds`
- `GET /v1/biz/pricing/0/?product_name=lastmile&currency=<currency>`
- `GET /v1/core/cards/`
- `GET /v1/core/coupon/`
- `GET /v1/core/orders/?user=<user_id>`

### Store-app probes (`app_probes.py`)

- `GET /v1/core/orders/?subentity_id=<id>`
- `GET /v1/statistics/subentities/<id>/`
- `GET /v1/statistics/subentities/<id>/top-customers/`

### Core order lifecycle

- Create order: `POST /v1/core/orders/`
- Fetch order: `GET /v1/core/orders/?order_id=<id>`
- Cancel order: `PATCH /v1/core/orders/?order_id=<id>` with `cancelled`
- Store decisions: `PATCH /v1/core/orders/?order_id=<id>` with `payment_processing`, `rejected`, `ready`
- Free-order completion: `POST /v1/core/order/free/`
- Payment path: Stripe simulation flow for paid scenarios

### Store setup + menu readiness

- Store login/profile: `POST /v1/entities/store/login`
- Store setup/update patch: `PATCH /v1/entities/subentities/<id>`
- Store open/restore patch: `PATCH /v1/entities/subentities/<id>` with status toggles
- Categories: `GET/POST /v1/core/subentities/<id>/categories`
- Menus: `GET/POST/PATCH /v1/core/subentities/<id>/menu...`

### Post-order actions (`post_order_actions.py`)

- Receipt: `GET /v1/core/generate-receipt/<order_id>/`
- Review: `POST /v1/core/reviews/`
- Reorder: `GET /v1/core/reorder/?order_id=<id>`

### Websocket channels

- User orders: `/ws/soc/<user_id>/`
- Store orders: `/ws/soc/store_<subentity_id>/`
- Store stats: `/ws/soc/store_statistics_<subentity_id>/`

### Assertion model

- Scenario expected vs actual terminal status.
- Per-order status path continuity.
- Expected websocket events matched by order and status, with match latency.
- Endpoint latency metrics (avg/p50/p95/max) and slowest endpoints.

## 6) Timing Profiles

`--timing fast`:

- Store decision delay: `0.2s .. 0.5s`
- Store prep delay: `0.2s .. 0.5s`
- Robot:
  - `enroute_pickup`: `0.2s .. 0.5s`
  - `robot_arrived_for_pickup`: `0.2s .. 0.4s`
  - `enroute_delivery`: `0.2s .. 0.6s`
  - `robot_arrived_for_delivery`: `0.2s .. 0.4s`
  - `completed`: `0.2s .. 0.3s`
- Auto-cancel wait: `30s`

`--timing realistic`:

- Store decision delay: `3s .. 12s`
- Store prep delay: `20s .. 90s`
- Robot:
  - `enroute_pickup`: `20s .. 60s`
  - `robot_arrived_for_pickup`: `5s .. 20s`
  - `enroute_delivery`: `30s .. 120s`
  - `robot_arrived_for_delivery`: `5s .. 20s`
  - `completed`: `2s .. 8s`
- Auto-cancel wait: `180s`

## 7) Store Behavior When `setup=true`

With auto-provision enabled (`SIM_AUTO_PROVISION_FIXTURES=true`, default), preflight now does this:

1. Detect store profile already setup.
2. Submit a profile update patch (`submit_store_update`) using profile-shaped payload derived from current backend values (fallback to simulator defaults only when fields are missing).
3. Continue with category/menu readiness checks.
4. Open store if closed, and restore original status during cleanup.

With `--no-auto-provision` (or `SIM_AUTO_PROVISION_FIXTURES=false`), the setup-true update mutation is skipped.

## 8) Report Tables and Identity Columns

The main report now includes explicit user/store identity context in operational tables:

- `Scenario Verdicts`
- `Order Lifecycle`
- `Websocket Assertions`
- `Developer Findings`

Identity format:

- User: `id / name / phone`
- Store: `subentity_id / store_login_id / name / branch / phone`

This lets operators correlate failures without digging through payload blobs.

## 9) Quick Start Commands

Daily recommended run:

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

Broad audit:

```bash
python3 -m simulate full --plan sim_actors.json --timing fast
```

High-concurrency load:

```bash
python3 -m simulate load --plan sim_actors.json --all-users --users 10 --orders 100 --interval 3 --reject 0.1
```

Targeted store setup only:

```bash
python3 -m simulate store-setup --plan sim_actors.json --store FZY_926025 --timing fast
```

## 10) Common Failures

- `No active delivery locations were returned`: adjust user delivery GPS (`SIM_LAT/SIM_LNG` or plan user GPS) and radius.
- `No available priced menu items found`: enable auto-provision or check store/menu endpoints.
- `No usable store candidate could serve this simulation`: every candidate store failed login/setup/fixture bootstrap.
- `SIM_COUPON_ID is required for coupon flows`: configure coupon or enable auto-select coupon.
- `STRIPE_SECRET_KEY is required`: paid flow selected without Stripe key.

## 11) Rebuild Outline (from scratch)

1. Config/plan parser with env + JSON validation.
2. HTTP transport wrapper with auth proof, masking, latency, structured events.
3. Recorder with events/issues/scenarios/orders + report/story/event artifact writers.
4. User actor (auth, fixtures, order, payment/cancel, websocket).
5. Store actor (auth, profile/setup/update, menu/category, status patching, websocket).
6. Robot actor (delivery status progression).
7. Trace orchestrator (scenario suites + deterministic assertions).
8. Load orchestrator (multi-user/multi-store concurrent runners).
9. Health summary builder (verdicts, latency percentiles, websocket match rate, bottlenecks).
10. Operator docs (this guide + command matrix + parameter/coverage reference).
