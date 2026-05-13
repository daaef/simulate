"use client";

import type { RunCreateRequest, RunRow, SimulationPlan } from "../../lib/api";

interface RunLaunchPanelProps {
  flows: string[];
  form: RunCreateRequest;
  isSubmitting: boolean;
  selectedRun: RunRow | null;
  isExpanded: boolean;
  onToggleExpanded: () => void;
  onFormChange: (updater: (prev: RunCreateRequest) => RunCreateRequest) => void;
  onStartRun: () => void;
  onCancelSelectedRun: () => void;
  onSaveAsProfileShortcut: () => void;
  commandPreview: string;
  canCancelSelectedRun: boolean;
  planOptions?: SimulationPlan[];
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

export default function RunLaunchPanel({
  flows,
  form,
  isSubmitting,
  selectedRun,
  isExpanded,
  onToggleExpanded,
  onFormChange,
  onStartRun,
  onCancelSelectedRun,
  onSaveAsProfileShortcut,
  commandPreview,
  canCancelSelectedRun,
  planOptions = [],
}: RunLaunchPanelProps) {
  return (
    <div className="panel grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Start Run</h2>
        <CollapseButton isExpanded={isExpanded} onToggle={onToggleExpanded} title="Start Run" />
      </div>
      {isExpanded ? (
        <>
          <div className="grid three">
            <label>
              Flow
              <select value={form.flow} onChange={(event) => onFormChange((prev) => ({ ...prev, flow: event.target.value }))}>
                {(flows.length ? flows : ["doctor"]).map((flow) => (
                  <option value={flow} key={flow}>
                    {flow}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Timing
              <select
                value={form.timing}
                onChange={(event) =>
                  onFormChange((prev) => ({ ...prev, timing: event.target.value as "fast" | "realistic" }))
                }
              >
                <option value="fast">fast</option>
                <option value="realistic">realistic</option>
              </select>
            </label>
            <label>
              Plan
              {planOptions.length ? (
                <select
                  value={form.plan}
                  onChange={(event) => onFormChange((prev) => ({ ...prev, plan: event.target.value }))}
                  style={{ marginBottom: 8 }}
                >
                  <option value="sim_actors.json">sim_actors.json</option>
                  {planOptions.map((plan) => (
                    <option value={plan.path} key={plan.id}>
                      {plan.name} ({plan.path})
                    </option>
                  ))}
                </select>
              ) : null}
              <textarea
                value={form.plan}
                onChange={(event) => onFormChange((prev) => ({ ...prev, plan: event.target.value }))}
                placeholder="Enter simulation plan..."
                rows={3}
              />
            </label>
          </div>
          <div className="grid three">
            <label>
              Store ID
              <input
                type="text"
                value={form.store_id}
                onChange={(event) => onFormChange((prev) => ({ ...prev, store_id: event.target.value }))}
                placeholder="Optional: store ID"
              />
            </label>
            <label>
              Phone
              <input
                type="text"
                value={form.phone}
                onChange={(event) => onFormChange((prev) => ({ ...prev, phone: event.target.value }))}
                placeholder="Optional: phone number"
              />
            </label>
          </div>
          <div className="grid three">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.all_users}
                onChange={(event) => onFormChange((prev) => ({ ...prev, all_users: event.target.checked }))}
              />
              All Users
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.no_auto_provision}
                onChange={(event) => onFormChange((prev) => ({ ...prev, no_auto_provision: event.target.checked }))}
              />
              No Auto Provision
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.post_order_actions || false}
                onChange={(event) => onFormChange((prev) => ({ ...prev, post_order_actions: event.target.checked }))}
              />
              Post-Order Actions
            </label>
          </div>
          <div className="grid two">
            <button disabled={isSubmitting} onClick={onStartRun}>
              {isSubmitting ? "Starting..." : "Start Simulation"}
            </button>
            <button className="secondary" disabled={!selectedRun || !canCancelSelectedRun} onClick={onCancelSelectedRun}>
              Stop Selected Run
            </button>
          </div>
          <div className="muted">Resolved command preview</div>
          <pre className="artifact command-preview">
            <code>{commandPreview}</code>
          </pre>
          <button className="secondary" onClick={onSaveAsProfileShortcut}>
            Save as profile
          </button>
        </>
      ) : null}
    </div>
  );
}
