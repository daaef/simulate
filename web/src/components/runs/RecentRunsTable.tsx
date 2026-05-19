"use client";

import { Pagination } from "../Pagination";
import type { RunRow } from "../../lib/api";
import { canDeleteRun, canStopRun } from "../../lib/run-control";

interface RecentRunsTableProps {
  runs: RunRow[];
  runsTotal: number;
  runsOffset: number;
  runsPerPage: number;
  onPageChange: (newOffset: number) => void;
  onViewRun: (runId: number) => void;
  onWatchRun?: (runId: number) => void;
  onCancelRun: (runId: number) => void;
  onDeleteRunRequest: (run: RunRow) => void;
}

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "succeeded") return "status-success";
  if (s === "failed" || s === "deleted") return "status-danger";
  if (s === "queued" || s === "running" || s === "cancelling") return "status-warning";
  return "status-info";
}

function relativeTime(value: string): string {
  try {
    const ms = Date.now() - new Date(value).getTime();
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return "just now";
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const days = Math.floor(hr / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo ago`;
    return `${Math.floor(months / 12)}y ago`;
  } catch {
    return value;
  }
}

function fullDate(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function RecentRunsTable({
  runs,
  runsTotal,
  runsOffset,
  runsPerPage,
  onPageChange,
  onViewRun,
  onWatchRun,
  onCancelRun,
  onDeleteRunRequest,
}: RecentRunsTableProps) {
  return (
    <div className="panel">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Flow</th>
            <th>Launch</th>
            <th>Target</th>
            <th>Created</th>
            <th>Exit</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {runs.length === 0 ? (
            <tr>
              <td
                colSpan={8}
                style={{
                  textAlign: "center",
                  padding: "40px 16px",
                  color: "var(--text-secondary)",
                  fontStyle: "italic",
                }}
              >
                No runs yet — launch one above
              </td>
            </tr>
          ) : (
            runs.map((run) => (
              <tr key={run.id} onClick={() => onViewRun(run.id)} style={{ cursor: "pointer" }}>
                <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>#{run.id}</td>
                <td>
                  <span className={`status-pill ${statusClass(run.status)}`}>
                    {run.status}
                  </span>
                </td>
                <td>{run.flow}</td>
                <td>
                  <div style={{ fontWeight: 500 }}>{run.trigger_source || "manual"}</div>
                  <div style={{ fontSize: "11px", opacity: 0.72, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "180px" }}>
                    {run.trigger_label || "Manual launch"}
                  </div>
                  {run.profile_id ? (
                    <div style={{ fontSize: "10px", opacity: 0.62 }}>
                      {(run.trigger_context as Record<string, unknown> | undefined)?.profile_name
                        ? `profile ${(run.trigger_context as Record<string, unknown>).profile_name as string}`
                        : `profile #${run.profile_id}`}
                    </div>
                  ) : null}
                </td>
                <td>
                  {run.store_id ? (
                    <div style={{ fontWeight: 500 }}>
                      {run.store_name || run.store_id}
                    </div>
                  ) : null}
                  {run.store_phone ? (
                    <div style={{ fontSize: "11px", opacity: 0.7 }}>{run.store_phone}</div>
                  ) : null}
                  {run.phone ? (
                    <div style={{ fontSize: "11px", opacity: 0.7 }}>
                      {run.phone}
                      {run.user_name ? (
                        <span style={{ marginLeft: 4, opacity: 0.75 }}>· {run.user_name}</span>
                      ) : null}
                    </div>
                  ) : null}
                  {!run.store_id && !run.phone ? (
                    <span style={{ opacity: 0.4 }}>—</span>
                  ) : null}
                </td>
                <td>
                  <span title={fullDate(run.created_at)}>
                    {relativeTime(run.created_at)}
                  </span>
                </td>
                <td style={{ color: run.exit_code === 0 ? "var(--chart-success)" : run.exit_code != null ? "var(--chart-danger)" : undefined }}>
                  {run.exit_code ?? "—"}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="secondary small" onClick={(e) => { e.stopPropagation(); onViewRun(run.id); }}>
                      View
                    </button>
                    {onWatchRun ? (
                      <button
                        className="secondary small"
                        onClick={(e) => { e.stopPropagation(); onWatchRun(run.id); }}
                      >
                        Console
                      </button>
                    ) : null}
                    <button
                      className="small"
                      disabled={!canStopRun(run)}
                      onClick={(e) => { e.stopPropagation(); onCancelRun(run.id); }}
                    >
                      Stop
                    </button>
                    <button
                      className="secondary small"
                      disabled={!canDeleteRun(run)}
                      onClick={(e) => { e.stopPropagation(); onDeleteRunRequest(run); }}
                      style={{ marginLeft: "4px" }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      <Pagination total={runsTotal} offset={runsOffset} limit={runsPerPage} onPageChange={onPageChange} />
    </div>
  );
}
