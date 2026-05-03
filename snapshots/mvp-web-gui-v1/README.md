# MVP Web GUI Snapshot (v1)

This folder is a frozen snapshot of the initial Dockerized web GUI MVP before the richer dashboard/artifact UX work.

## Included

- `api/` FastAPI MVP backend
- `web/` Next.js MVP frontend
- `infra/` Nginx config
- `docker-compose.yml`
- `.dockerignore`

## Run This Snapshot

From repository root:

```bash
docker compose -f snapshots/mvp-web-gui-v1/docker-compose.yml up --build
```

Then open:

- `http://localhost:8080`
- `http://localhost:8080/healthz`

Note: This compose file still references paths relative to the repository root.

