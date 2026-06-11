"use client";

import { useMemo, useRef, useState } from "react";
import type {
  FlowCapability,
  RunCreateRequest,
  RunRow,
  SimulationPlan,
  SimulationPlanContent,
} from "../../lib/api";
import {
  applyLoadPaceSelection,
  resolveLoadPaceSelection,
  type LoadPaceSelection,
} from "../../lib/load-mode-controls";
import type { LauncherFieldId } from "../../lib/run-launcher-config";
import LaunchActorSelect from "./LaunchActorSelect";
import { launcherFieldFocusHandlers, notifyLauncherField } from "./RunLaunchHelpSidebar";
import ScenarioChipsMultiSelect from "./ScenarioChipsMultiSelect";

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
  onFocusField: (fieldId: LauncherFieldId | null) => void;
  commandPreview: string;
  canCancelSelectedRun: boolean;
  planOptions?: SimulationPlan[];
  planContent?: SimulationPlanContent | null;
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
  onFocusField,
  commandPreview,
  canCancelSelectedRun,
  planOptions = [],
  planContent = null,
}: RunLaunchPanelProps) {
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const manualLoadIntervalRef = useRef<number | undefined>(undefined);
  const capability = useMemo(() => flowCapabilities[form.flow] || null, [flowCapabilities, form.flow]);
  const suiteOptions = capability?.available_suites || [];
  const scenarioOptions = capability?.available_scenarios || [];
  const isTraceMode = resolvedMode === "trace";
  const isLoadMode = resolvedMode === "load";
  const isPlaceOrderTrace = isTraceMode && form.flow === "place-order";
  const showOrdersField = isLoadMode || isPlaceOrderTrace;
  const loadPaceSelection = resolveLoadPaceSelection(form.interval);
  const focus = (fieldId: LauncherFieldId) => launcherFieldFocusHandlers(fieldId, onFocusField);
  const touch = (fieldId: LauncherFieldId) => notifyLauncherField(fieldId, onFocusField);

  return (
    <div id="launch-settings" className="panel grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Launch settings</h2>
        <CollapseButton isExpanded={isExpanded} onToggle={onToggleExpanded} title="launch settings" />
      </div>
      {isExpanded ? (
        <>
          <div className="grid three">
            <label {...focus("flow")}>
              <div>Flow</div>
              <select
                value={form.flow}
                onChange={(event) => {
                  touch("flow");
                  onFormChange((prev) => {
                    const nextFlow = event.target.value;
                    const nextMode = flowCapabilities[nextFlow]?.resolved_mode || "trace";
                    const allowsOrders = nextMode === "load" || nextFlow === "place-order";
                    return {
                      ...prev,
                      flow: nextFlow,
                      suite: undefined,
                      scenarios: [],
                      users: nextMode === "trace" ? undefined : prev.users,
                      orders: allowsOrders ? prev.orders : undefined,
                      interval: nextMode === "trace" ? undefined : prev.interval,
                      reject: nextMode === "trace" ? undefined : prev.reject,
                      continuous: nextMode === "trace" ? false : prev.continuous,
                    };
                  });
                }}
              >
                {(flows.length ? flows : ["doctor"]).map((flow) => (
                  <option value={flow} key={flow}>
                    {flow}
                  </option>
                ))}
              </select>
            </label>
            <label {...focus("timing")}>
              <div>Timing</div>
              <select
                value={form.timing}
                onChange={(event) => {
                  touch("timing");
                  onFormChange((prev) => ({ ...prev, timing: event.target.value as "fast" | "realistic" }));
                }}
              >
                <option value="fast">fast</option>
                <option value="realistic">realistic</option>
              </select>
            </label>
            <label {...focus("plan")}>
              <div>Plan</div>
              <select
                value={form.plan}
                onChange={(event) => {
                  touch("plan");
                  onFormChange((prev) => ({ ...prev, plan: event.target.value }));
                }}
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
          {isTraceMode ? (
            <div className="grid two">
              <button className="secondary" onClick={() => setAdvancedExpanded((prev) => !prev)}>
                {advancedExpanded ? "Hide Advanced Mode Overrides" : "Show Advanced Mode Overrides"}
              </button>
              <div className="muted" style={{ alignSelf: "center" }}>
                Resolved mode: <code>{resolvedMode}</code>
                {hasAdvancedOverrides ? " (overridden)" : ""}
              </div>
            </div>
          ) : (
            <div className="muted" style={{ alignSelf: "center" }}>
              Resolved mode: <code>{resolvedMode}</code>
              {hasAdvancedOverrides ? " (overridden)" : ""}
            </div>
          )}
          {isTraceMode && advancedExpanded ? (
            <div className="grid two">
              <label {...focus("mode")}>
                <div>Mode Override</div>
                <select
                  value={form.mode || ""}
                  onChange={(event) => {
                    touch("mode");
                    onFormChange((prev) => ({
                      ...prev,
                      mode: event.target.value ? (event.target.value as "trace" | "load") : undefined,
                      suite: event.target.value === "load" ? undefined : prev.suite,
                      scenarios: event.target.value === "load" ? [] : prev.scenarios,
                      users: event.target.value === "trace" ? undefined : prev.users,
                      orders:
                        event.target.value === "trace" && prev.flow !== "place-order"
                          ? undefined
                          : prev.orders,
                      interval: event.target.value === "trace" ? undefined : prev.interval,
                      reject: event.target.value === "trace" ? undefined : prev.reject,
                      continuous: event.target.value === "trace" ? false : prev.continuous,
                    }));
                  }}
                >
                  <option value="">Use flow default</option>
                  <option value="trace">trace</option>
                  <option value="load">load</option>
                </select>
              </label>
              <label {...focus("suite")}>
                <div>Suite (trace only)</div>
                <select
                  value={form.suite || ""}
                  disabled={!isTraceMode}
                  onChange={(event) => {
                    touch("suite");
                    onFormChange((prev) => ({ ...prev, suite: event.target.value || undefined }));
                  }}
                >
                  <option value="">Flow default</option>
                  {suiteOptions.map((suite) => (
                    <option key={suite} value={suite}>
                      {suite}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ gridColumn: "1 / -1" }} {...focus("scenarios")}>
                <div>Scenarios (trace only)</div>
                <ScenarioChipsMultiSelect
                  options={scenarioOptions}
                  value={form.scenarios || []}
                  disabled={!isTraceMode}
                  onTouch={() => touch("scenarios")}
                  onChange={(scenarios) => {
                    onFormChange((prev) => ({ ...prev, scenarios }));
                  }}
                />
              </label>
            </div>
          ) : null}
          <div className="grid three">
            <label {...focus("store")}>
              <div>Store ID</div>
              <LaunchActorSelect
                fieldId="store"
                planContent={planContent}
                value={form.store_id}
                onFocus={() => onFocusField("store")}
                onBlur={() => onFocusField(null)}
                onTouch={() => touch("store")}
                onChange={(store_id, isPlanDefault) => onFormChange((prev) => ({ ...prev, store_id, store_is_plan_default: isPlanDefault }))}
              />
            </label>
            <div {...focus("phone")}>
              <div>Phone</div>
              <LaunchActorSelect
                fieldId="phone"
                planContent={planContent}
                value={form.phone}
                onFocus={() => onFocusField("phone")}
                onBlur={() => onFocusField(null)}
                onTouch={() => touch("phone")}
                onChange={(phone, isPlanDefault) => onFormChange((prev) => ({ ...prev, phone, phone_is_plan_default: isPlanDefault }))}
              />
            </div>
            {isLoadMode ? (
              <label {...focus("users")}>
                <div>Users</div>
                <input
                  type="number"
                  min={1}
                  value={form.users ?? ""}
                  onChange={(event) => {
                    touch("users");
                    onFormChange((prev) => ({
                      ...prev,
                      users: event.target.value ? Number(event.target.value) : undefined,
                    }));
                  }}
                  placeholder="e.g. 5"
                />
              </label>
            ) : null}
            {showOrdersField ? (
              <label {...focus("orders")}>
                <div>Orders</div>
                <input
                  type="number"
                  min={1}
                  max={isPlaceOrderTrace ? 10 : undefined}
                  value={form.orders ?? ""}
                  onChange={(event) => {
                    touch("orders");
                    onFormChange((prev) => ({
                      ...prev,
                      orders: event.target.value ? Number(event.target.value) : undefined,
                    }));
                  }}
                  placeholder={isPlaceOrderTrace ? "e.g. 3" : "e.g. 50"}
                />
              </label>
            ) : null}
            {isLoadMode ? (
              <label {...focus("interval")}>
                <div>Load Pace</div>
                <select
                  value={loadPaceSelection}
                  onChange={(event) => {
                    touch("interval");
                    const selected = event.target.value as LoadPaceSelection;
                    onFormChange((prev) => {
                      const next = applyLoadPaceSelection({
                        selected,
                        currentInterval: prev.interval,
                        manualInterval: manualLoadIntervalRef.current,
                      });
                      manualLoadIntervalRef.current = next.manualInterval;
                      return {
                        ...prev,
                        interval: next.interval,
                      };
                    });
                  }}
                >
                  <option value="slow">slow (10s)</option>
                  <option value="normal">normal (3s)</option>
                  <option value="fast">fast (1s)</option>
                  <option value="custom">custom (manual)</option>
                </select>
              </label>
            ) : null}
            {isLoadMode ? (
              <label {...focus("interval")}>
                <div>Interval (sec)</div>
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  value={form.interval ?? ""}
                  onChange={(event) => {
                    touch("interval");
                    const parsed = event.target.value ? Number(event.target.value) : undefined;
                    const nextInterval =
                      parsed === undefined || Number.isFinite(parsed) ? parsed : undefined;
                    manualLoadIntervalRef.current = nextInterval;
                    onFormChange((prev) => ({
                      ...prev,
                      interval: nextInterval,
                    }));
                  }}
                  placeholder="e.g. 3"
                />
              </label>
            ) : null}
            {isLoadMode ? (
              <label {...focus("reject")}>
                <div>Reject Rate</div>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={form.reject ?? ""}
                  onChange={(event) => {
                    touch("reject");
                    onFormChange((prev) => ({
                      ...prev,
                      reject: event.target.value ? Number(event.target.value) : undefined,
                    }));
                  }}
                  placeholder="e.g. 0.10"
                />
              </label>
            ) : null}
          </div>
          <div className="grid three">
            <div className="launcher-field-group" {...focus("all_users")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.all_users}
                  onChange={(event) => {
                    touch("all_users");
                    onFormChange((prev) => ({ ...prev, all_users: event.target.checked }));
                  }}
                />
                All Users
              </label>
            </div>
            <div className="launcher-field-group" {...focus("strict_plan")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.strict_plan || false}
                  onChange={(event) => {
                    touch("strict_plan");
                    onFormChange((prev) => ({ ...prev, strict_plan: event.target.checked }));
                  }}
                />
                Strict Plan
              </label>
            </div>
            <div className="launcher-field-group" {...focus("skip_app_probes")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.skip_app_probes || false}
                  onChange={(event) => {
                    touch("skip_app_probes");
                    onFormChange((prev) => ({ ...prev, skip_app_probes: event.target.checked }));
                  }}
                />
                Skip App Probes
              </label>
            </div>
            <div className="launcher-field-group" {...focus("skip_store_dashboard_probes")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.skip_store_dashboard_probes || false}
                  onChange={(event) => {
                    touch("skip_store_dashboard_probes");
                    onFormChange((prev) => ({ ...prev, skip_store_dashboard_probes: event.target.checked }));
                  }}
                />
                Skip Store Dashboard Probes
              </label>
            </div>
            <div className="launcher-field-group" {...focus("no_auto_provision")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.no_auto_provision}
                  onChange={(event) => {
                    touch("no_auto_provision");
                    onFormChange((prev) => ({ ...prev, no_auto_provision: event.target.checked }));
                  }}
                />
                No Auto Provision
              </label>
            </div>
            <div className="launcher-field-group" {...focus("post_order_actions")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.post_order_actions || false}
                  onChange={(event) => {
                    touch("post_order_actions");
                    onFormChange((prev) => ({ ...prev, post_order_actions: event.target.checked }));
                  }}
                />
                Post-Order Actions
              </label>
            </div>
            {isLoadMode ? (
              <div className="launcher-field-group" {...focus("continuous")}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={form.continuous || false}
                    onChange={(event) => {
                      touch("continuous");
                      onFormChange((prev) => ({ ...prev, continuous: event.target.checked }));
                    }}
                  />
                  Continuous
                </label>
              </div>
            ) : null}
            <div className="launcher-field-group" {...focus("enforce_websocket_gates")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.enforce_websocket_gates || false}
                  onChange={(event) => {
                    touch("enforce_websocket_gates");
                    onFormChange((prev) => ({ ...prev, enforce_websocket_gates: event.target.checked }));
                  }}
                />
                Enforce Websocket Gates
              </label>
            </div>
            {isTraceMode ? (
              <div className="launcher-field-group" {...focus("store_auto_cancel")}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={form.store_auto_cancel || false}
                    onChange={(event) => {
                      touch("store_auto_cancel");
                      onFormChange((prev) => ({ ...prev, store_auto_cancel: event.target.checked }));
                    }}
                  />
                  Store auto cancel
                </label>
              </div>
            ) : null}
            {isTraceMode ? (
              <div className="launcher-field-group" {...focus("wait_for_store_action")}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={form.wait_for_store_action || false}
                    onChange={(event) => {
                      touch("wait_for_store_action");
                      onFormChange((prev) => ({ ...prev, wait_for_store_action: event.target.checked }));
                    }}
                  />
                  Wait for real store action
                </label>
              </div>
            ) : null}
            <div className="launcher-field-group" {...focus("timeout_fails")}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.timeout_fails || false}
                  onChange={(event) => {
                    touch("timeout_fails");
                    onFormChange((prev) => ({ ...prev, timeout_fails: event.target.checked }));
                  }}
                />
                Timeout Fails
              </label>
            </div>
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
