"use client";

import type { RunRow } from "../../../lib/api";

interface RunExecutionSnapshotPanelProps {
  run: RunRow;
  onReplay?: () => void;
  replaying?: boolean;
}

function boolLabel(value: boolean | null | undefined): string {
  if (value === true) return "enabled";
  if (value === false) return "disabled";
  return "not set";
}

function artifactState(path: string | null): string {
  return path ? "available" : "missing";
}

export default function RunExecutionSnapshotPanel({ run, onReplay, replaying = false }: RunExecutionSnapshotPanelProps) {
  const snapshot = run.execution_snapshot || null;
  const extraArgs = run.extra_args.length ? run.extra_args.join(" ") : "none";
  const snapshotCommand =
    snapshot && typeof snapshot["command"] === "string" ? String(snapshot["command"]) : run.command;
  const snapshotPlan =
    snapshot && typeof snapshot["plan"] === "string" ? String(snapshot["plan"]) : run.plan;
  const snapshotTiming =
    snapshot && typeof snapshot["timing"] === "string" ? String(snapshot["timing"]) : run.timing;
  const snapshotMode =
    snapshot && typeof snapshot["mode"] === "string" ? String(snapshot["mode"]) : run.mode || "default";
  const snapshotExtraArgs =
    snapshot && Array.isArray(snapshot["extra_args"])
      ? (snapshot["extra_args"] as unknown[]).join(" ")
      : extraArgs;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="grid two">
        <div className="panel grid" style={{ gap: 10 }}>
          <h3 style={{ margin: 0 }}>Actor Context</h3>
          <div className="grid two">
            <div className="muted">User phone: <strong>{run.phone || "auto-selected"}</strong></div>
            <div className="muted">User name: <strong>{run.user_name || "unknown"}</strong></div>
            <div className="muted">Store ID: <strong>{run.store_id || "auto-selected"}</strong></div>
            <div className="muted">Store name: <strong>{run.store_name || "unknown"}</strong></div>
            <div className="muted">Store phone: <strong>{run.store_phone || "unknown"}</strong></div>
            <div className="muted">Mode: <strong>{run.mode || "default"}</strong></div>
          </div>
        </div>
        <div className="panel grid" style={{ gap: 10 }}>
          <h3 style={{ margin: 0 }}>Resolved Inputs</h3>
          <div className="grid two">
            <div className="muted">Flow: <strong>{run.flow}</strong></div>
            <div className="muted">Timing: <strong>{snapshotTiming}</strong></div>
            <div className="muted">Plan: <strong>{snapshotPlan}</strong></div>
            <div className="muted">All users: <strong>{boolLabel(run.all_users)}</strong></div>
            <div className="muted">Auto-provision: <strong>{run.no_auto_provision ? "disabled" : "enabled"}</strong></div>
            <div className="muted">Post-order actions: <strong>{boolLabel(run.post_order_actions)}</strong></div>
            <div className="muted">Mode: <strong>{snapshotMode}</strong></div>
          </div>
          <div className="muted">Extra args</div>
          <pre className="artifact command-preview">
            <code>{snapshotExtraArgs || "none"}</code>
          </pre>
        </div>
      </div>

      <div className="panel grid" style={{ gap: 10 }}>
        <h3 style={{ margin: 0 }}>Execution Command</h3>
        <div className="muted">
          This is the exact command string recorded for this run. It is the current closest thing to a replay snapshot until immutable execution snapshots are added.
        </div>
        {onReplay ? (
          <div>
            <button disabled={replaying} onClick={onReplay} style={{ width: "auto" }}>
              {replaying ? "Replaying..." : "Replay Exact Run"}
            </button>
          </div>
        ) : null}
        <pre className="artifact command-preview">
          <code>{snapshotCommand}</code>
        </pre>
      </div>

      <div className="grid two">
        <div className="panel grid" style={{ gap: 10 }}>
          <h3 style={{ margin: 0 }}>Artifact Availability</h3>
          <div className="grid two">
            <div className="muted">Report: <strong>{artifactState(run.report_path)}</strong></div>
            <div className="muted">Story: <strong>{artifactState(run.story_path)}</strong></div>
            <div className="muted">Events: <strong>{artifactState(run.events_path)}</strong></div>
            <div className="muted">Log: <strong>{artifactState(run.log_path)}</strong></div>
          </div>
        </div>
        <div className="panel grid" style={{ gap: 10 }}>
          <h3 style={{ margin: 0 }}>Artifact Paths</h3>
          <div className="muted">Report path</div>
          <pre className="artifact command-preview"><code>{run.report_path || "not written"}</code></pre>
          <div className="muted">Story path</div>
          <pre className="artifact command-preview"><code>{run.story_path || "not written"}</code></pre>
          <div className="muted">Events path</div>
          <pre className="artifact command-preview"><code>{run.events_path || "not written"}</code></pre>
          <div className="muted">Log path</div>
          <pre className="artifact command-preview"><code>{run.log_path || "not written"}</code></pre>
        </div>
      </div>
    </div>
  );
}
