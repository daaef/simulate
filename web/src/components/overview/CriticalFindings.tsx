"use client";

import type { LatestRunIssue } from "../../lib/api";

function severityClass(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === "critical" || normalized === "error") return "severity-critical";
  if (normalized === "warning") return "severity-warning";
  return "severity-info";
}

export default function CriticalFindings({ issues }: { issues: LatestRunIssue[] }) {
  return (
    <article className="panel">
      <div className="section-heading-row">
        <h2 className="section-title">Critical Findings</h2>
        <span className="muted">{issues.length} items</span>
      </div>

      {issues.length ? (
        <div className="grid">
          {issues.slice(0, 6).map((issue, index) => (
            <div key={`${issue.code}-${index}`} className="finding-row">
              <div className="finding-row-head">
                <strong>{issue.code}</strong>
                <span className={`alert-pill ${severityClass(issue.severity)}`}>{issue.severity}</span>
              </div>
              <p className="muted">{issue.message}</p>
              {issue.actor ? <span className="chip">{issue.actor}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="chart-empty">No critical findings in the latest run.</div>
      )}
    </article>
  );
}