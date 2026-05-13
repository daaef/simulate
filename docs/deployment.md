# Simulator Deployment (Portable SSH + GitHub Actions)

This deployment flow is for the Simulator service in this repository only (`nginx`, `web`, `api`, `postgres`).

Deployment workflow handles only this simulator stack. Cross-project simulation automation is provided by GitHub webhooks delivered to this simulator API after upstream deployments complete.

## 1) First-Time Host Setup

1. Provision a Linux VPS (including Contabo or any provider) and open SSH access.
2. Install required packages:
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl git
   ```
3. Install Docker Engine and Docker Compose plugin (official Docker docs).
4. Create a deployment user and grant Docker access:
   ```bash
   sudo usermod -aG docker <deploy-user>
   ```
5. Create deploy directory:
   ```bash
   sudo mkdir -p /root/simulate
   sudo chown -R <deploy-user>:<deploy-user> /root/simulate
   ```
6. Harden SSH (`PasswordAuthentication no`, key auth only) and restrict firewall ports.

## 2) SSH Key and GitHub Access Setup

Two keys are required:

1. **GitHub Actions -> VPS SSH key** (for `appleboy/ssh-action`).
2. **VPS -> GitHub deploy key** (for `git clone/fetch` on the VPS).

Recommended VPS deploy key setup:

```bash
sudo -u <deploy-user> ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Add the public key as a deploy key (read-only is enough) on this repository.

## 3) GitHub Secrets Setup

Set repository secrets:

- `SIMULATOR_DEPLOY_HOST` (required)
- `SIMULATOR_DEPLOY_USERNAME` (required)
- `SIMULATOR_DEPLOY_SSH_KEY` (required, private key for Actions to SSH into VPS)
- `SIMULATOR_DEPLOY_PORT` (optional, defaults to `22`)
- `SIMULATOR_DEPLOY_PATH` (optional, defaults to `/root/simulate`)
- `SMTP_PASSWORD` (required when email notifications are enabled)

Set repository variables:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_TLS_MODE` (`starttls` or `ssl`)

## 4) .env.prod Setup (On Host)

1. Copy the template after first clone or by local upload:
   ```bash
   cp .env.prod.example .env.prod
   ```
2. Set real values for at least:
   - `POSTGRES_PASSWORD`
   - `DATABASE_URL` (must match `POSTGRES_PASSWORD`)
   - `JWT_SECRET_KEY`
   - `WEB_CORS_ORIGINS`
3. Keep safe binding by default:
   - `SIMULATOR_HOST_BIND=127.0.0.1`
   - `SIMULATOR_HOST_PORT=8090`
4. Do not commit `.env.prod`.

5. Configure GitHub webhook integration env values:
   - `SIMULATOR_EXTERNAL_BASE_URL` (public HTTPS base URL, for example `https://simulator.example.com`)
   - `GITHUB_WEBHOOK_PROJECT_SECRETS` JSON map:
     ```json
     {"backend":"<secret>","mobile":"<secret>","store":"<secret>","robot":"<secret>"}
     ```
   - `GITHUB_WEBHOOK_REPO_ALLOWLIST` JSON map:
     ```json
     {
       "backend":["org/backend-repo"],
       "mobile":["org/mobile-repo"],
       "store":["org/store-repo"],
       "robot":["org/robot-repo"]
     }
     ```
   - `GITHUB_STATUS_TOKEN` (GitHub token with deployment status write permissions)
   - Optional: `GITHUB_STATUS_API_BASE`, `GITHUB_STATUS_CONTEXT`

## 5) Production Compose Behavior

`docker-compose.prod.yml` is production-only and does not use dev bind mounts.

- `postgres`: internal only, no public host port.
- `api`: single Uvicorn worker to avoid multi-process in-memory run-state conflicts.
- `web`: built and served with `next build` + `next start`.
- `nginx`: published host binding controlled by `SIMULATOR_HOST_BIND` and `SIMULATOR_HOST_PORT`.
- Persistent named volumes:
  - `simulator_postgres_data`
  - `simulator_runs_data`
  - `simulator_gui_plans_data`

These volumes preserve DB records, run artifacts, and GUI plans across redeploys.

## 6) Deployment Workflow

Workflow file: `.github/workflows/deploy.yml`

Triggers:

- push to `main`
- manual `workflow_dispatch`

Remote deploy script behavior:

1. Verifies `docker` and `docker compose` are installed.
2. Clones repo if missing.
3. Force-syncs to latest `origin/main`:
   ```bash
   git fetch origin main
   git checkout main
   git reset --hard origin/main
   ```
4. Fails clearly if `.env.prod` is missing.
5. Runs:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod build
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans
   ```
6. Polls `http://127.0.0.1:${SIMULATOR_HOST_PORT}/healthz` and fails workflow if unhealthy.

## 7) Redeploy

Redeploy happens automatically on every push to `main`, or manually via Actions “Run workflow”.

Manual equivalent on host:

```bash
cd /root/simulate
git fetch origin main
git checkout main
git reset --hard origin/main
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans
```

## 8) Health Check, Logs, and Troubleshooting

Health endpoint:

```bash
curl -fsS http://127.0.0.1:8090/healthz
```

Container status:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
```

Logs:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 200 api
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 200 web
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 200 nginx
```

SMTP note:
1. Deploy workflow writes SMTP values from GitHub variables/secrets into host `.env`.
2. Recreate `api` after SMTP env changes:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate api
   ```

If health fails:

1. Confirm `.env.prod` values (DB URL/password consistency).
2. Confirm host firewall and bind settings.
3. Confirm Docker daemon is running.

## 9) Backup and Recovery

Backup PostgreSQL volume:

```bash
docker run --rm \
  -v simulator_simulator_postgres_data:/volume \
  -v /root/simulate/backups:/backup \
  alpine sh -c "tar czf /backup/postgres-$(date +%F-%H%M%S).tgz -C /volume ."
```

Backup run artifacts and plans volume:

```bash
docker run --rm \
  -v simulator_simulator_runs_data:/volume \
  -v /root/simulate/backups:/backup \
  alpine sh -c "tar czf /backup/runs-$(date +%F-%H%M%S).tgz -C /volume ."
```

## 10) Rollback

Rollback to a previous commit on host:

```bash
cd /root/simulate
git fetch --all
git checkout <previous_commit_sha>
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans
```

Then validate health endpoint and core UI/API paths.

## 11) Security Checklist

- Keep `SIMULATOR_HOST_BIND=127.0.0.1` unless public exposure is intentional.
- If public exposure is required, front with TLS termination and strict firewall rules.
- Set strong `JWT_SECRET_KEY` and rotate periodically.
- Restrict `WEB_CORS_ORIGINS` to trusted origins.
- Keep `SIM_AUTH_DISABLED=false` in production.
- Keep `SIMULATOR_SESSION_COOKIE_SECURE=true` on HTTPS deployments.
- Patch OS, Docker, and dependencies regularly.
- Do not expose Postgres host port.

## 12) Moving Host, Domain, or Port

When migrating infra:

1. Provision new host and repeat first-time setup.
2. Restore backups into named volumes.
3. Update `.env.prod` values (`SIMULATOR_HOST_BIND`, `SIMULATOR_HOST_PORT`, CORS origins, external URLs).
4. Update DNS/reverse-proxy routing.
5. Update GitHub secrets (`SIMULATOR_DEPLOY_HOST`, optional port/path).
6. Trigger manual workflow dispatch for cutover.

## 13) Cross-Project Deployment Webhook Setup

Endpoint on simulator:

- `POST https://<simulator-host>/api/v1/integrations/github/deployment-complete`

Payload/event expectations:

- GitHub webhook event must be `deployment_status`.
- Simulator accepts only `deployment_status.state=success`.
- Signature header must be present: `X-Hub-Signature-256`.

Per upstream repository setup:

1. In repo settings, add a webhook pointing to the endpoint above.
2. Select `deployment_status` event.
3. Set secret to the value configured for that project key in `GITHUB_WEBHOOK_PROJECT_SECRETS`.
4. Ensure repository full name is present in `GITHUB_WEBHOOK_REPO_ALLOWLIST` under the right project.
5. Ensure deployment workflow emits GitHub deployment + deployment status events.

Simulator profile routing setup:

1. Create saved run profiles in simulator (`Runs` page or `/api/v1/run-profiles`).
2. Upsert mapping rows via:
   - `POST /api/v1/integrations/github/mappings`
   - body: `{"project":"backend","environment":"production","profile_id":12,"enabled":true}`
3. Verify with `GET /api/v1/integrations/github/mappings`.

Verification and troubleshooting:

- Inspect trigger audit feed: `GET /api/v1/integrations/github/triggers`.
- Common rejection reasons:
  - `repository_not_allowlisted`
  - `invalid_signature`
  - `non_success_state`
  - `mapping_not_found`
  - `mapping_disabled`
- End-to-end success path:
  - upstream deployment completes -> webhook accepted and queued -> simulator run launched -> simulator posts final `simulator/verification` deployment status back to GitHub.
