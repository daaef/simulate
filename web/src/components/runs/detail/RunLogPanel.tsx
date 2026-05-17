"use client";

import RunLogViewer from "../RunLogViewer";

interface RunLogPanelProps {
  log: string | null;
  logClassForLine: (line: string) => string;
}

export default function RunLogPanel({ log, logClassForLine }: RunLogPanelProps) {
  return (
    <RunLogViewer
      log={log}
      logClassForLine={logClassForLine}
      emptyMessage="Log not available"
    />
  );
}
