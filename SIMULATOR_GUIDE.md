# Fainzy Simulator Guidebook

This simulator is a daily doctor for the ordering platform. It simulates user app, store app, and robot behavior; continuously checks HTTP and websocket paths; and writes operator-friendly reports plus full technical evidence.

Docker note: this stack runs the Next.js web app with `next start` from the built image. If `./web` is bind-mounted over `/app`, the built `.next` directory can be masked and `web` will crash with `Could not find a production build in the '.next' directory`.

**Capability catalog:** For an exhaustive reference to flows, suites, scenarios, CLI flags, run-plan JSON keys, environment variables, and web/API launch parity, see [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md).
**Flow guides:** For one comprehensive operator document per GUI Flow selector option, see [docs/flows/README.md](docs/flows/README.md).

**Simulation test guide (run efficiency):** For a practical operator playbook focused on choosing the right run quickly and using suites/scenarios/flags efficiently, see [docs/SIMULATION_TEST_GUIDE.md](docs/SIMULATION_TEST_GUIDE.md).

**GUI manual testing:** For a from-the-ground-up checklist of the web UI (every Start Run control, client-side validation, profiles, run detail, and role expectations), see [docs/GUI_TESTING.md](docs/GUI_TESTING.md).

**Ideas backlog:** For GUI and functional improvement ideas (not roadmap commitments), see [docs/IDEAS_GUI_AND_FUNCTIONAL.md](docs/IDEAS_GUI_AND_FUNCTIONAL.md).
**Bounded load fix deep-dive:** For root cause and before/after examples of the bounded load smoke redesign plus precedence fix, see [docs/BOUNDED_LOAD_SMOKE_FIX_EXPLAINER.md](docs/BOUNDED_LOAD_SMOKE_FIX_EXPLAINER.md).

## Operator observability (read first)

### Health contract: Up, Degraded, Down

- **Up:** Control plane is healthy (`GET /healthz` ok), you can authenticate, and—when judging product health—a **recent successful doctor or trace run** finished within your policy window.
- **Degraded:** Partial risk: open alerts, archive/purge backlog, schedule campaign warnings, or websocket **warnings** while a run still completed. Investigate before declaring all-clear.
- **Down:** Blocking failure: **failed run**, cannot sign in, cannot launch runs, or required ordering steps never complete (for example enforced websocket gates time out).

**`/healthz` is not last-mile green:** The JSON from `GET /healthz` reports the FastAPI process (`status`, `project_dir`, `simulator_workdir`, `db_path`). It does **not** exercise last-mile HTTP, menus, payment, or `wss://` gateways. Use **doctor** or **trace** for end-to-end proof.

### Socket status service

The web UI has a cached socket monitor for two required LastMile websocket channels:

- `store_orders`: `/ws/soc/store_<store_id>/`
- `store_stats`: `/ws/soc/store_statistics_<store_id>/`

The AppNav badge reports the active monitor state:

- **Sockets Up:** both required sockets connected on the last probe.
- **Sockets Degraded:** at least one required socket failed below the failure threshold.
- **Sockets Down:** at least one required socket failed at or above the failure threshold.
- **Sockets Unknown:** monitor disabled, target missing, or first probe pending.

The **Overview → Socket Service** panel also shows latest-run websocket evidence. That evidence is historical run context and is intentionally separate from the active connection probe, which proves websocket connection reachability only.

The monitor probes from the API container, so `LASTMILE_BASE_URL` and the `SIM_SOCKET_MONITOR_*` vars must be present there (compose passes them through). It assumes a single API worker — production pins workers to 1; with more workers the badge status is per-worker (email dedupe stays correct via persisted `system_settings`). In production, set `SIM_SOCKET_MONITOR_STORE_ID` explicitly, since the `sim_actors.json` fallback depends on the image-baked file.

Environment controls:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIM_SOCKET_MONITOR_ENABLED` | `true` | Enable API-side socket probing. |
| `SIM_SOCKET_MONITOR_STORE_ID` | empty | Explicit store id to probe; falls back to `sim_actors.json` `defaults.store_id`. |
| `SIM_SOCKET_MONITOR_INTERVAL_SECONDS` | `60` | Probe interval; minimum 15 seconds. |
| `SIM_SOCKET_MONITOR_CONNECT_TIMEOUT_SECONDS` | `5` | Per-socket connection timeout. |
| `SIM_SOCKET_MONITOR_FAILURE_THRESHOLD` | `2` | Consecutive failures before status becomes Down and email can fire. |

### Which simulation flow should I use?

1. **End-to-end platform health** → `doctor` + agreed plan (`sim_actors.json` or `runs/gui-plans/daily-doctor.json` or another standard GUI plan).
2. **Targeted regression** → `trace` + narrow suite (`core`, `doctor`, or specific scenarios listed under Trace Mode in `ARCHITECTURE.md`).
3. **Load / churn** → `load` mode (engineering; not the default “is the platform up?” check).

### Trace mode and websocket evidence

Use **trace** (or **`doctor`**, which runs in trace mode) when you need proof that **last-mile HTTP APIs** and, for order flows, **`wss://` traffic** behave—not only that the simulator API (`/healthz`) is up.

- **APIs (REST and similar):** Scenarios issue real requests: place and mutate orders, run `app_bootstrap` and `store_dashboard` probes, menu checks, payment paths, store setup, and so on. Failures (for example 5xx, timeouts, auth errors) are recorded in the run ledger and summarized in `report.md` / `story.md` / `events.json` for that run.
- **Websockets:** When the resolved scenario list includes **order-driving** scenarios (for example `completed`, `rejected`, `cancelled`, payment and robot completion paths, `receipt_review_reorder`), trace attaches a **`WebsocketObserver`**. That component **only opens the same socket URLs the apps use and receives messages**—it does **not** send app traffic to impersonate a user or store on those sockets. **Active** order-driving traffic still comes from the normal simulator paths (user / store / robot simulators and REST-driven steps). The observer is a **passive listener** used for **evidence** (coverage, recorded frames, optional gates).
- **Websocket gate enforcement:** With enforcement **on** (`SIM_ENFORCE_WEBSOCKET_GATES`, CLI flags, plan `rules`, or Runs **Enforce Websocket Gates**), required channels must be active at startup and remain recoverable during runtime, or the run fails immediately.
- **Order lifecycle contract (always on):** For any standard run that creates orders, success now requires both:
  1. every created order ends in exactly `completed`, `rejected`, or `cancelled`;
  2. websocket lifecycle proof exists for order progression (pending + driven intermediate statuses + terminal status). Missing/late lifecycle proof is run-failing.
- **Pending-order seed exception:** `place-order` is the only trace flow allowed to leave orders open. It places 1-10 orders, requires pending websocket proof, records `pending_order_seeded`, and skips cleanup so a real store operator can inspect or act on those pending orders.
- **Full scenario and flag matrix:** See [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md) for every scenario name, suite, and launcher field.

### Trace scenarios and flags (process truth)

| Scenario | Role in “does ordering work?” |
|----------|-------------------------------|
| `completed` | Full happy path through robot completion |
| `rejected` | Store rejects before payment |
| `cancelled` | Customer cancels while pending |
| `place_order` | Seeds pending order(s) for manual store-app inspection; intentionally leaves them pending |
| `backend_auto_cancel` | Store idle on pending, countdown ticks, observe `cancelled` (primary backend auto-cancel diagnostic) |
| `auto_cancel` | Explicit-only diagnostic: store accept, withhold payment, awaiting-payment countdown ticks, observe `cancelled` (optional; may time out if backend only cancels pending) |
| `app_bootstrap` | Config, product auth, pricing, cards, coupons, active orders |
| `store_dashboard` | Store orders, statistics, top customers |
| `receipt_review_reorder` | Receipt PDF, review, reorder fetch after completion |

**Websocket gates:** See **Trace mode and websocket evidence** above for how trace exercises APIs and passively observes sockets. In short: `SIM_ENFORCE_WEBSOCKET_GATES` default **off** keeps startup/runtime gates advisory, while **on** blocks run start until `user_orders` + `store_orders` + `store_stats` are active and fails if required channels stay degraded beyond retry window. Regardless of this toggle, order-producing runs still require websocket lifecycle proof for final success.
**Failure policy:** Default run policy is `SIM_FAILURE_POLICY=api_only` with `SIM_PREFLIGHT_STRATEGY=auto_recover`. In this mode, transport/timeouts/websocket-connect/HTTP 5xx are hard failures, while most precondition misses (for example coupon unavailable, user GPS fallback required, already-setup new-user phone) downgrade scenarios to degraded/unsupported instead of failing the whole run.

### Flow reliability and named-flow regression

Run the 12 named GUI flows under default policy and collect a summary table:

```bash
export PYTHONPATH=.
export SIM_FAILURE_POLICY=api_only
export SIM_PREFLIGHT_STRATEGY=auto_recover
./scripts/run_named_flow_regression.sh
```

Outputs: `runs/flow-reliability-<date>.json` and `runs/flow-reliability-<date>.md`. **Pass under `api_only`:** process exit `0` unless a true API fault occurred; health verdict `failed` only when `failure_class: api_fault` issues exist. Precondition-only runs may show **DEGRADED** or scenario **unsupported** — that is expected, not a regression failure.

**Strict parity spot-check** (optional; restores prior hard-fail semantics):

```bash
export PYTHONPATH=.
export SIM_FAILURE_POLICY=strict
export SIM_PREFLIGHT_STRATEGY=hard_stop
python3 __main__.py menus --plan sim_actors.json --timing fast
python3 __main__.py paid-coupon --plan sim_actors.json --timing fast
python3 __main__.py new-user --plan sim_actors.json --timing fast
```

| Flow / scenario | Typical precondition outcome (`api_only`) | Process exit | Health verdict |
| --- | --- | --- | --- |
| `free-coupon` / `paid-coupon` | No coupon in catalog → scenario `unsupported` (`coupon_missing`); alternate-store retry may recover | `0` if no API fault | `degraded` or `passed` |
| `new-user` | Phone already `setup_complete` → `unsupported` (`account_already_setup`) | `0` | `degraded` |
| `menus` | Creates a new catalog item in-store before gate scenarios; then runs menu_available/unavailable/sold_out/closed probes | `0` when setup/API OK | `passed` or `degraded` |
| `store-*`, `robot-complete` | Usually completes when plan store/user valid | `0` | `passed` |
| Any flow | HTTP 5xx / timeout / ws-connect failure on required path | `1` | `failed` |

Artifacts record `failure_class` on issues and decisions in `events.json`; run config snapshot includes `failure_policy`.

**Daily plan:** Prefer one owner-approved JSON path and document expected duration; failures surface in run log, `report.md`, Overview alerts, and optional email (`run_failed` / `critical_alert`).

### Dependency checking (no separate last-mile probe)

There is **no** dedicated lightweight “ping last-mile” API in this repo that replaces a real run. Rationale: a tiny GET could be green while websockets, Stripe, or menus are broken. **Use doctor/trace** (or a schedule that launches your doctor profile) as the proof signal. Combine with `scripts/check_lastmile_ws.sh` when failures cluster on `wss://` and `HTTP 502`.

## Operator GUI (web)

This section documents the **authenticated** Next.js operator UI (`web/src/app`). Public login lives at `/auth/login`. After sign-in, routes live under the `(app)` layout with a sticky header, **Theme toggle**, **User profile** menu, and **AppNav** links.

### Global shell and navigation

| Element | Meaning |
|---------|---------|
| **App header** | Sticky bar with product title area, `ThemeToggle`, `UserProfile`, and primary nav. |
| **AppNav** | `Overview`, `Runs`, `Config`, `Schedules`, `Archives`, `Retention`, `Admin` (users). Active route is highlighted. |
| **Theme toggle** | Switches light/dark; persists in `localStorage` / `ThemeContext`. |
| **User profile** | Sign out and account shortcuts. |

### Visual vocabulary (shared)

| Pattern | Meaning |
|---------|---------|
| **`.panel` / `.stat`** | Card containers; stats show label + big number. |
| **`.error-banner` / `.panel.error-banner`** | Hard failure message (often API unreachable or form error). |
| **`status-pill` + `status-success` / `status-danger` / `status-warning` / `status-info`** | Run or entity state colors (success, failed/deleted, paused/cancelled, default). |
| **`alert-pill` + `severity-critical|warning|info`** | Alert queue severity. |
| **`muted` / `.muted`** | Secondary explanatory text. |
| **`chart-empty`** | Legitimate empty dataset (not an error). |

**API vs run failure:** On **Runs**, “API health” reflects **`/healthz`** only (control plane). A run can still **fail** while API health is “reachable”—that is a **process Down** signal for that simulation, not “API Down.”

### Route: `/` (root)

Redirects to `/overview` when a session cookie exists, otherwise `/auth/login`.

### Route: `/overview`

**Purpose:** Single-page operations posture—latest run intelligence, backlog, schedules, alerts.

**Blocks:**

- **Latest Run Command Center** — Hero for most recent run: status, duration, context chips (`profile:`, `schedule:`, `route:`), **Metrics Dashboard** (expandable; Business KPI cards by default with segmented Business/Operations/Engineering switching, plus a collapsed technical action drill-down sourced from full run `action_counts`), actor strip, HTTP/WebSocket protocol boards, lifecycle timeline, **Critical Findings** (server/API/websocket **availability** only—see README Overview notes), top traffic.
- **Which simulation should I run?** — Anchor `id="which-simulation-flow"`. Short ladder: doctor vs trace vs load; points to this guide for depth.
- **Recent run outcomes** — **Last succeeded** and **Last failed** from dashboard API (quick links to run detail).
- **Stat cards** — Total runs, success rate, active runs, failed (24h), schedules count, alert count.
- **Charts** — Status donut, success split, flow distribution, 7-day failure sparkline, archive/purge backlog bars, schedule health donut.
- **Attention queue** — Active or failed runs (links to `/runs/{id}`) with created/started/finished date-time stamps.
- **Alerts** — Top operational alerts with links and alert date-time stamps.
- **Platform / Archive / Retention** panels — Policies and queue depths; **Platform** clarifies **`/healthz`** scope.

**Refresh:** Data loads once on mount (no auto-poll on Overview).

### Route: `/runs`

**Purpose:** Launch simulations, watch live log, manage **Saved profiles**, browse recent runs.

**Key blocks:**

- **Header strip** — Title, theme, profile, **API health** note (healthz scope), link to Overview flow ladder.
- **Run statistics** — Status + flow distribution bars; optional **Last succeeded / Last failed** panels when API returns highlights.
- **Start Run** (`CollapsibleSection`) — `RunLaunchPanel` + `RunLiveConsole`. Plan dropdown (`sim_actors.json` + `runs/gui-plans/*`), flow/mode/suite/scenario controls gated by `/api/v1/flows`, command preview, websocket gate checkbox, random-actor checkboxes (`Disable random phone`, `Disable random store`), advanced overrides. In Advanced Mode Overrides, `Scenarios (trace only)` is a searchable chips multiselect (typeahead + keyboard nav) limited to supported flow scenarios. After a successful manual start, launcher actor overrides reset to plan-default auto-random mode for the next run.
- **Saved profiles** — CRUD and launch saved configurations (behavior preserved; labels improved only under observability work).
- **Recent runs table** — Select run, open detail, actions.
- **Admin dashboard embed** — Role-gated operator tools when permitted.

**Refresh:** Health poll ~10s; runs + summary poll ~5s while page is open. The **Live Console** log tail polls on the selected run id only (not when the runs table refreshes), so the console does not flash empty during active runs; new lines auto-scroll only when you are already at the bottom.

### Start Run: Execution Impact assistant

The Runs launcher now shows an **Execution Impact** panel directly under command preview.

- **Default view:** concise summary (2–4 lines) of what the selected command will execute.
- **Expanded view:** scenario/suite behavior, mode mechanics, gate/probe policy, prerequisites, expected artifacts, and likely failure signatures.
- **Blocking warnings:** invalid combinations (for example trace + continuous, load + suite/scenarios, reject out of range) appear in the panel before launch and align with launcher submit validation.

How to interpret messages:

- **Informational context:** expected non-failure behavior (for example `unsupported_profile_fetch_contract`) is context, not outage.
- **Warning context:** strict toggles (for example websocket gate enforcement) may intentionally increase fail-fast behavior.
- **Blocking context:** configuration conflicts that must be corrected before run start.

### Start Run: load vs trace meaning (operator shorthand)

- `load` answers: "does the system hold up under many users/orders over time?" qualifier: use for throughput, race conditions, intermittent failures, and resilience under concurrency.
- `trace` suites/scenarios answer: "did each specific workflow/API behavior pass deterministically?" qualifier: use for branch-level verification and targeted reproduction.
- Trace overlap guidance: broad suites (`doctor`, `full`) cover many targeted flows; use targeted flows mainly to isolate failures after a broad run.

### Start Run: input example placeholders

Each launcher control now includes an example hint. Typical examples:

| Control | Example |
| --- | --- |
| Flow | `doctor` |
| Timing | `fast` |
| Plan | `sim_actors.json` |
| Mode override | `trace` |
| Suite | `doctor` |
| Scenarios | `completed`, `store_reject` |
| Store ID | `FZY_926025` |
| Phone | `+2348166675609` |
| Users | `5` |
| Orders | `50` for load, `3` for `place-order` |
| Interval | `3` |
| Reject rate | `0.10` |
| Continuous | on for soak tests |
| Strict plan | on when you require strict plan validation |
| Skip probes | on only when intentionally reducing diagnostic coverage |
| No auto provision | on for pure environment-readiness checks |
| Post-order actions | on when receipt/review/reorder verification is required |
| Enforce websocket gates | on when missing realtime events should hard-fail the run |

### Route: `/runs/{id}`

Run detail: summary, log download, artifacts (`report.md`, `story.md`, `events.json`), metrics—deep dive after a failure.
Run detail data is strictly scoped to the requested run id: active runs do not backfill artifact paths from historical logs, and `/runs/{id}` reads only `run-{id}.log` metadata plus that run row paths.
Artifact path hydration from `run-{id}.log` tolerates wrapped console path lines, so long file paths still resolve to Overview/Story/Traffic artifacts after run completion.

**Overview tab:** Shows aggregate metrics plus a **metrics-first dashboard** (Business default view, segmented Operations/Engineering views, and collapsed technical action drill-down with action-key search). It also renders side-by-side findings cards from `findings.critical` and `findings.operational` on `GET /api/v1/overview/runs/{run_id}` (flat `issues` is critical-only). Critical includes server/API/websocket availability and websocket event gaps. Operational includes non-critical artifact `issues` (missing tokens, gate bypass with `enforced: false`, etc.) **plus** non-critical failed events from the ledger using the same rules as the **Failed Events** metric (`decision` failed/error/blocked, HTTP 5xx in critical only, other `ok: false` / failure statuses in operational). **Order Rejections** and **Payment Failures** on the metrics dashboard are action-count KPIs, not findings rows. `GET /api/v1/runs/{id}/metrics` returns `action_counts` as `{ action, count }[]` (every distinct `action` in `events.json`, sorted by count then name). Process output is stored per run in `run-{id}.log`; the **Console** tab polls while the run is active and preserves scroll position (append-only updates, stick-to-bottom only when already at the bottom). Use **Traffic** for the raw event stream.

### Route: `/config`

Config uses three tabs: `Plans`, `Email`, and `Integration mappings`.
In `Plans`, `New` clones the currently loaded editor JSON (fallback to selected plan/template content when editor JSON is invalid), clears selected plan id, and names the draft `<selected plan> (Copy)` or `Daily Doctor Plan` when no plan is selected.
The `Email` tab contains **Email notifications** (non-secret SMTP settings + triggers); `Integration mappings` remains unchanged.

### Route: `/orders`

Orders is an authenticated operator page for looking up and mutating live Fainzy orders without leaving the simulator UI.

- Store selection comes from `sim_actors.json` (`defaults.store_id` and `stores[]`); no new Orders-specific environment variables are needed.
- Store sign-in calls the simulator API, which fetches the LastMile product-auth `Fainzy-Token` and validates store metadata through the existing Fainzy store-login endpoint (`POST /v1/entities/store/login` with `Store-Request`). The LastMile token is persisted in browser `localStorage`.
- Lookup accepts either a DB order id or reference (`#156382`). Numeric input first tries DB id, then falls back to reference `#<number>`. Reference lookup is scoped to the signed-in store; if the order belongs to a different store, the UI tells the operator to choose that store and retry.
- Both tabs show a read-only raw order JSON pane after lookup.
- `Order Summary` keeps the summary-details workflow. `Update Status` is the direct status-change tab: below lookup it shows only item names, total price, the lifecycle status selector, and `Update Status`; it does not repeat store details or item-level quantity/price rows.
- Both tabs submit status updates through the LastMile token path: `PATCH /v1/core/orders/?order_id=<id>` with `Fainzy-Token`.
- The status selector intentionally includes the full known lifecycle (`pending`, `payment_processing`, `order_processing`, `ready`, robot transit statuses, `completed`, `cancelled`, `rejected`, `missed`, `refunded`). The backend may reject invalid transitions for the current order state.

### Route: `/schedules`

Campaign-first schedules, previews, manual trigger, pause/resume, disable/enable, soft delete/restore. Auto-refresh ~15s and on window focus. **Semantics are protected**—observability work only clarifies labels/errors.
The page also supports editing existing schedules through an **Edit** action that loads the selected schedule into the form, then saves with `PUT /api/v1/schedules/{id}`.

### Route: `/archives` and `/retention`

Browse archived runs and inspect retention/purge posture; observation-first tooling.

### Route: `/admin/users` and `/admin/system`

User CRUD/roles live under **`/admin/users`** (primary **Admin** nav entry). **`/admin/system`** (system policies such as allowed schedule timezones) opens from the **Admin sub-navigation** when you are already in the admin area (`AdminSubNav`: Users vs System Settings).

### Route: `/auth/login`

Sign-in for the web UI; redirects to `/overview` when already authenticated.

### Email notifications (operators)

Failure emails (`run_failed`, `schedule_launch_failed`) append a short **“How to read this”** footer: failed run = process check failed; `/healthz` = control plane only; pointer to this guide. Configure triggers on **Config → Email tab → Email Notifications**.

## 1) Inputs and Outputs

Required operator inputs:

- `.env` for secrets, auth cache values, credentials, and deployment URLs only.
- A plan JSON (default `sim_actors.json`) with users, stores, GPS, runtime defaults, rules, fixture defaults, payment defaults without Stripe secrets, review defaults, and new-user metadata.

Generated artifacts per run:

- `runs/<timestamp>/events.json`: complete event ledger.
- `runs/<timestamp>/report.md`: summary + bottlenecks + tabled findings + technical trace.
- `runs/<timestamp>/story.md`: narrative scenario summary.
- `events.json` includes decision records (`called`, `blocked`, `passed`, `inconclusive`, `skipped`, `recovered`, `failed`) with reason code/message, next action, and whether the run continued.
- Probe decisions use strict semantics: `failed` only for transport/timeout/connection/HTTP `5xx`; documented response variants are `passed`; undocumented but successful responses are `inconclusive`; and missing data/sample contracts are `skipped`.
- Missing-sample probes are recorded as `reason_code=missing_reference_sample`, `next_action=request_sample_from_user`, and a `probe_sample_needed` operator finding.
- Overview page behavior: Latest Run `Critical Findings` is filtered to server/API availability failures (`5xx`, transport/network, websocket connection availability). Missing-information or business-availability conditions (for example missing token, no saved card, no coupon) stay in `events.json`/`report.md`/`story.md` but are intentionally excluded from Overview.
- Decision-category skips/recoveries for expected reasons (for example `unsupported_profile_fetch_contract`, `no_customer_id`, `missing_*`, `missing_auth_token`) are treated as informational context, not failures, in overview counters/findings and report decision summaries.
- Overview `Critical Findings` rows include failed route/endpoint, HTTP method/status, simulator flow/step, optional session phase label (`flow_label`), preceding steps from artifacts, and the Latest Run hero surfaces context chips such as `profile:<name>`, `schedule:<name>`, and integration `route:<project/environment>`.
- Latest Run Overview also renders **Operational Findings** next to critical: artifact issues that are not server/API critical, plus ledger events counted as failed by run metrics but not promoted to critical (up to 25 rows; use **Traffic** for the full stream).
- `receipt_review_reorder` with post-order actions enabled: after receipt/review/reorder fetch, the simulator builds the cart from `GET /v1/core/reorder/?order_id=` response data and runs a **full second order** lifecycle (place → accept → payment → robot → completed).

Configuration precedence:

1. Explicit CLI flags.
2. Values from the selected plan JSON.
3. `.env` fallback for secret/auth/deployment values.
4. Built-in defaults.

The GUI stores admin-created plans in `runs/gui-plans/` and launches them through the same `--plan` CLI path.
On the Runs page, Start Run plan selection is dropdown-only: `sim_actors.json` is always shown, then GUI plans from `runs/gui-plans/`; manual text entry is not supported.
Start Run now reads flow capabilities from `GET /api/v1/flows` and conditionally renders only flags valid for the selected `Flow`, resolved `Mode`, and selected `Suite/Scenarios`.
Advanced Mode Overrides are optional and let operators explicitly set `--mode`, `--suite`, and repeated `--scenario` flags; command preview and actual runtime resolution honor those explicit overrides over flow defaults.
When both `--suite` and repeated `--scenario` are provided in trace mode, suite scenarios resolve first, then explicit scenarios are appended (deduped in order).
The `Scenarios (trace only)` control in Advanced Mode Overrides is a searchable chips multiselect. It only allows scenarios returned by the selected flow capability (no free-text custom scenario values).
Trace-context fields in the launcher: `suite`, `scenarios`, `strict_plan`, `skip_app_probes`, `skip_store_dashboard_probes`, `post_order_actions`, `enforce_websocket_gates`, `timeout_fails`.
Load-context fields in the launcher: `users`, `orders`, `interval`, `reject`, `continuous`, `all_users`, plus shared store/phone/provision controls.

Load user-assignment semantics:
- `all_users=false` -> single selected/default user is reused across `users=N` workers.
- `all_users=true` and `N <= plan users` -> first `N` users are selected in plan order.
- `all_users=true` and `N > plan users` -> users are assigned by deterministic round-robin repeat from the beginning.

Simulation plan API reserved-id semantics (`sim-actors`):
- `GET /api/v1/simulation-plans/sim-actors` returns the default `sim_actors.json` plan payload.
- That endpoint returns `404` when the default file is missing or invalid.
- Creating or updating GUI plans cannot use `sim-actors` as the plan id (`400`).
- `GET /api/v1/simulation-plans` dedupes legacy GUI plan files whose id resolves to `sim-actors`, so only one reserved default entry appears.

Run scope enforcement is strict to the selected plan:
- Stores must come from plan `stores[]`.
- Phones/users must come from plan `users[]`.
- Out-of-plan `--store` and `--phone` values fail fast instead of falling back to discovered/service-area entities.
- Out-of-plan `STORE_ID` / `USER_PHONE_NUMBER` env values and cached identity reuse paths are rejected in both trace and load modes.
- If the selected plan cannot be loaded or validated (missing/unreadable file, invalid JSON, or plan validation error), the simulator warns and falls back to repo default `sim_actors.json`.
- If both selected plan and fallback plan fail, the run exits with a combined error showing both failures.
- Strict mode still applies after fallback: when `--strict-plan` (or `rules.strict_plan=true`) is active, whichever plan is used must satisfy strict validation.
- Trace/doctor order scenarios use **websocket-first gating** for progression (see **Trace mode and websocket evidence** in Operator observability for the passive observer model). The simulator waits for required websocket status events before each next action (store accept/reject, payment progression, ready, robot lifecycle, terminal state).
- Websocket gate enforcement is configurable and defaults to off. With enforcement on, the run blocks at startup until `user_orders`, `store_orders`, and `store_stats` are connected, then fails fast if required channels drop past the retry window.
- Universal order closure guard is always on for order-producing runs: every created order must end in `completed`, `rejected`, or `cancelled`.
- End-of-run cleanup is automatic for non-terminal orders: short settle wait, then cancel-first/reject-fallback cleanup attempts, then re-check. Any unresolved order fails the run.
- Websocket lifecycle proof is required for order-producing success even when gate enforcement is off.
- Controls: env `SIM_ENFORCE_WEBSOCKET_GATES=false` (default), CLI `--enforce-websocket-gates` / `--no-enforce-websocket-gates`, and Runs UI checkbox `Enforce Websocket Gates`.
- Timeout failure policy is configurable and defaults to off. With timeout-fails off, HTTP requests wait indefinitely for endpoint responses. With timeout-fails on, request timeout protection is enforced and timeout events fail the run.
- Controls: env `SIM_TIMEOUT_FAILS=false` (default), CLI `--timeout-fails`, and Runs UI checkbox `Timeout Fails`.

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
    "trace_scenarios": ["backend_auto_cancel"],
    "store_auto_cancel_seconds": 120,
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
    "run_enforce_websocket_gates": false,
    "run_timeout_fails": false,
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

Trace scenarios such as `backend_auto_cancel` and explicit diagnostics such as `auto_cancel` belong in `runtime_defaults.trace_scenarios` (or the Runs page scenario multiselect / catalog profile `scenarios`), not in `rules`. The `rules` block is boolean simulator behavior (`run_app_probes`, `strict_plan`, etc.). Use `runtime_defaults.store_auto_cancel_seconds` to override the awaiting-payment observe window for explicit `auto_cancel` runs (no env var).

Keep these out of plan JSON: keys containing `secret`, `token`, `password`, `api_key`, or `private_key`. Plan validation rejects them. Stripe secret keys, cached auth tokens, test-user passwords, and deployment URLs stay in `.env`.

Keep normal simulator behavior out of `.env`. Phone/store selection, delivery GPS, runtime defaults, fixture/menu defaults, payment mode/coupon defaults, review defaults, and new-user names/email belong in `sim_actors.json` or the selected GUI plan. If GUI Phone/Store fields are blank, each run now randomly selects from plan `users[]` / `stores[]` by default. Explicit `--phone` / `--store` still wins, and `--no-random-phone` / `--no-random-store` disable random defaults for that run. API-launched runs intentionally ignore `.env` actor pins unless the run request passes explicit actor overrides.

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
| `place-order` | `trace` + scenario `place_order` | Seeds live pending order(s) for manual store-app inspection | Plan with at least one usable user and store | `--orders` 1..10, `--store`, `--phone`, `--timing` | Same |
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
| `python3 -m simulate place-order --plan sim_actors.json --orders 3` | Seeds three pending live orders for manual store-app inspection. |
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
| `python3 -m simulate --mode trace --scenario place_order --plan sim_actors.json --orders 3` | Seeds pending live orders and leaves them open for manual inspection. |
| `python3 -m simulate --mode trace --scenario backend_auto_cancel --plan sim_actors.json` | Pending idle + observe backend/customer cancel (primary). |
| `python3 -m simulate --mode trace --scenario auto_cancel --plan sim_actors.json` | Awaiting-payment countdown + observe cancel (optional diagnostic). |
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
| `... --timing fast` | Short store/robot delays (~0.2–0.6s) in load and trace. |
| `... --timing realistic` | Realistic store prep and robot leg delays in load and trace. |
| `... --store <STORE_ID>` | Forces explicit store; disables store fallback autopilot. |
| `... --phone <PHONE>` | Forces explicit user phone selection. |
| `... --no-random-store` | Disables default random store selection for the run. |
| `... --no-random-phone` | Disables default random phone selection for the run. |
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
- Websocket lifecycle proof failures (missing/late order status evidence).

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
| `--timing` | `fast` or `realistic` | from plan/env (`SIM_TIMING_PROFILE`) | Store accept/prep and robot leg delays in load and trace | Does not change user `--interval` (order placement spacing) |
| `--users` | int | from plan/env (`N_USERS`) | User worker count for load | Must be `>=1` in load |
| `--orders` | int | from plan/env (`SIM_ORDERS`) | Total orders in bounded load | Must be `>=1` in load unless `--continuous` |
| `--interval` | float seconds | from plan/env (`ORDER_INTERVAL_SECONDS`) | Delay between user order attempts in load | Load-mode control |
| `--reject` | float `0..1` | from plan/env (`REJECT_RATE`) | Probabilistic store rejection rate in load | Must be between `0` and `1` |
| `--continuous` | boolean | from plan/env (`SIM_CONTINUOUS`) | Infinite load run | Invalid in trace |
| `--phone` | string | none | Overrides selected user phone | Explicit override; should exist in selected plan |
| `--store` | string | none | Forces a specific store ID | Explicit override; should exist in selected plan |
| `--no-random-phone` | boolean | `false` | Disables default random phone selection | Uses deterministic plan/default phone selection |
| `--no-random-store` | boolean | `false` | Disables default random store selection | Uses deterministic plan/default store selection |
| `--all-users` | boolean | `false` | In load, auth and run all plan users | Load-mode control |
| `--plan` | path | `sim_actors.json` | Run plan JSON path | Relative paths resolve from current cwd first |
| `--strict-plan` | boolean | from plan/env (`SIM_STRICT_PLAN`) | Enforces user GPS + store IDs at load time | Fails fast on missing required plan fields |
| `--skip-app-probes` | boolean | `false` | Disables user-side non-order probes | Affects `app_bootstrap`/doctor/full/audit evidence depth |
| `--skip-store-dashboard-probes` | boolean | `false` | Disables store dashboard probes | Affects `store_dashboard` coverage |
| `--post-order-actions` | boolean | from plan/env | Enables receipt/review/reorder after completed orders | Can create real review/receipt records |
| `--enforce-websocket-gates` / `--no-enforce-websocket-gates` | boolean | from plan/env (`SIM_ENFORCE_WEBSOCKET_GATES=false`) | When enabled, startup blocks until required websocket channels are active and runtime drops fail after retry window | Trace/doctor websocket progression behavior |
| `--timeout-fails` | boolean | from plan/env (`SIM_TIMEOUT_FAILS=false`) | Enables request timeout enforcement and fails the run on timeout events | When off, HTTP requests wait indefinitely |
| `--no-auto-provision` | boolean | `false` | Disables automatic setup/category/menu repair path | Sets `SIM_AUTO_PROVISION_FIXTURES=false` for run |

Policy env controls:
- `SIM_FAILURE_POLICY=api_only|strict` (default `api_only`)
- `SIM_PREFLIGHT_STRATEGY=auto_recover|skip_warn|hard_stop` (default `auto_recover`)
- `SIM_TIMEOUT_FAILS=true|false` (default `false`)
- Plan equivalents: `rules.failure_policy`, `rules.preflight_strategy`, `rules.run_timeout_fails` / `rules.timeout_fails`

## 5) What We Test (Coverage Map)

### User-app probes (`app_probes.py`)

Preflight and post-call validation are grounded in session walkthrough docs via `session_probe_reference.py`, and only these five docs are allowed as contract sources:
- `app-20260428.full-session-user.md`
- `app-20260430.full-session-user.md`
- `app-20260517.full-session-user.md`
- `app-20260429.full-session-store.md`
- `app-20260430.full-session-store.md`

Contracts are variant-based (documented status + envelope/schema-key signatures), not exact payload-value matching. Probe decisions in `report.md` include source-doc attribution and sanitized payload preview where available.

- `GET /v1/entities/configs/`
- `POST /v1/biz/product/authentication/?product=rds`
- `GET /v1/biz/pricing/0/?product_name=lastmile&currency=<currency>`
- `GET /v1/core/cards/` — empty and non-empty variants are both documented and can pass when schema keys match.
- `GET /v1/core/coupon/`
- `GET /v1/core/orders/?user=<user_id>`

### Store-app probes (`app_probes.py`)

- `GET /v1/core/orders/?subentity_id=<id>`
- `GET /v1/statistics/subentities/<id>/`
- `GET /v1/statistics/subentities/<id>/top-customers/`

Probe status policy:
- `failed`: request exception, timeout/connection error, or HTTP `5xx`.
- `passed`: endpoint called and response matches a documented contract variant.
- `inconclusive`: endpoint called, but status/shape variant is undocumented.
- `skipped`: required preflight data is missing, or no contract sample exists.
- `failed_events` metrics and run-event rendering use these statuses directly and do not infer failure from `decision.ok=false`.

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
- Reorder fetch: `GET /v1/core/reorder/?order_id=<id>` (returns cart lines; simulator may place a second order from that payload when post-order + `receipt_review_reorder` run)

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
- Awaiting-payment observe window: `30s` (override in plan `runtime_defaults.store_auto_cancel_seconds`)

`--timing realistic`:

- Store decision delay: `3s .. 12s`
- Store prep delay: `20s .. 90s`
- Robot:
  - `enroute_pickup`: `20s .. 60s`
  - `robot_arrived_for_pickup`: `5s .. 20s`
  - `enroute_delivery`: `30s .. 120s`
  - `robot_arrived_for_delivery`: `5s .. 20s`
  - `completed`: `2s .. 8s`
- Awaiting-payment observe window: `120s` (override in plan `runtime_defaults.store_auto_cancel_seconds`)

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
- `websocket_gate_source_unavailable` + websocket `HTTP 502`: upstream `lastmile` proxy/gateway is rejecting websocket upgrade for `/ws/soc/...`; REST can still pass while websocket-gated scenarios fail.

### Websocket 502 Recovery (Upstream Lastmile)

When reports show websocket coverage failures like:

- `server rejected WebSocket connection: HTTP 502`
- `websocket_gate_source_unavailable`

the fix is outside this simulator repo, on the reverse proxy that fronts `lastmile.fainzy.tech`.

Required upstream nginx-style websocket settings for `/ws/` routes:

```nginx
location /ws/ {
  proxy_pass http://<lastmile_backend_upstream>;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header Host $host;
  proxy_read_timeout 600s;
  proxy_send_timeout 600s;
  proxy_buffering off;
}
```

Also ensure `/ws/soc/<user_id>/`, `/ws/soc/store_<subentity_id>/`, and `/ws/soc/store_statistics_<subentity_id>/` are routed to the websocket-capable backend and not an HTTP-only upstream.

Handshake verification command (expects `101 Switching Protocols`):

```bash
scripts/check_lastmile_ws.sh https://lastmile.fainzy.tech 37 7
```

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
| `operator` | Normal simulator operator. | Create/read/cancel/**delete** runs, create/read/update/**delete**/trigger schedules, read alerts, read dashboard, read archives, read retention settings. |
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
| `/schedules` | Create campaign-first schedules (simple requests are normalized to campaign steps); configure recurrence, period-specific run slots, all-day mode, run windows, blackout skip dates, and next automatic trigger visibility; active schedules run through the in-process scheduler and can also be manually triggered, paused/resumed, disabled/enabled, soft-deleted, and restored. |
| `/archives` | Archived runs/profiles/schedules/integration mappings with restore actions, plus retention summaries. |
| `/retention` | Inspect active/archive policy windows, archive/purge queues, retained summary fields, and purge-safety state. |
| `/admin/users` | Create, edit, reset, deactivate, or delete users. |
| `/admin/system` | Configure system policies such as allowed scheduling timezones (IANA allowlist). |

### Schedule and Campaign APIs

Schedules use saved run profiles as their execution source. V1 keeps execution in-process with APScheduler and does not require Celery or Redis. The scheduler polls once per minute, launches due active schedules, records a schedule execution row, and advances `next_run_at`.

Preferred contract for new/edited schedules:

- `anchor_start_at`: first automated start timestamp.
- `period`: `daily` | `weekly` | `monthly`.
- `repeat`: `none` | `daily` | `weekly` | `monthly` | `annually` | `weekdays` | `custom`.
- `stop_rule`: `never` | `end_at` | `duration`.
- `all_day`: full-day mode without slot-time inputs.
- `run_slots`: period-specific slots:
  - daily: `[{ "time": "HH:MM" }]`
  - weekly: `[{ "weekday": "monday", "time": "HH:MM" }]`
  - monthly: mixed `day_of_month` and `weekday_ordinal` slot records.
- optional `blackout_dates`.

Legacy cadence/custom fields remain accepted for compatibility with existing schedules that have not been edited.

The scheduler computes `next_run_at` with this exact precedence:

1. Cadence anchor candidate.
2. Active date range bounds.
3. Run window bounds.
4. Blackout date skips.

The schedules UI shows pre-submit mode (`Automatic` or `Manual-only`) and next-trigger preview, then surfaces server-computed `next_run_at`, `execution_mode_label`, and `next_run_reason` in schedule rows.
The schedules page auto-refreshes schedule and execution state every 15 seconds and also revalidates when the browser tab regains focus, so newly triggered automatic runs appear without manual page reload.

Scheduling procedure:

1. Create or choose a saved run profile from `/runs`; schedules launch profiles through campaign steps.
2. Open `/schedules`, configure period, repeat rule, timezone, and add at least one campaign step.
3. For `custom` repeat, set `recurrence_config.weekdays` and `stop_rule=end_at`.
4. Use `Active From` and `Active Until` to define optional automatic scheduling date-time bounds. Leave either side blank for no start or end boundary.
5. Add blackout dates for full local calendar days when automatic triggers must not run. Manual `Trigger` still launches immediately.
6. Save the schedule, then confirm the `Next Automatic Trigger` panel and table metadata.
7. Use `Pause`, `Resume`, `Disable`, `Delete`, and `Restore` for lifecycle control. `pause`, `disable`, and `delete` clear `next_run_at`; `resume` and `restore` recalculate it.
8. Archived schedules/profiles are read-only; restore first, then edit.

#### Catalog presets

On database init, the API seeds two **catalog** run profiles (`api-sweep-max`, `bounded-load-smoke`) and one catalog schedule per profile. They appear in **Runs** (profiles may show a **Catalog** label) and **Schedules**. Older catalog slugs are retired on seed (profile `catalog_slug` cleared; schedule disabled) so only the current presets stay pinned.

- `api-sweep-max` is the top-pinned profile in list ordering and is paired with an **active** UTC schedule that runs at `06:00`, `14:00`, and `20:00` daily.
- `bounded-load-smoke` has a **paused** daily template at `08:00 UTC`; resume it in **Schedules** when you want automatic load smoke.

Catalog profiles and catalog-backed schedules are now deletable/archivable. On user edit/delete, they are detached from catalog management (`catalog_managed=false`) so seed does not overwrite or recreate them on restart. To disable this seed entirely, set env `SIM_SKIP_CATALOG_SEED` to `1`, `true`, or `yes` before starting the API.

`bounded-load-smoke` is a **phased bounded load** profile: `users`, `orders`, `interval`, and `reject` are set on the profile row (passed to the CLI as `--users`, `--orders`, `--interval`, `--reject`). It enforces a completed-order baseline first (`>=1`) before reject/cancel tail pressure. If baseline cannot be met within the configured bound, the run fails with `accepted_baseline_not_met`.

Run rows include durable ownership fields (`process_pid`, `launcher_instance_id`, `last_heartbeat_at`, `ownership_state`) plus a `control` object (`can_stop`, `can_delete`, `actively_running`, detached-process details). The GUI enables **Stop** only for attached live runs and blocks delete when detached liveness recovery proves the simulator process is still active.

While a CLI run is finishing, the API worker sets terminal status from the subprocess exit code as soon as `wait()` returns, then enriches the row with artifact paths and resolved `store_id` / phone. Reconciliation now attempts detached-process recovery (PID + command/log identity checks) before failing. If no terminal log evidence exists and detached ownership is dead after grace windows, the run fails with `detached_process_dead_no_terminal_evidence`.

Key endpoints:

```bash
GET  /api/v1/run-profiles?include_archived=<true|false>
DELETE /api/v1/run-profiles/<PROFILE_ID>            # archive
POST /api/v1/run-profiles/<PROFILE_ID>/restore
GET  /api/v1/runs?include_archived=<true|false>
DELETE /api/v1/runs/<RUN_ID>                        # archive
POST /api/v1/runs/<RUN_ID>/restore
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
GET  /api/v1/archives/profiles
GET  /api/v1/archives/schedules
GET  /api/v1/archives/integration-mappings
```

Campaign-first schedule payload:

```json
{
  "name": "daily doctor",
  "schedule_type": "simple",
  "profile_id": 1,
  "anchor_start_at": "2026-05-07T08:00:00+01:00",
  "period": "daily",
  "repeat": "daily",
  "stop_rule": "never",
  "all_day": false,
  "run_slots": [{"time": "08:00"}, {"time": "12:00"}],
  "timezone": "UTC",
  "run_window_start": "08:00",
  "run_window_end": "18:00",
  "blackout_dates": ["2026-12-25"],
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

Manual trigger launches runs immediately through the saved profile path and records a schedule execution row. Identical active schedule/profile/command launches are serialized; skipped overlaps are recorded with execution status `overlap_skipped`.

#### Field Reference and Validation

- `name`: required, non-empty.
- `schedule_type`: `simple` and `campaign` inputs are both accepted; new/edited schedules persist as campaign execution.
- `profile_id`: accepted for compatibility; when `schedule_type=simple`, it is converted to the first campaign step.
- `period`: `daily`, `weekly`, `monthly`.
- `repeat`: `none`, `daily`, `weekly`, `monthly`, `annually`, `weekdays`, `custom`.
- `all_day`: boolean.
- `run_slots`: required when `all_day=false`; slot shape must match period.
- `timezone`: required IANA timezone; constrained by optional system allowlist.
- `active_from` / `active_until`: optional ISO date-times; `active_until` must be later than `active_from`.
- `blackout_dates`: optional list of `YYYY-MM-DD` local dates to skip.
- `recurrence_config.weekdays`: required when `repeat=custom`; valid weekday names; `stop_rule` must be `end_at`.

#### Cadence Behaviors and Required Data

| Repeat Rule | Required Additional Data | Effective Behavior |
| --- | --- | --- |
| `none` | none | one-off schedule date at anchor window |
| `daily` | daily slot times | slot times every day |
| `weekdays` | daily slot times | slot times Mon-Fri |
| `weekly` | weekly slots (`weekday` + `time`) | selected weekday/time runs each week |
| `monthly` | monthly slots (`day_of_month` / `weekday_ordinal`) | selected monthly patterns with times |
| `annually` | slots + anchor month/day | same month/day each year |
| `custom` | `recurrence_config.weekdays`, `stop_rule=end_at` | selected weekdays with end date |

#### Worked Examples

1. Daily with two runs
`period=daily`, `repeat=daily`, `run_slots=[{"time":"08:00"},{"time":"14:00"}]` -> two local-time runs each day.
2. Weekly mixed days
`period=weekly`, `repeat=weekly`, `run_slots=[{"weekday":"monday","time":"09:00"},{"weekday":"thursday","time":"16:00"}]` -> runs every Monday and Thursday at configured times.
3. Monthly mixed patterns
`period=monthly`, `repeat=monthly`, `run_slots=[{"kind":"day_of_month","day":5,"time":"08:00"},{"kind":"weekday_ordinal","ordinal":2,"weekday":"tuesday","time":"11:00"}]` -> 5th day and 2nd Tuesday monthly.
4. Custom weekdays
`repeat=custom`, `recurrence_config.weekdays=["monday","wednesday","friday"]`, `stop_rule=end_at` -> selected weekdays only until end date.

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

- If candidate date is a blackout date, scheduler advances to next eligible date.
- If active range end is reached, `next_run_at` becomes null with `outside_active_range`.
- DST shifts are handled through schedule timezone conversion and UTC persistence.

#### Troubleshooting by `next_run_reason`

- `computed`: schedule is healthy; verify business expectations only.
- `blackout_skipped`: remove/adjust blackout dates if run should happen sooner.
- `outside_active_range`: extend `active_until` or clear end bound.
- `no_future_run`: fix cadence inputs (especially custom fields), then save schedule again.

#### Recent Executions Statuses

Recent Executions in `/schedules` renders one current-state card per schedule:
- Schedule phase chip: `Queued`/`Starting`/`Run launched`/`Overlap skipped`/`Launch failed` from latest schedule execution lifecycle.
- Run status chip: latest linked run status (`Queued`, `Running`, `Succeeded`, `Failed`, `Cancelled`) from the actual run row.

Cards are fully clickable to run detail when a latest run exists, with a `View run` hover tooltip; if no run exists yet, the card remains non-clickable and shows `No run created yet`.

### System Settings: Allowed Timezones

By default, schedules accept any valid IANA timezone. Admins can switch the system timezone policy to an allowlist at `/admin/system`; once configured, schedule create/update requests that specify a timezone not in the allowlist are rejected with HTTP 400.

Key endpoints:

```bash
GET /api/v1/system/timezones
PUT /api/v1/system/timezones
```

### System Settings: Email Notifications

Config page `Email` tab includes an Email Notifications panel to manage persisted non-secret settings:
- `email_enabled`
- `email_from_email`
- `email_from_name`
- `email_subject_prefix`
- `email_recipients`
- `email_event_triggers` (`run_failed`, `schedule_launch_failed`, `critical_alert`, `socket_failure`)

Key endpoints:

```bash
GET /api/v1/system/email
PUT /api/v1/system/email
POST /api/v1/system/email/test
```

SMTP config must be provided through env secrets (not system settings):
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_TLS_MODE` (`starttls` or `ssl`)

Docker wiring:
- Local compose reads from repo `.env` and injects `SMTP_*` into `api`.
- Production compose reads from `.env.prod` (`--env-file .env.prod`) and injects `SMTP_*` into `api`.
- Changing SMTP env values requires `api` container recreate/restart.

Behavior notes:
- `critical_alert` maps to run-failure events in v1 (deduped).
- `socket_failure` sends only when the socket monitor transitions to Down after the configured failure threshold. It can be disabled independently from run-failure emails and is deduped via persisted `system_settings` state.
- Test-email endpoint has a cooldown and may return HTTP 429 if called repeatedly.
- SMTP secrets are never returned in API payloads.
- Failure emails include launch context first in this order: `Profile`, `Trigger`, `Project`, `Repository` (plus `Schedule` for schedule triggers).

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

## Production Deployment Operations

Production deployment for this repository deploys the Simulator service stack (`nginx`, `web`, `api`, `postgres`) and supports GitHub deployment webhook-triggered simulation runs across other repositories.

- Workflow: `.github/workflows/deploy.yml`
- Compose file: `docker-compose.prod.yml`
- Host env file (required): `.env.prod`
- Trigger: push to `main` or manual workflow dispatch

Deployment is idempotent (`git fetch` + `git checkout main` + `git reset --hard origin/main`), does not delete volumes, and fails if health check (`/healthz`) fails.

GitHub deployment webhook automation:

- Inbound endpoint: `POST /api/v1/integrations/github/deployment-complete`.
- Supported events:
  - `deployment_status` with `state=success` (required fields in payload); other states/events are rejected for launches.
  - `workflow_run` with `action=completed` and `workflow_run.conclusion=success`; repository must be allowlisted and `(project, environment)` must map to a profile (same mapping table as deployments). **Runs created from `workflow_run` are stored with `trigger_source=github`**, `trigger_label` `GitHub integration: {project}/{environment}`, merged `trigger_context` (profile name, repository, workflow summary, `github_event: workflow_run`), and `integration_trigger_id` pointing at the `integration_triggers` row—same style as deployment-triggered runs, so the Runs page and overview chips show GitHub rather than a dashboard profile launch.
- Security: HMAC verification via `X-Hub-Signature-256` using project-specific signing secrets from the persistent webhook config file (`SIMULATOR_WEBHOOK_PROJECTS_FILE`, default `/workspace/simulate/data/webhook-projects.json`). Manage projects in **Config → Integration → Webhook Projects**; changes auto-sync to GitHub `SIMULATOR_WEBHOOK_PROJECT_SECRETS` when `SIMULATOR_GITHUB_CONFIG_TOKEN` is set on the API.
- Repository guardrail: repository must match an allowlisted `owner/repo` for the resolved project. Configure repositories in **Webhook Projects** (synced to `SIMULATOR_WEBHOOK_REPO_ALLOWLIST` on the simulator repo).
- Profile routing: simulator maps `(project, route key)` to a saved run profile through `integration_profile_mappings`. The route key column is named `environment` in the API/DB. By default it is GitHub’s deployment environment (`deployment.environment` on `deployment_status`, or `SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT` / `production` on `workflow_run`). Set `SIMULATOR_WEBHOOK_ROUTE_BY=branch` to route by git ref instead (`workflow_run.head_branch` or `deployment.ref`, normalized to lowercase).
- Idempotency key: `project + environment + deployment_id + sha`; duplicate webhook deliveries do not launch duplicate runs.
- Lifecycle states recorded per trigger: `validated`, `queued`, `launched`, `completed`/`failed`, `rejected`, `duplicate`.
- Callback: when run reaches terminal state, simulator posts deployment status back to GitHub with context `simulator/verification` using `GITHUB_STATUS_TOKEN`.

Webhook project setup (GUI):

1. Add repository secret `SIMULATOR_GITHUB_CONFIG_TOKEN` (fine-grained PAT with Actions read/write on this simulator repo) so the UI can auto-sync GitHub maps.
2. Open **Config → Integration → Webhook Projects**.
3. Enter the project key (same name used in mappings, for example `dashboard`) and allowed `owner/repo` lines.
4. Click **Generate webhook secret**, then **Copy secret** and paste it into the upstream repository GitHub webhook **Secret** field.
5. Confirm **Synced to GitHub** (or use the manual `gh` fallback commands if sync is skipped).
6. Copy the webhook URL into the upstream webhook **Payload URL**.
7. Add **Integration Mappings** for `(project, environment or branch)` → run profile.
8. Run deploy (or wait for push to `main`) so host `.env` picks up the updated GitHub secret and variable.

Operational APIs:

- `GET /api/v1/integrations/github/projects` (list saved webhook projects; secrets are masked)
- `POST /api/v1/integrations/github/projects` (create project + generate secret; plaintext secret returned once)
- `POST /api/v1/integrations/github/projects/{project}/rotate-secret` (new secret returned once)
- `PATCH /api/v1/integrations/github/projects/{project}/repositories` (update allowlisted repos)
- `DELETE /api/v1/integrations/github/projects/{project}` (archive project)
- `GET /api/v1/integrations/github/mappings?include_archived=<true|false>` (view mapping rows)
- `POST /api/v1/integrations/github/mappings` (upsert `{project, environment, profile_id, enabled}`)
- `DELETE /api/v1/integrations/github/mappings/{mapping_id}` (archive)
- `POST /api/v1/integrations/github/mappings/{mapping_id}/restore`
- `GET /api/v1/integrations/github/triggers` (audit and debugging feed)

To identify webhook-triggered runs in the GUI, use the **Launch** column on **Runs** (`trigger_source` is `github` and the label shows the integration route). For audit detail, use `GET /api/v1/integrations/github/triggers` and match `run_id` to the run.

**Config → Integration Mappings → Recent GitHub Triggers:** each row’s **GitHub payload** disclosure shows the stored `payload` field from the API: the full parsed webhook JSON for `deployment_status` events, or a compact workflow summary for `workflow_run` events (same column in `integration_triggers`).

**Why multiple trigger rows for one push:** the simulator does **not** fan out one webhook to every enabled route. It selects at most one mapping per delivery using `(project, route key)`. With default routing (`SIMULATOR_WEBHOOK_ROUTE_BY=environment`), the key is GitHub’s deployment environment on `deployment_status`, or the fixed default on `workflow_run` (see above). Seeing two rows for the same repository at the same time often means GitHub delivered **two** event types (for example both `deployment_status` for `dev` and `workflow_run` defaulting to `production`) or two successful deployment environments. Prefer a single webhook event type, or set `SIMULATOR_WEBHOOK_ROUTE_BY=branch` and map `dev` / `main` in **Config** so `workflow_run` uses `head_branch`.

**Branch-based routing (`SIMULATOR_WEBHOOK_ROUTE_BY=branch`):** set on the simulator API container (production: repository Actions variable `SIMULATOR_WEBHOOK_ROUTE_BY` on **this simulator repo**, passed through `.github/workflows/deploy.yml` into host `.env` — not on upstream app repos such as fainzy-dashboard). Restart API after deploy, then create mappings whose **Branch** field is the git branch name (for example `dev`, `main`). Subscribe to `workflow_run` only if you want one launch per completed workflow; use `deployment_status` if you want launch when a deployment record succeeds (routes by `deployment.ref` in branch mode).

Use `docs/deployment.md` as the full production runbook for first-time host setup, GitHub secrets, backup/restore, rollback, logs, troubleshooting, and security hardening.
