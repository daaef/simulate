"use client";

import RunLogViewer from "../RunLogViewer";

interface RunLogPanelProps {
  log: string | null;
  logClassForLine: (line: string) => string;
  logRef?: (node: HTMLPreElement | null) => void;
}

export default function RunLogPanel({ log, logClassForLine, logRef }: RunLogPanelProps) {
  return (
    <RunLogViewer
      ref={logRef}
      log={log}
      logClassForLine={logClassForLine}
      emptyMessage="Log not available"
    />
  );
}
