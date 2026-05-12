"use client";

import type { LifecycleStep } from "../../lib/api";

function formatTime(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return value;
  }
}

export default function LifecycleTimeline({ steps }: { steps: LifecycleStep[] }) {
  return (
    <article className="panel">
      <div className="section-heading-row">
        <h2 className="section-title">Latest Run Lifecycle</h2>
        <span className="muted">{steps.length} steps</span>
      </div>

      {steps.length ? (
        <div className="lifecycle-timeline">
          {steps.map((step, index) => (
            <div key={`${step.label}-${index}`} className={`lifecycle-step ${step.ok ? "ok" : "bad"}`}>
              <div className="lifecycle-dot" />
              <div className="lifecycle-copy">
                <div className="lifecycle-title-row">
                  <strong>{step.label}</strong>
                  <span>{formatTime(step.at)}</span>
                </div>
                <p className="muted">
                  {step.actor}
                  {step.status ? ` · ${step.status}` : ""}
                  {step.latency_ms ? ` · ${step.latency_ms}ms` : ""}
                </p>
                {step.endpoint ? <p className="muted lifecycle-endpoint">{step.endpoint}</p> : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="chart-empty">No lifecycle events captured.</div>
      )}
    </article>
  );
}