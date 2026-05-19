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

## Docs

- Canonical operator guide: [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md)
- Flow-by-flow GUI/CLI docs: [docs/flows/README.md](docs/flows/README.md)
- Architecture reference: [ARCHITECTURE.md](ARCHITECTURE.md)
- Capability matrix (flows/suites/scenarios/flags): [docs/SIMULATOR_CAPABILITIES.md](docs/SIMULATOR_CAPABILITIES.md)
- Run-efficiency playbook: [docs/SIMULATION_TEST_GUIDE.md](docs/SIMULATION_TEST_GUIDE.md)
- GUI testing checklist: [docs/GUI_TESTING.md](docs/GUI_TESTING.md)
