# Fainzy Simulator

CLI + web UI for running simulator flows, inspecting runs, and operating daily health checks.

## Quickstart (Docker)

```bash
docker compose up -d --build
```

Open:

- Web UI: `http://localhost:8080`
- PostgreSQL (host): `localhost:5433`

Default web admin credentials:

- Username: `admin`
- Password: `admin123`

## Quickstart (CLI)

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

## Launch precedence

- Explicit CLI flags (`--mode`, `--suite`, repeated `--scenario`) override flow preset defaults.
- In trace mode, `--suite` and repeated `--scenario` can be combined: suite scenarios resolve first, then explicit scenarios are appended (deduped in order).
- By default, each run randomly selects phone and store from the selected plan (`users[]`, `stores[]`). Use `--phone`/`--store` for explicit selection, or disable random defaults with `--no-random-phone` and `--no-random-store`.
- In the web launcher, successful manual starts reset Store/Phone to `Plan default` and clear random-disable flags for the next run.

## Failure Policy Defaults

- Default run-failure policy is API-focused: `SIM_FAILURE_POLICY=api_only`.
- Default preflight behavior is recovery-first: `SIM_PREFLIGHT_STRATEGY=auto_recover`.
- HTTP timeout enforcement is opt-in: `SIM_TIMEOUT_FAILS=false` by default.
- Plan rules can override both per run profile: `rules.failure_policy` and `rules.preflight_strategy`.
- Under `api_only`, precondition misses (coupon unavailable, already-setup new-user phone, GPS fallback) downgrade to **degraded/unsupported** with exit code `0`. Transport/timeouts/HTTP 5xx still hard-fail (exit `1`). See [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md#flow-reliability-and-named-flow-regression).
- `SIM_TIMEOUT_FAILS=true` (or `--timeout-fails`) applies request timeout protection and fails the run on timeout; when off, requests wait indefinitely for endpoint responses.
- `SIM_ENFORCE_WEBSOCKET_GATES=true` now requires websocket startup readiness (`user_orders`, `store_orders`, `store_stats`) and fails the run if required channels drop beyond the retry window.
- Universal order contract (always on): every created order must end in `completed`, `rejected`, or `cancelled` before run success, except the explicit `place-order` trace flow, which intentionally leaves websocket-proven pending orders for manual store-app inspection.
- End-of-run lifecycle cleanup is automatic: non-terminal orders get settle + cleanup attempts (`cancel`, then `reject` fallback). Any remaining non-terminal order forces run `failed` (non-zero exit).
- Websocket lifecycle proof is required for order-producing runs: missing/late lifecycle evidence now fails the run even when gate enforcement is not explicitly enabled.

## Flow reliability regression (local CLI)

From the repo root (requires valid `.env` and `sim_actors.json`):

```bash
export PYTHONPATH=.
export SIM_FAILURE_POLICY=api_only
export SIM_PREFLIGHT_STRATEGY=auto_recover
./scripts/run_named_flow_regression.sh
```

Writes `runs/flow-reliability-<date>.json` and `.md` with per-flow exit code, health verdict, and `failure_class` counts. Unit tests (no live API):

```bash
python3 -m unittest tests.test_simulate.FlowReliabilityPolicyTests -v
```

## Run reporting (web UI)

On **Runs → {id} → Overview**, **Failed Events** uses the same failure rules as `GET /api/v1/runs/{id}/metrics`. **Critical Findings** shows server/API/websocket availability failures; **Operational Findings** shows other failed ledger events and non-critical artifact issues (not order-rejection or payment-failure action counts—those are separate KPIs). See [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md) for details.
Run artifact paths (`report.md`, `story.md`, `events.json`) are hydrated from run logs, including long wrapped path lines from launcher console output.

On **Overview**, **Attention Queue** and **Alerts** rows now include explicit date/time stamps for easier triage ordering.

Run ownership/liveness is now persisted (`process_pid`, launcher instance, heartbeat, ownership state). The API reconciler uses detached-process recovery before failing runs; unresolved infra loss is reported as `detached_process_dead_no_terminal_evidence` instead of generic orphan wording.

Scheduled launches now serialize identical active schedule/profile/command combinations. Overlap skips are recorded in schedule execution history with status `overlap_skipped`.

## Orders page (web UI)

The authenticated **Orders** page (`/orders`) is an isolated operator tool for live order lookup and status updates. It reads store choices from `sim_actors.json`, signs into the selected store through the simulator API using the existing Fainzy store-login contract, and keeps the LastMile product-auth `Fainzy-Token` in browser `localStorage` for later lookups. It does not require new environment variables.

Lookup accepts a database order id or an order reference such as `#156382`; numeric input falls back to `#<number>` if no DB-id match is found. Both Orders tabs show a read-only raw order JSON pane after lookup. `Order Summary` keeps the summary workflow, while `Update Status` is a direct status-change flow showing only item names, total price, the lifecycle status selector, and `Update Status`. Updates submit through `PATCH /v1/core/orders/?order_id=<id>` with the LastMile `Fainzy-Token`.

## Archive-First Delete/Restore

- Deleting a run now archives it (`archived_at` set) instead of removing DB row/artifacts.
- Deleted run reports/stories/events remain attached to archived runs and are restorable.
- Deleting a run profile now archives it (`status=archived`) instead of hard-deleting it.
- Deleting a schedule remains soft-delete (`status=deleted`) and is restorable.
- Deleting a GitHub integration mapping now archives it (`status=archived`) instead of hard-deleting it.
- Archived runs, profiles, schedules, and integration mappings can be restored from **Archives**.
- Archived/deleted records must be restored before editing.
- `operator` and `admin` can delete/restore profiles and schedules.

## Docs

- Canonical operator guide: [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md)
- Flow-by-flow GUI/CLI docs: [docs/flows/README.md](docs/flows/README.md)
- Architecture reference: [ARCHITECTURE.md](ARCHITECTURE.md)
- Capability matrix (flows/suites/scenarios/flags): [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md)
- Run-efficiency playbook: [docs/SIMULATION_TEST_GUIDE.md](docs/SIMULATION_TEST_GUIDE.md)
- GUI testing checklist: [docs/GUI_TESTING.md](docs/GUI_TESTING.md)
- GUI presentation / personal demo checklist: [docs/GUI_PERSONAL_DEMO_CHECKLIST.md](docs/GUI_PERSONAL_DEMO_CHECKLIST.md)
- GitHub webhook projects (file-backed config + auto-sync to GitHub secrets in **Config → Integration**): [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md#production-deployment-operations)
