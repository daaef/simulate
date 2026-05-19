#!/usr/bin/env python3
"""Validate that each FLOW_PRESETS key has a matching docs/flows/<flow>.md file."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flow_presets import FLOW_PRESETS


def main() -> int:
    docs_dir = REPO_ROOT / "docs" / "flows"

    expected = sorted(FLOW_PRESETS.keys())
    missing = [flow for flow in expected if not (docs_dir / f"{flow}.md").is_file()]

    if missing:
        print("Flow docs check failed.")
        print(f"Missing {len(missing)} file(s):")
        for flow in missing:
            print(f"- docs/flows/{flow}.md")
        return 1

    print(f"Flow docs check passed: {len(expected)} flow docs present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
