---
name: implementation-tracker
description: Use before implementing, modifying, refactoring, debugging, or integrating code when work must be restartable. Creates and maintains implementation/tracker README.md, implementation_plan.md, tasks.md, and session_log.md so another human or AI agent can continue without chat history.
---

# Implementation Tracker Skill

## Purpose

Make implementation work restartable, auditable, and safe to continue across sessions.

The tracker is the source of truth for implementation state. Do not rely only on chat history.

Create and maintain this folder in the target repository:

```text
implementation/tracker/
├── README.md
├── implementation_plan.md
├── tasks.md
└── session_log.md
```

Optional, when useful:

```text
implementation/tracker/
├── decisions.md
├── risks.md
├── testing_log.md
└── change_log.md
```

## Activation Rules

Use this skill whenever the user asks to implement, modify, refactor, debug, integrate, migrate, or repair code and any of these are true:

- The task may take more than one session.
- The task touches multiple files.
- The task has dependencies, risks, or uncertain behavior.
- Another human or AI agent may need to continue the work.
- The user explicitly says to use an implementation tracker or this skill.

Do not use this skill for tiny one-line edits unless the user explicitly asks.

## Start Protocol

Before changing implementation code:

1. Check whether `implementation/tracker/` exists.
2. If it exists, read all required tracker files before continuing:
   - `README.md`
   - `implementation_plan.md`
   - `tasks.md`
   - `session_log.md`
3. If it does not exist, create it and create the four required files.
4. Initialize the tracker with enough information for a new agent to understand:
   - Goal
   - Scope
   - Out of scope
   - Existing behavior
   - Target behavior
   - Relevant files
   - Planned steps
   - Validation method
   - Risks, assumptions, blockers
5. Only after the tracker is created or updated, begin implementation.

## Required File Contents

### `README.md`

Keep this as the high-level orientation file.

Must include:

```md
# Implementation Tracker README

## Goal

Describe the implementation goal clearly.

## Current Status

Not started / In progress / Blocked / Completed

## Scope

What is included in this implementation.

## Out of Scope

What should not be changed.

## Relevant Files

- path/to/file
- path/to/directory

## How to Continue

1. Read `implementation_plan.md`
2. Check open items in `tasks.md`
3. Review the latest entries in `session_log.md`
4. Continue from the first incomplete task

## Validation

Describe how to confirm the implementation works.

## Known Blockers / Assumptions

- Blocker or assumption

## Last Updated

YYYY-MM-DD HH:MM
```

### `implementation_plan.md`

Keep this as the complete technical plan.

Must include:

```md
# Implementation Plan

## Problem Statement

Describe the problem clearly.

## Target Behavior

Describe the expected final behavior.

## Existing Behavior

Describe the current behavior before changes.

## Proposed Approach

Explain the chosen implementation strategy.

## Architecture / Design Notes

Explain important design choices.

## Files to Modify

| File | Purpose of Change |
|---|---|
| path/to/file | Explain change |

## Implementation Steps

1. Step one
2. Step two
3. Step three

## Testing Strategy

- Unit tests:
- Integration tests:
- Manual tests:
- Edge cases:

## Rollback Strategy

Explain how to safely undo the changes.

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
```

### `tasks.md`

Keep this as the active implementation task board.

Must include:

```md
# Implementation Tasks

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked

## Tasks

### Phase 1: Preparation

- [ ] Task description
  - Dependency:
  - Notes:
  - Completion evidence:

### Phase 2: Implementation

- [ ] Task description
  - Dependency:
  - Notes:
  - Completion evidence:

### Phase 3: Testing

- [ ] Task description
  - Dependency:
  - Notes:
  - Completion evidence:

### Phase 4: Cleanup / Documentation

- [ ] Task description
  - Dependency:
  - Notes:
  - Completion evidence:

## Next Immediate Task

Clearly state the next task to continue from.
```

### `session_log.md`

Keep this as a chronological work record.

Must include one entry per work session or stopping point:

```md
# Session Log

## YYYY-MM-DD HH:MM

### Summary

What was done in this session.

### Files Created / Modified

- path/to/file
- path/to/file

### Tests / Commands Run

```bash
command here
```

### Results

Describe results clearly.

### Issues / Blockers

- Issue or blocker

### Next Steps

1. Next step
2. Next step
```

## During-Work Protocol

After each meaningful implementation step:

1. Update `tasks.md`.
2. Record completion evidence before marking a task complete.
3. Update `implementation_plan.md` if the design changes.
4. Add assumptions or blockers immediately when discovered.
5. Keep `README.md` accurate enough for restart.
6. If tests are run, record commands and results in `session_log.md` or `testing_log.md`.

## Resume Protocol

When resuming work:

1. Read `implementation/tracker/README.md`.
2. Read `implementation/tracker/implementation_plan.md`.
3. Read `implementation/tracker/tasks.md`.
4. Read the latest entries in `implementation/tracker/session_log.md`.
5. Identify the first incomplete or blocked task.
6. Continue from `Next Immediate Task`.
7. Update tracker files before and after making changes.

## Stop Protocol

Before stopping, handing off, or ending the session:

1. Update task statuses in `tasks.md`.
2. Add a new timestamped entry to `session_log.md`.
3. List files changed.
4. List tests or checks run.
5. Record results.
6. Record blockers, risks, or assumptions.
7. Set `Next Immediate Task` in `tasks.md`.
8. Ensure another agent can continue with only:
   - the repository code
   - `implementation/tracker/`

## Quality Rules

- The tracker must be concrete, not generic.
- Do not mark tasks complete without evidence.
- Do not hide design decisions only in chat.
- Do not delete old session log entries.
- Do not rewrite history; append corrections.
- Keep task names actionable.
- Keep acceptance criteria testable.
- Keep the tracker self-contained enough for restart without the original conversation.
- If tracker files already exist, preserve useful existing content and update it instead of overwriting it.
