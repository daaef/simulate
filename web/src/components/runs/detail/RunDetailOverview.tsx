"use client";

import RunActionCountsPanel from "../RunActionCountsPanel";
import type { LatestRunIssue, RunMetrics } from "../../../lib/api";

interface RunDetailOverviewProps {
  metrics: RunMetrics | null;
  runStatus: string;
  runError: string | null;
  issues: LatestRunIssue[];
}

function MetricsGrid({ metrics }: { metrics: RunMetrics }) {
  return (
    <div className="grid four">
      <div className="panel stat">
        <div className="stat-value">{metrics.total_events}</div>
        <div className="stat-label">Total Events</div>
      </div>
      <div className="panel stat">
        <div className="stat-value">{metrics.http_calls}</div>
        <div className="stat-label">HTTP Calls</div>
      </div>
      <div className="panel stat">
        <div className="stat-value">{metrics.websocket_events}</div>
        <div className="stat-label">WebSocket Events</div>
      </div>
      <div className="panel stat">
        <div className="stat-value">{metrics.failed_events}</div>
        <div className="stat-label">Failed Events</div>
      </div>
    </div>
  );
}

function TopList({
  title,
  entries,
  emptyMessage,
}: {
  title: string;
  entries: Array<[string, number]>;
  emptyMessage: string;
}) {
  return (
    <div className="panel grid" style={{ gap: 10 }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      {entries.length ? (
        entries.slice(0, 8).map(([label, value]) => (
          <div key={label} className="bar-row">
            <div className="bar-label">{label}</div>
            <div className="bar-track">
              <div
                className="bar-fill flow"
                style={{ width: `${Math.max(8, (value / Math.max(1, entries[0][1])) * 100)}%` }}
              />
            </div>
            <div className="bar-value">{value}</div>
          </div>
        ))
      ) : (
        <div className="muted">{emptyMessage}</div>
      )}
    </div>
  );
}

export default function RunDetailOverview({ metrics, runStatus, runError, issues }: RunDetailOverviewProps) {
  const topActors = metrics ? Object.entries(metrics.top_actors).sort((a, b) => b[1] - a[1]) : [];
  const criticalFindings = issues.filter((issue) => {
    const severity = String(issue.severity || "").toLowerCase();
    return severity === "critical" || severity === "error";
  });
  const operationalFindings = issues.filter((issue) => {
    const severity = String(issue.severity || "").toLowerCase();
    return severity !== "critical" && severity !== "error";
  });

  return (
    <>
      {metrics ? (
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Summary</h3>
          <MetricsGrid metrics={metrics} />
        </div>
      ) : null}

      <RunActionCountsPanel
        action_counts={metrics?.action_counts}
        total_events={metrics?.total_events ?? 0}
        failed_events={metrics?.failed_events ?? 0}
        http_calls={metrics?.http_calls ?? 0}
        websocket_events={metrics?.websocket_events ?? 0}
        top_actors={metrics?.top_actors}
        title="Run Metrics Dashboard"
        showOutcomeChips
      />

      <div className="panel muted" style={{ fontSize: 14, lineHeight: 1.5 }}>
        <strong style={{ color: "var(--text-primary)" }}>Charts</strong> — Per-endpoint latency and success donuts need data
        that is not part of run metrics. Use the <strong>Traffic</strong> tab for raw events and <strong>Console</strong> for process
        output.
      </div>

      <div className="grid" style={{ gap: 12 }}>
        {runError ? (
          <div className="panel" style={{ borderColor: "#ef4444", color: "#b91c1c" }}>
            <strong>Error:</strong> {runError}
          </div>
        ) : null}
        {!runError && runStatus === "failed" && !metrics ? <p className="muted">Run failed before metrics were recorded.</p> : null}
      </div>

      <div className="grid two" style={{ alignItems: "start", gap: 12 }}>
        <div className="panel grid" style={{ gap: 10 }}>
          <div className="section-heading-row">
            <h3 style={{ margin: 0 }}>Critical Findings</h3>
            <span className="muted">{criticalFindings.length} items</span>
          </div>
          {criticalFindings.length ? (
            criticalFindings.slice(0, 8).map((issue, index) => (
              <div key={`critical-${issue.code}-${index}`} className="finding-row">
                <div className="finding-row-head">
                  <strong>{issue.code}</strong>
                  <span className="alert-pill severity-critical">{issue.severity}</span>
                </div>
                <p className="muted">{issue.message}</p>
                {issue.route ? <p className="muted">route: {issue.route}</p> : null}
                {issue.actor ? <span className="chip">{issue.actor}</span> : null}
              </div>
            ))
          ) : (
            <div className="chart-empty">No critical findings for this run.</div>
          )}
        </div>
        <div className="panel grid" style={{ gap: 10 }}>
          <div className="section-heading-row">
            <h3 style={{ margin: 0 }}>Operational Findings</h3>
            <span className="muted">{operationalFindings.length} items</span>
          </div>
          {operationalFindings.length ? (
            operationalFindings.slice(0, 8).map((issue, index) => (
              <div key={`ops-${issue.code}-${index}`} className="finding-row">
                <div className="finding-row-head">
                  <strong>{issue.code}</strong>
                  <span className="alert-pill severity-warning">{issue.severity}</span>
                </div>
                <p className="muted">{issue.message}</p>
                {issue.route ? <p className="muted">route: {issue.route}</p> : null}
                {issue.actor ? <span className="chip">{issue.actor}</span> : null}
              </div>
            ))
          ) : (
            <div className="chart-empty">No non-critical findings for this run.</div>
          )}
        </div>
      </div>

      <div className="grid two">
        {metrics ? <TopList title="Top actors (preview)" entries={topActors} emptyMessage="No actor breakdown recorded." /> : null}
      </div>
    </>
  );
}
