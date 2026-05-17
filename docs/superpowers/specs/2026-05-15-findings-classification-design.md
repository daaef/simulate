# Findings Classification and Per-Run Log Console

**Date:** 2026-05-15  
**Status:** Approved for implementation

## Problem

1. **Critical vs operational findings:** Overview API filters to server-only issues in `issues`, but run detail splits that same list by `severity`, mislabeling warning-level server failures (e.g. `websocket_connection_error`) as operational. True operational issues (`missing_user_token`, `probe_failed`) never reach the UI.
2. **Run logs:** Storage is already per-run (`run-{id}.log`). UI shows stale logs on run switch, strips blank lines on `/runs` Live Console, and does not poll on run detail Console tab.

## Classification rules

| Bucket | Rule |
|--------|------|
| **critical** | `_is_server_api_failure_issue` / `_is_server_api_failure_event`; codes `websocket_event_missing`, `websocket_event_late`; `websocket_gate_*` with `details.enforced === true` |
| **operational** | All other artifact `issues`; `websocket_gate_*` with `details.enforced === false` |

`issues` on overview responses remains an alias for `findings.critical` (backward compatible).

## API shape

`GET /api/v1/overview/latest-run` and `GET /api/v1/overview/runs/{run_id}` add:

```json
{
  "findings": {
    "critical": [LatestRunIssue],
    "operational": [LatestRunIssue]
  },
  "issues": []
}
```

Caps: 10 critical, 12 operational. Scan up to 24 artifact issues before capping.

## Backend changes

**File:** `api/app/overview/service.py`

- Add `CRITICAL_ISSUE_CODES`, `_finding_bucket_issue()`, `_issue_row_from_artifact()`, `_build_findings()`.
- `_issues()` returns `_build_findings(...)["critical"]` only.
- `_build_overview_payload()` sets `findings` and `issues`.
- Empty latest-run payload includes `"findings": {"critical": [], "operational": []}`.

**File:** `api/app/main.py` — `_run_log_payload()`

- Resolve `log_path`; if present, require `path.name == f"run-{run_id}.log"` and path under `LOG_DIR.resolve()`; otherwise return empty log (do not tail wrong file).

## Frontend changes

**File:** `web/src/lib/api.ts`

- Add `RunFindings` type; extend `LatestRunOverview` with `findings?: RunFindings`.

**File:** `web/src/components/runs/RunLogViewer.tsx` (new)

- Shared `<pre className="log">` renderer; preserve blank lines; optional `emptyMessage`.

**Files:** `RunLiveConsole.tsx`, `RunLogPanel.tsx` — use `RunLogViewer`.

**File:** `web/src/app/(app)/runs/page.tsx`

- On `selectedRunId` change: `setLogText("")` before fetch.
- Remove `.filter((line) => line.length > 0)`.
- Optional: `onWatchRun(runId)` on table sets `selectedRunId` without navigation.

**File:** `web/src/app/(app)/runs/[id]/page.tsx`

- Poll `fetchRunLog` every 1s while `activeTab === "console"` and run status is active.
- Reset `log` when `runId` changes.

**File:** `web/src/components/runs/detail/RunDetailOverview.tsx`

- Accept `findings: RunFindings`; render `findings.critical` / `findings.operational` (fallback: split deprecated `issues` only if `findings` absent).

## Tests

**File:** `tests/test_web_api.py`

- Extend `OverviewLatestRunTests`: assert `findings.operational` contains `missing_user_token`; `findings.critical` contains payment/503 route; `issues === findings.critical`.
- New cases: `websocket_event_missing` → critical; gate bypass `enforced: false` → operational.
- Log guard: wrong `log_path` name returns empty log.

## Docs

- `README.md` — findings buckets; one log file per run; Live Console behavior.
- `SIMULATOR_GUIDE.md` — same for overview/run detail sections.

## Verification

```bash
python -m unittest tests.test_web_api.OverviewLatestRunTests -v
```

Manual: start run A, switch to B on `/runs` — no A lines in Live Console; run detail Console updates while running.
