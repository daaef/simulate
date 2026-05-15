"use client";

import RunActionCountsPanel from "../RunActionCountsPanel";
import type { RunMetrics } from "../../../lib/api";

interface RunDetailOverviewProps {
  metrics: RunMetrics | null;
  runStatus: string;
  runError: string | null;
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

export default function RunDetailOverview({ metrics, runStatus, runError }: RunDetailOverviewProps) {
  const topActors = metrics ? Object.entries(metrics.top_actors).sort((a, b) => b[1] - a[1]) : [];

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

      <div className="grid two">
        {metrics ? <TopList title="Top actors (preview)" entries={topActors} emptyMessage="No actor breakdown recorded." /> : null}
      </div>
    </>
  );
}
