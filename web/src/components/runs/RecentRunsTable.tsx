"use client";

import { Pagination } from "../Pagination";
import type { RunRow } from "../../lib/api";

interface RecentRunsTableProps {
  runs: RunRow[];
  runsTotal: number;
  runsOffset: number;
  runsPerPage: number;
  onPageChange: (newOffset: number) => void;
  onViewRun: (runId: number) => void;
  onCancelRun: (runId: number) => void;
  onDeleteRunRequest: (run: RunRow) => void;
  isActiveStatus: (status: string) => boolean;
}

export default function RecentRunsTable({
  runs,
  runsTotal,
  runsOffset,
  runsPerPage,
  onPageChange,
  onViewRun,
  onCancelRun,
  onDeleteRunRequest,
  isActiveStatus,
}: RecentRunsTableProps) {
  return (
    <div className="panel">
      <h2 style={{ marginBottom: 12 }}>Recent Runs</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Flow</th>
            <th>Launch</th>
            <th>Store</th>
            <th>Phone</th>
            <th>Created</th>
            <th>Exit</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} onClick={() => onViewRun(run.id)} style={{ cursor: "pointer" }}>
              <td>{run.id}</td>
              <td>{run.status}</td>
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
                <div style={{ fontWeight: 500 }}>{run.store_id || "-"}</div>
                {run.store_name ? (
                  <div style={{ fontSize: "11px", opacity: 0.7, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "120px" }}>
                    {run.store_name}
                  </div>
                ) : null}
                {run.store_phone ? <div style={{ fontSize: "10px", opacity: 0.6 }}>{run.store_phone}</div> : null}
              </td>
              <td>
                <div style={{ fontWeight: 500 }}>{run.phone || "-"}</div>
                {run.user_name ? (
                  <div style={{ fontSize: "11px", opacity: 0.7, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "120px" }}>
                    {run.user_name}
                  </div>
                ) : null}
              </td>
              <td>{run.created_at}</td>
              <td>{run.exit_code ?? "-"}</td>
              <td>
                <div className="row-actions">
                  <button className="secondary small" onClick={(event) => { event.stopPropagation(); onViewRun(run.id); }}>
                    View
                  </button>
                  <button
                    className="small"
                    disabled={!isActiveStatus(run.status)}
                    onClick={(event) => {
                      event.stopPropagation();
                      onCancelRun(run.id);
                    }}
                  >
                    Stop
                  </button>
                  <button
                    className="secondary small"
                    disabled={isActiveStatus(run.status)}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteRunRequest(run);
                    }}
                    style={{ marginLeft: "4px" }}
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination total={runsTotal} offset={runsOffset} limit={runsPerPage} onPageChange={onPageChange} />
    </div>
  );
}
