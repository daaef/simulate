#!/usr/bin/env python3
"""Run named simulator flows under api_only policy and emit a reliability summary."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "runs"

DEFAULT_FLOWS = (
    "menus",
    "free-coupon",
    "new-user",
    "paid-coupon",
    "paid-no-coupon",
    "payments",
    "receipt-review",
    "robot-complete",
    "store-accept",
    "store-dashboard",
    "store-reject",
    "store-setup",
)


def latest_run_dir(before: set[str]) -> Path | None:
    candidates = [
        p
        for p in RUNS.iterdir()
        if p.is_dir() and p.name not in before and (p / "events.json").is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_verdict(report_path: Path) -> str:
    if not report_path.is_file():
        return "unknown"
    text = report_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\|\s*Verdict\s*\|\s*([A-Za-z]+)\s*\|", text)
    if match:
        return match.group(1).lower()
    match = re.search(r"Verdict[:\s]+([A-Za-z]+)", text, re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


def analyze_events(events_path: Path) -> dict:
    payload = json.loads(events_path.read_text(encoding="utf-8"))
    issues = payload.get("issues") or []
    decisions = payload.get("decisions") or []
    scenarios = payload.get("scenarios") or []
    failure_classes: dict[str, int] = {"api_fault": 0, "precondition": 0, "other": 0}

    for item in list(issues) + list(decisions):
        fc = str(item.get("failure_class") or "").strip().lower()
        if fc == "api_fault":
            failure_classes["api_fault"] += 1
        elif fc == "precondition":
            failure_classes["precondition"] += 1
        elif fc:
            failure_classes["other"] += 1

    for event in payload.get("events") or []:
        try:
            status = int(event.get("http_status") or event.get("status_code") or 0)
        except (TypeError, ValueError):
            status = 0
        if status >= 500 and event.get("ok") is False:
            failure_classes["api_fault"] += 1

    scenario_names: list[str] = []
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("name"):
            scenario_names.append(str(scenario["name"]))

    started = bool(payload.get("run", {}).get("started_at")) and bool(scenario_names)
    return {
        "started": started,
        "scenarios": scenario_names,
        "failure_class_counts": failure_classes,
    }


def policy_pass(*, api_only: bool, exit_code: int, verdict: str, failure_class_counts: dict[str, int]) -> bool:
    if exit_code != 0:
        return False
    if not api_only:
        return True
    if failure_class_counts.get("api_fault", 0) > 0 and verdict == "failed":
        return False
    if verdict == "failed":
        return False
    return True


def _simulator_cmd(flow: str, *, plan: str, timing: str) -> list[str]:
    return ["python3", "__main__.py", flow, "--plan", plan, "--timing", timing]


def run_flow(flow: str, *, plan: str, timing: str) -> dict:
    before = {p.name for p in RUNS.iterdir() if p.is_dir()}
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO))
    proc = subprocess.run(
        _simulator_cmd(flow, plan=plan, timing=timing),
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
    )
    run_dir = latest_run_dir(before)
    verdict = "unknown"
    analysis: dict = {
        "started": False,
        "scenarios": [],
        "failure_class_counts": {"api_fault": 0, "precondition": 0, "other": 0},
    }
    if run_dir and (run_dir / "events.json").is_file():
        analysis = analyze_events(run_dir / "events.json")
        verdict = parse_verdict(run_dir / "report.md")

    return {
        "flow": flow,
        "exit_code": proc.returncode,
        "run_dir": str(run_dir.relative_to(REPO)) if run_dir else None,
        "verdict": verdict,
        "started": analysis["started"],
        "scenarios": analysis["scenarios"],
        "failure_class_counts": analysis["failure_class_counts"],
        "stderr_tail": (proc.stderr or "")[-500:] if proc.returncode != 0 else "",
    }


def run_alias_smoke(*, plan: str, timing: str) -> dict:
    before = {p.name for p in RUNS.iterdir() if p.is_dir()}
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO))
    proc = subprocess.run(
        _simulator_cmd("ronot-complete", plan=plan, timing=timing),
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
    )
    run_dir = latest_run_dir(before)
    resolved_flow = None
    if run_dir and (run_dir / "events.json").is_file():
        cfg = json.loads((run_dir / "events.json").read_text(encoding="utf-8")).get("run", {}).get(
            "config", {}
        )
        resolved_flow = cfg.get("flow")
    return {
        "input": "ronot-complete",
        "resolved_flow": resolved_flow,
        "exit_code": proc.returncode,
        "pass": proc.returncode == 0 and resolved_flow == "robot-complete",
    }


def write_markdown(path: Path, summary: dict) -> None:
    lines = [
        f"# Flow reliability report ({date.today().isoformat()})",
        "",
        f"- Policy: `{summary['policy']['failure_policy']}` / `{summary['policy']['preflight_strategy']}`",
        f"- Plan: `{summary['plan']}` | Timing: `{summary['timing']}`",
        f"- Generated: {summary['generated_at']}",
        "",
        "| Flow | Started | Scenarios | Exit | Verdict | api_fault | precondition | Pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary["flows"]:
        fc = row["failure_class_counts"]
        scen = ", ".join(row["scenarios"][:4])
        if len(row["scenarios"]) > 4:
            scen += ", …"
        lines.append(
            f"| {row['flow']} | {row['started']} | {scen or '—'} | {row['exit_code']} | "
            f"{row['verdict']} | {fc.get('api_fault', 0)} | {fc.get('precondition', 0)} | "
            f"{'yes' if row['policy_pass'] else 'no'} |"
        )
    alias = summary["alias_smoke"]
    lines.extend(
        [
            "",
            "## Alias smoke",
            "",
            f"- Input `{alias['input']}` → resolved flow `{alias['resolved_flow']}` "
            f"(exit {alias['exit_code']}, pass={alias['pass']})",
            "",
            f"**Overall:** {'PASS' if summary['all_pass'] else 'FAIL'}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    plan = os.environ.get("SIM_PLAN", "sim_actors.json")
    timing = os.environ.get("SIM_TIMING", "fast")
    failure_policy = os.environ.get("SIM_FAILURE_POLICY", "api_only")
    preflight_strategy = os.environ.get("SIM_PREFLIGHT_STRATEGY", "auto_recover")
    api_only = failure_policy == "api_only"

    date_stamp = date.today().isoformat()
    json_out = Path(os.environ.get("SIM_RELIABILITY_JSON", f"runs/flow-reliability-{date_stamp}.json"))
    md_out = Path(os.environ.get("SIM_RELIABILITY_MD", f"runs/flow-reliability-{date_stamp}.md"))
    RUNS.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for flow in DEFAULT_FLOWS:
        row = run_flow(flow, plan=plan, timing=timing)
        row["policy_pass"] = policy_pass(
            api_only=api_only,
            exit_code=row["exit_code"],
            verdict=row["verdict"],
            failure_class_counts=row["failure_class_counts"],
        )
        rows.append(row)
        status = "PASS" if row["policy_pass"] else "FAIL"
        print(f"[{status}] {flow} exit={row['exit_code']} verdict={row['verdict']}")

    alias_smoke = run_alias_smoke(plan=plan, timing=timing)
    all_pass = all(row["policy_pass"] for row in rows) and alias_smoke["pass"]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "failure_policy": failure_policy,
            "preflight_strategy": preflight_strategy,
        },
        "plan": plan,
        "timing": timing,
        "flows": rows,
        "alias_smoke": alias_smoke,
        "all_pass": all_pass,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_out, summary)
    print(f"Wrote {json_out}")
    print(f"Wrote {md_out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
