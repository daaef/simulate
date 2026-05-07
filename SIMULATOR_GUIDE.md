# Fainzy Simulator Guidebook

This simulator is a daily doctor for the ordering platform. It simulates user app, store app, and robot behavior; continuously checks HTTP and websocket paths; and writes operator-friendly reports plus full technical evidence.

## 1) Inputs and Outputs

Required operator inputs:

- `.env` for secrets, auth cache values, credentials, and deployment URLs only.
- A plan JSON (default `sim_actors.json`) with users, stores, GPS, runtime defaults, rules, fixture defaults, payment defaults without Stripe secrets, review defaults, and new-user metadata.

Generated artifacts per run:

- `runs/<timestamp>/events.json`: complete event ledger.
- `runs/<timestamp>/report.md`: summary + bottlenecks + tabled findings + technical trace.
- `runs/<timestamp>/story.md`: narrative scenario summary.

Configuration precedence:

1. Explicit CLI flags.
2. Values from the selected plan JSON.
3. `.env` fallback for secret/auth/deployment values.
4. Built-in defaults.

The GUI stores admin-created plans in `runs/gui-plans/` and launches them through the same `--plan` CLI path.

## Plan-Backed Configuration

Existing actor-only plans remain valid:

```json
{
  "defaults": {"user_phone": "+2348166675609", "store_id": "FZY_586940"},
  "users": [{"phone": "+2348166675609", "role": "returning"}],
  "stores": [{"store_id": "FZY_586940", "subentity_id": 6}]
}
```

Richer plans can also carry non-sensitive defaults:

```json
{
  "schema_version": 2,
  "defaults": {
    "user_phone": "+2348166675609",
    "store_id": "FZY_586940",
    "location_radius": 1,
    "coupon_id": null
  },
  "runtime_defaults": {
    "flow": "doctor",
    "mode": "trace",
    "trace_suite": "doctor",
    "timing_profile": "fast",
    "users": 1,
    "orders": 1,
    "interval_seconds": 30,
    "reject_rate": 0.1,
    "continuous": false
  },
  "rules": {
    "strict_plan": false,
    "run_app_probes": true,
    "run_store_dashboard_probes": true,
    "run_post_order_actions": false,
    "auto_select_store": true,
    "auto_select_coupon": true,
    "auto_provision_fixtures": true
  },
  "payment_defaults": {
    "mode": "stripe",
    "case": "paid_no_coupon",
    "coupon_id": null,
    "save_card": false,
    "test_payment_method": "pm_card_visa"
  },
  "fixture_defaults": {
    "store_setup": {"name": "Fainzy Simulator Store", "city": "Nagoya"},
    "menu": {"category_name": "Simulator", "name": "Simulator item", "price": 100}
  },
  "review_defaults": {"rating": 4, "comment": "Simulator review"},
  "new_user_defaults": {"first_name": "Fainzy", "last_name": "Simulator", "email": ""},
  "users": [{"phone": "+2348166675609", "role": "returning"}],
  "stores": [{"store_id": "FZY_586940", "subentity_id": 6}]
}
```

Keep these out of plan JSON: keys containing `secret`, `token`, `password`, `api_key`, or `private_key`. Plan validation rejects them. Stripe secret keys, cached auth tokens, test-user passwords, and deployment URLs stay in `.env`.

Keep normal simulator behavior out of `.env`. Phone/store selection, delivery GPS, runtime defaults, fixture/menu defaults, payment mode/coupon defaults, review defaults, and new-user names/email belong in `sim_actors.json` or the selected GUI plan. If the GUI Phone field is blank, the launched run uses the selected plan's phone; if `--phone` is supplied, that explicit CLI value wins.

Admins can edit GUI-owned plans at `Config` in the web UI. The saved `path` field is launchable from the Runs page and from CLI:

```bash
python3 -m simulate doctor --plan runs/gui-plans/daily-doctor.json --timing fast
```

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
- Coupon scenarios fail fast when both are true: no configured plan/env coupon id and auto coupon selection is disabled.
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
- `SIM_COUPON_ID is required for coupon flows`: auto coupon selection disabled and no plan/env coupon is configured.
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
| `--mode` | `load` or `trace` | from plan/env (`SIM_RUN_MODE`) | Selects orchestration model | `trace` rejects `--continuous` |
| `--suite` | string | from plan/env (`SIM_TRACE_SUITE`) | Selects trace suite | Trace-mode only |
| `--scenario` | repeatable string | none | Appends explicit trace scenarios | Trace-mode only; invalid names fail |
| `--timing` | `fast` or `realistic` | from plan/env (`SIM_TIMING_PROFILE`) | Controls deterministic delays in trace | Does not throttle load worker creation |
| `--users` | int | from plan/env (`N_USERS`) | User worker count for load | Must be `>=1` in load |
| `--orders` | int | from plan/env (`SIM_ORDERS`) | Total orders in bounded load | Must be `>=1` in load unless `--continuous` |
| `--interval` | float seconds | from plan/env (`ORDER_INTERVAL_SECONDS`) | Delay between user order attempts in load | Load-mode control |
| `--reject` | float `0..1` | from plan/env (`REJECT_RATE`) | Probabilistic store rejection rate in load | Must be between `0` and `1` |
| `--continuous` | boolean | from plan/env (`SIM_CONTINUOUS`) | Infinite load run | Invalid in trace |
| `--phone` | string | none | Overrides selected user phone | Should exist in plan for deterministic selection |
| `--store` | string | none | Forces a specific store ID | Disables store fallback behavior by marking explicit store |
| `--all-users` | boolean | `false` | In load, auth and run all plan users | Load-mode control |
| `--plan` | path | `sim_actors.json` | Run plan JSON path | Relative paths resolve from current cwd first |
| `--strict-plan` | boolean | from plan/env (`SIM_STRICT_PLAN`) | Enforces user GPS + store IDs at load time | Fails fast on missing required plan fields |
| `--skip-app-probes` | boolean | `false` | Disables user-side non-order probes | Affects `app_bootstrap`/doctor/full/audit evidence depth |
| `--skip-store-dashboard-probes` | boolean | `false` | Disables store dashboard probes | Affects `store_dashboard` coverage |
| `--post-order-actions` | boolean | from plan/env | Enables receipt/review/reorder after completed orders | Can create real review/receipt records |
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

- `No active delivery locations were returned`: adjust plan user delivery GPS and radius.
- `No available priced menu items found`: enable auto-provision or check store/menu endpoints.
- `No usable store candidate could serve this simulation`: every candidate store failed login/setup/fixture bootstrap.
- `SIM_COUPON_ID is required for coupon flows`: configure a plan/env coupon or enable auto-select coupon.
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

## 12) Web UI Authentication, Admin Account, and Roles

The dockerized web UI is available at:

```bash
http://localhost:8080
```

Default admin login:

| Field | Value |
| --- | --- |
| Username | `admin` |
| Password | `admin123` |
| Email | `admin@simulator.local` |
| Role | `admin` |

Change this password before shared, staging, or production use. The default admin is seeded by `api/migrations/001-initial-schema.sql`; after a PostgreSQL volume already exists, changing that migration file does not update the running database.

### Role Model

Allowed persisted roles are:

| Role | Intended use | Permissions |
| --- | --- | --- |
| `admin` | Full system administrator. | Create/read/update/delete users, reset passwords, create/read/update/cancel/delete runs, create/read/update/delete/trigger schedules, read alerts, read/delete archives, read/update retention, read/configure system settings. |
| `operator` | Normal simulator operator. | Create/read/cancel runs, create/read/update/trigger schedules, read alerts, read dashboard, read archives, read retention settings. |
| `runner` | Limited user who can start and inspect runs. | Create/read runs, read schedules, read alerts, read dashboard. Cannot cancel runs, delete runs, mutate schedules, manage users, or change retention/system settings. |
| `viewer` | Read-only product/operations user. | Read runs, dashboard, schedules, alerts, archives, and retention settings. |
| `auditor` | Read-only evidence/audit user. | Same read-only access as `viewer`; use this role when the account exists for compliance, evidence review, or investigation workflows. |

Legacy role `user` is normalized to `operator` by the role migration and should not be used for new accounts.

### Authentication Behavior

- Self-service registration is disabled: `POST /api/v1/auth/register` always returns `403`.
- Users must be created by an `admin`.
- Browser login uses the HTTP-only `simulator_session` cookie.
- One active browser session is kept per user. Logging in again as the same user invalidates that user's previous session.
- Cookie defaults are `simulator_session`, seven-day max age, `SameSite=Lax`, path `/`, and `Secure=false` unless overridden by environment.
- `SIM_AUTH_DISABLED=true` creates a local development admin identity only outside production; it is rejected when `SIM_ENV=production` or `SIM_ENV=prod`.
- In production, set a strong `JWT_SECRET_KEY`; the default placeholder is rejected in production.

### Operations Routes

The authenticated app shell highlights the active route, including nested run detail pages. Current operations routes:

| Route | Purpose |
| --- | --- |
| `/overview` | Run status, flow distribution, success/failure split, failure trend, archive/purge backlog, schedule health, alerts, and platform status. |
| `/runs` | Launch, cancel, replay, delete completed runs, inspect top-of-page run statistics, logs, artifacts, event data, and saved run profiles. |
| `/config` | Edit GUI-owned run plans under `runs/gui-plans/`. |
| `/schedules` | Create profile-backed simple schedules and campaign schedules; configure active date/time ranges, run windows, blackout skip dates, and next automatic trigger visibility; active schedules run through the in-process scheduler and can also be manually triggered, paused, resumed, disabled, soft-deleted, and restored. |
| `/archives` | Search archive candidates, raw-purge candidates, and retained run summaries. |
| `/retention` | Inspect active/archive policy windows, archive/purge queues, retained summary fields, and purge-safety state. |
| `/admin/users` | Create, edit, reset, deactivate, or delete users. |
| `/admin/system` | Configure system policies such as allowed scheduling timezones (IANA allowlist). |

### Schedule and Campaign APIs

Schedules use saved run profiles as their execution source. V1 keeps execution in-process with APScheduler and does not require Celery or Redis. The scheduler polls once per minute, launches due active schedules, records a schedule execution row, and advances `next_run_at`.

Preferred contract for new/edited schedules:

- `anchor_start_at`: first automated start timestamp.
- `period`: `hourly` | `daily` | `weekly` | `monthly`.
- `stop_rule`: `never` | `end_at` | `duration`.
- `runs_per_period`: desired run count per period window.
- optional `run_window_start` / `run_window_end` and `blackout_dates`.

Legacy cadence/custom fields remain accepted for compatibility with existing schedules.

The scheduler computes `next_run_at` with this exact precedence:

1. Cadence anchor candidate.
2. Active date range bounds.
3. Run window bounds.
4. Blackout date skips.

The schedules UI shows pre-submit mode (`Automatic` or `Manual-only`) and next-trigger preview, then surfaces server-computed `next_run_at`, `execution_mode_label`, and `next_run_reason` in schedule rows.
The schedules page auto-refreshes schedule and execution state every 15 seconds and also revalidates when the browser tab regains focus, so newly triggered automatic runs appear without manual page reload.

Scheduling procedure:

1. Create or choose a saved run profile from `/runs`; schedules launch profiles, not ad hoc form state.
2. Open `/schedules`, choose `simple` for one profile or `campaign` for ordered campaign steps, then set cadence and timezone.
3. For `custom` cadence, set `custom_anchor_at` and `custom_every_n_days`; non-custom cadences must not send custom fields.
4. Use `Active From` and `Active Until` to define optional automatic scheduling date-time bounds. Leave either side blank for no start or end boundary.
5. Use `Window Start` and `Window End` for allowed local time-of-day execution. If a candidate is outside window, it shifts to next window start.
6. Add blackout dates for full local calendar days when automatic triggers must not run. Manual `Trigger` still launches immediately.
7. Save the schedule, then confirm the `Next Automatic Trigger` panel and table metadata.
8. Use `Pause`, `Resume`, `Disable`, `Delete`, and `Restore` for lifecycle control. `pause`, `disable`, and `delete` clear `next_run_at`; `resume` and `restore` recalculate it.

Key endpoints:

```bash
GET  /api/v1/schedules
GET  /api/v1/schedules/summary
POST /api/v1/schedules
PUT  /api/v1/schedules/<SCHEDULE_ID>
POST /api/v1/schedules/<SCHEDULE_ID>/trigger
POST /api/v1/schedules/<SCHEDULE_ID>/pause
POST /api/v1/schedules/<SCHEDULE_ID>/resume
POST /api/v1/schedules/<SCHEDULE_ID>/disable
POST /api/v1/schedules/<SCHEDULE_ID>/delete
POST /api/v1/schedules/<SCHEDULE_ID>/restore
```

Simple schedule payload:

```json
{
  "name": "daily doctor",
  "schedule_type": "simple",
  "profile_id": 1,
  "cadence": "daily",
  "timezone": "UTC",
  "active_from": "2026-05-07T08:00:00+01:00",
  "active_until": "2026-05-31T18:00:00+01:00",
  "run_window_start": "08:00",
  "run_window_end": "18:00",
  "blackout_dates": ["2026-12-25"]
}
```

Campaign schedule payload:

```json
{
  "name": "doctor campaign",
  "schedule_type": "campaign",
  "cadence": "custom",
  "timezone": "UTC",
  "custom_anchor_at": "2026-05-10T14:20:00+00:00",
  "custom_every_n_days": 3,
  "campaign_steps": [
    {
      "profile_id": 1,
      "repeat_count": 2,
      "spacing_seconds": 30,
      "timeout_seconds": 900,
      "failure_policy": "continue",
      "execution_mode": "saved_profile"
    }
  ]
}
```

Manual trigger launches runs immediately through the saved profile path and records a schedule execution row.

#### Field Reference and Validation

- `name`: required, non-empty.
- `schedule_type`: `simple` (single profile) or `campaign` (ordered steps).
- `profile_id`: required for `simple`; forbidden/ignored for `campaign`.
- `cadence`: `hourly`, `daily`, `weekdays`, `weekly`, `monthly`, `custom`.
- `timezone`: required IANA timezone; constrained by optional system allowlist.
- `active_from` / `active_until`: optional ISO date-times; `active_until` must be later than `active_from`.
- `run_window_start` / `run_window_end`: optional `HH:MM` 24-hour times; window can cross midnight.
- `blackout_dates`: optional list of `YYYY-MM-DD` local dates to skip.
- `custom_anchor_at`: required only when `cadence=custom`; forbidden otherwise.
- `custom_every_n_days`: required only when `cadence=custom`; integer `>= 1`; forbidden otherwise.

#### Cadence Behaviors and Required Data

| Cadence | Required Additional Data | Effective Behavior |
| --- | --- | --- |
| `hourly` | none | next hour at anchor minute, then window/blackout/range rules |
| `daily` | none | once daily at anchor time |
| `weekdays` | none | once Mon-Fri at anchor time |
| `weekly` | none | once weekly on anchor weekday/time |
| `monthly` | none | once monthly on anchor day/time (short month clamps to last day) |
| `custom` | `custom_anchor_at`, `custom_every_n_days` | every N days from anchor datetime |

#### Worked Examples

1. Hourly
`window=08:00-18:00`, `active_from=2026-05-07T00:00:00+01:00`, `active_until=2026-05-31T23:59:00+01:00` -> one run per hour during local window only.
2. Daily
Anchor time `10:30`, same window/range -> one run each day at local `10:30` while in range.
3. Weekdays
Anchor `10:30` -> Mon-Fri only.
4. Weekly
Anchor `2026-05-07T10:30:00+01:00` -> every 7 days at same local time.
5. Monthly
Anchor day 31 -> in shorter months runs on last day.
6. Custom
`custom_anchor_at=2026-05-10T14:20:00+01:00`, `custom_every_n_days=3` -> 10th, 13th, 16th... at local `14:20`, with window/range/blackout enforcement.

#### Explainability Fields (`GET/POST/PUT /api/v1/schedules*`)

- `execution_mode_label`
  - `automatic`: schedule can auto-run.
  - `manual_only`: no valid automatic path (for example invalid legacy custom state).
- `next_run_reason`
  - `computed`: normal next trigger computed.
  - `shifted_to_window_start`: candidate moved to next window start.
  - `blackout_skipped`: one or more blackout dates skipped while finding next trigger.
  - `outside_active_range`: no future trigger because active range expired.
  - `no_future_run`: no valid future trigger (including incomplete custom config).

#### Edge Cases

- Overnight window (`22:00` to `04:00`) is treated as crossing midnight; in-window checks include late night and early morning.
- If candidate time falls outside window, scheduler shifts to next window start.
- If candidate date is a blackout date, scheduler advances to next eligible date.
- If active range end is reached, `next_run_at` becomes null with `outside_active_range`.
- DST shifts are handled through schedule timezone conversion and UTC persistence.

#### Troubleshooting by `next_run_reason`

- `computed`: schedule is healthy; verify business expectations only.
- `shifted_to_window_start`: widen or move window, or change cadence anchor/custom anchor.
- `blackout_skipped`: remove/adjust blackout dates if run should happen sooner.
- `outside_active_range`: extend `active_until` or clear end bound.
- `no_future_run`: fix cadence inputs (especially custom fields), then save schedule again.

### System Settings: Allowed Timezones

By default, schedules accept any valid IANA timezone. Admins can switch the system timezone policy to an allowlist at `/admin/system`; once configured, schedule create/update requests that specify a timezone not in the allowlist are rejected with HTTP 400.

Key endpoints:

```bash
GET /api/v1/system/timezones
PUT /api/v1/system/timezones
```

### Alerts, Archives, and Retention

Alerts are exposed at `GET /api/v1/alerts`. Current alert sources include failed runs, retention backlog, paused schedules, and degraded campaign schedules.

Archive browsing uses:

```bash
GET /api/v1/archives/summary
GET /api/v1/archives/runs?limit=50&offset=0
```

Retention summary uses:

```bash
GET /api/v1/retention/summary
```

Retention is observation-only by default. Raw artifact purge remains disabled until purge safety is explicitly implemented. Runs that are ready for archive or raw purge include a retained summary shape before raw artifact deletion: verdict, flow, schedule/campaign source, actor summary, duration, latency placeholder, top failure signals, narrative, and audit attribution.

### Run Deletion and Runtime Files

Only admins can delete runs. Deleting a completed run removes that run's database row, its GUI log file under `runs/web-gui/`, and its own artifact folder containing `report.md`, `story.md`, and `events.json` when those paths are available.

Deletion must not remove the shared `runs/web-gui/` directory or files belonging to other runs. The API response includes `deleted_files` for files actually removed and `missing_files` for expected log/artifact paths that were already absent.

### Create and Manage Users in the UI

1. Sign in at `http://localhost:8080/auth/login` as an admin.
2. Open `Admin` in the app navigation, or go directly to `http://localhost:8080/admin/users`.
3. Click `Create User`.
4. Enter `username`, `email`, `password`, and one of these roles: `admin`, `operator`, `runner`, `viewer`, `auditor`.
5. Use the user table to edit email/role/active status, reset passwords, or delete accounts.

Notes:

- The UI disables editing and deleting the currently signed-in user's row.
- Password reset is available from the user table and invalidates that user's existing session.
- Prefer deactivating (`Active=false`) over deleting when you need history to remain explainable.
- Keep at least one known working admin account.

### Create Users Through the API

Login once and save the session cookie:

```bash
curl -sS -c /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  http://localhost:8080/api/v1/auth/login
```

Create an operator:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"ops1","email":"ops1@simulator.local","password":"change-me-123","role":"operator"}' \
  http://localhost:8080/api/v1/admin/users
```

Create a runner:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"runner1","email":"runner1@simulator.local","password":"change-me-123","role":"runner"}' \
  http://localhost:8080/api/v1/admin/users
```

Create a viewer:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"viewer1","email":"viewer1@simulator.local","password":"change-me-123","role":"viewer"}' \
  http://localhost:8080/api/v1/admin/users
```

Create an auditor:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"auditor1","email":"auditor1@simulator.local","password":"change-me-123","role":"auditor"}' \
  http://localhost:8080/api/v1/admin/users
```

Create another admin:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin2","email":"admin2@simulator.local","password":"change-me-123","role":"admin"}' \
  http://localhost:8080/api/v1/admin/users
```

List users and get user IDs:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  http://localhost:8080/api/v1/admin/users
```

Update a user's role, email, or active status:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"role":"runner","is_active":true}' \
  http://localhost:8080/api/v1/admin/users/<USER_ID>
```

Reset a user's password:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"new_password":"new-change-me-123"}' \
  http://localhost:8080/api/v1/admin/users/<USER_ID>/reset-password
```

Delete a user:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -X DELETE \
  http://localhost:8080/api/v1/admin/users/<USER_ID>
```

The delete endpoint refuses to delete the currently signed-in admin account.

### Change the Default Admin Password

Preferred path for an existing database:

1. Sign in as `admin`.
2. Open `Admin` -> `User Management`.
3. Click `Reset Password` on the `admin` row.
4. Enter the new password.
5. Sign out and sign in with the new password.

API path for an existing database:

```bash
curl -sS -c /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  http://localhost:8080/api/v1/auth/login

curl -sS -b /tmp/sim-admin.cookie \
  http://localhost:8080/api/v1/admin/users

curl -sS -b /tmp/sim-admin.cookie \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"new_password":"replace-with-a-strong-password"}' \
  http://localhost:8080/api/v1/admin/users/<ADMIN_USER_ID>/reset-password
```

The reset endpoint rewrites the bcrypt hash and deletes that user's existing sessions.

### Change the Seeded Admin for a Fresh Database

Use this only before creating a new PostgreSQL volume, or before resetting the local database from scratch.

Generate a bcrypt hash in the API container:

```bash
docker compose exec api python -c 'import bcrypt; print(bcrypt.hashpw(b"replace-with-a-strong-password", bcrypt.gensalt()).decode())'
```

Then update the default admin seed in `api/migrations/001-initial-schema.sql`:

```sql
INSERT INTO users (username, email, password_hash, role)
VALUES (
    'admin',
    'admin@simulator.local',
    '<GENERATED_BCRYPT_HASH>',
    'admin'
)
ON CONFLICT (username) DO NOTHING;
```

To seed a different first admin for a fresh database, change the `username`, `email`, bcrypt hash, and keep `role` set to `admin`.

### Create a New Admin Account

Preferred path:

1. Sign in with an existing admin.
2. Open `Admin` -> `User Management`.
3. Create a new user with role `admin`.
4. Sign out and verify the new admin can sign in.
5. Reset, deactivate, or delete the old admin only after the new admin is verified.

API path:

```bash
curl -sS -b /tmp/sim-admin.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"new-admin","email":"new-admin@simulator.local","password":"replace-with-a-strong-password","role":"admin"}' \
  http://localhost:8080/api/v1/admin/users
```

### Lockout Recovery

If no admin password is known, generate a bcrypt hash:

```bash
docker compose exec api python -c 'import bcrypt; print(bcrypt.hashpw(b"temporary-admin-password", bcrypt.gensalt()).decode())'
```

Open PostgreSQL:

```bash
docker compose exec postgres psql -U simulator -d simulator
```

Run SQL with the generated hash:

```sql
UPDATE users
SET password_hash = '<GENERATED_BCRYPT_HASH>',
    is_active = TRUE,
    role = 'admin',
    updated_at = NOW()
WHERE username = 'admin';

DELETE FROM user_sessions
WHERE user_id = (SELECT id FROM users WHERE username = 'admin');
```

Then sign in as `admin` with the temporary password and immediately reset it through the UI or API.
