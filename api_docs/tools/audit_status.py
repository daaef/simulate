#!/usr/bin/env python3
"""Report exactly which api_docs use cases are captured vs. gated, and why.

Read-only, no network calls, no side effects. Stdlib-only.

Usage:
  python3 api_docs/tools/audit_status.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # api_docs/


def scan(part: str) -> tuple[list[dict], list[dict]]:
    captured: list[dict] = []
    gated: list[dict] = []
    part_dir = ROOT / part
    for path in sorted(part_dir.rglob("*.json")):
        data = json.loads(path.read_text())
        row = {
            "file": str(path.relative_to(ROOT)),
            "useCase": data.get("useCase"),
            "group": data.get("group"),
            "endpoint": f"{data['endpoint']['method']} {data['endpoint']['host']}{data['endpoint']['path']}",
            "status": data.get("capture", {}).get("status"),
            "verifiedAt": data.get("capture", {}).get("verifiedAt"),
            "note": data.get("note"),
            "expectedNon2xx": data.get("expectedNon2xx", False),
        }
        if row["status"] is not None:
            captured.append(row)
        else:
            gated.append(row)
    return captured, gated


def main() -> None:
    total_captured = 0
    total_gated = 0
    for part in ("internal", "external"):
        captured, gated = scan(part)
        total_captured += len(captured)
        total_gated += len(gated)
        print(f"\n=== {part} ===")
        print(f"captured: {len(captured)}   gated: {len(gated)}")
        if gated:
            print(f"\n-- gated {part} use cases --")
            for row in gated:
                print(f"  {row['group']}/{row['useCase']}  ({row['endpoint']})")
                print(f"    reason: {row['note'] or '(no note field -- MISSING EXPLANATION, needs one)'}")
        # Flag anything captured but missing a note-worthy explanation of provenance, and
        # anything with a non-2xx status not marked expectedNon2xx.
        suspicious = [
            r for r in captured
            if (r["status"] is not None and r["status"] >= 300 and not r["expectedNon2xx"])
        ]
        if suspicious:
            print(f"\n-- captured but non-2xx and NOT marked expectedNon2xx (needs review) --")
            for row in suspicious:
                print(f"  {row['group']}/{row['useCase']}  status={row['status']}  ({row['endpoint']})")

    print(f"\n=== TOTAL ===")
    print(f"captured: {total_captured}   gated: {total_gated}   grand total: {total_captured + total_gated}")


if __name__ == "__main__":
    main()
