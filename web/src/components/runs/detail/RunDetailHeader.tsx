"use client";

import type { RunRow } from "../../../lib/api";
import { formatRelativeTime, formatRunDuration } from "../../../lib/time-format";

interface RunDetailHeaderProps {
  run: RunRow;
  onBack: () => void;
}

export default function RunDetailHeader({ run, onBack }: RunDetailHeaderProps) {
  const statusStyles =
    run.status === "succeeded"
      ? { background: "#dcfce7", color: "#166534", border: "#86efac" }
      : run.status === "failed"
        ? { background: "#fee2e2", color: "#991b1b", border: "#fca5a5" }
        : { background: "#fef3c7", color: "#92400e", border: "#fcd34d" };

  return (
    <div className="panel grid" style={{ gap: 12 }}>
      <button onClick={onBack} className="secondary" style={{ width: "auto" }}>
        Back to Runs
      </button>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1>Run #{run.id}</h1>
        <span
          style={{
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 600,
            textTransform: "lowercase",
            background: statusStyles.background,
            color: statusStyles.color,
            border: `1px solid ${statusStyles.border}`,
          }}
        >
          {run.status}
        </span>
      </div>
      <div className="grid three">
        <div className="muted">Flow: <strong>{run.flow}</strong></div>
        <div className="muted">Plan: <strong>{run.plan}</strong></div>
        <div className="muted">Timing: <strong>{run.timing}</strong></div>
        <div className="muted">Store: <strong>{run.store_id || "Auto-selected"}</strong></div>
        <div className="muted">Phone: <strong>{run.phone || "Auto-selected"}</strong></div>
        <div className="muted">Created: <strong>{formatRelativeTime(run.created_at)}</strong></div>
        <div className="muted">Duration: <strong>{formatRunDuration(run.started_at, run.finished_at)}</strong></div>
        {run.exit_code !== null ? <div className="muted">Exit Code: <strong>{run.exit_code}</strong></div> : null}
      </div>
    </div>
  );
}
