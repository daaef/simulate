"use client";

import type { RunRow } from "../../lib/api";

interface ActiveRunsStripProps {
  runs: RunRow[];
  selectedRunId: number | null;
  onSelectRun: (runId: number) => void;
}

function scrollToLaunchSettings(): void {
  document.getElementById("launch-settings")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function ActiveRunsStrip({ runs, selectedRunId, onSelectRun }: ActiveRunsStripProps) {
  const count = runs.length;

  return (
    <section className="active-runs-panel panel" aria-label="Active runs">
      <div className="active-runs-header">
        <div>
          <p className="eyebrow">Active runs</p>
          <div className="active-runs-title-row">
            <h3 className="active-runs-title">{count ? `${count} in progress` : "No runs in progress"}</h3>
            <span className={`active-runs-count-badge ${count ? "active" : "idle"}`} aria-hidden="true">
              {count}
            </span>
          </div>
        </div>
        {count ? <span className="status-pill status-warning">Live</span> : <span className="status-pill status-info">Idle</span>}
      </div>

      {count ? (
        <div className="active-runs-strip" role="list">
          {runs.map((run) => {
            const isSelected = run.id === selectedRunId;
            return (
              <button
                key={run.id}
                type="button"
                role="listitem"
                className={isSelected ? "active-run-chip selected" : "active-run-chip"}
                onClick={() => onSelectRun(run.id)}
                aria-pressed={isSelected}
              >
                <span>#{run.id}</span>
                <span className="muted">{run.status}</span>
                <span>{run.flow}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="active-runs-empty" aria-live="polite">
          <p className="muted active-runs-empty-body">
            Configure launch settings below, then press <strong>Start Simulation</strong>.
          </p>
          <button type="button" className="secondary active-runs-empty-cta" onClick={scrollToLaunchSettings}>
            Go to launch settings
          </button>
        </div>
      )}
    </section>
  );
}
