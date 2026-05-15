# Fainzy Simulator Guidebook

This simulator is a daily doctor for the ordering platform. It simulates user app, store app, and robot behavior; continuously checks HTTP and websocket paths; and writes operator-friendly reports plus full technical evidence.

Docker note: this stack runs the Next.js web app with `next start` from the built image. If `./web` is bind-mounted over `/app`, the built `.next` directory can be masked and `web` will crash with `Could not find a production build in the '.next' directory`.

**Capability catalog:** For an exhaustive reference to flows, suites, scenarios, CLI flags, run-plan JSON keys, environment variables, and web/API launch parity, see [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md).

**GUI manual testing:** For a from-the-ground-up checklist of the web UI (every Start Run control, client-side validation, profiles, run detail, and role expectations), see [docs/GUI_TESTING.md](docs/GUI_TESTING.md).

**Ideas backlog:** For GUI and functional improvement ideas (not roadmap commitments), see [docs/IDEAS_GUI_AND_FUNCTIONAL.md](docs/IDEAS_GUI_AND_FUNCTIONAL.md).

## Operator observability (read first)

### Health contract: Up, Degraded, Down

- **Up:** Control plane is healthy (`GET /healthz` ok), you can authenticate, and—when judging product health—a **recent successful doctor or trace run** finished within your policy window.
- **Degraded:** Partial risk: open alerts, archive/purge backlog, schedule campaign warnings, or websocket **warnings** while a run still completed. Investigate before declaring all-clear.
- **Down:** Blocking failure: **failed run**, cannot sign in, cannot launch runs, or required ordering steps never complete (for example enforced websocket gates time out).

**`/healthz` is not last-mile green:** The JSON from `GET /healthz` reports the FastAPI process (`status`, `project_dir`, `simulator_workdir`, `db_path`). It does **not** exercise last-mile HTTP, menus, payment, or `wss://` gateways. Use **doctor** or **trace** for end-to-end proof.

### Which simulation flow should I use?

1. **End-to-end platform health** → `doctor` + agreed plan (`sim_actors.json` or `runs/gui-plans/daily-doctor.json` or another standard GUI plan).
2. **Targeted regression** → `trace` + narrow suite (`core`, `doctor`, or specific scenarios listed under Trace Mode in `ARCHITECTURE.md`).
3. **Load / churn** → `load` mode (engineering; not the default “is the platform up?” check).

### Trace mode and websocket evidence

Use **trace** (or **`doctor`**, which runs in trace mode) when you need proof that **last-mile HTTP APIs** and, for order flows, **`wss://` traffic** behave—not only that the simulator API (`/healthz`) is up.

- **APIs (REST and similar):** Scenarios issue real requests: place and mutate orders, run `app_bootstrap` and `store_dashboard` probes, menu checks, payment paths, store setup, and so on. Failures (for example 5xx, timeouts, auth errors) are recorded in the run ledger and summarized in `report.md` / `story.md` / `events.json` for that run.
- **Websockets:** When the resolved scenario list includes **order-driving** scenarios (for example `completed`, `rejected`, `cancelled`, payment and robot completion paths, `receipt_review_reorder`), trace attaches a **`WebsocketObserver`**. That component **only opens the same socket URLs the apps use and receives messages**—it does **not** send app traffic to impersonate a user or store on those sockets. **Active** order-driving traffic still comes from the normal simulator paths (user / store / robot simulators and REST-driven steps). The observer is a **passive listener** used for **evidence** (coverage, recorded frames, optional gates).
- **Websocket gate enforcement:** With enforcement **off** (default), missing or late socket events are usually **warnings** and the scenario can continue—good for signal without blocking every run. With enforcement **on** (`SIM_ENFORCE_WEBSOCKET_GATES`, CLI flags, plan `rules`, or Runs **Enforce Websocket Gates**), required status events must arrive within the configured window or the run **fails**—a stricter check when you care whether “HTTP succeeded but realtime never showed up.”
- **Full scenario and flag matrix:** See [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md) for every scenario name, suite, and launcher field.

### Trace scenarios and flags (process truth)

| Scenario | Role in “does ordering work?” |
|----------|-------------------------------|
| `completed` | Full happy path through robot completion |
| `rejected` | Store rejects before payment |
| `cancelled` | Customer cancels while pending |
| `auto_cancel` | Backend timeout cancellation without store action |
| `app_bootstrap` | Config, product auth, pricing, cards, coupons, active orders |
| `store_dashboard` | Store orders, statistics, top customers |
| `receipt_review_reorder` | Receipt PDF, review, reorder fetch after completion |

**Websocket gates:** See **Trace mode and websocket evidence** above for how trace exercises APIs and passively observes sockets. In short: `SIM_ENFORCE_WEBSOCKET_GATES` default **off** (Runs checkbox off) records gate issues as **warnings** and continues; **on** = fail fast when required socket events are missing—stricter **Down** signal, more noise. **`SIM_STRICT_PLAN` / `rules.strict_plan`:** rejects invalid plans after any fallback—can flip a run from “best effort” to **Down** if the plan is wrong.

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
- **Attention queue** — Active or failed runs (links to `/runs/{id}`).
- **Alerts** — Top operational alerts with links.
- **Platform / Archive / Retention** panels — Policies and queue depths; **Platform** clarifies **`/healthz`** scope.

**Refresh:** Data loads once on mount (no auto-poll on Overview).

### Route: `/runs`

**Purpose:** Launch simulations, watch live log, manage **Saved profiles**, browse recent runs.

**Key blocks:**

- **Header strip** — Title, theme, profile, **API health** note (healthz scope), link to Overview flow ladder.
- **Run statistics** — Status + flow distribution bars; optional **Last succeeded / Last failed** panels when API returns highlights.
- **Start Run** (`CollapsibleSection`) — `RunLaunchPanel` + `RunLiveConsole`. Plan dropdown (`sim_actors.json` + `runs/gui-plans/*`), flow/mode/suite/scenario controls gated by `/api/v1/flows`, command preview, websocket gate checkbox, advanced overrides.
- **Saved profiles** — CRUD and launch saved configurations (behavior preserved; labels improved only under observability work).
- **Recent runs table** — Select run, open detail, actions.
- **Admin dashboard embed** — Role-gated operator tools when permitted.

**Refresh:** Health poll ~10s; runs + summary poll ~5s while page is open.

### Route: `/runs/{id}`

Run detail: summary, log download, artifacts (`report.md`, `story.md`, `events.json`), metrics—deep dive after a failure.

**Overview tab:** Shows aggregate metrics plus a **metrics-first dashboard** (Business default view, segmented Operations/Engineering views, and collapsed technical action drill-down with action-key search). It also renders side-by-side findings cards: **Critical Findings** (server/API availability failures) and **Operational Findings** (non-critical warnings/info from the same run). `GET /api/v1/runs/{id}/metrics` returns `action_counts` as `{ action, count }[]` (every distinct `action` in `events.json`, sorted by count then name), and the dashboard derives KPI cards from these counts and existing totals/actors. `top_actions` remains a capped top-10 map for older consumers. Findings for a specific run are available through `GET /api/v1/overview/runs/{run_id}` (latest-run summary remains `GET /api/v1/overview/latest-run`). Misleading placeholder charts were removed; use **Traffic** for the raw event stream and **Console** for process output.

### Route: `/config`

Edit GUI-owned plans, integration mappings, **Email notifications** panel (non-secret SMTP settings + triggers), and related operator configuration.

### Route: `/schedules`

Campaign-first schedules, previews, manual trigger, pause/resume, disable/enable, soft delete/restore. Auto-refresh ~15s and on window focus. **Semantics are protected**—observability work only clarifies labels/errors.

### Route: `/archives` and `/retention`

Browse archived runs and inspect retention/purge posture; observation-first tooling.

### Route: `/admin/users` and `/admin/system`

User CRUD/roles live under **`/admin/users`** (primary **Admin** nav entry). **`/admin/system`** (system policies such as allowed schedule timezones) opens from the **Admin sub-navigation** when you are already in the admin area (`AdminSubNav`: Users vs System Settings).

### Route: `/auth/login`

Sign-in for the web UI; redirects to `/overview` when already authenticated.

### Email notifications (operators)

Failure emails (`run_failed`, `schedule_launch_failed`) append a short **“How to read this”** footer: failed run = process check failed; `/healthz` = control plane only; pointer to this guide. Configure triggers on **Config → Email Notifications**.

## 1) Inputs and Outputs

Required operator inputs:

- `.env` for secrets, auth cache values, credentials, and deployment URLs only.
- A plan JSON (default `sim_actors.json`) with users, stores, GPS, runtime defaults, rules, fixture defaults, payment defaults without Stripe secrets, review defaults, and new-user metadata.

Generated artifacts per run:

- `runs/<timestamp>/events.json`: complete event ledger.
- `runs/<timestamp>/report.md`: summary + bottlenecks + tabled findings + technical trace.
- `runs/<timestamp>/story.md`: narrative scenario summary.
- `events.json` includes decision records (`called`, `blocked`, `skipped`, `recovered`, `failed`) with reason code/message, next action, and whether the run continued.
- Overview page behavior: Latest Run `Critical Findings` is filtered to server/API availability failures (`5xx`, transport/network, websocket connection availability). Missing-information or business-availability conditions (for example missing token, no saved card, no coupon) stay in `events.json`/`report.md`/`story.md` but are intentionally excluded from Overview.
- Overview `Critical Findings` rows include failed route/endpoint when available, and the Latest Run hero surfaces context chips such as `profile:<name>`, `schedule:<name>`, and integration `route:<project/environment>`.

Configuration precedence:

1. Explicit CLI flags.
2. Values from the selected plan JSON.
3. `.env` fallback for secret/auth/deployment values.
4. Built-in defaults.

The GUI stores admin-created plans in `runs/gui-plans/` and launches them through the same `--plan` CLI path.
On the Runs page, Start Run plan selection is dropdown-only: `sim_actors.json` is always shown, then GUI plans from `runs/gui-plans/`; manual text entry is not supported.
Start Run now reads flow capabilities from `GET /api/v1/flows` and conditionally renders only flags valid for the selected `Flow`, resolved `Mode`, and selected `Suite/Scenarios`.
Advanced Mode Overrides are optional and let operators explicitly set `--mode`, `--suite`, and repeated `--scenario` flags; command preview mirrors typed fields exactly.
Trace-context fields in the launcher: `suite`, `scenarios`, `strict_plan`, `skip_app_probes`, `skip_store_dashboard_probes`, `post_order_actions`, `enforce_websocket_gates`.
Load-context fields in the launcher: `users`, `orders`, `interval`, `reject`, `continuous`, `all_users`, plus shared store/phone/provision controls.

Run scope enforcement is strict to the selected plan:
- Stores must come from plan `stores[]`.
- Phones/users must come from plan `users[]`.
- Out-of-plan `--store` and `--phone` values fail fast instead of falling back to discovered/service-area entities.
- Out-of-plan `STORE_ID` / `USER_PHONE_NUMBER` env values and cached identity reuse paths are rejected in both trace and load modes.
- If the selected plan cannot be loaded or validated (missing/unreadable file, invalid JSON, or plan validation error), the simulator warns and falls back to repo default `sim_actors.json`.
- If both selected plan and fallback plan fail, the run exits with a combined error showing both failures.
- Strict mode still applies after fallback: when `--strict-plan` (or `rules.strict_plan=true`) is active, whichever plan is used must satisfy strict validation.
- Trace/doctor order scenarios use **websocket-first gating** for progression (see **Trace mode and websocket evidence** in Operator observability for the passive observer model). The simulator waits for required websocket status events before each next action (store accept/reject, payment progression, ready, robot lifecycle, terminal state).
- Websocket gate enforcement is configurable and defaults to off. With enforcement off, gate timeout/source failures are recorded as warnings and scenarios continue. With enforcement on, gate failures fail fast and stop downstream actions.
- Controls: env `SIM_ENFORCE_WEBSOCKET_GATES=false` (default), CLI `--enforce-websocket-gates` / `--no-enforce-websocket-gates`, and Runs UI checkbox `Enforce Websocket Gates`.

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
| `--enforce-websocket-gates` / `--no-enforce-websocket-gates` | boolean | from plan/env (`SIM_ENFORCE_WEBSOCKET_GATES=false`) | Controls whether websocket gate failures fail the scenario or are bypassed with warning evidence | Trace/doctor websocket progression behavior |
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
| `/schedules` | Create campaign-first schedules (simple requests are normalized to campaign steps); configure recurrence, period-specific run slots, all-day mode, run windows, blackout skip dates, and next automatic trigger visibility; active schedules run through the in-process scheduler and can also be manually triggered, paused/resumed, disabled/enabled, soft-deleted, and restored. |
| `/archives` | Search archive candidates, raw-purge candidates, and retained run summaries. |
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

#### Catalog presets (paused templates)

On database init, the API seeds six **catalog** run profiles (`daily-doctor`, `gates-on-doctor`, `core-trace`, `bounded-load-smoke`, `menu-gates`, `weekly-full`) and one **paused** daily schedule per profile (08:00 UTC). They appear in **Runs** (profiles may show a **Catalog** label) and **Schedules**; resume a schedule when you want that preset to run automatically. Catalog profiles and catalog-backed schedules are not deletable via the API (403). To disable this seed entirely, set env `SIM_SKIP_CATALOG_SEED` to `1`, `true`, or `yes` before starting the API.

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

Manual trigger launches runs immediately through the saved profile path and records a schedule execution row.

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
- Schedule phase chip: `Queued`/`Starting`/`Run launched`/`Launch failed` from latest schedule execution lifecycle.
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

Config page includes an Email Notifications panel to manage persisted non-secret settings:
- `email_enabled`
- `email_from_email`
- `email_from_name`
- `email_subject_prefix`
- `email_recipients`
- `email_event_triggers` (`run_failed`, `schedule_launch_failed`, `critical_alert`)

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
- Security: HMAC verification via `X-Hub-Signature-256` using project-specific secrets from `SIMULATOR_WEBHOOK_PROJECT_SECRETS` (JSON map of project key → secret string).
- Repository guardrail: repository must match `SIMULATOR_WEBHOOK_REPO_ALLOWLIST` for one configured project (JSON map: project key → list of `owner/repo` strings).
- Profile routing: simulator maps `(project, environment)` to a saved run profile through `integration_profile_mappings`.
- Idempotency key: `project + environment + deployment_id + sha`; duplicate webhook deliveries do not launch duplicate runs.
- Lifecycle states recorded per trigger: `validated`, `queued`, `launched`, `completed`/`failed`, `rejected`, `duplicate`.
- Callback: when run reaches terminal state, simulator posts deployment status back to GitHub with context `simulator/verification` using `GITHUB_STATUS_TOKEN`.

Operational APIs:

- `GET /api/v1/integrations/github/mappings` (view mapping rows)
- `POST /api/v1/integrations/github/mappings` (upsert `{project, environment, profile_id, enabled}`)
- `DELETE /api/v1/integrations/github/mappings/{mapping_id}`
- `GET /api/v1/integrations/github/triggers` (audit and debugging feed)

To identify webhook-triggered runs in the GUI, use the **Launch** column on **Runs** (`trigger_source` is `github` and the label shows the integration route). For audit detail, use `GET /api/v1/integrations/github/triggers` and match `run_id` to the run.

**Config → Integration Mappings → Recent GitHub Triggers:** each row’s **GitHub payload** disclosure shows the stored `payload` field from the API: the full parsed webhook JSON for `deployment_status` events, or a compact workflow summary for `workflow_run` events (same column in `integration_triggers`).

**Why multiple trigger rows for one push:** the simulator does **not** fan out one webhook to every enabled route. It selects at most one mapping per delivery using `(project, environment)` where `environment` comes from GitHub’s deployment environment (`deployment.environment` on `deployment_status`). Seeing two rows for the same repository at the same time usually means GitHub completed **two** successful deployments (for example `dev-cluster` and `production`) and delivered two webhooks. To stop production from queuing runs, **disable or delete** the production mapping on **Config**; GitHub may still record a trigger row with status `rejected` / reason `mapping_disabled` if a success webhook arrives for that environment. To verify upstream behavior, inspect the repository’s **Deployments** (or Actions deployment jobs) and confirm how many environments transition to success per event.

Use `docs/deployment.md` as the full production runbook for first-time host setup, GitHub secrets, backup/restore, rollback, logs, troubleshooting, and security hardening.
