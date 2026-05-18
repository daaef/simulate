"use client";

import type { RunRow } from "../../lib/api";
import RunLogViewer from "./RunLogViewer";

interface RunLiveConsoleProps {
  selectedRun: RunRow | null;
  log: string;
  logRef?: (node: HTMLPreElement | null) => void;
  isExpanded: boolean;
  onToggleExpanded: () => void;
  logClassForLine: (line: string) => string;
}

function CollapseButton({
  isExpanded,
  onToggle,
  title,
}: {
  isExpanded: boolean;
  onToggle: () => void;
  title: string;
}) {
  return (
    <button
      className="secondary"
      onClick={onToggle}
      style={{
        width: "auto",
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        fontSize: "14px",
      }}
    >
      <span
        style={{
          display: "inline-block",
          transition: "transform 0.2s",
          transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
        }}
      >
        ▼
      </span>
      {isExpanded ? `Collapse ${title}` : `Expand ${title}`}
    </button>
  );
}

function collapsedSummary(selectedRun: RunRow | null): string {
  if (!selectedRun) {
    return "No run selected";
  }
  return `Run #${selectedRun.id} · ${selectedRun.status} · ${selectedRun.flow}`;
}

export default function RunLiveConsole({
  selectedRun,
  log,
  logRef,
  isExpanded,
  onToggleExpanded,
  logClassForLine,
}: RunLiveConsoleProps) {
  return (
    <div className="panel grid live-console-panel" style={{ gap: 12 }}>
      <div className="live-console-header">
        <div>
          <h2 style={{ margin: 0 }}>Live Console</h2>
          {!isExpanded ? (
            <p className="muted live-console-collapsed-summary" style={{ margin: "6px 0 0", fontSize: 13 }}>
              {collapsedSummary(selectedRun)}
            </p>
          ) : null}
        </div>
        <CollapseButton isExpanded={isExpanded} onToggle={onToggleExpanded} title="Live Console" />
      </div>
      {isExpanded ? (
        <>
          {selectedRun ? (
            <div className="muted">
              Run #{selectedRun.id} ({selectedRun.status}) | {selectedRun.flow} | {selectedRun.store_id || "auto-store"} | {selectedRun.trigger_source || "manual"} · {selectedRun.trigger_label || "Manual launch"}
              {selectedRun.profile_id
                ? ` · ${((selectedRun.trigger_context as Record<string, unknown> | undefined)?.profile_name as string) || `profile #${selectedRun.profile_id}`}`
                : ""}
            </div>
          ) : (
            <div className="muted">No run selected.</div>
          )}
          <RunLogViewer ref={logRef} log={log || null} logClassForLine={logClassForLine} />
        </>
      ) : null}
    </div>
  );
}
