# Simulation Test Guide (Operator Efficiency)

Purpose: help you choose the **right simulation run quickly**, configure it correctly, and interpret results without wasting cycles.

Scope: active runtime only (`python3 -m simulate`, FastAPI, web UI launcher). Excludes `snapshots/`.

Primary source-of-truth docs you should keep open while using this guide:
- `docs/SIMULATOR_CAPABILITIES.md` (exhaustive catalog)
- `SIMULATOR_GUIDE.md` (operator + UI procedures)
- `ARCHITECTURE.md` (component responsibilities)

---

## 1) Fast run selection (what to run first)

Use this decision ladder in order:

1. Need end-to-end daily health proof: run `doctor`.
2. Need a targeted regression check: run `trace` with a narrow suite or explicit scenarios.
3. Need stress/concurrency behavior: run `load`.

Recommended operator defaults:
- plan: `sim_actors.json` (or one approved GUI plan)
- timing: `fast`
- mode overrides: avoid unless required
- websocket gates: off by default; turn on only when you need strict realtime enforcement

---

## 2) Configuration precedence (critical to avoid confusion)

Effective config resolution is:

1. explicit CLI flags
2. selected plan JSON (`--plan`)
3. `.env`
4. built-in defaults

Practical implication:
- If a run behaves unexpectedly, check whether a CLI override is masking plan defaults.
- If plan load/validation fails, runtime can fall back to repo `sim_actors.json`; this changes behavior if you expected a GUI/custom plan.

---

## 3) Canonical command forms

### 3.1 Daily health (recommended baseline)

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

What it does:
- resolves to `mode=trace`, `suite=doctor`
- runs app bootstrap + store setup/dashboard + menu gates + paid path + store accept/reject + robot complete + receipt/review/reorder

### 3.2 Targeted trace (specific scenarios)

```bash
python3 -m simulate --mode trace --scenario completed --scenario store_reject --plan sim_actors.json --timing fast
```

What it does:
- bypasses flow preset suite selection
- executes only listed scenarios in declaration order (deduped)

### 3.3 Bounded load smoke (strict baseline then tail pressure)

```bash
python3 -m simulate load --plan sim_actors.json --users 2 --orders 3 --interval 2 --reject 0.35 \
  --bounded-load-smoke-policy \
  --bounded-baseline-min-completed 1 \
  --bounded-baseline-max-attempts 3 \
  --bounded-tail-reject-rate 0.35 \
  --bounded-tail-cancel-rate 0.15
```

What it does:
- forces at least one accepted/completed baseline before applying reject/cancel tail pressure
- fails with `accepted_baseline_not_met` if baseline cannot be achieved within bound

### 3.4 Named-flow reliability matrix (`api_only`)

Runs all 12 preset flows sequentially and writes a pass/fail summary (requires live LastMile/Fainzy + valid `sim_actors.json`):

```bash
export PYTHONPATH=.
export SIM_FAILURE_POLICY=api_only
export SIM_PREFLIGHT_STRATEGY=auto_recover
./scripts/run_named_flow_regression.sh
```

Interpret results:
- **Exit `0` + verdict `degraded`:** precondition downgrade only (for example new-user phone already registered) — OK under `api_only`.
- **Exit `1`:** uncaught `RuntimeError`, usually API fault (5xx/timeout); inspect `runs/<stamp>/events.json` and console.
- **Policy unit tests** (no network): `python3 -m unittest tests.test_simulate.FlowReliabilityPolicyTests -v`

---

## 4) Modes, flows, suites, scenarios

## 4.1 Modes

- `trace`: deterministic scenario execution and assertions
- `load`: concurrent multi-actor traffic with worker knobs

Hard constraints:
- `--continuous` only valid in load mode
- `suite/scenarios` only valid in trace mode
- `users/orders/interval/reject` only valid in load mode

## 4.2 Flows (preset names)

Preset flow names and their intent:

- `doctor`: default daily health sweep
- `full`: broad weekly-style deep suite
- `audit`: broad trace audit with setup/probes/payment/robot/post-order coverage
- `core` equivalent is via `--mode trace --suite core` (flow key is not named `core`)
- `payments`: payment branch coverage
- `menus`: menu-state coverage
- `new-user`: onboarding path
- `paid-no-coupon`, `paid-coupon`, `free-coupon`: focused payment variants
- `store-setup`, `store-dashboard`, `store-accept`, `store-reject`: store-focused paths
- `robot-complete`: robot lifecycle completion path
- `receipt-review`: post-order actions path
- `load`: concurrent load mode

Aliases are supported (e.g. `daily` -> `doctor`, `paid` -> `paid-no-coupon`, `robot` -> `robot-complete`).

## 4.3 Trace suites (ordered expansion)

- `core`: `completed`, `rejected`, `cancelled`
- `payments`: `returning_paid_no_coupon`, `returning_paid_with_coupon`, `returning_free_with_coupon`
- `menus`: `menu_available`, `menu_unavailable`, `menu_sold_out`, `menu_store_closed`
- `store`: `store_first_setup`, `store_accept`, `store_reject`
- `doctor`: operational health sequence
- `audit`: broader than doctor (includes new-user + coupon branches)
- `full`: broadest standard suite

## 4.4 Scenario encyclopedia (how to choose each)

### Order lifecycle core
- `completed`: full happy path through robot completion.
- `rejected`: store rejects before payment completion.
- `cancelled`: user cancels pending order.
- `auto_cancel`: backend timeout cancellation diagnostic.

Use when:
- You are validating state machine progression and terminal statuses.

### Payment branch scenarios
- `returning_paid_no_coupon`: standard Stripe paid path.
- `returning_paid_with_coupon`: Stripe with discount coupon branch.
- `returning_free_with_coupon`: coupon reduces payable to zero; free-order branch.

Use when:
- You suspect payment path regressions, coupon routing, or free-order conditional logic.

### Menu gate scenarios
- `menu_available`, `menu_unavailable`, `menu_sold_out`, `menu_store_closed`.

Use when:
- User-facing orderability gates look wrong in app behavior.

### Store and robot operational scenarios
- `store_first_setup`: setup/profile/menu readiness provisioning path.
- `store_accept`: acceptance branch proof.
- `store_reject`: rejection branch proof.
- `robot_complete`: robot lifecycle progression to completed.

Use when:
- Store-side or robot progression behavior is suspect.

### Probe and post-order scenarios
- `app_bootstrap`: app probes (config, cards, coupons, active orders, etc.).
- `store_dashboard`: dashboard probes (orders/stats/top customers).
- `receipt_review_reorder`: completed path plus receipt/review/reorder checks.

Use when:
- You need non-core API readiness checks or post-order action verification.

**Saved-cards probe triage (`GET /v1/core/cards/`):**
- Compare the probe decision in `report.md` to session walkthroughs: empty list shape in `app-20260428.full-session-user.md` / `app-20260430.full-session-user.md`; non-empty Stripe list shape in `app-20260517.full-session-user.md`.
- HTTP 4xx/5xx or transport errors → probe **failed** (API/system issue).
- HTTP 200 with `data.data: []` or missing/invalid envelope → **inconclusive** with sanitized `raw_payload` in decision details (valid “no cards on file”, not a simulator failure).
- HTTP 200 with non-empty `data.data` → shape-checked against 20260517; mismatch → **failed**.

---

## 5) Full flag guide (operator effect + pitfalls)

## 5.1 Universal/trace-oriented flags

- `--plan <path>`
  - selects plan file
  - pitfall: invalid selected plan may fall back to default plan

- `--timing fast|realistic`
  - controls deterministic delay profile
  - pitfall: `realistic` increases runtime significantly

- `--mode trace|load`
  - explicit mode override
  - pitfall: conflicting mode-specific flags produce hard validation errors

- `--suite <name>`
  - trace suite selector
  - pitfall: ignored/invalid in load mode

- `--scenario <name>` (repeatable)
  - trace explicit scenario list
  - pitfall: unsupported scenario string fails run creation/validation

- `--store <store_id>`
  - store pinning
  - pitfall: must exist in selected plan `stores[]`

- `--phone <phone>`
  - user pinning
  - pitfall: must exist in selected plan `users[]`

- `--all-users`
  - expands to all plan users for load and relevant trace behavior
  - pitfall: increases runtime/data volume and concurrent side-effects

- `--strict-plan`
  - strict plan validation enforcement
  - pitfall: missing required plan fields becomes immediate failure

- `--skip-app-probes`
  - disables app probe section
  - pitfall: reduces diagnostic coverage

- `--skip-store-dashboard-probes`
  - disables store dashboard probes
  - pitfall: loses visibility into dashboard path regressions

- `--post-order-actions`
  - enables receipt/review/reorder checks
  - pitfall: adds runtime and dependencies on completed-order state

- `--enforce-websocket-gates`
  - strict websocket status gating
  - pitfall: can fail runs in partially degraded realtime environments

- `--no-enforce-websocket-gates`
  - explicitly disable strict gating
  - pitfall: allows continuation with warnings; less strict for uptime judgments

- `--no-auto-provision`
  - disables simulator auto-repair/provision behavior
  - pitfall: useful for “pure environment readiness” checks, but increases fail-fast due to missing fixtures

## 5.2 Load-specific flags

- `--users <int>=1+`
  - concurrent user workers

- `--orders <int>=1+`
  - total bounded orders

- `--interval <seconds>`
  - inter-order pacing

- `--reject <0..1>`
  - probabilistic rejection pressure

- `--continuous`
  - unbounded run until cancel
  - pitfall: not valid in trace mode

## 5.3 Bounded load policy flags

- `--bounded-load-smoke-policy`
- `--bounded-baseline-min-completed <int>`
- `--bounded-baseline-max-attempts <int>`
- `--bounded-tail-reject-rate <float>`
- `--bounded-tail-cancel-rate <float>`

Use when:
- you want stable smoke confidence that accepted baseline is actually possible before adding pressure

---

## 6) Valid and invalid option combinations

Valid examples:
- `doctor + --timing fast`
- `--mode trace --suite core`
- `--mode trace --scenario completed --scenario store_reject`
- `load + --users/--orders/--interval/--reject`

Invalid examples:
- `--mode trace --continuous`
- `--mode load --suite doctor`
- `--mode load --scenario completed`
- `--mode trace --users 5`
- `--reject 1.2`

---

## 7) Efficient run playbooks

## 7.1 Daily operations playbook

1. Run `doctor` fast.
2. If failed, open run detail and inspect:
   - Overview findings
   - Traffic tab (HTTP/event evidence)
   - Console logs
3. If failure is websocket gate-related and gates were enforced, rerun once with gates off to classify hard failure vs realtime-warning mode.
4. Escalate based on repeated failure signature.

## 7.2 Regression isolation playbook

1. Start with a narrow suite (`core` or specific scenarios).
2. Expand only if narrow run passes but incident persists.
3. Keep timing fast and probes enabled unless they are irrelevant to the regression.

## 7.3 Payment incident playbook

1. Run `payments` suite.
2. If coupon-related, verify coupon branch with both paid and free coupon scenarios.
3. If only Stripe fails, validate `STRIPE_SECRET_KEY` and payment mode/case alignment.

## 7.4 Load confidence playbook

1. Run bounded-load smoke policy first.
2. If baseline passes, run larger bounded load.
3. Use continuous mode only after bounded runs are stable.

---

## 8) Artifacts and how to read them quickly

Every run writes:
- `events.json`: source-of-truth ledger
- `report.md`: proof-oriented technical summary
- `story.md`: narrative summary

Fastest triage route:
1. `report.md` scenario verdicts + findings
2. run detail Overview findings split (critical vs operational) — each row should show API route, flow/step, and preceding steps when `related_event_id` is present
3. `events.json` for exact action/endpoint/status evidence (Traffic tab marks HTTP 4xx/5xx rows as errors)
4. For `receipt_review_reorder`: confirm second order events (`reorder_cart_built`, `reorder_place_order`, second lifecycle) after Phase 24 reorder fetch

---

## 9) `unsupported_profile_fetch_contract` explained

What it means:
- During cached-token bootstrap, simulator intentionally skips legacy cached-user profile hydration endpoint/method because backend contract is incompatible for that path.

How it is recorded:
- decision event in `user_sim.bootstrap_auth` with:
  - `action=hydrate_cached_user_profile`
  - `status=skipped`
  - `reason_code=unsupported_profile_fetch_contract`

How it is classified:
- [decision_reasons.py](../decision_reasons.py) marks it informational for skipped/recovered statuses.
- [api/app/overview/service.py](../api/app/overview/service.py) excludes informational decisions from failure counts/critical findings.
- [reporting.py](../reporting.py) renders it as informational context in decision sections.

Operational implication:
- treat this as expected compatibility context, not a backend outage signal.

---

## 10) Web UI launcher parity (how GUI maps to CLI)

Runs page `Start Run` builds the same logical request as CLI:
- Flow, plan, timing, mode override, suite, scenarios
- identity pinning (`store_id`, `phone`)
- strict/probe/provision/websocket/post-order toggles
- load knobs (`users`, `orders`, `interval`, `reject`, `continuous`)

Backend serializes request into exact CLI argv using API `_build_command`.

Important distinction:
- Live capability truth comes from `/api/v1/flows`.
- Flow planner guide tables in UI are static guidance content.

**Live Console on `/runs`:** Log tail polling is tied to the selected run id, not the 5s runs-table refresh, so the console should not blank or reset while the table updates. During active runs, new log lines append in place and auto-scroll only when you are already at the bottom.

### 10.1 Execution Impact panel (how to use it)

Runs -> Start Run now includes an **Execution Impact** panel under command preview.

- Default: concise “what will happen” summary.
- Expand details: scenario order, mode mechanics, gate/probe behavior, prerequisites, artifacts, and likely failure signatures.
- Blocking warnings align with launcher validation and must be fixed before launch.

### 10.2 Field example placeholders (quick-fill reference)

Use these as reference values when filling the launcher:

| Field | Example |
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
| Orders | `50` |
| Interval | `3` |
| Reject rate | `0.10` |
| Continuous | enable only for soak runs |
| All users | enable to fan out across all plan users |
| Strict plan | enable for strict plan validation |
| Skip app probes | enable only when bootstrap probe coverage is intentionally out of scope |
| Skip store dashboard probes | enable only when store dashboard checks are intentionally out of scope |
| No auto provision | enable for pure readiness checks without simulator setup/menu repair |
| Post-order actions | enable when receipt/review/reorder checks are required |
| Enforce websocket gates | enable when missing required realtime events should hard-fail |

---

## 11) Trace Overlap Map (what is redundant vs targeted)

Use this map to avoid running redundant trace flows when your goal is fast signal:

- Broad suites:
  - `full`: most complete deterministic suite; preferred broad verification entrypoint.
  - `doctor`: daily broad subset for faster routine checks.
  - `payments`: focused broad payment-branch suite.
  - `menus`: focused broad menu-gate suite.
- Overlap to be aware of:
  - `audit` and `full` are both broad, high-overlap suites; `full` is usually the clearer default.
  - Single-scenario flows (`paid-no-coupon`, `paid-coupon`, `free-coupon`) are targeted slices of `payments`/`full`.
  - `store-accept` and `robot-complete` are targeted slices already exercised in `doctor`/`full`.
- Recommended selection order:
  - Start with a broad suite (`doctor` for routine, `full` for deep verification).
  - Use targeted single-scenario flows only to reproduce or isolate a known failing branch.

---

## 12) Catalog profiles and when to use each

Catalog-seeded run profiles (API startup):
- `daily-doctor`: standard daily trace health check
- `gates-on-doctor`: same coverage with strict websocket gates
- `core-trace`: compact lifecycle proof
- `bounded-load-smoke`: baseline-then-tail load confidence
- `menu-gates`: menu-state coverage
- `weekly-full`: broad deep trace

Use these as stable operational entry points; clone/customize only when team-specific requirements diverge.

---

## 13) Minimal “best practice” defaults for efficient runs

- Start with `doctor --timing fast`.
- Keep probes enabled by default.
- Keep websocket gates off for routine monitoring; enable for strict realtime validation windows.
- Use explicit scenario chains for debugging, not for daily monitoring.
- Use bounded load before continuous load.
- Treat plan files as the canonical behavior definition; use CLI overrides sparingly.

---

## 14) Cross-reference map (where to go for depth)

- exhaustive flow/suite/scenario/flag/env/api matrices:
  - [docs/SIMULATOR_CAPABILITIES.md](./SIMULATOR_CAPABILITIES.md)
- full operator/web UI semantics:
  - [../SIMULATOR_GUIDE.md](../SIMULATOR_GUIDE.md)
- architecture and component ownership:
  - [../ARCHITECTURE.md](../ARCHITECTURE.md)
- bounded load policy deep-dive:
  - [./BOUNDED_LOAD_SMOKE_FIX_EXPLAINER.md](./BOUNDED_LOAD_SMOKE_FIX_EXPLAINER.md)
