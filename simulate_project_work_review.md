# Simulate Project Work Review — Discussion, Tasks, Decisions, and Current State

This document summarizes what we discussed about the `simulate` / Fainzy Simulator project, the tasks requested, the problems analyzed, the fixes proposed, the code regions discussed, and the work still pending.

The project is a CLI-driven and web-managed simulator for the Fainzy last-mile ordering platform. It simulates user, store, robot, HTTP, and WebSocket behavior, and writes evidence-rich run artifacts such as `events.json`, `report.md`, and `story.md`.

---

## 1. Project Context

The simulator is intended to act as an operator-focused “daily doctor” for the ordering platform.

It is expected to verify:

- User app behavior.
- Store app behavior.
- Robot delivery lifecycle.
- HTTP request/response behavior.
- WebSocket event behavior.
- Payment paths.
- Store availability.
- Menu availability.
- Run schedules.
- GitHub-triggered verification runs.
- Run artifacts and reports.

The repository includes:

- Python CLI simulator.
- FastAPI backend.
- Next.js web UI.
- Docker Compose deployment.
- Run profiles.
- Schedules.
- GitHub integration mappings.
- Reports, stories, logs, events, and metrics.

---

## 2. VPS Deployment and Docker Issues

### Problem discussed

The user ran:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The API and Postgres containers became healthy, but the `web` container became unhealthy.

### Cause discussed

The web container was using a development command in production:

```bash
npm run dev -- --hostname 0.0.0.0 --port 3000
```

That is not ideal for production and can cause health/startup issues.

### Advice given

Use production Next.js behavior:

```bash
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Also confirm:

- The currently live port is not interrupted unintentionally.
- `nginx` points to the correct internal web service.
- Docker Compose reads the intended `.env`.
- The deployment path is consistent.

---

## 3. Deployment Path and Env File Confusion

### Problem discussed

There was confusion between:

```txt
/root/simulate
```

and:

```txt
/root/simulator
```

There was also confusion around whether to use `.env` or `.env.prod`.

### Resolution

The user decided to use:

```txt
/root/simulator
```

and to use:

```txt
.env
```

by default.

### Guidance given

The GitHub deploy workflow should write `.env` directly if Docker Compose expects `.env`.

Example deployment output file:

```bash
cat > .env <<EOF
SIM_ENV=${SIM_ENV}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=${DATABASE_URL}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
WEB_CORS_ORIGINS=${WEB_CORS_ORIGINS}
SIM_AUTH_DISABLED=${SIM_AUTH_DISABLED}
SIMULATOR_HOST_BIND=${SIMULATOR_HOST_BIND}
SIMULATOR_HOST_PORT=${SIMULATOR_HOST_PORT}
SIMULATOR_SESSION_COOKIE_NAME=${SIMULATOR_SESSION_COOKIE_NAME}
SIMULATOR_SESSION_MAX_AGE_SECONDS=${SIMULATOR_SESSION_MAX_AGE_SECONDS}
SIMULATOR_SESSION_COOKIE_SECURE=${SIMULATOR_SESSION_COOKIE_SECURE}
SIMULATOR_SESSION_COOKIE_SAMESITE=${SIMULATOR_SESSION_COOKIE_SAMESITE}
SIMULATOR_EXTERNAL_BASE_URL=${SIMULATOR_EXTERNAL_BASE_URL}
SIMULATOR_WEBHOOK_PROJECT_SECRETS=${SIMULATOR_WEBHOOK_PROJECT_SECRETS}
SIMULATOR_WEBHOOK_REPO_ALLOWLIST=${SIMULATOR_WEBHOOK_REPO_ALLOWLIST}
SIMULATOR_GITHUB_STATUS_CONTEXT=${SIMULATOR_GITHUB_STATUS_CONTEXT}
SIMULATOR_GITHUB_STATUS_TOKEN=${SIMULATOR_GITHUB_STATUS_TOKEN}
EOF
```

---

## 4. GitHub Secrets and Variables

### Problem discussed

GitHub rejected this secret name:

```txt
GITHUB_WEBHOOK_PROJECT_SECRETS
```

because secret names cannot start with `GITHUB_`.

### Fix

Use `SIMULATOR_` names instead:

```txt
SIMULATOR_WEBHOOK_PROJECT_SECRETS
SIMULATOR_WEBHOOK_REPO_ALLOWLIST
SIMULATOR_GITHUB_STATUS_CONTEXT
SIMULATOR_GITHUB_STATUS_TOKEN
SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT
```

### Important lesson

The same names must be used consistently in:

- GitHub Actions.
- Docker Compose.
- `.env`.
- Python code.

---

## 5. GitHub Integration Mapping Debugging

### Problem discussed

Manual webhook ping worked:

```json
{"ok": true, "event": "ping", "message": "GitHub webhook ping received."}
```

but real `workflow_run` triggers were not creating records in:

```txt
integration_triggers
```

### Cause found

The handler still referenced old environment names:

```py
GITHUB_WEBHOOK_PROJECT_SECRETS
GITHUB_WEBHOOK_REPO_ALLOWLIST
```

instead of:

```py
SIMULATOR_WEBHOOK_PROJECT_SECRETS
SIMULATOR_WEBHOOK_REPO_ALLOWLIST
```

### Fix advised

In:

```txt
api/app/integrations/github_workflow_run.py
```

use:

```py
_json_env("SIMULATOR_WEBHOOK_PROJECT_SECRETS", {})
_json_env("SIMULATOR_WEBHOOK_REPO_ALLOWLIST", {})
```

### Verification command given

```bash
cd /root/simulator

docker compose -f docker-compose.prod.yml exec api python - <<'PY'
from api.app.integrations.github_workflow_run import (
    _github_project_secrets,
    _github_repo_allowlist,
    DEFAULT_WORKFLOW_ENVIRONMENT,
)

print("projects:", list(_github_project_secrets().keys()))
print("allowlist:", _github_repo_allowlist())
print("environment:", DEFAULT_WORKFLOW_ENVIRONMENT)
PY
```

Expected:

```txt
projects: ['simulator']
allowlist: {'simulator': ['Fainzy-Technologies/simulator']}
environment: production
```

---

## 6. Stripe Error During Doctor Simulation

### Error

```txt
Simulation failed: STRIPE_SECRET_KEY is required when SIM_PAYMENT_MODE=stripe.
The key must be from the same Stripe test account used by backend webhooks.
```

### Cause

The selected run was using:

```env
SIM_PAYMENT_MODE=stripe
```

but the runtime did not have:

```env
STRIPE_SECRET_KEY
```

### Options advised

For real Stripe test payment simulation:

```env
STRIPE_SECRET_KEY=sk_test_xxx
```

For non-payment doctor checks:

```env
SIM_PAYMENT_MODE=free
```

or configure the selected plan/profile to use free mode.

---

## 7. Integration Mappings GUI

### User request

Add a GitHub Integration Mappings GUI under Config.

### Purpose

Map:

```txt
GitHub project + environment -> simulator run profile
```

Example:

```txt
Project: simulator
Environment: production
Run Profile: simulator
Enabled: true
```

### Expected behavior

When GitHub sends a webhook:

1. Verify signature.
2. Check repo allowlist.
3. Find mapping by project/environment.
4. Launch the mapped run profile.
5. Record trigger status.
6. Optionally post GitHub commit status.

### Suggested UI data

```txt
Project
Environment
Run Profile
Enabled
Last Trigger Status
Last Trigger Reason
Last Run ID
Created At
Updated At
```

---

## 8. Missing CLI Values in GUI

### User request

Expose missing CLI options in the GUI:

```txt
Mode: trace/load
Users: --users
Orders: --orders
Interval seconds: --interval
Reject rate: --reject
Continuous: --continuous
```

### Reason

The GUI should be able to launch the same kinds of runs as the CLI.

Example CLI behavior to support from GUI:

```bash
python3 -m simulate load --plan sim_actors.json --users 5 --orders 100 --interval 2 --reject 0.1
```

---

## 9. Latest Run Overview / Command Center

### User request

On the overview page after login, show rich latest-run information at a glance:

- User.
- Store.
- Robot.
- HTTP requests.
- WebSocket requests.
- Latest status.
- Run detail link.
- Clear visual explanation.

### Direction proposed

Add a “Latest Run Command Center” at the top of `/overview`.

Sections:

```txt
Latest Run Hero
Actor Strip: User / Store / Robot
Protocol Health: HTTP / WebSocket
Lifecycle Timeline
Critical Findings
Top Traffic
```

### Files proposed

Backend:

```txt
api/app/overview/service.py
api/app/overview/routes.py
api/app/main.py
```

Frontend:

```txt
web/src/lib/api.ts
web/src/app/(app)/overview/page.tsx
web/src/components/overview/LatestRunCommandCenter.tsx
web/src/components/overview/LatestRunHero.tsx
web/src/components/overview/ActorStrip.tsx
web/src/components/overview/ProtocolHealthBoard.tsx
web/src/components/overview/LifecycleTimeline.tsx
web/src/components/overview/CriticalFindings.tsx
web/src/components/overview/TopTrafficPanel.tsx
web/src/app/globals.css
```

### Code provided

A complete backend and frontend implementation was provided, including:

- Latest-run API endpoint.
- Frontend types.
- Fetcher.
- Overview widgets.
- Styling.

---

## 10. CSS Issue: `.actor-card-meta`

### Problem

The user changed:

```css
grid-template-columns: repeat(4, minmax(0, 1fr));
```

to:

```css
grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
```

but it did not reflect.

### Cause

Two problems:

1. Later media queries overrode `.actor-card-meta`.
2. `minmax(0, 1fr)` is not a useful minimum for `auto-fit`.

### Fix advised

Use a real minimum width:

```css
.latest-run-meta-grid,
.protocol-metrics,
.actor-card-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
```

Then remove `.actor-card-meta` from later media query overrides.

---

## 11. Complete Project Documentation

### User request

Create complete project documentation covering:

- All commands.
- All options.
- All flows.
- Modes.
- Timing.
- Suites/scenarios.
- What each scenario tests.
- Prerequisites.
- Optional flags.
- Examples.
- Meeting-ready explanation.

### What was created

A Markdown file was generated earlier:

```txt
fainzy_simulator_complete_project_documentation.md
```

It covered:

- Executive summary.
- Repo map.
- CLI grammar.
- CLI flags.
- Flow presets.
- Trace suites.
- Trace scenarios.
- Timing profiles.
- Payment model.
- Actor model.
- HTTP coverage.
- WebSocket coverage.
- Docker and deployment.
- GitHub integration.
- Meeting explanation script.

---

## 12. HTTP and WebSocket Safety Review

### User requirement

The simulator must not act blindly.

Rules requested:

```txt
Do not make HTTP requests when required data is missing.
Do not add unavailable or sold-out items to cart.
Do not act on impossible data.
Validate fetched responses before acting.
Every simulation must use WebSockets where applicable.
Every simulation should clearly explain why actions happened or did not happen.
```

### Core issue found

`request_json(...)` records and executes HTTP calls, but it does not know whether an app action should be allowed. The decision must happen before calling `request_json(...)`.

### Desired action categories

```txt
called    = all data exists and request was valid
blocked   = real UI would block the action
skipped   = required data/context missing, so no request made
recovered = something failed safely and simulator recovered
failed    = valid allowed request failed unexpectedly
```

---

## 13. `user_sim.py` Guidance

### Confusion corrected

The user could not find:

```py
cart_items, total = _real_cart_selection(fixtures.menu_items)
```

inside `place_order(...)`.

The correct location was:

```py
def generate_order_payload(fixtures: UserFixtures) -> dict[str, Any]:
    menu_items, total_price = _real_cart_selection(fixtures.menu_items)
```

### Correct change

Update `generate_order_payload(...)`:

```py
def generate_order_payload(
    fixtures: UserFixtures,
    *,
    recorder: RunRecorder | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    menu_items, total_price = _real_cart_selection(
        fixtures.menu_items,
        store=fixtures.store,
        recorder=recorder,
        scenario=scenario,
    )

    return {
        "order_id": _random_order_id(),
        "restaurant": fixtures.store,
        "location": fixtures.location,
        "menu": menu_items,
        "total_price": total_price,
        "status": "pending",
        "user": fixtures.user_id,
    }
```

Then in `place_order(...)`:

```py
payload = generate_order_payload(
    fixtures,
    recorder=recorder,
    scenario=scenario,
)
```

### Purpose

Ensure order creation cannot happen unless menu/store/cart data is valid.

---

## 14. Doctor Simulation False Errors

### User reported

```txt
tap_add_to_cart
error
{'allowed': False, 'blocked_reason': 'store_closed', 'user_message': "This store can't take orders"}
- 3 times
```

```txt
validate_cached_user_token
error
{"detail": "Invalid token."}
- once
```

```txt
probe_pricing
error
{"detail": "Authentication credentials were not provided."}
- once
```

```txt
probe_saved_cards
error
{"status": "error", "message": "No customer ID found !!!"}
- once
```

### Causes

#### `tap_add_to_cart`

Doctor includes negative menu checks:

```txt
menu_unavailable
menu_sold_out
menu_store_closed
```

These are expected UI blocks, not errors.

Correct status:

```txt
blocked_expected
```

#### `validate_cached_user_token`

The simulator tries cached token first. If invalid, it should refresh via OTP and continue.

Correct status:

```txt
recovered
```

#### `probe_pricing`

Pricing was called without product authentication.

Correct behavior:

```txt
skip when product auth is missing
```

#### `probe_saved_cards`

Saved cards were called without customer ID.

Correct behavior:

```txt
skip when no customer ID exists
```

---

## 15. Step 5: `app_probes.py` Fix

### Purpose

Prevent false errors from:

```txt
probe_pricing
probe_saved_cards
coupons
active orders
store dashboard probes
```

### Main changes provided

In:

```txt
app_probes.py
```

Update `pricing` probe to require:

```py
auth_header_name="Fainzy-Token"
auth_scheme=None
```

Add helper functions:

```py
_present(...)
_extract_customer_id(...)
_extract_probe_token(...)
_record_probe_decision(...)
_probe_preflight(...)
```

Replace `run_probe(...)` so it:

1. Checks preflight.
2. Records `skipped` if data/auth is missing.
3. Records `called` if valid.
4. Only then calls `request_json(...)`.

Replace `run_user_app_probes(...)` so it:

1. Calls global config.
2. Calls product auth.
3. Extracts product token.
4. Calls pricing only if product token exists.
5. Calls saved cards only if customer ID exists.
6. Calls coupons only if user token exists.
7. Calls active orders only if user ID and token exist.

### Required call updates

In:

```txt
__main__.py
trace_runner.py
```

add:

```py
user=us.user
```

or:

```py
user=user_session.user
```

to `run_user_app_probes(...)`.

---

## 16. Step 6: `trace_runner.py` Menu Gate Fix

### Purpose

Fix false add-to-cart errors.

### Correct result

For:

```txt
menu_store_closed
menu_sold_out
menu_unavailable
```

the simulator should:

1. Confirm action is blocked.
2. Record `blocked_expected`.
3. Mark scenario as passed.
4. Not create any order/cart mutation.

### Function to replace

```txt
_run_menu_status_probe(...)
```

### Expected result

```txt
menu_store_closed -> tap_add_to_cart blocked_expected, scenario passed
menu_sold_out -> tap_add_to_cart blocked_expected, scenario passed
menu_unavailable -> tap_add_to_cart blocked_expected, scenario passed
menu_available -> tap_add_to_cart allowed, scenario passed
```

---

## 17. Step 7: `websocket_observer.py` Coverage Tracking

### Purpose

Make WebSocket usage visible in all simulations.

### Changes provided

In:

```txt
websocket_observer.py
```

Add coverage object:

```py
self.coverage = {
    "user_orders": {
        "status": "not_started",
        "reason": None,
        "messages": 0,
        "url": self.targets["user_orders"][0],
    },
    "store_orders": {
        "status": "not_started",
        "reason": None,
        "messages": 0,
        "url": self.targets["store_orders"][0],
    },
    "store_stats": {
        "status": "not_started",
        "reason": None,
        "messages": 0,
        "url": self.targets["store_stats"][0],
    },
    "expected_order_events": 0,
    "matched_order_events": 0,
    "missed_order_events": 0,
}
```

Track:

```txt
connecting
connected
failed
messages
expected_order_events
matched_order_events
missed_order_events
```

Add:

```py
def coverage_summary(self) -> dict[str, Any]:
    return self.coverage
```

---

## 18. Step 8: Save WebSocket Coverage

### Purpose

Make coverage visible in run artifacts.

### Files

```txt
reporting.py
trace_runner.py
__main__.py
```

### In `reporting.py`

Add:

```py
self.websocket_coverage = {...}
```

Add:

```py
def set_websocket_coverage(self, coverage: dict[str, Any]) -> None:
    self.websocket_coverage = _json_safe(coverage)
```

Add to `events.json`:

```py
"websocket_coverage": self.websocket_coverage
```

Add report section:

```md
## WebSocket Coverage
```

### In `trace_runner.py`

After stopping observer:

```py
recorder.set_websocket_coverage(observer.coverage_summary())
```

### In `__main__.py`

Start observer in load mode and save coverage in `finally`.

---

## 19. Step 9: “Why This Run Happened” Metadata

### User requirement

Users should see why a run happened:

```txt
Manual launch
Profile launch
Schedule launch
GitHub integration
Replay
```

### Current issue

The run table did not have first-class fields for trigger reason.

### Step 9A provided

In:

```txt
api/app/runs/models.py
```

add to `RunCreateRequest`:

```py
trigger_source: Optional[
    Literal["manual", "profile", "schedule", "github", "replay"]
] = "manual"
trigger_label: Optional[str] = "Manual launch"
trigger_context: Dict[str, Any] = Field(default_factory=dict)
profile_id: Optional[int] = None
schedule_id: Optional[int] = None
integration_trigger_id: Optional[int] = None
launched_by_user_id: Optional[int] = None
```

In:

```txt
api/app/main.py
```

add database columns:

```txt
trigger_source
trigger_label
trigger_context
profile_id
schedule_id
integration_trigger_id
launched_by_user_id
```

Add SQLite and Postgres migrations.

Parse `trigger_context` in row-to-dict helpers.

### Step 9B pending

Populate those fields during:

```txt
manual run creation
profile launch
schedule launch
GitHub integration launch
replay launch
```

This was the next step when the user asked for this review document.

---

## 20. Still Pending

The following items are not fully completed yet:

### 1. Step 9B

Populate trigger metadata when runs are created.

Examples:

```json
{
  "trigger_source": "github",
  "trigger_label": "GitHub workflow_run: dashboard",
  "trigger_context": {
    "project": "dashboard",
    "environment": "production",
    "repository": "Fainzy-Technologies/dashboard",
    "event": "workflow_run",
    "mapped_profile": "simulator"
  }
}
```

```json
{
  "trigger_source": "schedule",
  "trigger_label": "Schedule: Daily Doctor",
  "trigger_context": {
    "schedule_name": "Daily Doctor",
    "profile_name": "simulator",
    "reason": "due_at_slot"
  }
}
```

### 2. UI display for run reason

Likely files:

```txt
web/src/lib/api.ts
web/src/components/runs/detail/RunDetailOverview.tsx
web/src/components/overview/LatestRunCommandCenter.tsx
```

### 3. “Why did this happen?” panel

The UI/report should explain:

```txt
Cached token invalid -> refreshed through OTP
Saved cards skipped -> no customer ID
Pricing skipped -> missing product auth
Add-to-cart blocked -> store closed/sold out/unavailable
WebSocket missed/matched -> with reason
```

### 4. Cached token recovery

`validate_cached_user_token` should be reported as:

```txt
recovered
```

not as an error, if OTP refresh succeeds.

File:

```txt
user_sim.py
```

### 5. True “Plan: none”

Current behavior likely still uses:

```txt
sim_actors.json
```

when no explicit plan is selected. The user wants a real “none” option that uses built-in defaults.

### 6. Event UI grouping

Run events should be grouped as:

```txt
Called HTTP
Blocked by UI
Skipped due to missing data
Recovered auth/session
Failed request
WebSocket
```

---

## 21. Recommended Next Implementation Order

1. Confirm Step 5 compiles.
2. Confirm Step 6 compiles.
3. Confirm Step 7 and Step 8 compile.
4. Run doctor simulation.
5. Check that false errors are now skipped/blocked/recovered.
6. Finish Step 9B.
7. Add UI run-reason display.
8. Add “Why did this happen?” UI/report section.
9. Fix cached token recovery classification.
10. Implement true Plan: none.
11. Test GitHub-triggered run and verify run detail explains why it happened.

---

## 22. Useful Test Commands

Compile key Python files:

```bash
python3 -m compileall app_probes.py trace_runner.py websocket_observer.py reporting.py __main__.py user_sim.py interaction_catalog.py
```

Run doctor:

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

Check production API logs:

```bash
cd /root/simulator
docker compose -f docker-compose.prod.yml logs --tail 200 api
```

Check recent runs:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U simulator -d simulator -c "
select id, flow, plan, timing, mode, status, command, created_at
from runs
order by id desc
limit 10;
"
```

Check integration triggers:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U simulator -d simulator -c "
select id, event_name, project, environment, repository, status, reason, run_id, created_at
from integration_triggers
order by id desc
limit 10;
"
```

---

## 23. Final Summary

The main direction is to make the simulator more realistic, safer, and easier to explain.

The simulator should not blindly call APIs. It should:

```txt
Fetch data
Validate data
Check if the app would allow the action
Only call the API if allowed
Otherwise record skipped / blocked / recovered with a clear reason
```

The simulator should also explain itself:

```txt
Why the run happened
Why a request was skipped
Why a UI action was blocked
Why auth refreshed
Why WebSocket matched or missed
What happened after an error
```

The most important unfinished work is completing run-trigger metadata population and exposing it in the UI.
