# Flow: `store-setup`

## Intent

Use this flow to validate first-time store setup and readiness prerequisites.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["store_first_setup"]
}
```

## Operator behavior

- Runs `store_first_setup` scenario in trace mode.
- Confirms store-side prerequisites can be created or validated as expected.

## Launch examples

- GUI: Runs -> Flow `store-setup`.
- CLI: `python3 -m simulate store-setup --plan sim_actors.json --timing fast`

## Required inputs

- Valid store identity in selected plan `stores[]`.
- Working store auth path.

## Expected artifacts

- Evidence of setup checks/creation steps.
- Clear diagnostics when setup cannot complete.

## Common failure signals

- Store login/auth failures.
- Setup endpoint errors or missing required store metadata.
