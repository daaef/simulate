# Flow: `load`

## Intent

Use this flow to validate concurrency behavior, churn resilience, and throughput under repeated order activity.

## Preset defaults

```json
{
  "mode": "load"
}
```

## Operator behavior

- This is load mode, not trace mode.
- `users`, `orders`, `interval`, `reject`, `continuous`, and `all_users` drive runtime shape.
- `all_users` semantics:
  - `all_users=false`: one selected/default user is reused across all `users=N` workers.
  - `all_users=true` and `N <= plan users`: first `N` users in plan order are assigned.
  - `all_users=true` and `N > plan users`: users are assigned by deterministic round-robin from the beginning.

## Launch examples

- GUI: Runs -> Flow `load`, then set `users`, `orders`, `interval`, and `reject`.
- CLI: `python3 -m simulate load --plan sim_actors.json --users 20 --orders 100 --interval 3`

## Required inputs

- A valid plan with `stores[]` and `users[]`.
- Valid store/user identities within selected plan scope.

## Expected artifacts

- `events.json`, `report.md`, `story.md` under the run artifact directory.
- Runtime metrics emphasizing latency, failures, and worker outcomes.

## Common failure signals

- `--users must be >= 1` or `--orders must be >= 1`.
- Out-of-plan store/phone validation failures.
- Stripe/payment backend failures when payment mode requires external dependencies.
