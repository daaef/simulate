#!/usr/bin/env python3
"""End-to-end flow test: CLI regression + GUI launch + GUI representation check.

For each of the 12 named flows:
  1. Reports CLI regression verdict (re-runs via script).
  2. Launches each flow via the GUI API (POST /api/v1/runs).
  3. Polls until the run reaches a terminal state.
  4. Verifies run detail in the GUI (story/report/traffic tabs).

All events logged to SIMULATOR_APPLOGGER NDJSON.

Usage::
    python3 scripts/flow_e2e_test.py
    python3 scripts/flow_e2e_test.py --skip-cli   # skip regression, use cached data
    python3 scripts/flow_e2e_test.py --headed      # show browser
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim_applogger import SimulatorAppLogger, _now_iso, _today_str  # noqa: E402

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
except ImportError:
    print("ERROR: playwright not installed. Run: pip3 install playwright && python3 -m playwright install chromium")
    sys.exit(1)

import urllib.request
import urllib.parse

# ─── Constants ────────────────────────────────────────────────────────────────

_BASE_URL   = "http://localhost:8080"
ADMIN_USER  = "admin"
ADMIN_PASS  = "admin123"
PLAN        = "sim_actors.json"
SESSION_ID  = f"e2e-{_today_str()}-{uuid.uuid4().hex[:8]}"
LOG_BASE    = ROOT / "logs" / "simulator-runs"


def _base() -> str:
    return _BASE_URL

NAMED_FLOWS = [
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
]

# Maximum seconds to wait for a GUI run to reach terminal state
RUN_POLL_TIMEOUT = 300   # 5 minutes per flow
RUN_POLL_INTERVAL = 5


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _live(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}+00:00"
    print(f"{ts}  {msg}", flush=True)


def _api(path: str, *, method: str = "GET", body: dict | None = None, cookie: str = "") -> dict | None:
    """Simple urllib JSON API call (no external deps beyond stdlib)."""
    url = f"{_base()}{path}"
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"_error": str(exc)}


def _login() -> str:
    """Return cookie string for subsequent API calls."""
    url = f"{_base()}/api/v1/auth/login"
    data = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw_headers = resp.info()
        cookie_header = raw_headers.get("Set-Cookie", "")
        # Extract simulator_session=...
        import re
        m = re.search(r"simulator_session=[^;]+", cookie_header)
        return m.group(0) if m else ""


def _get_run(run_id: int, cookie: str) -> dict | None:
    result = _api(f"/api/v1/runs/{run_id}", cookie=cookie)
    if result and "_error" not in result:
        return result.get("run") or result
    return None


def _wait_for_run(run_id: int, cookie: str, logger: SimulatorAppLogger, flow: str) -> dict | None:
    """Poll until run reaches a terminal state."""
    terminal = {"succeeded", "failed", "cancelled"}
    deadline = time.time() + RUN_POLL_TIMEOUT
    while time.time() < deadline:
        run = _get_run(run_id, cookie)
        if not run:
            time.sleep(RUN_POLL_INTERVAL)
            continue
        status = run.get("status", "")
        logger.console("INFO", f"  polling run={run_id} status={status}", flow=flow, source="poller")
        if status in terminal:
            return run
        time.sleep(RUN_POLL_INTERVAL)
    logger.error("PollTimeout", f"Run {run_id} did not complete within {RUN_POLL_TIMEOUT}s", flow=flow)
    return None


# ─── GUI page helpers ─────────────────────────────────────────────────────────

def _ensure_logged_in(page: Page, logger: SimulatorAppLogger) -> None:
    url = page.url
    if "login" in url:
        page.goto(f"{_base()}/auth/login", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        page.locator("input[name=username]").fill(ADMIN_USER)
        page.locator("input[type=password]").fill(ADMIN_PASS)
        page.locator("button[type=submit]").click()
        try:
            page.wait_for_url(lambda u: "login" not in u, timeout=10_000)
        except Exception:
            pass
        logger.action("login", target="auth-form", flow="session")


def _check_run_detail_gui(
    page: Page,
    run_id: int,
    flow: str,
    logger: SimulatorAppLogger,
) -> dict[str, str]:
    """Navigate to /runs/{id} and verify tabs are populated. Returns check results."""
    results: dict[str, str] = {}
    try:
        _ensure_logged_in(page, logger)
        logger.route(f"/runs/{run_id}", "navigate", details={"flow": flow})
        page.goto(f"{_base()}/runs/{run_id}", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        page.wait_for_timeout(500)

        content = page.inner_text("body")

        # Overview
        has_overview = any(kw in content.lower() for kw in ["status", "exit", "succeeded", "failed", "overview"])
        results["overview"] = "pass" if has_overview else "fail"
        logger.step_check(flow, f"run-{run_id} overview tab", passed=has_overview)

        # Status visible
        has_status = any(s in content.lower() for s in ["succeeded", "failed", "cancelled", "running"])
        results["status_visible"] = "pass" if has_status else "fail"
        logger.step_check(flow, f"run-{run_id} status visible", passed=has_status)

        # Story/Report tab present
        has_artifact_tabs = any(kw in content.lower() for kw in ["story", "report", "traffic", "console"])
        results["artifact_tabs"] = "pass" if has_artifact_tabs else "fail"
        logger.step_check(flow, f"run-{run_id} artifact tabs", passed=has_artifact_tabs)

        # Flow name visible
        has_flow = flow in content.lower()
        results["flow_name"] = "pass" if has_flow else "fail"
        logger.step_check(flow, f"run-{run_id} flow name visible", passed=has_flow)

        # Check Story tab content if available
        story_btn = page.locator("button, [role=tab]").filter(
            has_text=__import__("re").compile(r"story", __import__("re").I)
        ).first
        if story_btn.count() > 0:
            logger.action("click", target="story-tab", flow=flow)
            story_btn.click()
            page.wait_for_timeout(800)
            story_content = page.inner_text("body")
            has_story_content = len(story_content) > 200 and any(
                kw in story_content.lower() for kw in ["scenario", "result", "run", "order", "error", "✓", "→", "status"]
            )
            results["story_content"] = "pass" if has_story_content else "fail"
            logger.step_check(flow, f"run-{run_id} story has content", passed=has_story_content)
        else:
            results["story_content"] = "skip"

    except Exception as exc:
        logger.error("GUICheckError", str(exc), flow=flow, stacktrace=traceback.format_exc())
        results["error"] = str(exc)
    return results


# ─── CLI regression ───────────────────────────────────────────────────────────

def run_cli_regression(logger: SimulatorAppLogger) -> dict[str, dict[str, Any]]:
    """Run the named flow regression script and parse results."""
    _live("[CLI] Running named flow regression…")
    logger.lifecycle("cli_regression_start")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["SIM_FAILURE_POLICY"] = "api_only"
    env["SIM_PREFLIGHT_STRATEGY"] = "auto_recover"

    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, "scripts/run_named_flow_regression.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=env,
            timeout=900,  # 15 min max
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.lifecycle("cli_regression_done", details={
            "exit_code": result.returncode,
            "elapsed_ms": elapsed,
        })
        if result.stdout:
            logger.console("INFO", result.stdout[-2000:], source="regression_stdout")
        if result.stderr:
            logger.console("WARN", result.stderr[-1000:], source="regression_stderr")
    except subprocess.TimeoutExpired:
        logger.error("Timeout", "CLI regression timed out after 15 minutes")
        return {}
    except Exception as exc:
        logger.error("CLIError", str(exc))
        return {}

    # Parse the JSON output
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = ROOT / "runs" / f"flow-reliability-{today}.json"
    if not json_path.exists():
        logger.error("MissingArtifact", f"Regression JSON not found: {json_path}")
        return {}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    cli_results: dict[str, dict[str, Any]] = {}
    for flow_data in data.get("flows", []):
        flow = flow_data["flow"]
        cli_results[flow] = {
            "exit_code": flow_data.get("exit_code"),
            "verdict": flow_data.get("verdict", "unknown"),
            "policy_pass": flow_data.get("policy_pass", False),
            "api_fault": flow_data.get("failure_class_counts", {}).get("api_fault", 0),
            "precondition": flow_data.get("failure_class_counts", {}).get("precondition", 0),
            "scenarios": flow_data.get("scenarios", []),
            "run_dir": flow_data.get("run_dir", ""),
        }
        icon = "✅" if flow_data.get("policy_pass") else "❌"
        _live(f"  [CLI] {icon} {flow}: exit={flow_data.get('exit_code')} verdict={flow_data.get('verdict')}")
        logger.flow_status(
            f"cli-{flow}",
            "passed" if flow_data.get("policy_pass") else "failed",
            step="regression",
            expected="exit 0 under api_only",
            actual=f"exit {flow_data.get('exit_code')} verdict={flow_data.get('verdict')}",
            root_cause=None if flow_data.get("policy_pass") else (
                f"precondition failures: {flow_data.get('failure_class_counts', {}).get('precondition', 0)}"
                if flow_data.get("failure_class_counts", {}).get("api_fault", 0) == 0
                else f"api_fault: {flow_data.get('failure_class_counts', {}).get('api_fault', 0)}"
            ),
        )
    return cli_results


def load_cached_cli_results(logger: SimulatorAppLogger) -> dict[str, dict[str, Any]]:
    """Load today's cached regression results (if --skip-cli)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = ROOT / "runs" / f"flow-reliability-{today}.json"
    if not json_path.exists():
        logger.error("MissingArtifact", f"No cached regression for {today}. Run without --skip-cli.")
        return {}
    data = json.loads(json_path.read_text())
    cli_results: dict[str, dict[str, Any]] = {}
    for flow_data in data.get("flows", []):
        flow = flow_data["flow"]
        cli_results[flow] = {
            "exit_code": flow_data.get("exit_code"),
            "verdict": flow_data.get("verdict", "unknown"),
            "policy_pass": flow_data.get("policy_pass", False),
            "api_fault": flow_data.get("failure_class_counts", {}).get("api_fault", 0),
            "precondition": flow_data.get("failure_class_counts", {}).get("precondition", 0),
            "scenarios": flow_data.get("scenarios", []),
            "run_dir": flow_data.get("run_dir", ""),
        }
        icon = "✅" if flow_data.get("policy_pass") else "❌"
        _live(f"  [CLI cached] {icon} {flow}: exit={flow_data.get('exit_code')} verdict={flow_data.get('verdict')}")
        logger.console("INFO",
            f"cli-cached {flow}: exit={flow_data.get('exit_code')} verdict={flow_data.get('verdict')}",
            source="regression_cache")
    return cli_results


# ─── GUI flow launcher ────────────────────────────────────────────────────────

def launch_gui_flow(flow: str, cookie: str, logger: SimulatorAppLogger) -> int | None:
    """POST /api/v1/runs for a flow, return run ID."""
    payload = {
        "flow": flow,
        "plan": PLAN,
        "timing": "fast",
        "trigger_source": "manual",
        "trigger_label": f"e2e-test: {flow}",
    }
    t0 = time.perf_counter()
    result = _api("/api/v1/runs", method="POST", body=payload, cookie=cookie)
    latency = int((time.perf_counter() - t0) * 1000)
    launch_url = f"{_base()}/api/v1/runs"
    if not result or "_error" in result:
        logger.error("LaunchError", f"Failed to launch {flow}: {result}", flow=flow)
        logger.network("POST", launch_url, error=str(result), latency_ms=latency, flow=flow)
        return None
    run_id = result.get("id") or result.get("run", {}).get("id")
    logger.network("POST", launch_url, status=200, latency_ms=latency, flow=flow)
    logger.action("submit", target="POST /api/v1/runs", flow=flow, step="launch",
                  details={"run_id": run_id, "payload": payload})
    return run_id


# ─── Master runner ────────────────────────────────────────────────────────────

def main() -> None:
    global _BASE_URL
    parser = argparse.ArgumentParser(description="Flow E2E: CLI regression + GUI launch + GUI verification")
    parser.add_argument("--skip-cli", action="store_true",
                        help="Skip CLI regression, use today's cached result")
    parser.add_argument("--base-url", default=_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    _BASE_URL = args.base_url.rstrip("/")

    _live(f"[SIMULATOR_APPLOGGER] E2E flow test  session={SESSION_ID}")
    logger = SimulatorAppLogger(session_id=SESSION_ID, log_dir=LOG_BASE)
    logger.lifecycle("ready", details={"flows": NAMED_FLOWS, "plan": PLAN})

    # ── Phase 1: CLI regression ──────────────────────────────────────────────
    _live("─" * 60)
    _live("Phase 1: CLI regression")
    _live("─" * 60)
    if args.skip_cli:
        cli_results = load_cached_cli_results(logger)
    else:
        cli_results = run_cli_regression(logger)

    if not cli_results:
        _live("[WARN] CLI results empty — continuing with GUI phase")

    # ── Phase 2: GUI launch + poll ───────────────────────────────────────────
    _live("─" * 60)
    _live("Phase 2: GUI — launch all flows via API, poll to completion")
    _live("─" * 60)

    cookie = _login()
    if not cookie:
        logger.error("AuthError", "Failed to get session cookie")
        _live("[ERROR] Could not log in to GUI API — aborting GUI phase")
        gui_run_ids: dict[str, int] = {}
    else:
        logger.action("login", target="GUI API", flow="session", step="auth")
        _live(f"  Logged in: cookie={cookie[:30]}…")

        # Get existing runs to avoid re-launching already-present flows
        existing_runs_data = _api("/api/v1/runs?limit=100", cookie=cookie) or {}
        existing_runs = existing_runs_data.get("runs", [])
        existing_by_flow: dict[str, dict] = {}
        for r in existing_runs:
            cmd = r.get("command", "")
            for f in NAMED_FLOWS:
                if f in cmd and f not in existing_by_flow:
                    existing_by_flow[f] = r

        gui_run_ids: dict[str, int] = {}

        for flow in NAMED_FLOWS:
            if flow in existing_by_flow:
                run = existing_by_flow[flow]
                run_id = run.get("id")
                status = run.get("status", "")
                _live(f"  [GUI] {flow}: existing run id={run_id} status={status} — launching fresh anyway")

            _live(f"  [GUI] Launching {flow}…")
            logger.lifecycle("gui_launch_start", details={"flow": flow})
            run_id = launch_gui_flow(flow, cookie, logger)
            if run_id is None:
                _live(f"  [GUI] ❌ {flow}: launch failed")
                continue

            gui_run_ids[flow] = run_id
            _live(f"  [GUI] {flow} → run_id={run_id}  polling…")

            # Poll to completion
            completed_run = _wait_for_run(run_id, cookie, logger, flow)
            if completed_run:
                status = completed_run.get("status", "unknown")
                exit_code = completed_run.get("exit_code")
                _live(f"  [GUI] {flow}: done  status={status}  exit={exit_code}")
                logger.flow_status(
                    f"gui-launch-{flow}",
                    "passed" if status == "succeeded" else ("failed" if status == "failed" else "blocked"),
                    step="poll_complete",
                    expected="succeeded",
                    actual=f"status={status} exit={exit_code}",
                )
            else:
                _live(f"  [GUI] {flow}: timed out waiting for completion")
                logger.flow_status(f"gui-launch-{flow}", "blocked",
                                   step="poll", expected="terminal status within 300s",
                                   actual="timeout")

    # ── Phase 3: GUI representation verification ─────────────────────────────
    _live("─" * 60)
    _live("Phase 3: GUI representation verification (Playwright)")
    _live("─" * 60)

    gui_check_results: dict[str, dict[str, str]] = {}

    # Collect all run IDs to check (fresh launches + pre-existing if any)
    all_run_ids: dict[str, int] = dict(gui_run_ids)
    # Re-fetch to pick up any pre-existing runs we might have missed
    if cookie:
        latest_data = _api("/api/v1/runs?limit=100", cookie=cookie) or {}
        for r in latest_data.get("runs", []):
            cmd = r.get("command", "")
            for f in NAMED_FLOWS:
                if f in cmd and f not in all_run_ids:
                    all_run_ids[f] = r["id"]
                    break

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=not args.headed)
        ctx: BrowserContext = browser.new_context(
            base_url=_base(),
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
        )
        page: Page = ctx.new_page()
        page.on("console", lambda msg: logger.console(msg.type.upper(), msg.text[:300], source="browser"))
        page.on("pageerror", lambda exc: logger.error("PageError", str(exc)))

        # Login
        page.goto(f"{_base()}/auth/login", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        page.locator("input[name=username]").fill(ADMIN_USER)
        page.locator("input[type=password]").fill(ADMIN_PASS)
        page.locator("button[type=submit]").click()
        try:
            page.wait_for_url(lambda u: "login" not in u, timeout=10_000)
        except Exception:
            pass
        logger.action("login", target="browser", flow="session")

        for flow in NAMED_FLOWS:
            run_id = all_run_ids.get(flow)
            if run_id is None:
                _live(f"  [GUI-verify] {flow}: no run ID — skipping")
                gui_check_results[flow] = {"overview": "skip", "note": "no run in DB"}
                logger.flow_status(f"gui-verify-{flow}", "blocked",
                                   step="find_run_id",
                                   expected="run ID present in DB",
                                   actual="no matching run found")
                continue

            _live(f"  [GUI-verify] {flow}: run_id={run_id}")
            checks = _check_run_detail_gui(page, run_id, flow, logger)
            gui_check_results[flow] = checks

            all_pass = all(v == "pass" for v in checks.values() if v not in ("skip", ""))
            icon = "✅" if all_pass else "❌"
            _live(f"  [GUI-verify] {icon} {flow}: {checks}")
            logger.flow_status(
                f"gui-verify-{flow}",
                "passed" if all_pass else "failed",
                step="representation",
                actual=str(checks),
            )

        browser.close()

    # ── Final report ─────────────────────────────────────────────────────────
    ended_at = _now_iso()
    logger.lifecycle("shutdown", details={"ended_at": ended_at})

    print("\n" + "═" * 72, flush=True)
    print("Flow E2E Test — Complete", flush=True)
    print("═" * 72, flush=True)
    print(f"  Session: {SESSION_ID}", flush=True)
    print(f"  Raw log: {logger.log_path}", flush=True)
    print(f"  Started: {logger.started_at}", flush=True)
    print(f"  Ended:   {ended_at}", flush=True)
    print("", flush=True)

    print(f"  {'FLOW':<22} {'CLI exit':<10} {'CLI verdict':<12} {'CLI pass':<10} {'GUI status':<12} {'GUI UI'}", flush=True)
    print(f"  {'─'*22} {'─'*10} {'─'*12} {'─'*10} {'─'*12} {'─'*10}", flush=True)

    all_cli_pass = True
    all_gui_pass = True
    failed_flows: list[str] = []

    for flow in NAMED_FLOWS:
        cli = cli_results.get(flow, {})
        cli_exit = cli.get("exit_code", "?")
        cli_verdict = cli.get("verdict", "?")
        cli_pass = cli.get("policy_pass", False)
        cli_icon = "✅" if cli_pass else "❌"
        if not cli_pass:
            all_cli_pass = False

        run_id = all_run_ids.get(flow)
        gui_checks = gui_check_results.get(flow, {})

        # Determine GUI run status from the completed_run data
        gui_status = "?"
        if cookie and run_id:
            r = _get_run(run_id, cookie)
            if r:
                gui_status = r.get("status", "?")

        gui_ui_pass = all(v == "pass" for v in gui_checks.values() if v not in ("skip", ""))
        gui_icon = "✅" if gui_ui_pass and gui_checks else ("⚠️" if not gui_checks else "❌")
        if not gui_ui_pass or not gui_checks:
            all_gui_pass = False

        if not cli_pass or not gui_ui_pass:
            failed_flows.append(flow)

        print(f"  {flow:<22} {str(cli_exit):<10} {cli_verdict:<12} {cli_icon:<10} {gui_status:<12} {gui_icon}", flush=True)

    print("", flush=True)

    overall = "RUN SUCCEEDED" if all_cli_pass and all_gui_pass else "RUN FAILED"
    print(f"  CLI regression: {'ALL PASS ✅' if all_cli_pass else 'FAILURES ❌'}", flush=True)
    print(f"  GUI launched:   {len(gui_run_ids)}/12 flows", flush=True)
    print(f"  GUI UI checks:  {'ALL PASS ✅' if all_gui_pass else 'FAILURES ❌'}", flush=True)
    if failed_flows:
        print(f"  Failed flows:   {', '.join(failed_flows)}", flush=True)
    print(f"  Verdict:        {overall}", flush=True)
    print("═" * 72, flush=True)

    logger.stop()
    sys.exit(0 if overall == "RUN SUCCEEDED" else 1)


if __name__ == "__main__":
    main()
