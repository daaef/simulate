"use client";

import type { HttpProtocolSummary, WebSocketProtocolSummary } from "../../lib/api";

function percentage(success?: number, total?: number): string {
  if (!total) return "—";
  return `${Math.round(((success || 0) / total) * 100)}%`;
}

export default function ProtocolHealthBoard({
  http,
  websocket,
}: {
  http: Partial<HttpProtocolSummary>;
  websocket: Partial<WebSocketProtocolSummary>;
}) {
  const totalHttp = http.total || 0;
  const successHttp = http.success || 0;

  return (
    <section className="protocol-health-board">
      <article className="panel protocol-card">
        <div className="protocol-card-head">
          <div>
            <p className="eyebrow">HTTP</p>
            <h3>{percentage(successHttp, totalHttp)} healthy</h3>
          </div>
          <span className={`status-pill ${(http.failed || 0) > 0 ? "status-danger" : "status-success"}`}>
            {http.failed || 0} failed
          </span>
        </div>

        <div className="protocol-metrics">
          <div><span>Total</span><strong>{http.total || 0}</strong></div>
          <div><span>Avg latency</span><strong>{http.avg_latency_ms ? `${http.avg_latency_ms}ms` : "—"}</strong></div>
          <div><span>2xx</span><strong>{http.status_groups?.["2xx"] || 0}</strong></div>
          <div><span>4xx/5xx</span><strong>{(http.status_groups?.["4xx"] || 0) + (http.status_groups?.["5xx"] || 0)}</strong></div>
        </div>

        {http.slowest ? (
          <p className="muted">
            Slowest: <strong>{http.slowest.method || "HTTP"} {http.slowest.endpoint}</strong> · {http.slowest.latency_ms}ms
          </p>
        ) : null}
      </article>

      <article className="panel protocol-card">
        <div className="protocol-card-head">
          <div>
            <p className="eyebrow">WebSocket</p>
            <h3>{websocket.total || 0} messages</h3>
          </div>
          <span className={`status-pill ${(websocket.missed || 0) > 0 ? "status-danger" : "status-success"}`}>
            {websocket.missed || 0} missed
          </span>
        </div>

        <div className="protocol-metrics">
          <div><span>Expected</span><strong>{websocket.expected || 0}</strong></div>
          <div><span>Matched</span><strong>{websocket.matched || 0}</strong></div>
          <div><span>Missed</span><strong>{websocket.missed || 0}</strong></div>
          <div><span>Sources</span><strong>{websocket.sources?.length || 0}</strong></div>
        </div>

        {websocket.latest ? (
          <p className="muted">
            Latest: <strong>{websocket.latest.action || "message"}</strong>
            {websocket.latest.status ? ` · ${websocket.latest.status}` : ""}
          </p>
        ) : null}
      </article>
    </section>
  );
}