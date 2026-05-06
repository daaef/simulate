# Plan-Backed Simulator Config Design

## Goal

Move non-sensitive simulator configuration out of `.env` and into validated JSON run plans, while keeping existing CLI commands and the web run launcher compatible.

## Design

`.env` remains the place for secrets and deployment/runtime wiring: database URL, session secrets, backend service URLs when needed, auth tokens, Stripe secret keys, and local paths. A run plan JSON file becomes the editable recipe for simulator behavior: actors, store/user defaults, run mode defaults, fixture setup defaults, payment mode/coupon behavior without Stripe secrets, probe toggles, load controls, review defaults, and autopilot rules.

Existing `sim_actors.json` files remain valid. New fields are additive and grouped under explicit sections:

- `schema_version`
- `defaults`
- `users`
- `stores`
- `runtime_defaults`
- `rules`
- `fixture_defaults`
- `payment_defaults`
- `review_defaults`
- `new_user_defaults`

The CLI still accepts the same commands, flags, and `--plan` argument. Precedence is:

1. Explicit CLI flags
2. Values from the selected JSON plan
3. Existing `.env` values
4. Built-in defaults

The web GUI stores its editable plans under `runs/gui-plans/` and launches simulations by passing the selected generated plan path to the same CLI execution path. The GUI does not write secrets into plan files.

## Security Boundary

Plans must reject sensitive keys such as `secret`, `token`, `password`, `api_key`, and `private_key`. Stripe secret keys, cached auth tokens, and new-user passwords stay in `.env`.

## Acceptance Criteria

- Existing `python3 -m simulate doctor --plan sim_actors.json --timing fast` command syntax still works.
- Existing actor-only `sim_actors.json` remains valid.
- New plan sections can set non-sensitive defaults used by CLI and GUI.
- Explicit CLI flags override plan defaults.
- Web GUI can create, edit, list, read, and delete generated plans.
- Docs explain the new `.env` and plan split.
