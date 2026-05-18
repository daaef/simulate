"use client";

type EventRow = Record<string, unknown>;

interface RunEventsPanelProps {
  events: EventRow[];
  eventsTotal: number;
  eventsOffset: number;
  pageSize: number;
  onPreviousPage: () => void;
  onNextPage: () => void;
}

function eventField(event: EventRow, key: string): string {
  const value = event[key];
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function eventTimestamp(event: EventRow): string {
  return eventField(event, "ts") || eventField(event, "timestamp");
}

function eventStatus(event: EventRow): string {
  const explicit = eventField(event, "status");
  if (explicit) return explicit;
  if (eventField(event, "category") === "decision") return "";
  const ok = event["ok"];
  if (typeof ok === "boolean") return ok ? "ok" : "failed";
  return "";
}

function eventMessage(event: EventRow): string {
  return eventField(event, "message") || eventField(event, "details") || eventField(event, "detail") || eventField(event, "response_preview");
}

function detailField(event: EventRow, key: string): string {
  const details = event["details"];
  if (!details || typeof details !== "object") return "";
  const value = (details as Record<string, unknown>)[key];
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function methodClass(method?: string): string {
  const m = (method || "").toUpperCase();
  if (m === "GET") return "method-get";
  if (m === "POST") return "method-post";
  if (m === "PATCH") return "method-patch";
  if (m === "PUT") return "method-put";
  if (m === "DELETE") return "method-delete";
  return "";
}

function isHttpEvent(event: EventRow): boolean {
  const method = eventField(event, "method");
  const url = eventField(event, "url") || eventField(event, "endpoint") || eventField(event, "path");
  return !!method && !!url;
}

function httpStatusCode(event: EventRow): number | null {
  const raw = event["http_status"] ?? event["status_code"];
  if (typeof raw === "number") return raw;
  const parsed = Number(eventField(event, "http_status") || eventField(event, "status_code"));
  return Number.isFinite(parsed) ? parsed : null;
}

function isHttpError(event: EventRow): boolean {
  if (!isHttpEvent(event)) return false;
  const status = httpStatusCode(event);
  if (status !== null) return status >= 500;
  return event["ok"] === false;
}

function httpResultLabel(event: EventRow): string {
  const status = httpStatusCode(event);
  if (status !== null) {
    if (status >= 500) return "error";
    if (status >= 400) return "client error";
  }
  const label = eventStatus(event);
  if (label === "failed") return "error";
  return label || "ok";
}

export default function RunEventsPanel({
  events,
  eventsTotal,
  eventsOffset,
  pageSize,
  onPreviousPage,
  onNextPage,
}: RunEventsPanelProps) {
  if (!events.length && !eventsTotal) {
    return <p className="muted">Events not available</p>;
  }

  const httpEvents = events.filter(isHttpEvent);

  return (
    <div className="grid" style={{ gap: 16 }}>
      {httpEvents.length ? (
        <div>
          <h4 style={{ marginBottom: 8 }}>HTTP Calls ({httpEvents.length})</h4>
          <div className="panel" style={{ maxHeight: 300, overflow: "auto", padding: 0 }}>
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Status</th>
                  <th>Latency</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {httpEvents.map((event, idx) => {
                  const method = eventField(event, "method");
                  const url = eventField(event, "url") || eventField(event, "endpoint") || eventField(event, "path");
                  const status = eventField(event, "status_code") || eventField(event, "http_status") || eventStatus(event);
                  const latency = eventField(event, "latency_ms") || eventField(event, "duration_ms");
                  const errorRow = isHttpError(event);
                  return (
                    <tr key={idx} className={errorRow ? "log-line-error" : undefined}>
                      <td>{eventTimestamp(event) || "—"}</td>
                      <td>{method ? <span className={`method-badge ${methodClass(method)}`}>{method.toUpperCase()}</span> : null}</td>
                      <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>{url}</td>
                      <td>{status}</td>
                      <td>{latency ? `${latency}ms` : "—"}</td>
                      <td>{httpResultLabel(event)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      <div>
        <h4 style={{ marginBottom: 8 }}>Event Stream ({events.length})</h4>
        <p className="muted" style={{ marginBottom: 8 }}>Showing {events.length} of {eventsTotal} events</p>
        <div className="panel" style={{ maxHeight: 400, overflow: "auto", padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Status</th>
                <th>Reason</th>
                <th>Next</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, idx) => {
                const errorRow = isHttpError(event) || eventStatus(event) === "failed" || eventStatus(event) === "error";
                return (
                <tr key={idx} className={errorRow ? "log-line-error" : undefined}>
                  <td>{eventTimestamp(event) || "—"}</td>
                  <td>{eventField(event, "actor") || "—"}</td>
                  <td>{eventField(event, "action") || eventField(event, "method") || "—"}</td>
                  <td>{eventStatus(event) || "—"}</td>
                  <td>{eventField(event, "reason_code") || detailField(event, "reason_code") || "—"}</td>
                  <td>{eventField(event, "next_action") || detailField(event, "next_action") || "—"}</td>
                  <td style={{ maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis" }}>{eventMessage(event) || "—"}</td>
                </tr>
              );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {eventsTotal > pageSize ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 16, marginTop: 12 }}>
          <button onClick={onPreviousPage} disabled={eventsOffset === 0} style={{ width: "auto" }} className="secondary">
            Previous
          </button>
          <span className="muted">Events {eventsOffset + 1}-{Math.min(eventsOffset + events.length, eventsTotal)} of {eventsTotal}</span>
          <button onClick={onNextPage} disabled={eventsOffset + events.length >= eventsTotal} style={{ width: "auto" }}>
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}
