"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiRequestError,
  fetchArchiveSummary,
  fetchDashboardSummary,
  fetchHealth,
  fetchRetentionSummary,
  fetchRuns,
  type ArchiveSummary,
  type DashboardSummary,
  type HealthResponse,
  type RetentionSummary,
  type RunRow,
} from "../../../lib/api";

export default function OverviewPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [archiveSummary, setArchiveSummary] = useState<ArchiveSummary | null>(null);
  const [retentionSummary, setRetentionSummary] = useState<RetentionSummary | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [summaryPayload, healthPayload, archivePayload, retentionPayload, runsPayload] = await Promise.all([
          fetchDashboardSummary(),
          fetchHealth(),
          fetchArchiveSummary(),
          fetchRetentionSummary(),
          fetchRuns(8, 0),
        ]);
        if (!active) return;
        setSummary(summaryPayload);
        setHealth(healthPayload);
        setArchiveSummary(archivePayload);
        setRetentionSummary(retentionPayload);
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
    { label: "Archive Backlog", value: summary?.archive_backlog ?? 0 },
    { label: "Purge Backlog", value: summary?.purge_backlog ?? 0 },
  ];

  const activeOrDegraded = recentRuns.filter((run) => ["queued", "running", "cancelling", "failed"].includes(run.status.toLowerCase()));

  return (
    <div style={{ padding: "24px" }}>
      <section style={{ marginBottom: "24px" }}>
        <h1 style={{ margin: "0 0 8px", fontSize: "42px", color: "var(--text-primary)" }}>
          Operations Overview
        </h1>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "18px" }}>
          Monitoring-first landing page for simulator health and operational access.
        </p>
      </section>

      {error ? (
        <div className="error-banner" style={{ marginBottom: "24px", padding: "12px 16px" }}>
          {error}
        </div>
      ) : null}

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        {cards.map((card) => (
          <article key={card.label} className="panel" style={{ padding: "20px" }}>
            <div style={{ color: "var(--text-secondary)", fontSize: "13px", marginBottom: "8px" }}>
              {card.label}
            </div>
            <div style={{ color: "var(--text-primary)", fontSize: "32px", fontWeight: 700 }}>
              {card.value}
            </div>
          </article>
        ))}
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(320px, 1fr)", gap: "16px", marginBottom: "16px" }}>
        <article className="panel" style={{ padding: "20px" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "28px", color: "var(--text-primary)" }}>Attention Queue</h2>
          {activeOrDegraded.length ? (
            <div style={{ display: "grid", gap: "12px" }}>
              {activeOrDegraded.slice(0, 6).map((run) => (
                <div key={run.id} style={{ padding: "12px 14px", border: "1px solid var(--border-primary)", borderRadius: "6px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", marginBottom: "6px" }}>
                    <strong style={{ color: "var(--text-primary)" }}>Run #{run.id} · {run.flow}</strong>
                    <span style={{ color: "var(--text-secondary)" }}>{run.status}</span>
                  </div>
                  <div style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
                    {run.store_id || "auto-store"} · {run.phone || "auto-user"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ margin: 0, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              No active or degraded runs need attention right now.
            </p>
          )}
        </article>

        <article className="panel" style={{ padding: "20px" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "24px", color: "var(--text-primary)" }}>Platform Status</h2>
          <div style={{ display: "grid", gap: "10px", color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>API</strong>: {health?.status ?? "loading"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Project</strong>: {health?.project_dir ?? "--"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Run DB</strong>: {health?.db_path ?? "--"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Retention mode</strong>: {retentionSummary?.status ?? "--"}</div>
          </div>
        </article>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr)", gap: "16px", marginBottom: "16px" }}>
        <article className="panel" style={{ padding: "20px" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "24px", color: "var(--text-primary)" }}>Run Access</h2>
          <p style={{ margin: "0 0 16px", color: "var(--text-secondary)", lineHeight: 1.6 }}>
            Use the runs workspace for launch, live control, report inspection, and technical forensics. The overview is now focused on attention, backlog, and system posture.
          </p>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <Link href="/runs" style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: "140px",
              padding: "12px 16px",
              borderRadius: "6px",
              backgroundColor: "var(--button-primary)",
              color: "var(--button-primary-text)",
              textDecoration: "none",
              fontWeight: 600,
            }}>
              Open Runs Workspace
            </Link>
            <Link href="/archives" style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: "140px",
              padding: "12px 16px",
              borderRadius: "6px",
              border: "1px solid var(--border-primary)",
              color: "var(--text-primary)",
              textDecoration: "none",
              fontWeight: 600,
            }}>
              Open Archives
            </Link>
          </div>
        </article>

        <article className="panel" style={{ padding: "20px" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "24px", color: "var(--text-primary)" }}>Archive Window</h2>
          <div style={{ display: "grid", gap: "10px", color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Active policy</strong>: {archiveSummary?.policy_days.active ?? "--"} days</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Archive policy</strong>: {archiveSummary?.policy_days.archive ?? "--"} days</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Ready to archive</strong>: {archiveSummary?.counts.archive_ready ?? 0}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Ready to purge</strong>: {archiveSummary?.counts.purge_ready ?? 0}</div>
          </div>
        </article>

        <article className="panel" style={{ padding: "20px" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "24px", color: "var(--text-primary)" }}>Retention Queue</h2>
          <div style={{ display: "grid", gap: "10px", color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Archive-ready runs</strong>: {retentionSummary?.queue.archive_ready ?? 0}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Purge-ready runs</strong>: {retentionSummary?.queue.purge_ready ?? 0}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Artifact-backed runs</strong>: {retentionSummary?.queue.artifact_backed_runs ?? 0}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Observation mode</strong>: raw purge not active yet</div>
          </div>
        </article>
      </section>

      <section className="panel" style={{ padding: "20px" }}>
        <h2 style={{ margin: "0 0 12px", fontSize: "24px", color: "var(--text-primary)" }}>Flow Distribution</h2>
        <div style={{ display: "grid", gap: "10px" }}>
          {summary && Object.entries(summary.flow_breakdown).length ? (
            Object.entries(summary.flow_breakdown).map(([flow, count]) => (
              <div key={flow} className="bar-row">
                <div className="bar-label">{flow}</div>
                <div className="bar-track">
                  <div className="bar-fill flow" style={{ width: `${Math.max(8, (count / Math.max(1, summary.total_runs || 1)) * 100)}%` }} />
                </div>
                <div className="bar-value">{count}</div>
              </div>
            ))
          ) : (
            <div style={{ color: "var(--text-secondary)" }}>No runs recorded yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}
