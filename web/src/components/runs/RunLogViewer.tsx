"use client";

interface RunLogViewerProps {
  log: string | null;
  logClassForLine: (line: string) => string;
  emptyMessage?: string;
}

export default function RunLogViewer({
  log,
  logClassForLine,
  emptyMessage = "No log output yet.",
}: RunLogViewerProps) {
  if (!log) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <pre className="log">
      {log.split("\n").map((line, idx) => (
        <span key={idx} className={logClassForLine(line)}>
          {line}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}
