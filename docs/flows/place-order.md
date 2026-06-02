# Flow: `place-order`

## Intent

Use this flow to seed live pending orders for manual store-app inspection. It is the only simulator flow that intentionally leaves created orders non-terminal.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["place_order"]
}
```

## Operator behavior

- Places 1-10 order(s) through the normal user order API.
- Requires websocket proof that each order reached `pending`.
- Records `pending_order_seeded` for every created order.
- Skips end-of-run cleanup only for these `place_order` pending orders.

## Launch examples

- GUI: Runs -> Flow `place-order`, set Orders to `3`.
- CLI: `python3 -m simulate place-order --plan sim_actors.json --orders 3`
- Pinned actors: `python3 -m simulate place-order --plan sim_actors.json --store FZY_926025 --phone +2348166675609 --orders 2`

## Required inputs

- Selected plan with at least one usable user and store.
- Optional `--store` and `--phone` only when you need exact actors.
- `--orders` is optional, defaults to `1`, and must be between `1` and `10`.

## Expected artifacts

- `events.json`, `report.md`, and `story.md`.
- Per-order `place_order`, pending websocket proof, and `pending_order_seeded` events.
- `order_contract_non_terminal_allowed` cleanup-bypass evidence for the seeded pending orders.

## Common failure signals

- Pending websocket proof missing or late.
- Selected plan has no usable user/store.
- `--orders` is outside `1..10`.
- `place_order` was combined with another suite or scenario.
