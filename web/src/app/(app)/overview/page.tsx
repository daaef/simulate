"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { DistributionDonut } from "../../../components/charts/DistributionDonut";
import { HorizontalBarChart } from "../../../components/charts/HorizontalBarChart";
import { Sparkline } from "../../../components/charts/Sparkline";
import {
  ApiRequestError,
  fetchAlerts,
  fetchArchiveSummary,
  fetchDashboardSummary,
  fetchHealth,
  fetchRetentionSummary,
  fetchRuns,
  fetchScheduleSummary,
  type AlertItem,
  type ArchiveSummary,
  type DashboardSummary,
  type HealthResponse,
  type RetentionSummary,
  type RunRow,
  type ScheduleSummary,
} from "../../../lib/api";

function statusColor(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded" || normalized === "active") return "var(--chart-success)";
  if (normalized === "failed" || normalized === "degraded") return "var(--chart-danger)";
  if (normalized === "paused" || normalized === "cancelled" || normalized === "disabled") return "var(--chart-warning)";
  return "var(--chart-info)";
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded" || normalized === "active") return "status-success";
  if (normalized === "failed" || normalized === "deleted") return "status-danger";
  if (normalized === "paused" || normalized === "disabled" || normalized === "cancelled") return "status-warning";
  return "status-info";
}

function buildFailureTrend(runs: RunRow[]): { labels: string[]; points: number[] } {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    return date;
  });
  const labels = days.map((date) => date.toLocaleDateString(undefined, { month: "short", day: "numeric" }));
  const keys = days.map((date) => date.toISOString().slice(0, 10));
  const counts = new Map(keys.map((key) => [key, 0]));
  runs.forEach((run) => {
    if (run.status.toLowerCase() !== "failed") return;
    const key = new Date(run.created_at).toISOString().slice(0, 10);
    if (counts.has(key)) counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return { labels, points: keys.map((key) => counts.get(key) ?? 0) };
}

export default function OverviewPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [archiveSummary, setArchiveSummary] = useState<ArchiveSummary | null>(null);
  const [retentionSummary, setRetentionSummary] = useState<RetentionSummary | null>(null);
  const [scheduleSummary, setScheduleSummary] = useState<ScheduleSummary | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunRow[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [summaryPayload, healthPayload, archivePayload, retentionPayload, schedulePayload, alertsPayload, runsPayload] =
          await Promise.all([
            fetchDashboardSummary(),
            fetchHealth(),
            fetchArchiveSummary(),
            fetchRetentionSummary(),
            fetchScheduleSummary(),
            fetchAlerts(),
            fetchRuns(50, 0),
          ]);
        if (!active) return;
        setSummary(summaryPayload);
        setHealth(healthPayload);
        setArchiveSummary(archivePayload);
        setRetentionSummary(retentionPayload);
        setScheduleSummary(schedulePayload);
        setAlerts(alertsPayload);
        setRecentRuns(runsPayload.runs);
        setError(null);
      } catch (caughtError) {
        if (!active) return;
        const message =
          caughtError instanceof ApiRequestError
            ? caughtError.message
            : caughtError instanceof Error
              ? caughtError.message
              : "Failed to load overview";
        setError(message);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const cards = [
    { label: "Total Runs", value: summary?.total_runs ?? "--" },
    { label: "Success Rate", value: summary ? `${summary.success_rate}%` : "--" },
    { label: "Active Runs", value: summary?.active_runs ?? 0 },
    { label: "Failed 24h", value: summary?.failed_last_24h ?? 0 },
    { label: "Schedules", value: scheduleSummary?.total ?? 0 },
    { label: "Alerts", value: alerts.length },
  ];

  const chartData = useMemo(() => {
    const statuses = Object.entries(summary?.status_breakdown ?? {}).map(([label, value]) => ({
      label,
      value,
      color: statusColor(label),
    }));
    const flows = Object.entries(summary?.flow_breakdown ?? {}).map(([label, value]) => ({
      label,
      value,
      color: "var(--chart-info)",
    }));
    const succeeded = summary?.status_breakdown.succeeded ?? 0;
    const failed = summary?.status_breakdown.failed ?? 0;
    const cancelled = summary?.status_breakdown.cancelled ?? 0;
    const other = Math.max(0, (summary?.total_runs ?? 0) - succeeded - failed - cancelled);
    const backlog = [
      { label: "Archive", value: archiveSummary?.counts.archive_ready ?? 0, color: "var(--chart-warning)" },
      { label: "Raw purge", value: archiveSummary?.counts.purge_ready ?? 0, color: "var(--chart-danger)" },
    ];
    const schedules = [
      { label: "Active", value: scheduleSummary?.health.active ?? 0, color: "var(--chart-success)" },
      { label: "Paused", value: scheduleSummary?.health.paused ?? 0, color: "var(--chart-warning)" },
      { label: "Disabled", value: scheduleSummary?.health.disabled ?? 0, color: "var(--chart-info)" },
      { label: "Degraded", value: scheduleSummary?.health.degraded_campaigns ?? 0, color: "var(--chart-danger)" },
    ];
    return {
      statuses,
      flows,
      outcomes: [
        { label: "Succeeded", value: succeeded, color: "var(--chart-success)" },
        { label: "Failed", value: failed, color: "var(--chart-danger)" },
        { label: "Cancelled", value: cancelled, color: "var(--chart-warning)" },
        { label: "Other", value: other, color: "var(--chart-info)" },
      ],
      backlog,
      schedules,
      trend: buildFailureTrend(recentRuns),
    };
  }, [archiveSummary, recentRuns, scheduleSummary, summary]);

  const activeOrDegraded = recentRuns.filter((run) =>
    ["queued", "running", "cancelling", "failed"].includes(run.status.toLowerCase())
  );

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Operations Overview</h1>
        <p className="page-subtitle">Live simulator posture, backlog, schedule health, and recent failure pressure.</p>
      </section>

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      <section className="grid four">
        {cards.map((card) => (
          <article key={card.label} className="panel stat">
            <div className="stat-label">{card.label}</div>
            <div className="stat-value">{card.value}</div>
          </article>
        ))}
      </section>

      <section className="chart-grid">
        <article className="panel">
          <DistributionDonut title="Run Status" data={chartData.statuses} emptyLabel="No runs recorded yet" />
        </article>
        <article className="panel">
          <DistributionDonut title="Success Split" data={chartData.outcomes} emptyLabel="No outcome data yet" />
        </article>
        <article className="panel">
          <HorizontalBarChart title="Flow Distribution" data={chartData.flows} emptyLabel="No flows recorded yet" />
        </article>
        <article className="panel">
          <Sparkline title="Failures Over 7 Days" points={chartData.trend.points} labels={chartData.trend.labels} />
        </article>
        <article className="panel">
          <HorizontalBarChart title="Archive / Purge Backlog" data={chartData.backlog} emptyLabel="No retention backlog" />
        </article>
        <article className="panel">
          <DistributionDonut title="Schedule Health" data={chartData.schedules} emptyLabel="No schedules configured" />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <h2 className="section-title">Attention Queue</h2>
          {activeOrDegraded.length ? (
            <div className="grid">
              {activeOrDegraded.slice(0, 6).map((run) => (
                <Link key={run.id} href={`/runs/${run.id}`} style={{ color: "inherit", textDecoration: "none" }}>
                  <div className="list-row">
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", marginBottom: "6px" }}>
                      <strong>Run #{run.id} - {run.flow}</strong>
                      <span className={`status-pill ${statusClass(run.status)}`}>{run.status}</span>
                    </div>
                    <div className="muted" style={{ fontSize: "14px" }}>
                      {run.store_id || "auto-store"} / {run.phone || "auto-user"}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="chart-empty">No active or degraded runs.</div>
          )}
        </article>

        <article className="panel">
          <h2 className="section-title">Alerts</h2>
          {alerts.length ? (
            <div className="grid">
              {alerts.slice(0, 6).map((alert) => (
                <Link key={alert.id} href={alert.href} style={{ color: "inherit", textDecoration: "none" }}>
                  <div className="list-row">
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", marginBottom: "6px" }}>
                      <strong>{alert.title}</strong>
                      <span className={`alert-pill severity-${alert.severity}`}>{alert.severity}</span>
                    </div>
                    <div className="muted" style={{ fontSize: "14px" }}>{alert.message}</div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="chart-empty">No alerts.</div>
          )}
        </article>
      </section>

      <section className="grid three">
        <article className="panel">
          <h2 className="section-title">Platform Status</h2>
          <div className="grid" style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>API</strong>: {health?.status ?? "loading"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Project</strong>: {health?.project_dir ?? "--"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Run DB</strong>: {health?.db_path ?? "--"}</div>
          </div>
        </article>
        <article className="panel">
          <h2 className="section-title">Archive Window</h2>
          <div className="grid" style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Active policy</strong>: {archiveSummary?.policy_days.active ?? "--"} days</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Archive policy</strong>: {archiveSummary?.policy_days.archive ?? "--"} days</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Ready to archive</strong>: {archiveSummary?.counts.archive_ready ?? 0}</div>
          </div>
        </article>
        <article className="panel">
          <h2 className="section-title">Retention Queue</h2>
          <div className="grid" style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Mode</strong>: {retentionSummary?.status ?? "--"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Purge-ready</strong>: {retentionSummary?.queue.purge_ready ?? 0}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Artifact-backed</strong>: {retentionSummary?.queue.artifact_backed_runs ?? 0}</div>
          </div>
        </article>
      </section>
    </div>
  );
}
