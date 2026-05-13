export type RunRow = {
  id: number;
  flow: string;
  plan: string;
  timing: string;
  mode: string | null;
  store_id: string | null;
  phone: string | null;
  store_phone: string | null;
  user_name: string | null;
  store_name: string | null;
  all_users: boolean;
  no_auto_provision: boolean;
  enforce_websocket_gates: boolean;
  post_order_actions: boolean | null;
  extra_args: string[];
  status: string;
  command: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  log_path: string | null;
  report_path: string | null;
  story_path: string | null;
  events_path: string | null;
  error: string | null;
  execution_snapshot?: Record<string, unknown> | null;
  trigger_source?: "manual" | "profile" | "schedule" | "github" | "replay" | string | null;
  trigger_label?: string | null;
  trigger_context?: Record<string, unknown>;
  profile_id?: number | null;
  schedule_id?: number | null;
  integration_trigger_id?: number | null;
  launched_by_user_id?: number | null;
};

export type RunCreateRequest = {
  flow: string;
  plan: string;
  timing: "fast" | "realistic";
  mode?: "trace" | "load";
  suite?: string;
  scenarios?: string[];
  store_id?: string;
  phone?: string;
  all_users?: boolean;
  strict_plan?: boolean;
  skip_app_probes?: boolean;
  skip_store_dashboard_probes?: boolean;
  no_auto_provision?: boolean;
  enforce_websocket_gates?: boolean;
  post_order_actions?: boolean;
  users?: number;
  orders?: number;
  interval?: number;
  reject?: number;
  continuous?: boolean;
  extra_args?: string[];
};

export type RunProfile = {
  id: number;
  user_id?: number | null;
  name: string;
  description: string | null;
  flow: string;
  plan: string;
  timing: "fast" | "realistic";
  mode: "trace" | "load" | null;
  suite: string | null;
  scenarios: string[];
  store_id: string | null;
  phone: string | null;
  all_users: boolean;
  strict_plan: boolean;
  skip_app_probes: boolean;
  skip_store_dashboard_probes: boolean;
  no_auto_provision: boolean;
  enforce_websocket_gates: boolean;
  post_order_actions: boolean | null;
  users: number | null;
  orders: number | null;
  interval: number | null;
  reject: number | null;
  continuous: boolean;
  extra_args: string[];
  created_at: string;
  updated_at: string;
};

export type RunProfileUpsertRequest = {
  name: string;
  description?: string;
  flow: string;
  plan: string;
  timing: "fast" | "realistic";
  mode?: "trace" | "load";
  suite?: string;
  scenarios?: string[];
  store_id?: string;
  phone?: string;
  all_users?: boolean;
  strict_plan?: boolean;
  skip_app_probes?: boolean;
  skip_store_dashboard_probes?: boolean;
  no_auto_provision?: boolean;
  enforce_websocket_gates?: boolean;
  post_order_actions?: boolean;
  users?: number;
  orders?: number;
  interval?: number;
  reject?: number;
  continuous?: boolean;
  extra_args?: string[];
};

export type FlowCapability = {
  flow: string;
  resolved_mode: "trace" | "load";
  default_suite: string | null;
  default_scenarios: string[];
  allowed_optional_flags: string[];
  available_suites: string[];
  available_scenarios: string[];
};

export type FlowsResponse = {
  flows: string[];
  capabilities: Record<string, FlowCapability>;
};

export type DashboardSummary = {
  total_runs: number;
  status_breakdown: Record<string, number>;
  flow_breakdown: Record<string, number>;
  success_rate: number;
  active_runs?: number;
  failed_last_24h?: number;
  degraded_runs?: number;
  archive_backlog?: number;
  purge_backlog?: number;
};

export type ArchiveSummary = {
  policy_days: {
    active: number;
    archive: number;
  };
  counts: {
    active: number;
    archive_ready: number;
    purge_ready: number;
  };
};

export type RetainedRunSummary = {
  verdict: string;
  flow: string | null;
  schedule_or_campaign_source: string;
  actor_summary: {
    store_id: string | null;
    phone: string | null;
    store_name: string | null;
    user_name: string | null;
  };
  duration: {
    seconds: number | null;
    started_at: string | null;
    finished_at: string | null;
  };
  latency: {
    avg_http_latency_ms: number | null;
  };
  top_failure_signals: string[];
  narrative: string;
  audit_attribution: {
    run_id: number;
    created_at: string;
    artifact_available: boolean;
  };
};

export type ArchiveRun = RunRow & {
  lifecycle_state?: "active" | "archive_candidate" | "raw_purge_candidate";
  age_days?: number | null;
  retained_summary?: RetainedRunSummary;
};

export type RetentionSummary = {
  policies: {
    active_days: number;
    archive_days: number;
  };
  queue: {
    archive_ready: number;
    purge_ready: number;
    artifact_backed_runs: number;
  };
  lifecycle_states?: {
    active: number;
    archive_candidate: number;
    raw_purge_candidate: number;
  };
  retained_summary_fields?: string[];
  purge_safety?: {
    mode: string;
    raw_artifact_purge_enabled: boolean;
    retained_summary_required: boolean;
  };
  status: string;
};

export type ScheduleStatus = "active" | "paused" | "disabled" | "deleted";
export type ScheduleType = "simple" | "campaign";
export type ScheduleCadence = "hourly" | "daily" | "weekdays" | "weekly" | "monthly" | "custom";
export type SchedulePeriod = "hourly" | "daily" | "weekly" | "monthly";
export type ScheduleStopRule = "never" | "end_at" | "duration";
export type ScheduleRepeatRule = "none" | "daily" | "weekly" | "monthly" | "annually" | "weekdays" | "custom";

export type CampaignStep = {
  profile_id: number;
  repeat_count: number;
  spacing_seconds: number;
  timeout_seconds: number;
  failure_policy: "continue" | "stop";
  execution_mode: "saved_profile" | "exact_snapshot";
};

export type Schedule = {
  id: number;
  user_id?: number | null;
  name: string;
  description: string | null;
  schedule_type: ScheduleType;
  status: ScheduleStatus;
  profile_id: number | null;
  anchor_start_at: string | null;
  period: SchedulePeriod | null;
  stop_rule: ScheduleStopRule | null;
  end_at: string | null;
  duration_seconds: number | null;
  runs_per_period: number;
  repeat?: ScheduleRepeatRule | null;
  all_day?: boolean;
  recurrence_config?: Record<string, unknown>;
  run_slots?: Record<string, unknown>[];
  cadence: ScheduleCadence;
  timezone: string;
  active_from: string | null;
  active_until: string | null;
  run_window_start: string | null;
  run_window_end: string | null;
  custom_anchor_at: string | null;
  custom_every_n_days: number | null;
  blackout_dates: string[];
  failure_policy: "continue" | "stop";
  campaign_steps: CampaignStep[];
  last_triggered_at: string | null;
  next_run_at: string | null;
  next_run_reason: string;
  execution_mode_label: "automatic" | "manual_only";
  current_period_runs?: string[];
  requested_runs_per_period?: number;
  feasible_runs_per_period?: number;
  schedule_warnings?: string[];
  created_at: string;
  updated_at: string;
};

export type ScheduleUpsertRequest = {
  name: string;
  description?: string;
  schedule_type: ScheduleType;
  profile_id?: number;
  anchor_start_at?: string;
  period?: SchedulePeriod;
  stop_rule?: ScheduleStopRule;
  end_at?: string;
  duration_seconds?: number;
  runs_per_period?: number;
  repeat?: ScheduleRepeatRule;
  all_day?: boolean;
  recurrence_config?: Record<string, unknown>;
  run_slots?: Record<string, unknown>[];
  cadence?: ScheduleCadence;
  timezone?: string;
  active_from?: string;
  active_until?: string;
  run_window_start?: string;
  run_window_end?: string;
  custom_anchor_at?: string;
  custom_every_n_days?: number;
  blackout_dates?: string[];
  failure_policy?: "continue" | "stop";
  campaign_steps?: CampaignStep[];
};

export type ScheduleExecution = {
  id: number;
  schedule_id: number;
  run_id: number | null;
  execution_chain_key?: string | null;
  status: string;
  detail: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
};

export type ScheduleSummary = {
  total: number;
  status_breakdown: Record<string, number>;
  type_breakdown: Record<string, number>;
  health: {
    active: number;
    paused: number;
    disabled: number;
    degraded_campaigns: number;
  };
  recent_executions: ScheduleExecution[];
  recent_schedule_states?: Array<{
    schedule_id: number;
    schedule_name?: string | null;
    schedule_phase: string;
    latest_run_id: number | null;
    latest_run_status: string | null;
    last_triggered_at: string | null;
    latest_run_finished_at: string | null;
  }>;
};

export type AlertItem = {
  id: string;
  domain: "runs" | "retention" | "schedules" | string;
  severity: "critical" | "warning" | "info" | string;
  title: string;
  message: string;
  href: string;
  created_at: string;
};

export type RunMetrics = {
  total_events: number;
  failed_events: number;
  http_calls: number;
  websocket_events: number;
  avg_http_latency_ms?: number;
  top_actors: Record<string, number>;
  top_actions: Record<string, number>;
};

export type ActorSummary = {
  key: "user" | "store" | "robot" | string;
  label: string;
  identity: Record<string, unknown>;
  events: number;
  failed_events: number;
  latest_action?: string | null;
  latest_status?: string | null;
  latest_at?: string | null;
};

export type HttpProtocolSummary = {
  total: number;
  failed: number;
  success: number;
  avg_latency_ms?: number | null;
  status_groups: Record<string, number>;
  slowest?: {
    endpoint: string;
    method?: string | null;
    status?: string | number | null;
    latency_ms?: number | null;
  } | null;
  top_endpoints: Array<{ endpoint: string; count: number }>;
  top_failed_endpoints: Array<{ endpoint: string; count: number }>;
};

export type WebSocketProtocolSummary = {
  total: number;
  expected: number;
  matched: number;
  missed: number;
  sources: Array<{ source: string; count: number }>;
  latest?: {
    at?: string | null;
    action?: string | null;
    status?: string | null;
    message?: string | null;
  } | null;
};

export type LifecycleStep = {
  at?: string | null;
  actor: string;
  label: string;
  status?: string | number | null;
  ok: boolean;
  endpoint?: string | null;
  latency_ms?: number | null;
};

export type LatestRunIssue = {
  severity: string;
  code: string;
  message: string;
  actor?: string | null;
  at?: string | null;
  route?: string | null;
};

export type LatestRunOverview = {
  run: (RunRow & { duration_seconds?: number | null }) | null;
  metrics: RunMetrics | null;
  actors: Record<string, ActorSummary>;
  protocols: {
    http: Partial<HttpProtocolSummary>;
    websocket: Partial<WebSocketProtocolSummary>;
  };
  lifecycle: LifecycleStep[];
  issues: LatestRunIssue[];
  run_meta?: Record<string, unknown>;
};

export type RunArtifactResponse<T> = {
  run_id: number;
  kind: "report" | "story" | "events";
  available: boolean;
  path?: string;
  count?: number;
  total_count?: number;
  offset?: number;
  limit?: number;
  content: T | null;
};

export type HealthResponse = {
  status: string;
  project_dir: string;
  simulator_workdir: string;
  db_path: string;
};

export type SimulationPlanContent = Record<string, unknown>;

export type SimulationPlan = {
  id: string;
  name: string;
  path: string;
  content: SimulationPlanContent;
};

export type SimulationPlanUpsertRequest = {
  name: string;
  content: SimulationPlanContent;
};

export type IntegrationMapping = {
  id: number;
  project: string;
  environment: string;
  profile_id: number;
  enabled: boolean;
  profile_name?: string | null;
  created_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
};

export type IntegrationMappingUpsertRequest = {
  project: string;
  environment: string;
  profile_id: number;
  enabled: boolean;
};

export type GitHubIntegrationTrigger = {
  id: number;
  project?: string | null;
  environment?: string | null;
  repository?: string | null;
  status: string;
  reason?: string | null;
  run_id?: number | null;
  deployment_id?: string | number | null;
  delivery_id?: string | null;
  created_at?: string | null;
  meta?: Record<string, unknown> | null;
  [key: string]: unknown;
};

export type TimezonePolicyMode = "all" | "allowlist";

export type SystemTimezonesPolicy = {
  mode: TimezonePolicyMode;
  allowed_timezones: string[] | null;
  available_timezones: string[];
};

export type EmailEventTrigger = "run_failed" | "schedule_launch_failed" | "critical_alert";

export type SystemEmailSettings = {
  email_enabled: boolean;
  email_from_email: string;
  email_from_name: string;
  email_subject_prefix: string;
  email_recipients: string[];
  email_event_triggers: EmailEventTrigger[];
};

export class ApiRequestError extends Error {
  source: string;
  status: number;
  details: string | null;

  constructor(source: string, status: number, message: string, details: string | null = null) {
    super(message);
    this.name = "ApiRequestError";
    this.source = source;
    this.status = status;
    this.details = details;
  }
}

function truncateText(value: string, maxLen = 1200): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLen) return compact;
  return `${compact.slice(0, maxLen - 3)}...`;
}

function looksLikeHtml(value: string): boolean {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) return false;
  return (
    trimmed.startsWith("<!doctype html") ||
    trimmed.startsWith("<html") ||
    (trimmed.includes("<head") && trimmed.includes("<body"))
  );
}

function stripHtml(value: string): string {
  return truncateText(value.replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&"));
}

function withSession(init: RequestInit = {}): RequestInit {
  return {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  };
}

function statusMessage(status: number): string {
  if (status === 502) return "Gateway failed to reach the backend API.";
  if (status === 503) return "Backend API is temporarily unavailable.";
  if (status === 504) return "Gateway timed out while waiting for the backend API.";
  if (status >= 500) return `Backend request failed (HTTP ${status}).`;
  if (status >= 400) return `Request was rejected (HTTP ${status}).`;
  return `Request failed (HTTP ${status}).`;
}

function parseStructuredError(raw: string): string | null {
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>;
    const detail = payload["detail"];
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    const message = payload["message"];
    if (typeof message === "string" && message.trim()) return message.trim();
    const error = payload["error"];
    if (typeof error === "string" && error.trim()) return error.trim();
  } catch {
    return null;
  }
  return null;
}

function toApiError(source: string, response: Response, rawPayload: string): ApiRequestError {
  const raw = rawPayload || "";
  const structured = parseStructuredError(raw);
  const isHtml = looksLikeHtml(raw);
  if (isHtml) {
    const details = stripHtml(raw);
    return new ApiRequestError(source, response.status, statusMessage(response.status), details || null);
  }
  if (structured) {
    return new ApiRequestError(
      source,
      response.status,
      truncateText(structured, 240),
      truncateText(raw, 1200) || null
    );
  }
  const fallback = truncateText(raw, 240);
  if (fallback) {
    return new ApiRequestError(source, response.status, fallback, truncateText(raw, 1200));
  }
  return new ApiRequestError(source, response.status, statusMessage(response.status), null);
}

async function unwrap<T>(response: Response, source: string): Promise<T> {
  if (!response.ok) {
    const payload = await response.text();
    throw toApiError(source, response, payload);
  }
  return (await response.json()) as T;
}

export async function fetchFlows(): Promise<FlowsResponse> {
  return unwrap<FlowsResponse>(await fetch("/api/v1/flows", withSession()), "flows");
}

export async function fetchRuns(limit: number = 50, offset: number = 0): Promise<{ runs: RunRow[]; total: number; limit: number; offset: number }> {
  const payload = await unwrap<{ runs: RunRow[]; total: number; limit: number; offset: number }>(
    await fetch(`/api/v1/runs?limit=${limit}&offset=${offset}`, withSession()),
    "runs"
  );
  return payload;
}

export async function fetchRun(runId: number): Promise<RunRow> {
  return unwrap<RunRow>(await fetch(`/api/v1/runs/${runId}`, withSession()), "run");
}

export async function fetchRunsCount(): Promise<number> {
  const payload = await unwrap<{ count: number }>(await fetch("/api/v1/runs/count", withSession()), "runs-count");
  return payload.count;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return unwrap<DashboardSummary>(await fetch("/api/v1/dashboard/summary", withSession()), "dashboard-summary");
}

export async function fetchLatestRunOverview(): Promise<LatestRunOverview> {
  return unwrap<LatestRunOverview>(
    await fetch("/api/v1/overview/latest-run", withSession()),
    "latest-run-overview"
  );
}

export async function fetchArchiveSummary(): Promise<ArchiveSummary> {
  return unwrap<ArchiveSummary>(await fetch("/api/v1/archives/summary", withSession()), "archives-summary");
}

export async function fetchArchiveRuns(limit: number = 50, offset: number = 0): Promise<{ runs: ArchiveRun[]; total: number; limit: number; offset: number }> {
  return unwrap<{ runs: ArchiveRun[]; total: number; limit: number; offset: number }>(
    await fetch(`/api/v1/archives/runs?limit=${limit}&offset=${offset}`, withSession()),
    "archives-runs"
  );
}

export async function fetchRetentionSummary(): Promise<RetentionSummary> {
  return unwrap<RetentionSummary>(await fetch("/api/v1/retention/summary", withSession()), "retention-summary");
}

export async function fetchSchedules(includeDeleted: boolean = false): Promise<Schedule[]> {
  const payload = await unwrap<{ schedules: Schedule[] }>(
    await fetch(`/api/v1/schedules?include_deleted=${includeDeleted ? "true" : "false"}`, withSession()),
    "schedules"
  );
  return payload.schedules;
}

export async function fetchScheduleSummary(): Promise<ScheduleSummary> {
  return unwrap<ScheduleSummary>(await fetch("/api/v1/schedules/summary", withSession()), "schedules-summary");
}

export async function createSchedule(request: ScheduleUpsertRequest): Promise<Schedule> {
  const payload = await unwrap<{ schedule: Schedule }>(
    await fetch("/api/v1/schedules", {
      method: "POST",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "create-schedule"
  );
  return payload.schedule;
}

export async function updateSchedule(scheduleId: number, request: ScheduleUpsertRequest): Promise<Schedule> {
  const payload = await unwrap<{ schedule: Schedule }>(
    await fetch(`/api/v1/schedules/${scheduleId}`, {
      method: "PUT",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "update-schedule"
  );
  return payload.schedule;
}

export async function triggerSchedule(scheduleId: number): Promise<{ schedule: Schedule; execution: ScheduleExecution; run?: RunRow; runs: RunRow[] }> {
  return unwrap<{ schedule: Schedule; execution: ScheduleExecution; run?: RunRow; runs: RunRow[] }>(
    await fetch(`/api/v1/schedules/${scheduleId}/trigger`, {
      method: "POST",
      ...withSession(),
    }),
    "trigger-schedule"
  );
}

export async function setScheduleStatus(scheduleId: number, action: "pause" | "resume" | "disable" | "delete" | "restore"): Promise<Schedule> {
  const payload = await unwrap<{ schedule: Schedule }>(
    await fetch(`/api/v1/schedules/${scheduleId}/${action}`, {
      method: "POST",
      ...withSession(),
    }),
    `${action}-schedule`
  );
  return payload.schedule;
}

export async function fetchAlerts(): Promise<AlertItem[]> {
  const payload = await unwrap<{ alerts: AlertItem[]; total: number }>(
    await fetch("/api/v1/alerts", withSession()),
    "alerts"
  );
  return payload.alerts;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return unwrap<HealthResponse>(await fetch("/healthz"), "healthz");
}

export async function fetchSystemTimezones(): Promise<SystemTimezonesPolicy> {
  return unwrap<SystemTimezonesPolicy>(await fetch("/api/v1/system/timezones", withSession()), "system-timezones");
}

export async function updateSystemTimezones(request: {
  mode: TimezonePolicyMode;
  allowed_timezones?: string[];
}): Promise<SystemTimezonesPolicy> {
  return unwrap<SystemTimezonesPolicy>(
    await fetch("/api/v1/system/timezones", {
      method: "PUT",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "system-timezones-update"
  );
}

export async function fetchSystemEmailSettings(): Promise<SystemEmailSettings> {
  return unwrap<SystemEmailSettings>(await fetch("/api/v1/system/email", withSession()), "system-email");
}

export async function updateSystemEmailSettings(request: {
  email_enabled: boolean;
  email_from_email: string;
  email_from_name: string;
  email_subject_prefix: string;
  email_recipients: string[] | string;
  email_event_triggers: EmailEventTrigger[];
}): Promise<SystemEmailSettings> {
  return unwrap<SystemEmailSettings>(
    await fetch("/api/v1/system/email", {
      method: "PUT",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "system-email-update"
  );
}

export async function sendSystemTestEmail(): Promise<{
  sent: boolean;
  recipients?: string[];
  subject?: string;
  reason?: string;
}> {
  return unwrap(
    await fetch("/api/v1/system/email/test", {
      method: "POST",
      ...withSession(),
    }),
    "system-email-test"
  );
}

export async function createRun(request: RunCreateRequest): Promise<RunRow> {
  return unwrap<RunRow>(
    await fetch("/api/v1/runs", {
      method: "POST",
      ...withSession(),
      body: JSON.stringify(request)
    }),
    "create-run"
  );
}

export async function cancelRun(runId: number): Promise<void> {
  await unwrap(
    await fetch(`/api/v1/runs/${runId}/cancel`, {
      method: "POST",
      ...withSession()
    }),
    "cancel-run"
  );
}

export async function deleteRun(runId: number): Promise<{
  run_id: number;
  deleted: boolean;
  deleted_files: string[];
  missing_files: string[];
  message: string;
}> {
  return unwrap<{
    run_id: number;
    deleted: boolean;
    deleted_files: string[];
    missing_files: string[];
    message: string;
  }>(
    await fetch(`/api/v1/runs/${runId}`, {
      method: "DELETE",
      ...withSession()
    }),
    "delete-run"
  );
}

export async function fetchRunProfiles(): Promise<RunProfile[]> {
  const payload = await unwrap<{ profiles: RunProfile[] }>(await fetch("/api/v1/run-profiles", withSession()), "run-profiles");
  return payload.profiles;
}

export async function createRunProfile(request: RunProfileUpsertRequest): Promise<RunProfile> {
  const payload = await unwrap<{ profile: RunProfile }>(
    await fetch("/api/v1/run-profiles", {
      method: "POST",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "create-run-profile"
  );
  return payload.profile;
}

export async function updateRunProfile(profileId: number, request: RunProfileUpsertRequest): Promise<RunProfile> {
  const payload = await unwrap<{ profile: RunProfile }>(
    await fetch(`/api/v1/run-profiles/${profileId}`, {
      method: "PUT",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "update-run-profile"
  );
  return payload.profile;
}

export async function deleteRunProfile(profileId: number): Promise<{ profile_id: number; deleted: boolean }> {
  return unwrap<{ profile_id: number; deleted: boolean }>(
    await fetch(`/api/v1/run-profiles/${profileId}`, {
      method: "DELETE",
      ...withSession(),
    }),
    "delete-run-profile"
  );
}

export async function launchRunProfile(profileId: number): Promise<{ profile: RunProfile; run: RunRow }> {
  return unwrap<{ profile: RunProfile; run: RunRow }>(
    await fetch(`/api/v1/run-profiles/${profileId}/launch`, {
      method: "POST",
      ...withSession(),
    }),
    "launch-run-profile"
  );
}

export async function fetchExecutionSnapshot(runId: number): Promise<{ run_id: number; available: boolean; snapshot: Record<string, unknown> }> {
  return unwrap<{ run_id: number; available: boolean; snapshot: Record<string, unknown> }>(
    await fetch(`/api/v1/runs/${runId}/execution-snapshot`, withSession()),
    "execution-snapshot"
  );
}

export async function replayRun(runId: number): Promise<{ source_run_id: number; run: RunRow; snapshot: Record<string, unknown> }> {
  return unwrap<{ source_run_id: number; run: RunRow; snapshot: Record<string, unknown> }>(
    await fetch(`/api/v1/runs/${runId}/replay`, {
      method: "POST",
      ...withSession(),
    }),
    "replay-run"
  );
}

export async function fetchRunLog(runId: number, tail?: number): Promise<{ available: boolean; log: string }> {
  const url = tail 
    ? `/api/v1/runs/${runId}/log?tail=${tail}`
    : `/api/v1/runs/${runId}/log?tail=300`;
  const payload = await unwrap<{ run_id: number; log: string }>(
    await fetch(url, withSession()),
    "run-log"
  );
  return { available: true, log: payload.log };
}

export async function fetchRunArtifactText(
  runId: number,
  kind: "report" | "story"
): Promise<RunArtifactResponse<string>> {
  return unwrap<RunArtifactResponse<string>>(
    await fetch(`/api/v1/runs/${runId}/artifacts/${kind}`, withSession()),
    `artifact-${kind}`
  );
}

export async function fetchRunArtifactEvents(
  runId: number,
  options?: { offset?: number; limit?: number; compact?: boolean }
): Promise<RunArtifactResponse<Array<Record<string, unknown>>>> {
  const offset = options?.offset ?? 0;
  const limit = options?.limit ?? 200;
  const compact = options?.compact ?? true;
  return unwrap<RunArtifactResponse<Array<Record<string, unknown>>>>(
    await fetch(
      `/api/v1/runs/${runId}/artifacts/events?offset=${offset}&limit=${limit}&compact=${compact ? "true" : "false"}`,
      withSession()
    ),
    "artifact-events"
  );
}

export async function fetchRunMetrics(runId: number): Promise<{
  run_id: number;
  available: boolean;
  metrics: RunMetrics;
}> {
  return unwrap(await fetch(`/api/v1/runs/${runId}/metrics`, withSession()), "run-metrics");
}

export async function fetchSimulationPlans(): Promise<SimulationPlan[]> {
  const payload = await unwrap<{ plans: SimulationPlan[] }>(
    await fetch("/api/v1/simulation-plans", withSession()),
    "simulation-plans"
  );
  return payload.plans;
}

export async function fetchSimulationPlan(planId: string): Promise<SimulationPlan> {
  const payload = await unwrap<{ plan: SimulationPlan }>(
    await fetch(`/api/v1/simulation-plans/${planId}`, withSession()),
    "simulation-plan"
  );
  return payload.plan;
}

export async function createSimulationPlan(request: SimulationPlanUpsertRequest): Promise<SimulationPlan> {
  const payload = await unwrap<{ plan: SimulationPlan }>(
    await fetch("/api/v1/simulation-plans", {
      method: "POST",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "create-simulation-plan"
  );
  return payload.plan;
}

export async function updateSimulationPlan(planId: string, request: SimulationPlanUpsertRequest): Promise<SimulationPlan> {
  const payload = await unwrap<{ plan: SimulationPlan }>(
    await fetch(`/api/v1/simulation-plans/${planId}`, {
      method: "PUT",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "update-simulation-plan"
  );
  return payload.plan;
}

export async function deleteSimulationPlan(planId: string): Promise<{ plan_id: string; deleted: boolean }> {
  return unwrap<{ plan_id: string; deleted: boolean }>(
    await fetch(`/api/v1/simulation-plans/${planId}`, {
      method: "DELETE",
      ...withSession(),
    }),
    "delete-simulation-plan"
  );
}

export async function fetchGitHubIntegrationMappings(): Promise<IntegrationMapping[]> {
  const payload = await unwrap<{ mappings: IntegrationMapping[] }>(
    await fetch("/api/v1/integrations/github/mappings", withSession()),
    "github-integration-mappings"
  );
  return payload.mappings;
}

export async function upsertGitHubIntegrationMapping(
  request: IntegrationMappingUpsertRequest
): Promise<IntegrationMapping> {
  const payload = await unwrap<{ mapping: IntegrationMapping }>(
    await fetch("/api/v1/integrations/github/mappings", {
      method: "POST",
      ...withSession(),
      body: JSON.stringify(request),
    }),
    "github-integration-mapping-upsert"
  );
  return payload.mapping;
}

export async function deleteGitHubIntegrationMapping(
  mappingId: number
): Promise<{ mapping_id: number; deleted: boolean }> {
  return unwrap<{ mapping_id: number; deleted: boolean }>(
    await fetch(`/api/v1/integrations/github/mappings/${mappingId}`, {
      method: "DELETE",
      ...withSession(),
    }),
    "github-integration-mapping-delete"
  );
}

export async function fetchGitHubIntegrationTriggers(
  limit = 50,
  offset = 0
): Promise<{ triggers: GitHubIntegrationTrigger[]; total?: number; limit?: number; offset?: number }> {
  return unwrap<{ triggers: GitHubIntegrationTrigger[]; total?: number; limit?: number; offset?: number }>(
    await fetch(`/api/v1/integrations/github/triggers?limit=${limit}&offset=${offset}`, withSession()),
    "github-integration-triggers"
  );
}
