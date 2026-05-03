export type RunRow = {
  id: number;
  flow: string;
  plan: string;
  timing: string;
  mode: string | null;
  store_id: string | null;
  phone: string | null;
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

export type DashboardSummary = {
  total_runs: number;
  status_breakdown: Record<string, number>;
  flow_breakdown: Record<string, number>;
  success_rate: number;
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

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchFlows(): Promise<string[]> {
  const payload = await unwrap<{ flows: string[] }>(await fetch("/api/v1/flows"));
  return payload.flows;
}

export async function fetchRuns(): Promise<RunRow[]> {
  const payload = await unwrap<{ runs: RunRow[] }>(await fetch("/api/v1/runs?limit=200"));
  return payload.runs;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return unwrap<DashboardSummary>(await fetch("/api/v1/dashboard/summary"));
}

export async function createRun(request: RunCreateRequest): Promise<RunRow> {
  return unwrap<RunRow>(
    await fetch("/api/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    })
  );
}

export async function cancelRun(runId: number): Promise<void> {
  await unwrap(
    await fetch(`/api/v1/runs/${runId}/cancel`, {
      method: "POST"
    })
  );
}

export async function fetchRunLog(runId: number): Promise<string> {
  const payload = await unwrap<{ run_id: number; log: string }>(
    await fetch(`/api/v1/runs/${runId}/log?tail=300`)
  );
  return payload.log;
}

export async function fetchRunArtifactText(
  runId: number,
  kind: "report" | "story"
): Promise<RunArtifactResponse<string>> {
  return unwrap<RunArtifactResponse<string>>(
    await fetch(`/api/v1/runs/${runId}/artifacts/${kind}`)
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
      `/api/v1/runs/${runId}/artifacts/events?offset=${offset}&limit=${limit}&compact=${compact ? "true" : "false"}`
    )
  );
}

export async function fetchRunMetrics(runId: number): Promise<{
  run_id: number;
  available: boolean;
  metrics: RunMetrics;
}> {
  return unwrap(await fetch(`/api/v1/runs/${runId}/metrics`));
}
