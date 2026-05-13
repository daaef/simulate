"use client";

import { useMemo, useState } from "react";
import type { FlowCapability, RunCreateRequest, RunRow, SimulationPlan } from "../../lib/api";

interface RunLaunchPanelProps {
  flows: string[];
  flowCapabilities: Record<string, FlowCapability>;
  resolvedMode: "trace" | "load";
  modeValidationError: string | null;
  hasAdvancedOverrides: boolean;
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
  flowCapabilities,
  resolvedMode,
  modeValidationError,
  hasAdvancedOverrides,
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
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const capability = useMemo(() => flowCapabilities[form.flow] || null, [flowCapabilities, form.flow]);
  const suiteOptions = capability?.available_suites || [];
  const scenarioOptions = capability?.available_scenarios || [];
  const isTraceMode = resolvedMode === "trace";
  const isLoadMode = resolvedMode === "load";

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
              <select
                value={form.flow}
                onChange={(event) =>
                  onFormChange((prev) => {
                    const nextFlow = event.target.value;
                    const nextMode = flowCapabilities[nextFlow]?.resolved_mode || "trace";
                    return {
                      ...prev,
                      flow: nextFlow,
                      suite: undefined,
                      scenarios: [],
                      users: nextMode === "trace" ? undefined : prev.users,
                      orders: nextMode === "trace" ? undefined : prev.orders,
                      interval: nextMode === "trace" ? undefined : prev.interval,
                      reject: nextMode === "trace" ? undefined : prev.reject,
                      continuous: nextMode === "trace" ? false : prev.continuous,
                    };
                  })
                }
              >
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
              <select
                value={form.plan}
                onChange={(event) => onFormChange((prev) => ({ ...prev, plan: event.target.value }))}
              >
                <option value="sim_actors.json">sim_actors.json</option>
                {planOptions.map((plan) => (
                  <option value={plan.path} key={plan.id}>
                    {plan.name} ({plan.path})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid two">
            <button className="secondary" onClick={() => setAdvancedExpanded((prev) => !prev)}>
              {advancedExpanded ? "Hide Advanced Mode Overrides" : "Show Advanced Mode Overrides"}
            </button>
            <div className="muted" style={{ alignSelf: "center" }}>
              Resolved mode: <code>{resolvedMode}</code>
              {hasAdvancedOverrides ? " (overridden)" : ""}
            </div>
          </div>
          {advancedExpanded ? (
            <div className="grid two">
              <label>
                Mode Override
                <select
                  value={form.mode || ""}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      mode: event.target.value ? (event.target.value as "trace" | "load") : undefined,
                      suite: event.target.value === "load" ? undefined : prev.suite,
                      scenarios: event.target.value === "load" ? [] : prev.scenarios,
                      users: event.target.value === "trace" ? undefined : prev.users,
                      orders: event.target.value === "trace" ? undefined : prev.orders,
                      interval: event.target.value === "trace" ? undefined : prev.interval,
                      reject: event.target.value === "trace" ? undefined : prev.reject,
                      continuous: event.target.value === "trace" ? false : prev.continuous,
                    }))
                  }
                >
                  <option value="">Use flow default</option>
                  <option value="trace">trace</option>
                  <option value="load">load</option>
                </select>
              </label>
              <label>
                Suite (trace only)
                <select
                  value={form.suite || ""}
                  disabled={!isTraceMode}
                  onChange={(event) =>
                    onFormChange((prev) => ({ ...prev, suite: event.target.value || undefined }))
                  }
                >
                  <option value="">Flow default</option>
                  {suiteOptions.map((suite) => (
                    <option key={suite} value={suite}>
                      {suite}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ gridColumn: "1 / -1" }}>
                Scenarios (trace only)
                <select
                  multiple
                  value={form.scenarios || []}
                  disabled={!isTraceMode}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      scenarios: Array.from(event.target.selectedOptions).map((option) => option.value),
                    }))
                  }
                  style={{ minHeight: 120 }}
                >
                  {scenarioOptions.map((scenario) => (
                    <option key={scenario} value={scenario}>
                      {scenario}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}
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
            {isLoadMode ? (
              <label>
                Users
                <input
                  type="number"
                  min={1}
                  value={form.users ?? ""}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      users: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                  placeholder="Optional: load users"
                />
              </label>
            ) : null}
            {isLoadMode ? (
              <label>
                Orders
                <input
                  type="number"
                  min={1}
                  value={form.orders ?? ""}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      orders: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                  placeholder="Optional: load orders"
                />
              </label>
            ) : null}
            {isLoadMode ? (
              <label>
                Interval (sec)
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  value={form.interval ?? ""}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      interval: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                  placeholder="Optional: load interval"
                />
              </label>
            ) : null}
            {isLoadMode ? (
              <label>
                Reject Rate
                <input
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={form.reject ?? ""}
                  onChange={(event) =>
                    onFormChange((prev) => ({
                      ...prev,
                      reject: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                  placeholder="Optional: 0..1"
                />
              </label>
            ) : null}
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
                checked={form.strict_plan || false}
                onChange={(event) => onFormChange((prev) => ({ ...prev, strict_plan: event.target.checked }))}
              />
              Strict Plan
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.skip_app_probes || false}
                onChange={(event) => onFormChange((prev) => ({ ...prev, skip_app_probes: event.target.checked }))}
              />
              Skip App Probes
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.skip_store_dashboard_probes || false}
                onChange={(event) =>
                  onFormChange((prev) => ({ ...prev, skip_store_dashboard_probes: event.target.checked }))
                }
              />
              Skip Store Dashboard Probes
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
            {isLoadMode ? (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.continuous || false}
                  onChange={(event) => onFormChange((prev) => ({ ...prev, continuous: event.target.checked }))}
                />
                Continuous
              </label>
            ) : null}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.enforce_websocket_gates || false}
                onChange={(event) => onFormChange((prev) => ({ ...prev, enforce_websocket_gates: event.target.checked }))}
              />
              Enforce Websocket Gates
            </label>
          </div>
          {modeValidationError ? (
            <div className="muted" style={{ color: "var(--danger)" }}>
              {modeValidationError}
            </div>
          ) : null}
          <div className="grid two">
            <button disabled={isSubmitting || Boolean(modeValidationError)} onClick={onStartRun}>
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
