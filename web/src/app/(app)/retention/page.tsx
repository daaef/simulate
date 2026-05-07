"use client";

import { useEffect, useMemo, useState } from "react";
import { DistributionDonut } from "../../../components/charts/DistributionDonut";
import { HorizontalBarChart } from "../../../components/charts/HorizontalBarChart";
import {
  ApiRequestError,
  fetchArchiveSummary,
  fetchRetentionSummary,
  type ArchiveSummary,
  type RetentionSummary,
} from "../../../lib/api";

function toMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Failed to load retention";
}

export default function RetentionPage() {
  const [summary, setSummary] = useState<RetentionSummary | null>(null);
  const [archiveSummary, setArchiveSummary] = useState<ArchiveSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [retentionPayload, archivePayload] = await Promise.all([
          fetchRetentionSummary(),
          fetchArchiveSummary(),
        ]);
        if (!active) return;
        setSummary(retentionPayload);
        setArchiveSummary(archivePayload);
        setError(null);
      } catch (caughtError) {
        if (active) setError(toMessage(caughtError));
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const chartData = useMemo(() => {
    const lifecycle = summary?.lifecycle_states ?? {
      active: archiveSummary?.counts.active ?? 0,
      archive_candidate: archiveSummary?.counts.archive_ready ?? 0,
      raw_purge_candidate: archiveSummary?.counts.purge_ready ?? 0,
    };
    return {
      lifecycle: [
        { label: "Active", value: lifecycle.active, color: "var(--chart-success)" },
        { label: "Archive", value: lifecycle.archive_candidate, color: "var(--chart-warning)" },
        { label: "Raw purge", value: lifecycle.raw_purge_candidate, color: "var(--chart-danger)" },
      ],
      queue: [
        { label: "Archive ready", value: summary?.queue.archive_ready ?? 0, color: "var(--chart-warning)" },
        { label: "Purge ready", value: summary?.queue.purge_ready ?? 0, color: "var(--chart-danger)" },
        { label: "Artifact-backed", value: summary?.queue.artifact_backed_runs ?? 0, color: "var(--chart-info)" },
      ],
    };
  }, [archiveSummary, summary]);

  const purgeSafety = summary?.purge_safety;

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Retention</h1>
        <p className="page-subtitle">Policy posture, queue pressure, retained summary coverage, and purge safety.</p>
      </section>

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      <section className="grid four">
        <article className="panel stat">
          <span className="stat-label">Active Window</span>
          <strong className="stat-value">{summary?.policies.active_days ?? "--"}d</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archive Window</span>
          <strong className="stat-value">{summary?.policies.archive_days ?? "--"}d</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archive Queue</span>
          <strong className="stat-value">{summary?.queue.archive_ready ?? 0}</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Purge Queue</span>
          <strong className="stat-value">{summary?.queue.purge_ready ?? 0}</strong>
        </article>
      </section>

      <section className="chart-grid">
        <article className="panel">
          <DistributionDonut title="Lifecycle State" data={chartData.lifecycle} emptyLabel="No run lifecycle data" />
        </article>
        <article className="panel">
          <HorizontalBarChart title="Queue Pressure" data={chartData.queue} emptyLabel="No retention pressure" />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <h2 className="section-title">Purge Safety</h2>
          <div className="grid" style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Status</strong>: {summary?.status ?? "--"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Mode</strong>: {purgeSafety?.mode ?? "manual-review"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Raw purge enabled</strong>: {purgeSafety?.raw_artifact_purge_enabled ? "yes" : "no"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Retained summary required</strong>: {purgeSafety?.retained_summary_required ? "yes" : "no"}</div>
          </div>
        </article>

        <article className="panel">
          <h2 className="section-title">Retained Summary Fields</h2>
          {summary?.retained_summary_fields?.length ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
              {summary.retained_summary_fields.map((field) => (
                <span key={field} className="status-pill status-info">{field}</span>
              ))}
            </div>
          ) : (
            <div className="chart-empty">Retained summary field list unavailable.</div>
          )}
        </article>
      </section>
    </div>
  );
}
