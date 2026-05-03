# Prompt Snippets

## Claude Code

Direct invocation:

```text
/implementation-tracker Implement the requested feature.
```

Or:

```text
Use the implementation-tracker skill.

Before changing code, create or update implementation/tracker.
Keep the tracker current during implementation.
```

## Codex

Direct invocation:

```text
$implementation-tracker
Implement the requested feature.
```

Or:

```text
Use the implementation-tracker skill.

Before changing code, create or update implementation/tracker.
Keep the tracker current during implementation.
```

## Resume prompt for either agent

```text
Resume the previous implementation using the implementation-tracker skill.

First read implementation/tracker/README.md, implementation_plan.md, tasks.md, and session_log.md.
Continue from the Next Immediate Task.
Before stopping, update tasks.md and session_log.md.
```
