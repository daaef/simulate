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

## Failure Policy Defaults

- Default run-failure policy is API-focused: `SIM_FAILURE_POLICY=api_only`.
- Default preflight behavior is recovery-first: `SIM_PREFLIGHT_STRATEGY=auto_recover`.
- Plan rules can override both per run profile: `rules.failure_policy` and `rules.preflight_strategy`.
- Under `api_only`, precondition misses (coupon unavailable, already-setup new-user phone, GPS fallback) downgrade to **degraded/unsupported** with exit code `0`. Transport/timeouts/HTTP 5xx still hard-fail (exit `1`). See [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md#flow-reliability-and-named-flow-regression).

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
- GitHub webhook projects (generate signing secrets in **Config → Integration**): [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md#production-deployment-operations)
