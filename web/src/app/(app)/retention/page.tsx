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

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function formatDate(d: Date): string {
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
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
        { label: "Archive-ready", value: lifecycle.archive_candidate, color: "var(--chart-warning)" },
        { label: "Purge-ready", value: lifecycle.raw_purge_candidate, color: "var(--chart-danger)" },
      ],
      queue: [
        { label: "Archive ready", value: summary?.queue.archive_ready ?? 0, color: "var(--chart-warning)" },
        { label: "Purge ready", value: summary?.queue.purge_ready ?? 0, color: "var(--chart-danger)" },
        { label: "Artifact-backed", value: summary?.queue.artifact_backed_runs ?? 0, color: "var(--chart-info)" },
      ],
    };
  }, [archiveSummary, summary]);

  const activeDays = summary?.policies.active_days ?? archiveSummary?.policy_days.active ?? 30;
  const archiveDays = summary?.policies.archive_days ?? archiveSummary?.policy_days.archive ?? 180;

  const now = new Date();
  const archiveCutoff = addDays(now, -activeDays);
  const purgeCutoff = addDays(now, -archiveDays);

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Retention</h1>
        <p className="page-subtitle">
          Policy thresholds, lifecycle distribution, and queue pressure for run data.
        </p>
      </section>

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      <section className="grid four">
        <article className="panel stat">
          <span className="stat-label">Runs stay visible for</span>
          <strong className="stat-value">{activeDays} days</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            Runs older than this are auto-archived
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archived runs kept for</span>
          <strong className="stat-value">{archiveDays} days</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            After this, they are permanently deleted
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Pending archive</span>
          <strong className="stat-value">{summary?.queue.archive_ready ?? 0}</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            Active runs due to be archived soon
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Pending deletion</span>
          <strong className="stat-value">{summary?.queue.purge_ready ?? 0}</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            Archived runs due to be deleted soon
          </span>
        </article>
      </section>

      {/* Policy timeline */}
      <section className="panel">
        <h2 className="section-title">Policy Timeline</h2>
        <div style={{ display: "grid", gap: "12px", fontSize: "14px" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span
              style={{
                display: "inline-block",
                width: 12,
                height: 12,
                borderRadius: "50%",
                backgroundColor: "var(--chart-success)",
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Active</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created within the last {activeDays} days (after{" "}
              <strong>{formatDate(archiveCutoff)}</strong>). Fully visible on the Runs page.
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span
              style={{
                display: "inline-block",
                width: 12,
                height: 12,
                borderRadius: "50%",
                backgroundColor: "var(--chart-warning)",
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Archive-ready</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created between {activeDays}–{archiveDays} days ago (between{" "}
              <strong>{formatDate(purgeCutoff)}</strong> and{" "}
              <strong>{formatDate(archiveCutoff)}</strong>). Auto-archived hourly — hidden from
              Runs but restorable from the Archives page.
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span
              style={{
                display: "inline-block",
                width: 12,
                height: 12,
                borderRadius: "50%",
                backgroundColor: "var(--chart-danger)",
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Purge-ready</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created more than {archiveDays} days ago (before{" "}
              <strong>{formatDate(purgeCutoff)}</strong>). Auto-purged hourly — permanently
              deleted including all on-disk artifacts. Use the Archives page to manually purge
              sooner or restore before the cutoff.
            </span>
          </div>
        </div>
      </section>

      <section className="chart-grid">
        <article className="panel">
          <DistributionDonut
            title="Lifecycle Distribution"
            data={chartData.lifecycle}
            emptyLabel="No run lifecycle data"
          />
        </article>
        <article className="panel">
          <HorizontalBarChart
            title="Queue Pressure"
            data={chartData.queue}
            emptyLabel="No retention pressure"
          />
        </article>
      </section>
    </div>
  );
}
