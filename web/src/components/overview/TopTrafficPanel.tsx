"use client";

import type { HttpProtocolSummary, WebSocketProtocolSummary } from "../../lib/api";

export default function TopTrafficPanel({
  http,
  websocket,
}: {
  http: Partial<HttpProtocolSummary>;
  websocket: Partial<WebSocketProtocolSummary>;
}) {
  return (
    <article className="panel">
      <h2 className="section-title">Top Traffic</h2>

      <div className="traffic-grid">
        <div>
          <h3 className="subsection-title">HTTP endpoints</h3>
          {http.top_endpoints?.length ? (
            <div className="traffic-list">
              {http.top_endpoints.slice(0, 6).map((item) => (
                <div key={item.endpoint} className="traffic-row">
                  <span>{item.endpoint}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No HTTP traffic captured.</p>
          )}
        </div>

        <div>
          <h3 className="subsection-title">WebSocket sources</h3>
          {websocket.sources?.length ? (
            <div className="traffic-list">
              {websocket.sources.slice(0, 6).map((item) => (
                <div key={item.source} className="traffic-row">
                  <span>{item.source}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No websocket traffic captured.</p>
          )}
        </div>
      </div>
    </article>
  );
}