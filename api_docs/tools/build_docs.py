#!/usr/bin/env python3
"""Validate every api_docs/<part>/<group>/<use_case>.json against SCHEMA.md and regenerate
api_docs/manifest.json. Stdlib-only, adapted from last_mile_user/api_docs/tools/build_docs.py
to handle the internal/external partition.

Usage:
  python3 api_docs/tools/build_docs.py            # structural validation (skeleton-safe)
  python3 api_docs/tools/build_docs.py --strict    # also requires a real, fresh capture

Adding a new use case = drop a JSON file in the right part/group folder + re-run this script.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # api_docs/
ALLOWED_METHODS = {"GET", "POST", "PATCH", "DELETE", "PUT", "WSS"}
ALLOWED_PARTS = {"internal", "external"}
REQUIRED_TOP_KEYS = {
    "useCase", "group", "part", "endpoint", "usedIn", "trigger", "params",
    "auth", "sensitivePaths", "alsoTriggeredBy", "capture", "response",
}
ALLOWED_TOP_KEYS = REQUIRED_TOP_KEYS | {"badge", "note", "expectedNon2xx"}
SENSITIVE_PATH_RE = re.compile(r"^[a-zA-Z_][\w\[\]\.]*$")
STALE_AFTER_DAYS = 7


class Finding:
    def __init__(self, file: Path, level: str, message: str):
        self.file = file
        self.level = level  # "error" | "warn"
        self.message = message

    def __str__(self) -> str:
        rel = self.file.relative_to(ROOT.parent) if self.file else "?"
        return f"[{self.level.upper()}] {rel}: {self.message}"


def validate_file(path: Path, strict: bool) -> tuple[dict | None, list[Finding]]:
    findings: list[Finding] = []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        findings.append(Finding(path, "error", f"invalid JSON: {e}"))
        return None, findings

    keys = set(data.keys())
    missing = REQUIRED_TOP_KEYS - keys
    if missing:
        findings.append(Finding(path, "error", f"missing required keys: {sorted(missing)}"))
    unknown = keys - ALLOWED_TOP_KEYS
    if unknown:
        findings.append(Finding(path, "error", f"unknown top-level keys: {sorted(unknown)}"))

    # Validate path structure: api_docs/<part>/<group>/<use_case>.json
    if path.parent.parent.name not in ALLOWED_PARTS:
        findings.append(Finding(
            path, "error",
            f"file at {path.relative_to(ROOT)} does not match api_docs/<part>/<group>/<use_case>.json "
            f"(part must be {sorted(ALLOWED_PARTS)})"
        ))

    expected_part = path.parent.parent.name
    expected_group = path.parent.name
    expected_use_case = path.stem

    if data.get("part") != expected_part:
        findings.append(Finding(
            path, "error",
            f"part={data.get('part')!r} does not match folder {expected_part!r}",
        ))
    if data.get("group") != expected_group:
        findings.append(Finding(
            path, "error",
            f"group={data.get('group')!r} does not match folder {expected_group!r}",
        ))
    if data.get("useCase") != expected_use_case:
        findings.append(Finding(
            path, "error",
            f"useCase={data.get('useCase')!r} does not match filename {expected_use_case!r}",
        ))

    endpoint = data.get("endpoint") or {}
    method = endpoint.get("method")
    if method not in ALLOWED_METHODS:
        findings.append(Finding(path, "error", f"endpoint.method={method!r} not in {sorted(ALLOWED_METHODS)}"))
    for key in ("host", "path"):
        if not endpoint.get(key):
            findings.append(Finding(path, "error", f"endpoint.{key} missing/empty"))

    used_in = data.get("usedIn") or {}
    if not used_in.get("screen"):
        findings.append(Finding(path, "error", "usedIn.screen missing/empty"))
    if not used_in.get("chain"):
        findings.append(Finding(path, "error", "usedIn.chain missing/empty"))

    if not (data.get("trigger") or "").strip():
        findings.append(Finding(path, "error", "trigger missing/empty"))

    params = data.get("params") or {}
    for key in ("path", "query", "body"):
        if key not in params:
            findings.append(Finding(path, "error", f"params.{key} missing (may be {{}})"))

    auth = data.get("auth") or {}
    for key in ("header", "howObtained"):
        if not auth.get(key):
            findings.append(Finding(path, "error", f"auth.{key} missing/empty"))
    if "value" not in auth:
        findings.append(Finding(path, "error", "auth.value key missing (may be null)"))

    sensitive = data.get("sensitivePaths")
    if not isinstance(sensitive, list):
        findings.append(Finding(path, "error", "sensitivePaths must be an array"))
    else:
        for sp in sensitive:
            if not isinstance(sp, str) or not SENSITIVE_PATH_RE.match(sp):
                findings.append(Finding(path, "error", f"sensitivePaths entry looks malformed: {sp!r}"))

    also = data.get("alsoTriggeredBy")
    if also is not None and not isinstance(also, list):
        findings.append(Finding(path, "error", "alsoTriggeredBy must be null or an array"))

    capture = data.get("capture") or {}
    for key in ("tool", "flavor"):
        if not capture.get(key):
            findings.append(Finding(path, "error", f"capture.{key} missing/empty"))
    if "verifiedAt" not in capture:
        findings.append(Finding(path, "error", "capture.verifiedAt key missing (may be null)"))
    if "status" not in capture:
        findings.append(Finding(path, "error", "capture.status key missing (may be null)"))

    verified_at = capture.get("verifiedAt")
    status = capture.get("status")
    response = data.get("response")
    expected_non_2xx = bool(data.get("expectedNon2xx"))

    if verified_at is None or response is None:
        if strict:
            findings.append(Finding(path, "error", "not yet captured (verifiedAt/response null) -- run capture script"))
        # else: expected skeleton state, no finding
    else:
        try:
            parsed = datetime.datetime.fromisoformat(verified_at)
            now = datetime.datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.datetime.now()
            age_days = (now - parsed).days
            if strict and age_days > STALE_AFTER_DAYS:
                findings.append(Finding(path, "warn", f"capture is {age_days} days old (>{STALE_AFTER_DAYS}d)"))
        except ValueError:
            findings.append(Finding(path, "error", f"capture.verifiedAt not valid ISO8601: {verified_at!r}"))

        if strict and status not in (200, 201) and not expected_non_2xx:
            findings.append(Finding(
                path, "error",
                f"capture.status={status!r} (not 200/201) and expectedNon2xx is not set -- "
                "this is a REAL failure to investigate/re-capture; only set expectedNon2xx:true "
                "if this endpoint genuinely returns non-2xx (e.g. a known-404 route). A "
                "descriptive `badge` does NOT excuse a failure.",
            ))
        if strict and (response == {} or response == [] or response == ""):
            findings.append(Finding(path, "error", "response is present but empty"))

    return data, findings


def build_manifest(all_data: dict[str, dict]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = {}  # (part, group) -> list of entries
    for rel, data in sorted(all_data.items()):
        part = data["part"]
        group = data["group"]
        key = (part, group)
        capture = data.get("capture", {})
        entry = {
            "useCase": data["useCase"],
            "file": rel,
            "endpoint": data["endpoint"],
            "screen": data.get("usedIn", {}).get("screen"),
            "trigger": data.get("trigger"),
            "verifiedAt": capture.get("verifiedAt"),
            "status": capture.get("status"),
            "badge": data.get("badge"),
            "expectedNon2xx": bool(data.get("expectedNon2xx")),
            "hasAlsoTriggeredBy": bool(data.get("alsoTriggeredBy")),
        }
        groups.setdefault(key, []).append(entry)

    return {
        "generatedAt": datetime.datetime.now().astimezone().isoformat(),
        "totalUseCases": sum(len(v) for v in groups.values()),
        "parts": {
            part: {
                "totalUseCases": sum(len(v) for k, v in groups.items() if k[0] == part),
                "groups": [
                    {"group": g, "useCaseCount": len(entries), "useCases": entries}
                    for (p, g), entries in sorted(groups.items()) if p == part
                ]
            }
            for part in ALLOWED_PARTS
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="require a real, fresh, 200 capture per file")
    args = parser.parse_args()

    # Find all part directories (internal/, external/)
    part_dirs = sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and d.name in ALLOWED_PARTS
    )
    if not part_dirs:
        print("No part folders (internal/, external/) found under api_docs/ -- nothing to validate.", file=sys.stderr)
        return 1

    all_findings: list[Finding] = []
    all_data: dict[str, dict] = {}
    file_count = 0

    for part_dir in part_dirs:
        # Within each part, find group directories
        group_dirs = sorted(
            d for d in part_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        for group_dir in group_dirs:
            for path in sorted(group_dir.glob("*.json")):
                file_count += 1
                data, findings = validate_file(path, args.strict)
                all_findings.extend(findings)
                if data is not None:
                    rel = str(path.relative_to(ROOT))
                    all_data[rel] = data

    errors = [f for f in all_findings if f.level == "error"]
    warnings = [f for f in all_findings if f.level == "warn"]

    for f in all_findings:
        print(f)

    manifest = build_manifest(all_data)
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    internal_count = len([d for d in all_data.values() if d.get("part") == "internal"])
    external_count = len([d for d in all_data.values() if d.get("part") == "external"])

    print(
        f"\n{file_count} files scanned, {len(errors)} error(s), {len(warnings)} warning(s). "
        f"manifest.json written ({manifest['totalUseCases']} total use cases: "
        f"{internal_count} internal, {external_count} external)."
    )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
