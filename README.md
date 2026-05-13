# Fainzy Simulator

This repo contains a CLI-driven ordering-flow simulator plus a Dockerized web UI to run simulations, inspect runs, and manage users/roles. It is intended as an operator-focused "daily doctor" for the ordering platform: it simulates user/store/robot behavior, checks HTTP + websocket paths, and writes evidence-rich reports.

## Quick Start (Docker)

```bash
docker compose up -d --build
```

The `web` service runs `next start` (production mode) from the built image. Do not bind-mount `./web` into `/app` for this stack, or the image-built `.next` output will be hidden and the container will fail with `Could not find a production build in the '.next' directory`.

Open:

- Web UI: `http://localhost:8080`
- PostgreSQL (host): `localhost:5433` (container: `postgres:5432`)

## Web UI Auth

Default admin credentials:

- Username: `admin`
- Password: `admin123`

User roles: `admin`, `operator`, `runner`, `viewer`, `auditor`. See `SIMULATOR_GUIDE.md` (section "Web UI Authentication, Admin Account, and Roles") for the full role model, how to change the default admin, create new admins/users, and lockout recovery.

Admins can delete completed runs from the web UI. Deleting a run removes only that run's database row, GUI log file, and owned artifact folder; shared GUI log storage and other runs are preserved. The delete API reports both `deleted_files` and `missing_files`.

## Web UI Operations

The authenticated app shell includes active route highlighting for `Overview`, `Runs`, `Config`, `Schedules`, `Archives`, `Retention`, and `Admin`.

- `Overview`: status cards, run status and success charts, flow distribution, failure trend, archive/purge backlog, schedule health, and alerts.
- `Runs`: launch, cancel, replay, delete completed runs, and inspect top-of-page run statistics, logs, artifacts, event data, and saved run profiles.
  - Runs now show launch attribution (`trigger_source`, `trigger_label`, optional `profile_id`) in list/console/detail views.
  - Start Run now includes a `Save as profile` shortcut under command preview that scrolls/focuses the Saved Profiles name input.
- `Schedules`: creates campaign-first schedules (simple requests are normalized to campaign execution), supports period-specific run slots, all-day mode, blackout skip dates, and next automatic trigger visibility, then supports manual trigger, pause, resume, disable, soft delete, and restore. The page auto-refreshes schedule status/execution state every 15 seconds and on browser focus.
- `Archives`: searchable archive/raw-purge candidate browsing with retained run summaries.
- `Retention`: policy windows, archive/purge queues, retained-summary fields, and purge-safety state.
- `Admin`: manage users under `/admin/users` and configure system policies (including allowed scheduling timezones) under `/admin/system`.

## Schedule Semantics

Preferred schedule contract (for new/edited schedules):

1. `anchor_start_at`: when recurring automation starts.
2. `period`: `daily`, `weekly`, or `monthly`.
3. `repeat`: `none`, `daily`, `weekly`, `monthly`, `annually`, `weekdays`, or `custom`.
4. `stop_rule`: `never`, `end_at`, or `duration`.
5. `all_day`: when `true`, scheduler uses whole-day triggers and ignores slot times.
6. `run_slots`: period-specific slot definitions:
   - daily: `[{ "time": "HH:MM" }]`
   - weekly: `[{ "weekday": "monday", "time": "HH:MM" }]`
   - monthly: mixed `day_of_month` + `weekday_ordinal` slots
7. Optional constraint: `blackout_dates`.

Custom repeat uses `recurrence_config.weekdays` and requires `stop_rule=end_at`.

The scheduler computes period candidates, applies stop rule, applies window/blackout constraints, then emits:

- `next_run_at`
- `next_run_reason`
- `current_period_runs`
- `requested_runs_per_period`
- `feasible_runs_per_period`
- `schedule_warnings`

Legacy cadence/custom fields remain accepted for compatibility with existing schedules that have not been edited.

The `/schedules` form shows pre-submit automation preview (next run, requested vs feasible runs, and warnings). See `SIMULATOR_GUIDE.md` section **Schedule and Campaign APIs** for full details and worked examples.

Recent schedule executions now show lifecycle states (`queued`, `started`, `launched`, `failed`) and link `run_id` directly to run detail pages.

## CLI Simulator

Daily recommended run:

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

See `SIMULATOR_GUIDE.md` for the full command matrix, scenarios, flags, artifacts, and common failure signatures.

## Configuration Model

`.env` is for secrets, auth cache values, credentials, and deployment URLs only. Non-sensitive simulator choices live in JSON run plans such as `sim_actors.json` or GUI-generated plans under `runs/gui-plans/`.

Plan files define users, stores, delivery GPS, runtime defaults, autopilot rules, fixture/menu defaults, payment mode/coupon defaults, and review/new-user defaults. Existing CLI commands still work: explicit CLI flags override plan values, and `.env` is only a fallback for secret/auth/deployment values.

Store and user scope for execution is now strict to the selected plan:
- Load and trace runs only use stores defined in plan `stores[]`.
- Run phones must exist in plan `users[]`.
- Explicit `--store` / `--phone` values outside plan scope fail fast with a validation error.

Keep actor and run behavior out of `.env`: do not set `USER_PHONE_NUMBER`, `STORE_ID`, `SIM_RUN_MODE`, `SIM_TRACE_SUITE`, `SIM_TIMING_PROFILE`, `N_USERS`, `SIM_ORDERS`, `ORDER_INTERVAL_SECONDS`, `REJECT_RATE`, `SIM_LAT`, or `SIM_LNG` there for normal use. Put those values in `sim_actors.json` or the selected GUI plan; use `--phone` or `--store` only for one-off overrides.

Admins can edit GUI-owned plans from `Config`. Use the saved plan path, for example `runs/gui-plans/daily-doctor.json`, in the Runs launcher or with `--plan`.

## Repo Map

- `api/`: FastAPI service (auth, run orchestration, schedules, alerts, archive/retention, admin APIs) used by the web UI.
- `web/`: Next.js frontend for the web UI.
- `infra/`: Nginx config and infra wiring for the Docker stack.
- `runs/`: Generated run artifacts (`events.json`, `report.md`, `story.md`) and web UI runtime storage, including per-run GUI logs under `runs/web-gui/`.
- `tests/`: API/unit tests.

## Docs

- `SIMULATOR_GUIDE.md`: Operator guide (CLI + web UI + auth/roles).
- `ARCHITECTURE.md`: System architecture and component responsibilities.
- `docs/deployment.md`: Production deployment runbook (SSH + GitHub Actions + Docker Compose).

## Production Deployment

Production deployment is handled by a portable SSH workflow in `.github/workflows/deploy.yml`.

- Triggered on push to `main` and manually via `workflow_dispatch`.
- Deploys only the simulator stack (`nginx`, `web`, `api`, `postgres`) using `docker-compose.prod.yml`.
- Preserves state with named Docker volumes for Postgres data, run artifacts, and GUI plans.
- Requires host-managed `.env.prod`; workflow fails if `.env.prod` is missing.
- Uses `git@github.com:daaef/simulate.git` and defaults deployment path to `/root/simulate`.
- Defaults to `http://127.0.0.1:8090` via `SIMULATOR_HOST_BIND=127.0.0.1` and `SIMULATOR_HOST_PORT=8090`; set `0.0.0.0` only when intentionally exposing publicly.
- Supports cross-repository GitHub `deployment_status` webhooks at `POST /api/v1/integrations/github/deployment-complete`, with HMAC verification, `(project, environment)` profile mapping, idempotent trigger records, async profile launch, and deployment-status callback to GitHub (`simulator/verification` context).

See `docs/deployment.md` for first-time VPS setup, cross-project GitHub Actions trigger integration, verification, troubleshooting, and security hardening.
