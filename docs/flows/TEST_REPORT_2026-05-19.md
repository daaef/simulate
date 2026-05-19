# GUI Flow Test Report — 2026-05-19

> Session: `gui-2026-05-19-d4c6d449`  
> Started: `2026-05-19T09:53:31.210+00:00`  
> Ended: `2026-05-19T09:54:12.177+00:00`  
> Base URL: `http://localhost:8080`  
> Raw log: `logs/simulator-runs/2026-05-19/gui-2026-05-19-d4c6d449.ndjson`

## Summary

| | Count |
|--|-------|
| Discovered | 28 |
| Passed | 28 |
| Failed | 0 |
| Blocked | 0 |

**Verdict: RUN SUCCEEDED**

---

## Flow Results

| Flow ID | Name | Section | Status |
|---------|------|---------|--------|
| `auth-login` | Authentication – Login | 1. Auth & Shell | ✅ **passed** |
| `auth-nav` | Authentication – Nav presence | 1. Auth & Shell | ✅ **passed** |
| `auth-theme` | Authentication – Theme toggle | 1. Auth & Shell | ✅ **passed** |
| `auth-logout` | Authentication – Sign out | 1. Auth & Shell | ✅ **passed** |
| `runs-layout` | /runs – Page layout and health | 2. Runs Page | ✅ **passed** |
| `start-run-layout` | Start Run – Form layout | 3. Start Run Layout | ✅ **passed** |
| `start-run-no-active` | Start Run – No active runs state | 3. Start Run Layout | ✅ **passed** |
| `flow-dropdown` | Start Run – Flow dropdown options | 4. Core Controls | ✅ **passed** |
| `flow-load-mode` | Start Run – Load mode controls | 4. Core Controls | ✅ **passed** |
| `flow-timing` | Start Run – Timing toggle | 4. Core Controls | ✅ **passed** |
| `flow-plan` | Start Run – Plan dropdown | 4. Core Controls | ✅ **passed** |
| `checkboxes` | Start Run – Checkboxes | 7. Checkboxes | ✅ **passed** |
| `validation-continuous-trace` | Validation – Continuous not allowed in trace | 8. Client-side Validation | ✅ **passed** |
| `validation-reject-range` | Validation – Reject rate range | 8. Client-side Validation | ✅ **passed** |
| `advanced-overrides` | Start Run – Advanced Mode Overrides | 5. Advanced Overrides | ✅ **passed** |
| `saved-profiles` | Saved Profiles – Save / Load / Delete | 10. Saved Profiles | ✅ **passed** |
| `recent-runs-table` | Recent Runs – Table and pagination | 11. Recent Runs | ✅ **passed** |
| `run-detail` | Run detail – /runs/[id] tabs | 12. Run Detail | ✅ **passed** |
| `route-overview` | Route – /overview | 14. Other Routes | ✅ **passed** |
| `route-config` | Route – /config | 14. Other Routes | ✅ **passed** |
| `route-schedules` | Route – /schedules | 14. Other Routes | ✅ **passed** |
| `route-archives` | Route – /archives | 14. Other Routes | ✅ **passed** |
| `route-retention` | Route – /retention | 14. Other Routes | ✅ **passed** |
| `route-admin-users` | Route – /admin/users | 14. Other Routes | ✅ **passed** |
| `route-admin-system` | Route – /admin/system | 14. Other Routes | ✅ **passed** |
| `flow-planner` | Flow Planner & Command Guide | 13. Flow Planner | ✅ **passed** |
| `api-flows` | API – GET /api/v1/flows | API Smoke | ✅ **passed** |
| `api-runs-list` | API – GET /api/v1/runs | API Smoke | ✅ **passed** |

---

## Failed / Blocked Detail
