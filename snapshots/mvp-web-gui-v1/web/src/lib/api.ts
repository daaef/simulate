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
  const payload = await unwrap<{ runs: RunRow[] }>(await fetch("/api/v1/runs?limit=50"));
  return payload.runs;
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

