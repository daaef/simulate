"use client";

import type { RunRow } from "../../lib/api";

interface RunLiveConsoleProps {
  selectedRun: RunRow | null;
  logLines: string[];
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

export default function RunLiveConsole({
  selectedRun,
  logLines,
  isExpanded,
  onToggleExpanded,
  logClassForLine,
}: RunLiveConsoleProps) {
  return (
    <div className="panel grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Live Console</h2>
        <CollapseButton isExpanded={isExpanded} onToggle={onToggleExpanded} title="Live Console" />
      </div>
      {isExpanded ? (
        <>
          {selectedRun ? (
            <div className="muted">
              Run #{selectedRun.id} ({selectedRun.status}) | {selectedRun.flow} | {selectedRun.store_id || "auto-store"}
            </div>
          ) : (
            <div className="muted">No run selected.</div>
          )}
          <pre className="log">
            {logLines.length ? (
              logLines.map((line, index) => (
                <span key={`${index}-${line}`} className={logClassForLine(line)}>
                  {line}
                  {"\n"}
                </span>
              ))
            ) : (
              <span className="log-line-default">No log output yet.</span>
            )}
          </pre>
        </>
      ) : null}
    </div>
  );
}
