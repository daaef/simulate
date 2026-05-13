"use client";

import Link from "next/link";
import type { LatestRunOverview } from "../../lib/api";

function statusClass(status?: string | null): string {
  const normalized = (status || "").toLowerCase();
  if (normalized === "succeeded") return "status-success";
  if (normalized === "failed" || normalized === "deleted") return "status-danger";
  if (normalized === "queued" || normalized === "running" || normalized === "cancelling") return "status-warning";
  return "status-info";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

function commandPreview(command?: string | null): string {
  if (!command) return "No command recorded.";
  return command.length > 220 ? `${command.slice(0, 220)}...` : command;
}

function runContextChips(run: NonNullable<LatestRunOverview["run"]>): string[] {
  const chips: string[] = [];
  const context = (run.trigger_context || {}) as Record<string, unknown>;

  const profileName = (context.profile_name as string | undefined) || (run.profile_id ? `#${run.profile_id}` : undefined);
  if (profileName) chips.push(`profile:${profileName}`);

  const scheduleName = (context.schedule_name as string | undefined) || (run.schedule_id ? `#${run.schedule_id}` : undefined);
  if (scheduleName) chips.push(`schedule:${scheduleName}`);

  const routeFromContext = (() => {
    const project = context.project as string | undefined;
    const environment = context.environment as string | undefined;
    if (project && environment) return `${project}/${environment}`;
    return undefined;
  })();
  const integrationRoute = context.route as string | undefined;
  const route = routeFromContext
    || integrationRoute
    || (run.trigger_source === "github" ? run.trigger_label || undefined : undefined);
  if (route) chips.push(`route:${route}`);

  return chips;
}

export default function LatestRunHero({ overview }: { overview: LatestRunOverview }) {
  const run = overview.run;
  if (!run) {
    return (
      <article className="panel latest-run-hero">
        <div>
          <p className="eyebrow">Latest Run</p>
          <h2>No runs yet</h2>
          <p className="muted">Launch a simulator run to populate this overview.</p>
        </div>
      </article>
    );
  }

  return (
    <article className="panel latest-run-hero">
      <div className="latest-run-hero-main">
        <div>
          <p className="eyebrow">Latest Run</p>
          <div className="latest-run-title-row">
            <h2>Run #{run.id}</h2>
            <span className={`status-pill ${statusClass(run.status)}`}>{run.status}</span>
          </div>
          <p className="muted">
            {run.flow || "unknown flow"} · {run.mode || "default mode"} · {run.timing || "default timing"}
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
            {runContextChips(run).map((chip) => <span key={chip} className="chip">{chip}</span>)}
          </div>
        </div>

        <Link href={`/runs/${run.id}`} className="hero-link">
          Open run detail
        </Link>
      </div>

      <div className="latest-run-meta-grid">
        <div>
          <span>Started</span>
          <strong>{formatDate(run.started_at || run.created_at)}</strong>
        </div>
        <div>
          <span>Finished</span>
          <strong>{formatDate(run.finished_at)}</strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>{formatDuration(run.duration_seconds)}</strong>
        </div>
        <div>
          <span>Exit</span>
          <strong>{run.exit_code ?? "—"}</strong>
        </div>
      </div>

      <pre className="artifact command-preview">{commandPreview(run.command)}</pre>

      {run.error ? (
        <div className="error-banner" style={{ padding: "10px 12px" }}>
          {run.error}
        </div>
      ) : null}
    </article>
  );
}
