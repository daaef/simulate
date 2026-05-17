"use client";

import type { LatestRunIssue } from "../../lib/api";

function severityClass(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === "critical" || normalized === "error") return "severity-critical";
  if (normalized === "warning") return "severity-warning";
  return "severity-info";
}

export default function FindingsPanel({
  title,
  issues,
  emptyMessage,
  limit = 8,
}: {
  title: string;
  issues: LatestRunIssue[];
  emptyMessage: string;
  limit?: number;
}) {
  return (
    <div className="panel grid" style={{ gap: 10 }}>
      <div className="section-heading-row">
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span className="muted">{issues.length} items</span>
      </div>
      {issues.length ? (
        issues.slice(0, limit).map((issue, index) => (
          <div key={`${issue.code}-${index}`} className="finding-row">
            <div className="finding-row-head">
              <strong>{issue.code}</strong>
              <span className={`alert-pill ${severityClass(issue.severity)}`}>{issue.severity}</span>
            </div>
            <p className="muted">{issue.message}</p>
            {issue.route ? <p className="muted">route: {issue.route}</p> : null}
            {issue.actor ? <span className="chip">{issue.actor}</span> : null}
          </div>
        ))
      ) : (
        <div className="chart-empty">{emptyMessage}</div>
      )}
    </div>
  );
}
