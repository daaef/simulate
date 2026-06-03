# Fainzy Simulator — How It Works

> Written for developers unfamiliar with Python or TypeScript. No language knowledge required.

---

## What is the Fainzy Simulator?

The Fainzy Simulator is a **scripted rehearsal of a real ordering system**. It pretends to be a customer placing an order, a store receiving and fulfilling it, and a robot delivering it — all at once, all automated.

Its job is to prove that the Fainzy platform works end-to-end. Not just that the endpoints respond, but that a full ordering lifecycle — from tapping "place order" to "delivered" — completes correctly, and that every actor along the way behaves as expected.

The simulator runs against a **real server** (not a mock). Every HTTP call it makes is a real call. Every websocket message it listens to is live traffic.

---

## The Three Actors

Every simulation involves three simultaneous participants:

| Actor | What it pretends to be | What it does |
|-------|------------------------|--------------|
| **User** | A customer on the Fainzy app | Places orders, pays, cancels, reviews |
| **Store** | A restaurant dashboard | Receives orders, accepts or rejects, marks food ready |
| **Robot** | A delivery bot | Picks up from the store, delivers to the user |

These three actors coordinate via the server — they never talk to each other directly. The User places an order, the Store sees it on its websocket, accepts it, the Robot sees it marked ready, picks it up, delivers it. The simulator watches all three feeds simultaneously.

There is also a fourth, passive participant:

| Actor | Role |
|-------|------|
| **WebSocket Observer** | Connects to all three real-time channels (user feed, store feed, store stats) purely to *watch* — never sends anything, just confirms that status changes appear on the wire when they should |

---

## The Two Execution Modes

### Trace Mode — "Does it work correctly?"

Trace mode runs a **fixed sequence of scenarios**, one at a time, in order. Each scenario has a known starting state and a known expected outcome. If the outcome doesn't match, the run fails.

Think of it like a checklist: scenario 1 passes → scenario 2 starts → and so on.

This is what the `full`, `doctor`, `audit`, and all named flow profiles use.

### Load Mode — "Does it hold up under traffic?"

Load mode spawns **multiple users simultaneously**, each placing orders at intervals, with a store and robot listening in the background to process them. There is no fixed order of events — it's concurrent and randomized.

Think of it like a lunch rush simulation: 5 users ordering at the same time, one store handling them, one robot completing deliveries in parallel.

---

## What is a "Run"?

A **run** is one complete execution of the simulator. It has:

- A **flow** (which set of scenarios to execute)
- A **mode** (trace or load)
- A **timing profile** (fast: sub-second delays, realistic: human-paced delays)
- A **payment mode** (stripe test card, free order, or coupon-based)
- A **plan** (which real user phone numbers and store IDs to use)

Every run produces three output files:

| File | Purpose |
|------|---------|
| `events.json` | Complete machine-readable ledger of every action, request, response, and decision |
| `report.md` | Technical proof document: verdicts, latency, websocket assertions, findings |
| `story.md` | Plain-English narrative of what happened and why |

The web UI surfaces these as tabs inside a run's detail page: **Overview**, **Story**, **Report**, **Traffic** (events), and **Console** (live log while running).

---

## Flows and Profiles

A **flow** is a named preset that sets mode, suite, timing, and payment defaults. You pick a flow name and the simulator fills in the rest.

The full list of flows:

| Flow | Mode | What it runs |
|------|------|--------------|
| `full` | Trace | All 20 scenarios |
| `doctor` | Trace | 12 daily-recommended scenarios |
| `audit` | Trace | 15 breadth scenarios |
| `payments` | Trace | 3 payment scenarios only |
| `menus` | Trace | 4 menu-state scenarios only |
| `new-user` | Trace | OTP and account creation only |
| `place-order` | Trace | Seed pending live orders for manual store-app inspection |
| `store-setup` | Trace | Store profile creation and menu readiness |
| `store-dashboard` | Trace | Store probes (orders, stats, top customers) |
| `store-accept` | Trace | Store accepts and robot completes |
| `store-reject` | Trace | Store rejects before payment |
| `paid-no-coupon` | Trace | Standard Stripe paid order |
| `paid-coupon` | Trace | Paid order with coupon discount |
| `free-coupon` | Trace | Free order via coupon |
| `robot-complete` | Trace | Full robot delivery lifecycle |
| `receipt-review` | Trace | Receipt fetch, review submission, reorder |
| `load` | Load | Concurrent multi-user load |

Each focused flow (`store-accept`, `paid-coupon`, etc.) is a **subset** of what `full` runs. Running `full` is like running all of them in sequence.

---

## The `full` Profile — Step by Step

`full` is the completeness test. It runs all 20 scenarios in a deliberate order designed to build on itself — setup first, then features, then edge cases.

Below is what happens, in plain language:

---

### Phase 1 — Bootstrap (before any scenario starts)

1. **User authentication** — The simulator logs in as the test user (OTP flow or cached token). The token is saved so it is not re-fetched between scenarios.
2. **Store authentication** — The simulator logs in as the test store (product auth endpoint). Same caching applies.
3. **WebSocket Observer connects** — Three passive listeners open: one on the user's channel, one on the store's channel, one on the store's stats channel. They stay connected for the entire run.
4. **Fixture check** — If auto-provisioning is enabled and the store has no menu yet, the simulator creates a test category and menu item before any order scenarios run.

---

### Phase 2 — Setup Scenarios (scenarios 1–4)

These don't place orders. They probe and configure.

**Scenario 1: `app_bootstrap`**
The simulator acts as the Fainzy mobile app starting up. It calls every endpoint the app would call at launch: config, product authentication, pricing, saved cards, coupons, and open user orders. If any return an error, the scenario fails.

**Scenario 2: `new_user_setup`**
Simulates a brand-new user going through OTP verification and account creation. Runs the full registration flow and validates the user can log in afterward. If the phone number is already registered, this scenario is marked `blocked` (not failed — it's expected to be a one-time operation).

**Scenario 3: `store_first_setup`**
Simulates a store owner setting up their store for the first time: patching their profile, creating a category, and adding a menu item. If the store is already set up, this is marked `blocked`.

**Scenario 4: `store_dashboard`**
The simulator calls every endpoint a store dashboard would load: current orders, statistics, and top customers. Validates all three return valid data.

---

### Phase 3 — Menu State Scenarios (scenarios 5–8)

These verify that the ordering system correctly gates purchases based on menu state.

For each scenario, the simulator creates a test item with a specific status, attempts to add it to a user cart, and validates the outcome.

| Scenario | Item State | Expected Outcome |
|----------|-----------|-----------------|
| `menu_available` | Available | User can add to cart |
| `menu_unavailable` | Marked unavailable | User cannot add to cart |
| `menu_sold_out` | Sold out | User cannot add to cart |
| `menu_store_closed` | Store closed | User cannot add to cart |

---

### Phase 4 — Payment Path Scenarios (scenarios 9–11)

These verify the three checkout routes.

**Scenario 9: `returning_paid_no_coupon`**
A returning user places a paid order with no coupon. Stripe test card is used. The simulator waits for the Stripe webhook to confirm payment before proceeding.

**Scenario 10: `returning_paid_with_coupon`**
Same as above, but a coupon is applied. The coupon reduces the total. If the coupon is not available, this scenario is marked `blocked`.

**Scenario 11: `returning_free_with_coupon`**
A coupon covers the entire order cost. No Stripe call is made (zero-amount orders skip payment). The order goes directly to `order_processing`.

---

### Phase 5 — Store Decision Scenarios (scenarios 12–13)

**Scenario 12: `store_accept`**
Full happy-path order lifecycle:
1. User places order → `pending`
2. Store accepts → `payment_processing`
3. Stripe payment succeeds → `order_processing`
4. Store marks ready → `ready`
5. Robot picks up and delivers → `completed`

**Scenario 13: `store_reject`**
1. User places order → `pending`
2. Store rejects → `rejected`
3. Run verifies the user sees `rejected` on their websocket feed

---

### Phase 6 — Robot Delivery Scenario (scenario 14)

**Scenario 14: `robot_complete`**
The simulator drives the robot through every delivery status in sequence:

```
pending → payment_processing → order_processing → ready
  → enroute_pickup → robot_arrived_for_pickup
  → enroute_delivery → robot_arrived_for_delivery → completed
```

Each status change is patched by the robot actor, and the WebSocket Observer confirms each transition appears on both the user and store feeds.

---

### Phase 7 — Post-Order Actions (scenario 15)

**Scenario 15: `receipt_review_reorder`**
After an order completes:
1. Fetch the receipt PDF endpoint
2. Submit a review (rating + comment)
3. Fetch the reorder endpoint (which returns a pre-filled cart)
4. Build a second order from the reorder data and execute its full lifecycle

This is the only scenario that places two orders.

---

### Phase 8 — Core Lifecycle Edge Cases (scenarios 16–20)

These are the fundamental order lifecycle variants, run last because they stress-test cancellation and timeout paths.

| Scenario | What triggers the end state | Expected terminal status |
|----------|-----------------------------|--------------------------|
| `completed` | Normal happy path | `completed` |
| `rejected` | Store rejects before payment | `rejected` |
| `cancelled` | User cancels while `pending` | `cancelled` |
| `backend_auto_cancel` | Store does nothing; server countdown expires | `cancelled` |
| `auto_cancel` | Store accepts, payment withheld; server countdown expires | `cancelled` |

`backend_auto_cancel` and `auto_cancel` are the most diagnostic scenarios — they catch timeout-handling regressions on the server side.

---

### End of Run — Contract Enforcement

After all 20 scenarios, the simulator enforces the **order lifecycle contract**:

> Every order created during the run must have reached a terminal status (`completed`, `rejected`, or `cancelled`).

If any order is still open, the simulator attempts to close it:
1. Wait and poll for natural settlement
2. If still open, user cancels it
3. If cancel fails, store rejects it
4. If still open after all attempts → **run fails**

This prevents lingering test orders from polluting the live system.

---

## How `full` Relates to the Other Flows

Every focused flow is a named subset of `full`. Here is the mapping:

```
full (all 20 scenarios)
├── doctor (12) ─── app_bootstrap, store_first_setup, store_dashboard,
│                   menu_available, menu_unavailable, menu_sold_out, menu_store_closed,
│                   paid_no_coupon, paid_coupon, store_accept, store_reject, robot_complete
│
├── audit (15) ──── all doctor scenarios + new_user_setup, free_coupon,
│                   receipt_review_reorder, completed, rejected, cancelled
│
├── store (3) ────── store_first_setup, store_accept, store_reject
├── payments (3) ─── paid_no_coupon, paid_coupon, free_coupon
├── menus (4) ────── menu_available, menu_unavailable, menu_sold_out, menu_store_closed
├── core (3) ─────── completed, rejected, cancelled
│
└── Single-scenario flows (1 scenario each):
    new-user, place-order, store-setup, store-dashboard, store-accept, store-reject,
    paid-no-coupon, paid-coupon, free-coupon, robot-complete, receipt-review
```

When you run `doctor` daily, you are running a curated 12-scenario subset of `full`. When something in `doctor` fails, running its corresponding single-scenario flow (`store-accept`, `paid-no-coupon`, etc.) isolates the failure with less noise.

---

## The Console Log — Current State and What It Could Show

### What the console shows today

The console tab in the web UI streams the simulator's live output as it runs. This is a mix of:
- Internal trace labels (scenario names, step names)
- Raw HTTP decisions (status codes, response keys)
- Lifecycle contract checks
- WebSocket event receipts

For someone unfamiliar with the code internals, a line like:

```
[trace] scenario=store_accept step=wait_payment decision=passed
```

does not communicate *what the simulator actually did at that moment*.

### What it could show instead

The simulator already knows at every step who is acting, what they are doing, and what the result was. That information could be emitted as a human-readable log line instead of a trace label. For example, the `store_accept` scenario could emit:

```
[store-setup] store: checking profile ... found (FZY_926025 — Ask Me Restaurant)
[store-accept] user: placing order (₦2,500, no coupon) ... order #12345 created
[store-accept] payment: Stripe test card charged ... succeeded
[store-accept] store: accepting order #12345 ... accepted (order_processing)
[store-accept] store: marking food ready ... ready
[store-accept] robot: picking up from store ... enroute
[store-accept] robot: arrived at store ... picked up
[store-accept] robot: delivering to user ... enroute
[store-accept] robot: arrived at user ... completed ✓
[store-accept] websocket: confirmed all 8 status transitions on user and store feeds
```

This is technically achievable — the data is already captured in the event ledger. It would require the simulator to emit structured log lines (with a `[flow-name] actor: action ... result` format) at each step, and the web UI's console stream would display them as-is.

The `story.md` file already does this after the fact (as a post-run narrative). Surfacing it in real time during the console stream would make the live view much more useful for monitoring runs without reading the report afterward.

---

## The Artifact Pipeline

At the end of every run, three files are written:

### `events.json`
Every action the simulator took, in order. Each event records: which actor did it, what step of which scenario it was in, the HTTP request and response (with auth headers masked), the latency, and the decision (passed/failed/blocked/etc.). This is the raw source of truth.

### `report.md`
The technical proof document. Contains:
- Run summary (verdict, duration, scenario count)
- Slowest endpoints and latency percentiles
- Per-scenario verdict table
- WebSocket coverage assertions (which status transitions were confirmed on the wire)
- Developer findings (critical issues, operational notes)
- Full per-event trace

### `story.md`
Plain-language explanation of the run. Describes what happened, what went wrong, why, and what the next action should be. Written to be readable by anyone, not just engineers.

---

## Configuration: How the Simulator Knows What to Do

### The Plan File (`sim_actors.json`)

The plan file defines the real actors: which phone numbers are users, which store IDs are stores, their GPS coordinates, and their roles (`returning`, `new_user`). The simulator reads this once at startup.

### Environment Variables (`.env`)

Stripe API keys, cached auth tokens (so OTP is not triggered on every run), and feature flags live here.

### CLI Flags

Every setting can be overridden at the command line when launching a run. The web UI's run launcher generates the CLI command based on the selected flow and options.

### Precedence (highest to lowest)

```
1. Explicit CLI flags  (--mode, --store, --phone, etc.)
2. Plan JSON          (sim_actors.json or a GUI plan)
3. .env file          (STRIPE_SECRET_KEY, USER_LASTMILE_TOKEN, etc.)
4. Built-in defaults  (fast timing, load mode if unspecified)
```

---

## Timing Profiles

Two profiles control how long the simulator waits between actions:

| Profile | Delay per action | Use case |
|---------|-----------------|----------|
| `fast` | 0.2–0.6 seconds | CI, daily `doctor` runs, iterative testing |
| `realistic` | 3–120 seconds | Throughput benchmarking, latency observation, load soak tests |

Fast timing is the default for all named flows. Realistic timing is used when you need to observe real-world latency behavior or stress-test the server under extended pressure.

---

## Verdict Glossary

When a scenario or an individual step completes, it is assigned one of these verdicts:

| Verdict | Meaning |
|---------|---------|
| `passed` | The expected outcome was achieved |
| `failed` | Wrong outcome, timeout, HTTP 5xx, or contract violation |
| `blocked` | A required precondition was not met (coupon not available, store already set up) — not a code failure |
| `degraded` | Non-critical issue; the scenario completed but with a warning |
| `inconclusive` | Response was valid but undocumented; cannot make a verdict |
| `skipped` | Missing fixture data; scenario could not run |
| `recovered` | Auto-provisioning fixed a missing resource and the scenario continued |
| `unsupported` | Scenario does not apply to the current plan or fixtures |

`blocked` is important to understand: it is **not a failure**. A `new_user_setup` scenario on a phone number that already completed registration is expected to be `blocked`. The run does not fail because of it.

---

## Glossary

| Term | Definition |
|------|-----------|
| **Scenario** | One named, self-contained test (e.g., `store_accept`, `menu_sold_out`) |
| **Suite** | A named group of scenarios (e.g., `full`, `doctor`, `payments`) |
| **Flow** | A named preset that sets mode, suite, timing, and payment defaults |
| **Run** | One complete execution of the simulator against a live server |
| **Plan** | JSON file defining which real users and stores the simulator uses |
| **Actor** | One of: User, Store, Robot, WebSocket Observer |
| **Trace mode** | Deterministic, sequential scenario execution |
| **Load mode** | Concurrent, randomized multi-user simulation |
| **Terminal status** | An order state from which no further transitions are possible: `completed`, `rejected`, or `cancelled` |
| **Lifecycle contract** | The rule that every order created during a run must reach a terminal status |
| **WebSocket proof** | Confirmation that a status transition appeared on the real-time feed, not just via REST polling |
| **Auto-provision** | The simulator creating missing fixtures (store profile, menu item) automatically before running scenarios that require them |

---

---

# Developer Reference

> The sections below are intended for engineers working on the simulator itself — extending it, debugging it, or integrating it into CI. They assume Python and async familiarity.

---

## Module Map

Every Python file at the project root has a single, well-bounded responsibility. Nothing is monolithic.

| Module | Responsibility |
|--------|---------------|
| `__main__.py` | CLI entrypoint. Parses flags, resolves the run plan, selects trace or load mode, calls `trace_runner` or the load worker pool |
| `config.py` | Reads all environment variables and `.env` values into typed attributes. Single source of truth for runtime configuration |
| `scenarios.py` | Defines `TRACE_SCENARIOS`, `TRACE_SUITES`, `TimingProfile`, and the resolver functions that turn a flow/suite name into an ordered tuple of scenario strings |
| `flow_presets.py` | Maps named flow presets (e.g. `"doctor"`, `"audit"`) to their `(suite, mode, timing, payment)` defaults |
| `trace_runner.py` | The deterministic orchestrator. Bootstraps auth, runs scenarios in order, enforces the lifecycle contract, and writes the run folder |
| `transport.py` | Wraps `httpx` with tracing, auth-header masking, timing, and event recording. Every HTTP call in the simulator goes through here |
| `reporting.py` | `RunRecorder` — collects every event, computes verdicts, writes `events.json`, `report.md`, and `story.md` |
| `user_sim.py` | All HTTP calls that a customer would make: login, OTP, place order, cancel, review, reorder |
| `store_sim.py` | All HTTP calls a store owner makes: login, accept, reject, mark-ready, profile PATCH |
| `robot_sim.py` | All HTTP calls the delivery robot makes: status progression through every delivery phase |
| `websocket_observer.py` | Passive multi-channel listener. Opens three WebSocket connections and records every message without sending anything |
| `order_contract.py` | Lifecycle contract enforcer. After all scenarios complete, closes any non-terminal orders via cancel/reject fallbacks |
| `app_probes.py` | The `app_bootstrap` scenario: calls every endpoint a mobile app hits at launch and validates the responses |
| `menu_catalog.py` | Creates, patches, and removes test menu items for menu-state scenarios |
| `interaction_catalog.py` | Lookup tables mapping scenario names to their expected menu-action decisions (`MENU_AVAILABLE`, `MENU_SOLD_OUT`, etc.) |
| `failure_policy.py` | Classifies HTTP response codes as hard stops, recoverable, or informational; normalizes failure policy labels |
| `action_decisions.py` | Maps HTTP outcomes to simulator decision strings (`passed`, `failed`, `blocked`, etc.) |
| `decision_reasons.py` | Predicates for classifying why a decision was made (informational, hard-stop, etc.) |
| `post_order_actions.py` | Receipt fetch, review submission, and reorder execution — used by `receipt_review_reorder` |
| `stripe_sim.py` | Creates and confirms Stripe PaymentIntents using test card data |
| `run_plan.py` | Loads and validates `sim_actors.json`; resolves which actor gets which role for a given run |
| `health.py` | ASCII bar charts and health summary helpers used in `reporting.py` |
| `sim_applogger.py` | Structured log emitter for the web console stream |

The API server lives separately under `api/`. It is a FastAPI application — the simulator is its client, not part of it.

---

## How Scenarios Are Resolved

The chain from a user-typed flow name to an ordered list of scenario keys:

```
CLI flag / web UI  →  flow_presets.py  →  scenarios.py  →  trace_runner.py
     "doctor"       →  { suite: "doctor", timing: "fast", ... }
                    →  resolve_trace_scenarios("doctor") → ("app_bootstrap", "store_first_setup", ...)
                    →  for scenario in tuple: run_scenario(scenario)
```

`scenarios.py` holds the canonical `TRACE_SUITES` dict and `TRACE_SCENARIOS` tuple (the master ordering). When you ask for the `"doctor"` suite, you get back a subtuple taken from that master order — the order is always preserved.

`flow_presets.py` wraps suites with defaults (timing, payment mode) so the user doesn't have to specify everything manually. Adding a new named flow means adding one entry to the dict in `flow_presets.py` and, if it references a new suite, one entry in `TRACE_SUITES` in `scenarios.py`.

---

## The Transport Layer

`transport.py` is the lowest level the simulator touches. Every HTTP call in every actor module (`user_sim`, `store_sim`, `robot_sim`, `app_probes`) goes through one of its helpers — never raw `httpx` calls.

What `transport.py` does per request:

1. **Injects auth headers** — Bearer token for the user or store, depending on caller context
2. **Measures wall-clock latency** in milliseconds
3. **Masks sensitive fields** — `token`, `client_secret`, `otp` are redacted in the recorded payload using regex substitution before the event is stored
4. **Returns an `HttpResult`** — a frozen dataclass holding the raw `httpx.Response`, the decoded JSON payload, a pre-built event dict, and the latency
5. **Optionally applies a `ResponseTransform`** — the caller can pass a function to reshape the response before it's recorded (e.g. to extract the `order_id` from a nested field)

The event dict produced for each request is what `RunRecorder` stores in `events.json`. The structure is fixed:

```json
{
  "scenario": "store_accept",
  "step": "place_order",
  "actor": "user",
  "method": "POST",
  "url": "/orders/",
  "status_code": 201,
  "latency_ms": 312,
  "decision": "passed",
  "payload_summary": { "order_id": 12345, "status": "pending" }
}
```

This is why the report can reconstruct a per-event trace without re-running anything — the transport layer records it all in real time.

---

## The RunRecorder

`reporting.py` exports a single class: `RunRecorder`. It is instantiated once per run and passed down to every actor and scenario function as a dependency. No global state.

What it tracks:

- **Events** — appended via `recorder.record_event(event_dict)` as each HTTP call completes
- **Scenario verdicts** — set via `recorder.set_verdict(scenario, verdict, notes)`
- **WebSocket observations** — the observer posts status transitions it sees via `recorder.record_ws_event(...)`
- **Timing** — start time captured at construction; duration computed when `recorder.finalize()` is called

`recorder.finalize()` writes three files to the run folder:
- `events.json` — the raw event ledger, one JSON object per line (NDJSON)
- `report.md` — built by walking every event and computing latency percentiles, per-scenario tables, and WebSocket assertions
- `story.md` — a post-hoc narrative generated by summarizing verdicts and findings into plain language

The run folder name is constructed from the timestamp, suite, store ID, and user phone suffix — making it sortable and identifiable without opening any file.

---

## The WebSocket Observer

`websocket_observer.py` opens three persistent async WebSocket connections at the start of every trace run and holds them open until the run finishes:

| Channel | What it listens to |
|---------|-------------------|
| User feed | Real-time order status updates pushed to the customer |
| Store feed | Incoming orders and status changes pushed to the store dashboard |
| Store stats | Aggregate stats updates |

The observer never sends anything. It just records every message it receives into `RunRecorder`. After all scenarios complete, `reporting.py` walks the recorded WebSocket messages and checks that each expected status transition appeared on the correct channel.

This is the **WebSocket proof** — it proves status changes are actually broadcast on the wire, not just stored in the database. A scenario can pass its REST assertions (the order reached `completed` via polling) but fail the WebSocket assertion (the transition was never broadcast).

`REQUIRED_WEBSOCKET_SOURCES` in `websocket_observer.py` is the authoritative list of which scenarios require proof on which channels.

---

## The Order Lifecycle Contract

`order_contract.py` runs after all scenarios complete, before `RunRecorder.finalize()` is called.

It:
1. Fetches every order created during the run from the API
2. Checks whether each reached a terminal status (`completed`, `rejected`, `cancelled`)
3. For any non-terminal order:
   - Waits up to a configurable polling window for natural settlement
   - If still open, attempts a user cancel
   - If that fails, attempts a store reject
   - If both fail, marks the run as failed and records the orphaned order ID

One special exemption: orders placed by the `place_order` scenario are allowed to remain `pending` — they are intentionally seeded for manual inspection and are not expected to auto-complete.

This contract is what prevents the test environment from accumulating ghost orders. Every run is responsible for cleaning up what it creates.

---

## The API Server Structure

The `api/` directory is a FastAPI application. The simulator is its client. It is organized by domain:

```
api/app/
├── main.py              ← FastAPI app instance, router registration, startup hooks
├── runs/                ← Run lifecycle: create, poll status, stream logs, archive
├── schedules/           ← Schedule CRUD, status transitions, trigger logic
├── overview/            ← Dashboard summary: health, recent activity, KPIs
├── alerts/              ← Threshold-based alerting on run outcomes
├── archives/            ← Completed run storage and retrieval
├── admin/               ← Admin-only endpoints: actor config, system reset
├── auth/                ← Token validation middleware
├── integrations/        ← Webhook configuration and outbound event delivery
├── simulation_plans/    ← Saved actor plans (user/store/robot configs)
├── system/              ← Health, version, timezone policy
└── catalog_seed.py      ← Dev-time fixture seeding for menus and stores
```

The web frontend (`web/`) talks exclusively to this API — it never touches the simulator Python code directly. The simulator also talks exclusively to this API (plus the Fainzy platform's own API). The two never share in-process state.

---

## How to Add a New Scenario

Adding a scenario is a five-step process:

**1. Name it** — choose a `snake_case` identifier that describes the outcome, not the method. `store_reject_after_payment` is better than `test_store_rejection`.

**2. Register it in `scenarios.py`** — add the name to `TRACE_SCENARIOS` (in the logical position relative to its dependencies) and to any relevant `TRACE_SUITES` entries.

**3. Write the scenario function in `trace_runner.py`** — a scenario is an `async def` that receives `(recorder, config_snapshot, actor_tokens, ws_observer)` and returns a verdict string. Use the existing scenarios as templates — the pattern is: arrange → act → poll → assert → record.

**4. Declare its WebSocket expectations** (if it places an order) — add an entry to `REQUIRED_WEBSOCKET_SOURCES` in `websocket_observer.py` so the contract knows which channels to check.

**5. Register it in the dispatch table** — `trace_runner.py` has a dict that maps scenario name strings to their async functions. Add your new scenario there.

If the scenario needs menu fixtures, use `menu_catalog.py`. If it needs Stripe, use `stripe_sim.py`. If it needs post-order actions (receipt, review), use `post_order_actions.py`. Never write raw `httpx` calls inside a scenario — always go through `transport.py`.

---

## Adding a New Flow Preset

A flow preset is just a named entry in `flow_presets.py` that maps to a `(suite, timing, payment_mode)` tuple. If the suite doesn't exist yet, add it to `TRACE_SUITES` in `scenarios.py` first. The web UI's flow picker reads these presets from the API — no frontend changes are needed when a new preset is added.

---

## Config and Environment Precedence (Full Detail)

`config.py` reads all values at import time. The precedence stack is:

```
1. Explicit CLI flags          ← always wins; parsed in __main__.py, passed to config at startup
2. Plan JSON (sim_actors.json) ← actor identities, GPS, roles
3. .env file                   ← secrets: STRIPE_SECRET_KEY, USER_LASTMILE_TOKEN, STORE_TOKEN, etc.
4. Built-in defaults           ← fast timing, trace mode, no coupon, UTC timezone
```

Never put secrets in `sim_actors.json` — that file is committed. Secrets belong in `.env`, which is gitignored. Feature flags (e.g. `SIM_AUTO_PROVISION_FIXTURES=1`) also live in `.env`.

The config module exposes typed accessors (`config.stripe_secret_key`, `config.timing_profile`, etc.) rather than raw `os.getenv` calls scattered through the codebase. If you need a new config value, add it to `config.py` — do not call `os.getenv` anywhere else.

---

## Testing Patterns

Tests live in `tests/`. There are two test files with distinct purposes:

| File | What it tests |
|------|--------------|
| `test_simulate.py` | Unit and integration tests for simulator internals: scenario resolution, verdict assignment, transport masking, contract enforcement, config parsing |
| `test_web_api.py` | API-level tests that call the FastAPI routes directly using the test client; no real network calls |

The simulator does not use mocks for the Fainzy platform API — integration tests that call the real server are tagged separately and run only in CI against a staging environment. The unit tests in `test_simulate.py` use fixtures and a local `httpx` transport override to avoid real network calls.

When writing a new test:
- For a new scenario function: test the verdict it returns under controlled HTTP fixtures
- For a new API endpoint: test via `test_web_api.py` with the FastAPI test client
- For a new config value: add a test in `test_simulate.py` asserting the default and the override both resolve correctly

---

## The `_sim_log` Pattern

`trace_runner.py` uses a `_sim_log(scenario, actor, message, level)` helper to emit Rich-formatted console output during a run. The format it produces is:

```
[scenario-name] actor: message
```

This is the same format the `story.md` narrative uses — if you want an action to appear in both the live console stream and the post-run story, emit it via `_sim_log` and also record it on the `RunRecorder`. The two are not automatically linked.

`level` controls the Rich markup color: `info` → default, `success` → green, `warn` → yellow, `error` → red.

---

## Debugging a Failing Run

The fastest path to understanding a failure:

1. **Open `events.json`** in the run folder — find the first event with `"decision": "failed"` and read its `payload_summary`. The exact HTTP response body is there.
2. **Check the WebSocket assertions in `report.md`** — a scenario that passes REST but fails WebSocket proof will show up as `degraded` or `failed` in the WebSocket section, not in the main verdict table.
3. **Check `order_contract.py` output** at the bottom of `report.md` — if the run ends with open orders, the contract section lists their IDs and last known status.
4. **Re-run the single-scenario flow** — if `doctor` fails on `store_accept`, run `--flow store-accept` alone. Less noise, same assertions.
5. **Set `SIM_TIMING_PROFILE=realistic`** — some race conditions only appear at real-world timings. If fast timing passes and realistic fails, there is a server-side timing sensitivity.

---

## Architecture Decisions Worth Knowing

**Why async throughout?** The simulator must hold three WebSocket connections open while simultaneously driving HTTP calls across three actors. Async Python (`asyncio`) makes this straightforward — the observer runs as a background task, and each actor awaits its HTTP calls without blocking the others.

**Why no mock server?** The simulator's entire value is that it tests the real platform. A mock would test the simulator's assumptions about the platform, not the platform itself. The only acceptable substitute is a staging environment with real data flows.

**Why `RunRecorder` as a passed dependency, not a singleton?** Parallel load-mode runs execute concurrently. If `RunRecorder` were a global, concurrent runs would corrupt each other's event ledgers. Passing it as an argument makes isolation explicit and free.

**Why the transport layer masks secrets?** The event ledger is written to disk and surfaced in the web UI. Auth tokens and Stripe client secrets must never appear in a file that could be shared or indexed. Masking happens at the transport layer — not in each caller — so no scenario can accidentally log a secret by bypassing it.
