"use client";

import { ActorHeatmap } from "../../charts/ActorHeatmap";
import { EventTimeline } from "../../charts/EventTimeline";
import { LatencyBarChart } from "../../charts/LatencyBarChart";
import { SuccessDonut } from "../../charts/SuccessDonut";
import type { RunMetrics } from "../../../lib/api";

interface RunDetailOverviewProps {
  metrics: RunMetrics | null;
  runStatus: string;
  runError: string | null;
  timelineData: {
    events: Array<{ timestamp: number; label: string; category: "scenario"; status: "success" }>;
    startTime: number;
    endTime: number;
  };
  latencyData: Array<{ endpoint: string; latency: number; status: number; count: number }>;
  successData: {
    httpSuccess: number;
    httpFailed: number;
    wsSuccess: number;
    wsFailed: number;
    scenariosPassed: number;
    scenariosFailed: number;
  };
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

export default function RunDetailOverview({
  metrics,
  runStatus,
  runError,
  timelineData,
  latencyData,
  successData,
}: RunDetailOverviewProps) {
  const topActors = metrics ? Object.entries(metrics.top_actors).sort((a, b) => b[1] - a[1]) : [];
  const topActions = metrics ? Object.entries(metrics.top_actions).sort((a, b) => b[1] - a[1]) : [];

  return (
    <>
      {metrics ? (
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Summary Metrics</h3>
          <MetricsGrid metrics={metrics} />
        </div>
      ) : null}
      <div className="panel">
        <h3 style={{ marginBottom: 12 }}>Data Visualizations</h3>
        <div className="grid two">
          <EventTimeline events={timelineData.events} startTime={timelineData.startTime} endTime={timelineData.endTime} />
          <LatencyBarChart data={latencyData} />
          <SuccessDonut data={successData} />
          <ActorHeatmap data={[]} actors={[]} timeBuckets={[]} />
        </div>
      </div>
      <div className="grid" style={{ gap: 12 }}>
        {metrics ? <MetricsGrid metrics={metrics} /> : <p className="muted">Loading metrics...</p>}
        {runError ? (
          <div className="panel" style={{ borderColor: "#ef4444", color: "#b91c1c" }}>
            <strong>Error:</strong> {runError}
          </div>
        ) : null}
        {!runError && runStatus === "failed" && !metrics ? <p className="muted">Run failed before metrics were recorded.</p> : null}
      </div>
      <div className="grid two">
        <TopList title="Top Actors" entries={topActors} emptyMessage="No actor breakdown recorded." />
        <TopList title="Top Actions" entries={topActions} emptyMessage="No action breakdown recorded." />
      </div>
    </>
  );
}
