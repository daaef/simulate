"use client";

import type { SocketStatusResponse } from "../../lib/api";
import { formatDateTime } from "../../lib/time-format";
import { socketStatusTone } from "../../lib/socket-status";

function statusClass(status: string | null | undefined): string {
  const tone = socketStatusTone(status);
  if (tone === "success") return "status-success";
  if (tone === "warning") return "status-warning";
  if (tone === "danger") return "status-danger";
  return "status-info";
}

export default function SocketServicePanel({
  status,
}: {
  status: SocketStatusResponse | null;
}) {
  if (!status) {
    return (
      <section id="socket-service" className="panel socket-service-panel" aria-labelledby="socket-service-title">
        <div className="section-heading-row">
          <h2 id="socket-service-title" className="section-title">Socket Service</h2>
          <span className="status-pill status-info">unknown</span>
        </div>
        <div className="chart-empty">Socket monitor status is unavailable.</div>
      </section>
    );
  }

  const evidence = status.latest_run_evidence;

  return (
    <section id="socket-service" className="panel socket-service-panel" aria-labelledby="socket-service-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Realtime Monitor</p>
          <h2 id="socket-service-title" className="section-title">Socket Service</h2>
        </div>
        <span className={`status-pill ${statusClass(status.status)}`}>{status.status}</span>
      </div>

      <div className="socket-service-meta">
        <span>Last checked: <strong>{formatDateTime(status.checked_at, { fallback: "not checked yet" })}</strong></span>
        <span>Store: <strong>{status.target?.store_id || "not configured"}</strong></span>
        <span>Target: <strong>{status.target?.source || status.reason || "unknown"}</strong></span>
      </div>

      {status.required.length ? (
        <div className="socket-service-rows">
          {status.required.map((row) => (
            <div key={row.key} className="socket-service-row">
              <div>
                <strong>{row.label}</strong>
                <p className="muted">{row.key}</p>
              </div>
              <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
              <span className="muted">{row.latency_ms != null ? `${row.latency_ms}ms` : "no latency"}</span>
              <span className="muted">{row.reason || "healthy"}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="chart-empty">No socket target is configured for active probing.</div>
      )}

      <div className="socket-service-evidence">
        <h3 className="subsection-title">Latest run websocket evidence</h3>
        {evidence?.run_id ? (
          <p className="muted">
            Run #{evidence.run_id} ({evidence.run_status || "unknown"}) matched {evidence.matched ?? 0}/
            {evidence.expected ?? 0} expected websocket event{(evidence.expected ?? 0) === 1 ? "" : "s"}.
            {(evidence.missed ?? 0) > 0 ? ` Missed: ${evidence.missed}.` : ""}
          </p>
        ) : (
          <p className="muted">No latest-run websocket evidence is available yet.</p>
        )}
      </div>
    </section>
  );
}
