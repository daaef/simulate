# Fainzy Simulator

This repo contains a CLI-driven ordering-flow simulator plus a Dockerized web UI to run simulations, inspect runs, and manage users/roles. It is intended as an operator-focused "daily doctor" for the ordering platform: it simulates user/store/robot behavior, checks HTTP + websocket paths, and writes evidence-rich reports.

## Quick Start (Docker)

```bash
docker compose up -d --build
```

Open:

- Web UI: `http://localhost:8080`
- PostgreSQL (host): `localhost:5433` (container: `postgres:5432`)

## Web UI Auth

Default admin credentials:

- Username: `admin`
- Password: `admin123`

User roles: `admin`, `operator`, `runner`, `viewer`, `auditor`. See `SIMULATOR_GUIDE.md` (section "Web UI Authentication, Admin Account, and Roles") for the full role model, how to change the default admin, create new admins/users, and lockout recovery.

Admins can delete completed runs from the web UI. Deleting a run removes only that run's database row, GUI log file, and owned artifact folder; shared GUI log storage and other runs are preserved. The delete API reports both `deleted_files` and `missing_files`.

## CLI Simulator

Daily recommended run:

```bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
```

See `SIMULATOR_GUIDE.md` for the full command matrix, scenarios, flags, artifacts, and common failure signatures.

## Configuration Model

`.env` is for secrets, auth cache values, credentials, and deployment URLs only. Non-sensitive simulator choices live in JSON run plans such as `sim_actors.json` or GUI-generated plans under `runs/gui-plans/`.

Plan files define users, stores, delivery GPS, runtime defaults, autopilot rules, fixture/menu defaults, payment mode/coupon defaults, and review/new-user defaults. Existing CLI commands still work: explicit CLI flags override plan values, and `.env` is only a fallback for secret/auth/deployment values.

Keep actor and run behavior out of `.env`: do not set `USER_PHONE_NUMBER`, `STORE_ID`, `SIM_RUN_MODE`, `SIM_TRACE_SUITE`, `SIM_TIMING_PROFILE`, `N_USERS`, `SIM_ORDERS`, `ORDER_INTERVAL_SECONDS`, `REJECT_RATE`, `SIM_LAT`, or `SIM_LNG` there for normal use. Put those values in `sim_actors.json` or the selected GUI plan; use `--phone` or `--store` only for one-off overrides.

Admins can edit GUI-owned plans from `Config`. Use the saved plan path, for example `runs/gui-plans/daily-doctor.json`, in the Runs launcher or with `--plan`.

## Repo Map

- `api/`: FastAPI service (auth, run orchestration, admin APIs) used by the web UI.
- `web/`: Next.js frontend for the web UI.
- `infra/`: Nginx config and infra wiring for the Docker stack.
- `runs/`: Generated run artifacts (`events.json`, `report.md`, `story.md`) and web UI runtime storage, including per-run GUI logs under `runs/web-gui/`.
- `tests/`: API/unit tests.

## Docs

- `SIMULATOR_GUIDE.md`: Operator guide (CLI + web UI + auth/roles).
- `ARCHITECTURE.md`: System architecture and component responsibilities.
