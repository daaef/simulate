# Fainzy Simulator Standup Sheet (Engineering)

Date: Thursday, May 14, 2026  
Reference date for "yesterday": Tuesday, May 13, 2026

## A) Yesterday's Changes (May 13, 2026)

- SMTP and email notification capability was implemented across API, UI config, docs, and deployment wiring.
- New system email endpoints and UI controls were added for non-secret notification settings and test sends.
- Observability contract was sharpened to shared `Up/Degraded/Down` semantics and explicit `/healthz` scope.
- Run/overview observability was improved with stronger critical finding presentation and launch context attribution.
- Websocket observer + order status handling was improved for better progression/tracing fidelity.
- Trace runner and user simulation coverage/profile handling were expanded for stronger validation evidence.

Commit anchors:
- `36cd65e`, `0e593a2`, `61bada2`, `9b85f72`, `768883f`

## B) Ground-Up Architecture Map

- Layer 1: Simulation runtime engine (CLI)
  - `__main__.py` orchestrates runs.
  - Actor simulators (`user_sim.py`, `store_sim.py`, `robot_sim.py`) execute real flow transitions.
  - `trace_runner.py` provides deterministic scenario proofs.
  - `websocket_observer.py` validates passive status stream evidence.
- Layer 2: API control plane (FastAPI)
  - Launches/manages runs, exposes flows, schedules, retention, archives, alerts, admin/system settings.
  - Persists run metadata and trigger attribution context.
- Layer 3: Operator UX (Next.js)
  - Operations pages: Overview, Runs, Config, Schedules, Archives, Retention, Admin.
  - Separates control-plane health from process/run outcome semantics.
- Layer 4: Data and artifacts
  - PostgreSQL for control-plane state.
  - `runs/` filesystem for artifacts and GUI plan files.
- Layer 5: Deployment topology
  - Docker compose local/prod, SSH-based GitHub Actions deployment, volume-backed persistence.

## C) Runtime + Failure-Path Cheat Sheet

Runtime flow:
1. Operator selects plan and flow/mode.
2. API launches simulation run with resolved config precedence.
3. Simulators execute HTTP + websocket-driven actions.
4. Artifacts (`events.json`, `report.md`, `story.md`) are generated.
5. UI/alerts/email reflect outcome and severity.

Signal interpretation:
- `/healthz` failing: simulator/control-plane stack issue.
- `/healthz` healthy + doctor/trace failing: product-path/process failure.
- websocket `wss://lastmile...` 502: likely upstream last-mile gateway/proxy fault.

Gate/strictness trade-offs:
- websocket gate enforcement off (default): records warnings, allows continuity.
- websocket gate enforcement on: fail-fast when required status events are missing.
- strict plan mode: invalid plan becomes hard failure by design.

## D) Ops/Deploy Quick Commands + Operational Signals

Quick commands:
- Local stack: `docker compose up -d --build`
- Daily proof run: `python3 -m simulate doctor --plan sim_actors.json --timing fast`
- Websocket boundary check: `scripts/check_lastmile_ws.sh https://lastmile.fainzy.tech <user_id> <store_subentity_id>`

Deployment model:
- Production deploy via `.github/workflows/deploy.yml` over SSH.
- Uses `docker-compose.prod.yml` + host `.env.prod`.
- SMTP vars must be present in runtime env and API container recreated after changes.

What to watch in standup follow-up:
- Repeated failed runs by scenario/flow.
- Schedule warnings and launch failures.
- Retention/archive backlog growth.
- Websocket gateway failure clusters indicating upstream dependency instability.
