#!/usr/bin/env python3
"""
Initialize or repair an implementation tracker.

Usage:
  python scripts/init_tracker.py
  python scripts/init_tracker.py --root /path/to/repo
  python scripts/init_tracker.py --force

This script creates:
  implementation/tracker/README.md
  implementation/tracker/implementation_plan.md
  implementation/tracker/tasks.md
  implementation/tracker/session_log.md

It does not overwrite existing files unless --force is passed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


README_TEMPLATE = """# Implementation Tracker README

## Goal

TODO: Describe the implementation goal clearly.

## Current Status

Not started

## Scope

TODO: Describe what is included.

## Out of Scope

TODO: Describe what should not be changed.

## Relevant Files

- TODO: path/to/file

## How to Continue

1. Read `implementation_plan.md`
2. Check open items in `tasks.md`
3. Review the latest entries in `session_log.md`
4. Continue from the first incomplete task

## Validation

TODO: Describe how to confirm the implementation works.

## Known Blockers / Assumptions

- TODO: Add blockers or assumptions.

## Last Updated

{timestamp}
"""

PLAN_TEMPLATE = """# Implementation Plan

## Problem Statement

TODO: Describe the problem clearly.

## Target Behavior

TODO: Describe the expected final behavior.

## Existing Behavior

TODO: Describe the current behavior before changes.

## Proposed Approach

TODO: Explain the chosen implementation strategy.

## Architecture / Design Notes

TODO: Explain important design choices.

## Files to Modify

| File | Purpose of Change |
|---|---|
| TODO | TODO |

## Implementation Steps

1. TODO
2. TODO
3. TODO

## Testing Strategy

- Unit tests:
- Integration tests:
- Manual tests:
- Edge cases:

## Rollback Strategy

TODO: Explain how to safely undo the changes.

## Acceptance Criteria

- [ ] TODO
- [ ] TODO
- [ ] TODO
"""

TASKS_TEMPLATE = """# Implementation Tasks

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked

## Tasks

### Phase 1: Preparation

- [ ] Create or update the implementation tracker.
  - Dependency: None
  - Notes:
  - Completion evidence:

### Phase 2: Implementation

- [ ] Implement the planned code changes.
  - Dependency: Preparation complete
  - Notes:
  - Completion evidence:

### Phase 3: Testing

- [ ] Run validation checks.
  - Dependency: Implementation complete
  - Notes:
  - Completion evidence:

### Phase 4: Cleanup / Documentation

- [ ] Update documentation and handoff notes.
  - Dependency: Testing complete
  - Notes:
  - Completion evidence:

## Next Immediate Task

Fill in the implementation goal, scope, relevant files, and acceptance criteria.
"""

SESSION_LOG_TEMPLATE = """# Session Log

## {timestamp}

### Summary

Initialized implementation tracker.

### Files Created / Modified

- implementation/tracker/README.md
- implementation/tracker/implementation_plan.md
- implementation/tracker/tasks.md
- implementation/tracker/session_log.md

### Tests / Commands Run

```bash
python scripts/init_tracker.py
```

### Results

Tracker files are ready to be completed before implementation.

### Issues / Blockers

- None recorded yet.

### Next Steps

1. Fill in the tracker with concrete implementation details.
2. Begin the first incomplete task in `tasks.md`.
"""


def write_file(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing tracker files.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    tracker = root / "implementation" / "tracker"
    tracker.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    files = {
        tracker / "README.md": README_TEMPLATE.format(timestamp=timestamp),
        tracker / "implementation_plan.md": PLAN_TEMPLATE,
        tracker / "tasks.md": TASKS_TEMPLATE,
        tracker / "session_log.md": SESSION_LOG_TEMPLATE.format(timestamp=timestamp),
    }

    created = []
    skipped = []

    for path, content in files.items():
        if write_file(path, content, args.force):
            created.append(str(path.relative_to(root)))
        else:
            skipped.append(str(path.relative_to(root)))

    print("Implementation tracker path:", tracker)
    if created:
        print("\nCreated/updated:")
        for item in created:
            print(" -", item)
    if skipped:
        print("\nSkipped existing files:")
        for item in skipped:
            print(" -", item)
        print("\nUse --force to overwrite existing files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
