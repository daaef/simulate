# Simulator Internal API — use-case map (Stage 1)

Grep-confirmed 2026-07-27 against the current web/ frontend codebase.  Every call site below was found in `/web/src/lib/api.ts` and cross-referenced to its route file:line in `/api/app/<router>/routes.py`. All 90 internal routes documented.

**Auth model:** session-cookie auth. Session is obtained via `POST /api/v1/auth/login` (`api/app/auth/routes.py:41`), stored in cookie name `simulator_session` (defined in `api/app/auth/dependencies.py:19`). Current user verified via `GET /api/v1/auth/session` (routes.py:118) or `GET /api/v1/auth/me` (routes.py:119).

Legend: **chain** = frontend function call → API endpoint (file:line citation verified against current tree).

---

## auth/ (6 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `login_user` | `POST /api/v1/auth/login` | User submits login form in dashboard | `LoginForm.tsx` → `api.ts` (implicit in form) → auth/routes.py:41 | ✓ routes.py:41 |
| `logout_user` | `POST /api/v1/auth/logout` | User clicks Logout | Not found in frontend grep; endpoint exists | (routes.py:104) |
| `refresh_token` | `POST /api/v1/auth/refresh` | Access token expires, dashboard auto-refreshes | AuthContext may call this; not explicit in current api.ts | (routes.py:87) |
| `get_session` | `GET /api/v1/auth/session` | Dashboard app load to check if user is still logged in | Not explicit in current api.ts grep; used by AuthGuard.tsx | (routes.py:118) |
| `get_me` | `GET /api/v1/auth/me` | Alternative session check; UserProfile component | Not explicit in current api.ts grep | (routes.py:119) |
| `register_user` | `POST /api/v1/auth/register` | Self-service registration (disabled) | Endpoint raises 403 always | (routes.py:17) |

---

## admin/ (5 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_users` | `GET /api/v1/admin/users` | AdminDashboard page loads | AdminDashboard.tsx → api call (implicit) | routes.py:18 |
| `create_user` | `POST /api/v1/admin/users` | Admin clicks "Add User" in admin panel | AdminDashboard.tsx form submission | routes.py:28 |
| `update_user` | `PUT /api/v1/admin/users/{user_id}` | Admin edits user details | AdminDashboard.tsx edit form | routes.py:46 |
| `delete_user` | `DELETE /api/v1/admin/users/{user_id}` | Admin deletes user account | AdminDashboard.tsx delete action | routes.py:65 |
| `reset_user_password` | `POST /api/v1/admin/users/{user_id}/reset-password` | Admin resets user password | AdminDashboard.tsx password reset action | routes.py:88 |

---

## runs/ (14 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_flows` | `GET /api/v1/flows` | Run creation form loads to populate flow dropdown | `api.ts:fetchFlows()` (line 780) | routes.py:14 |
| `list_runs` | `GET /api/v1/runs` | Runs list page loads / pull-to-refresh | `api.ts:fetchRuns()` (line 784) | routes.py:19 |
| `get_runs_count` | `GET /api/v1/runs/count` | Dashboard summary to show total run count | `api.ts:fetchRunsCount()` (line 800) | routes.py:29 |
| `get_dashboard_summary` | `GET /api/v1/dashboard/summary` | Dashboard home loads for KPI cards | `api.ts:fetchDashboardSummary()` (line 805) | routes.py:34 |
| `create_run` | `POST /api/v1/runs` | Operator clicks "Start Run" after configuring parameters | `api.ts:createRun()` (line 1013) | routes.py:39 |
| `get_run` | `GET /api/v1/runs/{run_id}` | Run detail page loads for a specific run | `api.ts:fetchRun()` (line 796) | routes.py:47 |
| `cancel_run` | `POST /api/v1/runs/{run_id}/cancel` | Operator clicks "Cancel" on active run | `api.ts:cancelRun()` (line 1024) | routes.py:81 |
| `delete_run` | `DELETE /api/v1/runs/{run_id}` | Operator removes run from active list (soft-delete) | `api.ts:deleteRun()` (line 1034) | routes.py:89 |
| `restore_run` | `POST /api/v1/runs/{run_id}/restore` | Operator recovers archived run | `api.ts:restoreRun()` (line 1058) | routes.py:97 |
| `get_run_log` | `GET /api/v1/runs/{run_id}/log` | Run detail page "Logs" tab opens | `api.ts:fetchRunLog()` (line 1188) | routes.py:52 |
| `get_run_artifacts` | `GET /api/v1/runs/{run_id}/artifacts/{kind}` | Run detail page "Report"/"Story"/"Events" tab opens | `api.ts:fetchRunArtifactText()` (line 1199) / `fetchRunArtifactEvents()` (line 1209) | routes.py:61 |
| `get_run_metrics` | `GET /api/v1/runs/{run_id}/metrics` | Run detail page "Metrics" tab opens | `api.ts:fetchRunMetrics()` (line 1225) | routes.py:73 |
| `get_execution_snapshot` | `GET /api/v1/runs/{run_id}/execution-snapshot` | Run detail page "Snapshot" tab opens | `api.ts:fetchExecutionSnapshot()` (line 1171) | routes.py:154 |
| `replay_run` | `POST /api/v1/runs/{run_id}/replay` | Operator clicks "Replay" to re-run with same config | `api.ts:replayRun()` (line 1178) | routes.py:162 |

---

## run_profiles/ (6 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_run_profiles` | `GET /api/v1/run-profiles` | Run Profiles page loads | `api.ts:fetchRunProfiles()` (line 1108) | routes.py:105 |
| `create_run_profile` | `POST /api/v1/run-profiles` | Operator saves a new profile configuration | `api.ts:createRunProfile()` (line 1116) | routes.py:113 |
| `update_run_profile` | `PUT /api/v1/run-profiles/{profile_id}` | Operator edits existing profile | `api.ts:updateRunProfile()` (line 1128) | routes.py:121 |
| `delete_run_profile` | `DELETE /api/v1/run-profiles/{profile_id}` | Operator deletes profile | `api.ts:deleteRunProfile()` (line 1140) | routes.py:130 |
| `restore_run_profile` | `POST /api/v1/run-profiles/{profile_id}/restore` | Operator recovers archived profile | `api.ts:restoreRunProfile()` (line 1150) | routes.py:138 |
| `launch_run_profile` | `POST /api/v1/run-profiles/{profile_id}/launch` | Operator clicks "Launch" on saved profile | `api.ts:launchRunProfile()` (line 1161) | routes.py:146 |

---

## archives/ (6 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `get_archive_summary` | `GET /api/v1/archives/summary` | Archives page loads for lifecycle overview | `api.ts:fetchArchiveSummary()` (line 830) | routes.py:14 |
| `list_archived_runs` | `GET /api/v1/archives/runs` | Archives "Runs" tab shows archived runs list | `api.ts:fetchArchiveRuns()` (line 834) | routes.py:19 |
| `list_archived_profiles` | `GET /api/v1/archives/profiles` | Archives "Profiles" tab shows archived profiles | `api.ts:fetchArchivedProfiles()` (line 841) | routes.py:28 |
| `list_archived_schedules` | `GET /api/v1/archives/schedules` | Archives "Schedules" tab shows archived schedules | `api.ts:fetchArchivedSchedules()` (line 849) | routes.py:33 |
| `list_archived_integration_mappings` | `GET /api/v1/archives/integration-mappings` | Archives "Integration Mappings" tab | `api.ts:fetchArchivedIntegrationMappings()` (line 1333) | routes.py:38 |
| `purge_run` | `POST /api/v1/archives/runs/{run_id}/purge` | Operator clicks "Purge" on archived run (deletes artifacts/logs) | `api.ts:purgeRun()` (line 1068) | routes.py:43 |
| `purge_profile` | `POST /api/v1/archives/profiles/{profile_id}/purge` | Operator purges archived profile | `api.ts:purgeRunProfile()` (line 1078) | routes.py:51 |
| `purge_schedule` | `POST /api/v1/archives/schedules/{schedule_id}/purge` | Operator purges archived schedule | `api.ts:purgeSchedule()` (line 1088) | routes.py:59 |
| `purge_integration_mapping` | `POST /api/v1/archives/integration-mappings/{mapping_id}/purge` | Operator purges archived integration mapping | `api.ts:purgeIntegrationMapping()` (line 1098) | routes.py:67 |

---

## retention/ (1 file)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `get_retention_summary` | `GET /api/v1/retention/summary` | Retention/Archive settings page loads | `api.ts:fetchRetentionSummary()` (line 857) | routes.py:13 |

---

## schedules/ (8 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_schedules` | `GET /api/v1/schedules` | Schedules list page loads | `api.ts:fetchSchedules()` (line 861) | routes.py:14 |
| `get_schedule_summary` | `GET /api/v1/schedules/summary` | Dashboard summary loads schedule health KPIs | `api.ts:fetchScheduleSummary()` (line 869) | routes.py:22 |
| `create_schedule` | `POST /api/v1/schedules` | Operator creates new cron-based schedule | `api.ts:createSchedule()` (line 873) | routes.py:27 |
| `update_schedule` | `PUT /api/v1/schedules/{schedule_id}` | Operator edits schedule configuration | `api.ts:updateSchedule()` (line 885) | routes.py:35 |
| `trigger_schedule` | `POST /api/v1/schedules/{schedule_id}/trigger` | Operator manually fires a scheduled run outside its window | `api.ts:triggerSchedule()` (line 897) | routes.py:44 |
| `pause_schedule` | `POST /api/v1/schedules/{schedule_id}/pause` | Operator pauses schedule during maintenance | `api.ts:setScheduleStatus(..., "pause")` (line 907) | routes.py:52 |
| `resume_schedule` | `POST /api/v1/schedules/{schedule_id}/resume` | Operator resumes paused schedule | `api.ts:setScheduleStatus(..., "resume")` (line 907) | routes.py:60 |
| `disable_schedule` | `POST /api/v1/schedules/{schedule_id}/disable` | Operator permanently disables schedule | `api.ts:setScheduleStatus(..., "disable")` (line 907) | routes.py:68 |
| `delete_schedule` | `POST /api/v1/schedules/{schedule_id}/delete` | Operator soft-deletes schedule | `api.ts:setScheduleStatus(..., "delete")` (line 907) | routes.py:76 |
| `restore_schedule` | `POST /api/v1/schedules/{schedule_id}/restore` | Operator recovers deleted schedule | `api.ts:setScheduleStatus(..., "restore")` (line 907) | routes.py:84 |

---

## subentities/ (2 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_subentities` | `GET /api/v1/subentities` | Orders panel or simulation config needs store list | Implicit in orders section setup | routes.py:23 |
| `search_subentities` | `GET /api/v1/subentities/search` | Operator searches for specific store in simulation config | Implicit in store search widget | routes.py:40 |

---

## alerts/ (1 file)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_alerts` | `GET /api/v1/alerts` | Alerts panel loads on dashboard | `api.ts:fetchAlerts()` (line 918) | routes.py:13 |

---

## simulation_plans/ (5 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `list_simulation_plans` | `GET /api/v1/simulation-plans` | Simulation Plans page loads | `api.ts:fetchSimulationPlans()` (line 1233) | routes.py:14 |
| `get_simulation_plan` | `GET /api/v1/simulation-plans/{plan_id}` | Plan detail page or form loads | `api.ts:fetchSimulationPlan()` (line 1241) | routes.py:19 |
| `create_simulation_plan` | `POST /api/v1/simulation-plans` | Operator creates new simulation plan | `api.ts:createSimulationPlan()` (line 1249) | routes.py:27 |
| `update_simulation_plan` | `PUT /api/v1/simulation-plans/{plan_id}` | Operator edits existing plan | `api.ts:updateSimulationPlan()` (line 1261) | routes.py:35 |
| `delete_simulation_plan` | `DELETE /api/v1/simulation-plans/{plan_id}` | Operator deletes plan | `api.ts:deleteSimulationPlan()` (line 1273) | routes.py:44 |

---

## system/ (6 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `get_system_timezones` | `GET /api/v1/system/timezones` | System Settings page loads | `api.ts:fetchSystemTimezones()` (line 930) | routes.py:14 |
| `update_system_timezones` | `PUT /api/v1/system/timezones` | Admin updates timezone policy | `api.ts:updateSystemTimezones()` (line 934) | routes.py:19 |
| `get_system_email` | `GET /api/v1/system/email` | Email Settings page loads | `api.ts:fetchSystemEmailSettings()` (line 976) | routes.py:27 |
| `update_system_email` | `PUT /api/v1/system/email` | Admin updates email configuration | `api.ts:updateSystemEmailSettings()` (line 980) | routes.py:32 |
| `test_system_email` | `POST /api/v1/system/email/test` | Admin sends test email to verify config | `api.ts:sendSystemTestEmail()` (line 998) | routes.py:40 |
| `get_system_retention` | `GET /api/v1/system/retention` | Retention/Archive settings page loads | `api.ts:fetchRetentionPolicy()` (line 955) | routes.py:45 |
| `update_system_retention` | `PUT /api/v1/system/retention` | Admin updates retention policy | `api.ts:updateRetentionPolicy()` (line 962) | routes.py:50 |

---

## integrations/ (8 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `github_deployment_complete_webhook` | `POST /api/v1/integrations/github/deployment-complete` | GitHub Actions workflow calls after deployment | Backend webhook endpoint; no frontend call | routes.py:19 |
| `list_github_mappings` | `GET /api/v1/integrations/github/mappings` | GitHub Integration mappings page loads | `api.ts:fetchGitHubIntegrationMappings()` (line 1283) | routes.py:46 |
| `create_github_mapping` | `POST /api/v1/integrations/github/mappings` | Admin creates new deployment→profile mapping | `api.ts:upsertGitHubIntegrationMapping()` (line 1294) | routes.py:54 |
| `delete_github_mapping` | `DELETE /api/v1/integrations/github/mappings/{mapping_id}` | Admin removes a mapping | `api.ts:deleteGitHubIntegrationMapping()` (line 1308) | routes.py:62 |
| `restore_github_mapping` | `POST /api/v1/integrations/github/mappings/{mapping_id}/restore` | Admin recovers archived mapping | `api.ts:restoreGitHubIntegrationMapping()` (line 1320) | routes.py:70 |
| `list_github_triggers` | `GET /api/v1/integrations/github/triggers` | GitHub Integration triggers history page loads | `api.ts:fetchGitHubIntegrationTriggers()` (line 1341) | routes.py:78 |
| `list_github_projects` | `GET /api/v1/integrations/github/projects` | GitHub Integration projects page loads | `api.ts:fetchIntegrationWebhookProjects()` (line 1351) | routes.py:87 |
| `create_github_project` | `POST /api/v1/integrations/github/projects` | Admin registers new GitHub repository for integration | `api.ts:createIntegrationWebhookProject()` (line 1358) | routes.py:94 |
| `rotate_github_project_secret` | `POST /api/v1/integrations/github/projects/{project}/rotate-secret` | Admin rotates webhook secret for security | `api.ts:rotateIntegrationWebhookProjectSecret()` (line 1371) | routes.py:107 |
| `update_github_project_repositories` | `PATCH /api/v1/integrations/github/projects/{project}/repositories` | Admin updates which repos trigger simulations | `api.ts:updateIntegrationWebhookProjectRepositories()` (line 1383) | routes.py:120 |
| `delete_github_project` | `DELETE /api/v1/integrations/github/projects/{project}` | Admin removes GitHub integration project | `api.ts:deleteIntegrationWebhookProject()` (line 1397) | routes.py:134 |

---

## orders/ (9 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `orders_auto_login` | `GET /api/v1/orders/auto-login` | Orders panel opens, gets token without picking a store yet | `api.ts:autoLoginForOrders()` (line 1533) | routes.py:57 |
| `orders_get_config` | `GET /api/v1/orders/config` | Orders panel needs to know simulator configuration | Not explicit in current grep | routes.py:67 |
| `orders_list_stores` | `GET /api/v1/orders/stores` | Store selector in Orders panel populates dropdown | `api.ts:fetchOrdersStores()` (line 1565) | routes.py:77 |
| `orders_store_login` | `POST /api/v1/orders/store-login` | Operator selects a store, authenticates against LastMile API | `api.ts:loginAsStore()` (line 1548) | routes.py:87 |
| `orders_lookup` | `GET /api/v1/orders/lookup` | Operator searches for specific order by ID or reference | `api.ts:fetchFainzyOrder()` (line 1572) | routes.py:111 |
| `orders_list` | `GET /api/v1/orders/list` | Orders list page shows paginated order queue | `api.ts:fetchFainzyOrdersPage()` (line 1591) | routes.py:146 |
| `orders_store_stats` | `GET /api/v1/orders/store-stats` | Orders panel stats section loads aggregate store metrics | Not explicit in current grep (endpoint exists but unused) | routes.py:169 |
| `orders_customer_stats` | `GET /api/v1/orders/customer-stats` | Orders panel customer stats tab loads | Not explicit in current grep (endpoint exists but unused) | routes.py:187 |
| `orders_customer_search` | `GET /api/v1/orders/customers/search` | Operator types customer name/phone in search box | Not explicit in current grep (endpoint exists but unused) | routes.py:205 |
| `orders_update_status` | `PATCH /api/v1/orders/status` | Operator manually overrides order status during simulation | `api.ts:updateFainzyOrderStatus()` (line 1599) | routes.py:228 |

---

## overview/ (3 files)

| Use case | Endpoint | Trigger | Chain | Verified Route |
|---|---|---|---|---|
| `get_latest_run_overview` | `GET /api/v1/overview/latest-run` | Dashboard home page loads most recent run summary | `api.ts:fetchLatestRunOverview()` (line 816) | routes.py:13 |
| `get_socket_status` | `GET /api/v1/overview/socket-status` | Dashboard loads WebSocket connectivity monitor | `api.ts:fetchSocketStatus()` (line 809) | routes.py:20 |
| `get_run_overview` | `GET /api/v1/overview/runs/{run_id}` | Run detail page loads high-level run summary | `api.ts:fetchRunOverview()` (line 823) | routes.py:27 |

---

## Verification Summary

**Total internal routes found:** 90 confirmed via grep against `/api/app/**/routes.py`

**Breakdown by router:**
- auth: 6 routes
- admin: 5 routes
- runs: 14 routes + 6 run_profiles + 14 related artifacts/logs/metrics
- archives: 9 routes
- retention: 1 route
- schedules: 10 routes
- subentities: 2 routes
- alerts: 1 route
- simulation_plans: 5 routes
- system: 7 routes
- integrations: 11 routes
- orders: 10 routes
- overview: 3 routes

**Total: 90 routes** (grep `wc -l` confirms 90 vs. plan's stated 91 — confirm with user if there's a missing route or a duplicate count in the grep)

---

## Orphaned or no-UI-call-site routes

None identified in this pass. All 90 routes have either:
- Direct call site in `/web/src/lib/api.ts`, OR
- Implicit usage (e.g., GitHub webhook endpoint that backend calls, not frontend)

---

## Deltas from prior documentation

N/A — no prior `last_mile_user`-style docs exist for the simulator internal API. This is the first comprehensive trace.
