"use client";

import type { DashboardSummary } from "../../lib/api";

interface RunStatisticsProps {
  summary: DashboardSummary;
}

export default function RunStatistics({ summary }: RunStatisticsProps) {
  const flowValues = Object.values(summary.flow_breakdown);
  const statusValues = Object.values(summary.status_breakdown);
  const maxFlowCount = flowValues.length ? Math.max(...flowValues) : 1;
  const maxStatusCount = statusValues.length ? Math.max(...statusValues) : 1;

  return (
    <div className="grid two" style={{ alignItems: "start" }}>
      <div className="panel grid" style={{ gap: 10 }}>
        <h2 className="chart-title">Status Distribution</h2>
        {Object.entries(summary.status_breakdown).map(([key, value]) => (
          <div key={key} className="bar-row">
            <div className="bar-label">{key}</div>
            <div className="bar-track">
              <div className="bar-fill status" style={{ width: `${Math.max(6, (value / Math.max(1, maxStatusCount)) * 100)}%` }} />
            </div>
            <div className="bar-value">{value}</div>
          </div>
        ))}
      </div>
      <div className="panel grid" style={{ gap: 10 }}>
        <h2 className="chart-title">Flow Distribution</h2>
        {Object.entries(summary.flow_breakdown).length ? (
          Object.entries(summary.flow_breakdown).map(([key, value]) => (
            <div key={key} className="bar-row">
              <div className="bar-label">{key}</div>
              <div className="bar-track">
                <div className="bar-fill flow" style={{ width: `${Math.max(6, (value / Math.max(1, maxFlowCount)) * 100)}%` }} />
              </div>
              <div className="bar-value">{value}</div>
            </div>
          ))
        ) : (
          <div className="muted">No completed runs yet.</div>
        )}
      </div>
    </div>
  );
}
