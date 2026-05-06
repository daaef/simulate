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
};

export type RunCreateRequest = {
  flow: string;
  plan: string;
  timing: "fast" | "realistic";
  mode?: "trace" | "load";
  store_id?: string;
  phone?: string;
  all_users?: boolean;
  no_auto_provision?: boolean;
  post_order_actions?: boolean;
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
  store_id: string | null;
  phone: string | null;
  all_users: boolean;
  no_auto_provision: boolean;
  post_order_actions: boolean | null;
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
  store_id?: string;
  phone?: string;
  all_users?: boolean;
  no_auto_provision?: boolean;
  post_order_actions?: boolean;
  extra_args?: string[];
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
  status: string;
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

export async function fetchFlows(): Promise<string[]> {
  const payload = await unwrap<{ flows: string[] }>(await fetch("/api/v1/flows", withSession()), "flows");
  return payload.flows;
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

export async function fetchArchiveSummary(): Promise<ArchiveSummary> {
  return unwrap<ArchiveSummary>(await fetch("/api/v1/archives/summary", withSession()), "archives-summary");
}

export async function fetchRetentionSummary(): Promise<RetentionSummary> {
  return unwrap<RetentionSummary>(await fetch("/api/v1/retention/summary", withSession()), "retention-summary");
}

export async function fetchHealth(): Promise<HealthResponse> {
  return unwrap<HealthResponse>(await fetch("/healthz"), "healthz");
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
  message: string;
}> {
  return unwrap<{
    run_id: number;
    deleted: boolean;
    deleted_files: string[];
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
