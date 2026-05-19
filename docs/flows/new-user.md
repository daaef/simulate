# Flow: `new-user`

## Intent

Use this flow to validate first-time user onboarding and initial ordering setup behavior.

## Preset defaults

```json
{
  "mode": "trace",
  "scenarios": ["new_user_setup"],
  "user_role": "new_user"
}
```

## Operator behavior

- Runs a single trace scenario: `new_user_setup`.
- Applies `user_role=new_user` to force onboarding path expectations.

## Launch examples

- GUI: Runs -> Flow `new-user`.
- CLI: `python3 -m simulate new-user --plan sim_actors.json --timing fast`

## Required inputs

- Plan user that can authenticate as a new-user path.
- Store and menu prerequisites available for first order attempt.

## Expected artifacts

- Evidence of onboarding/auth/setup steps.
- Clear pass/fail around new-user bootstrap dependencies.

## Common failure signals

- OTP/auth bootstrap contract mismatches.
- Missing setup data for new-user profile creation.
