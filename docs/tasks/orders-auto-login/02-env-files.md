# Sub-task 02 — Env files: SIMULATOR_PRODUCT

**Status:** Done

## What we're doing

Wiring `SIMULATOR_PRODUCT` through all the places environment variables are declared so GitHub
Actions can inject it as a Secret.

## Files to change

- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.env.prod.example`
- `simulate_project_work_review.md` (the `.env` template section)

## Done when

1. `docker-compose.yml` has `SIMULATOR_PRODUCT: ${SIMULATOR_PRODUCT:-rds}` in the API service env.
2. `docker-compose.prod.yml` has `SIMULATOR_PRODUCT: ${SIMULATOR_PRODUCT:-rds}`.
3. `.env.prod.example` includes a commented or uncommented `SIMULATOR_PRODUCT=rds` line with a
   note explaining what it controls.
4. `simulate_project_work_review.md` env-template block includes `SIMULATOR_PRODUCT`.
