"use client";

import type { LatestRunIssue } from "../../lib/api";

function severityClass(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === "critical" || normalized === "error") return "severity-critical";
  if (normalized === "warning") return "severity-warning";
  return "severity-info";
}

function formatApiLine(issue: LatestRunIssue): string | null {
  const route = issue.route?.trim();
  const method = issue.method?.trim();
  if (method && route) return `${method} ${route}`;
  return route || null;
}

function formatFlowLine(issue: LatestRunIssue): string | null {
  if (issue.flow_label) return issue.flow_label;
  const flow = issue.flow?.trim();
  const step = issue.step?.trim();
  if (flow && step) return `${flow} · ${step}`;
  return flow || step || null;
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
        issues.slice(0, limit).map((issue, index) => {
          const apiLine = formatApiLine(issue);
          const flowLine = formatFlowLine(issue);
          const preceding = issue.preceding_steps || [];

          return (
            <div key={`${issue.code}-${index}`} className="finding-row">
              <div className="finding-row-head">
                <strong>{issue.code}</strong>
                <span className={`alert-pill ${severityClass(issue.severity)}`}>{issue.severity}</span>
              </div>
              <p className="muted">{issue.message}</p>
              {apiLine ? (
                <p className="muted">
                  <strong style={{ color: "var(--text-primary)" }}>API:</strong> {apiLine}
                  {issue.http_status != null ? ` · HTTP ${issue.http_status}` : null}
                </p>
              ) : null}
              {flowLine ? (
                <p className="muted">
                  <strong style={{ color: "var(--text-primary)" }}>Flow:</strong> {flowLine}
                </p>
              ) : null}
              {issue.order_ref ? <p className="muted">order: {issue.order_ref}</p> : null}
              {preceding.length ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  <strong style={{ color: "var(--text-primary)" }}>Before:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {preceding.map((step, stepIndex) => (
                      <li key={`${step.action}-${stepIndex}`}>
                        {step.action}
                        {step.endpoint ? ` · ${step.endpoint}` : ""}
                        {step.ok === false ? " · failed" : step.ok === true ? " · ok" : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {issue.actor ? <span className="chip">{issue.actor}</span> : null}
            </div>
          );
        })
      ) : (
        <div className="chart-empty">{emptyMessage}</div>
      )}
    </div>
  );
}
