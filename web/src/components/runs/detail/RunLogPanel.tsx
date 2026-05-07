"use client";

interface RunLogPanelProps {
  log: string | null;
  logClassForLine: (line: string) => string;
}

export default function RunLogPanel({ log, logClassForLine }: RunLogPanelProps) {
  if (!log) {
    return <p className="muted">Log not available</p>;
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
