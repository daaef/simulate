"use client";

import { forwardRef } from "react";

interface RunLogViewerProps {
  log: string | null;
  logClassForLine: (line: string) => string;
  emptyMessage?: string;
}

const RunLogViewer = forwardRef<HTMLPreElement, RunLogViewerProps>(function RunLogViewer(
  { log, logClassForLine, emptyMessage = "No log output yet." },
  ref,
) {
  if (!log) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <pre ref={ref} className="log">
      {log.split("\n").map((line, idx) => (
        <span key={`${idx}-${line.length}`} className={logClassForLine(line)}>
          {line}
          {"\n"}
        </span>
      ))}
    </pre>
  );
});

export default RunLogViewer;
