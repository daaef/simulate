"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FocusEvent } from "react";
import type { FlowCapability } from "../../lib/api";
import { buildExecutionImpact, type ExecutionImpact, type ImpactSeverity } from "../../lib/run-impact-explainer";
import {
  formatActorSource,
  resolveLaunchActors,
  type ResolvedLaunchScope,
} from "../../lib/resolve-launch-actors";
import {
  getLauncherFieldHelp,
  getSelectedOptionHelp,
  type LauncherFieldHelp,
  type LauncherFieldId,
  type LauncherHelpContext,
  type SelectedOptionHelp,
} from "../../lib/run-launcher-config";
import { useDebouncedValue } from "../../lib/useDebouncedValue";

interface RunLaunchHelpSidebarProps {
  focusedFieldId: LauncherFieldId | null;
  helpContext: LauncherHelpContext;
  flowGuideSectionId?: string;
}

function SeverityBadge({ severity }: { severity: ImpactSeverity }) {
  return (
    <span
      className="launcher-impact-severity"
      data-severity={severity}
      style={{
        fontSize: "11px",
        textTransform: "uppercase",
        padding: "2px 6px",
        borderRadius: 999,
        border: "1px solid",
        borderColor:
          severity === "blocking"
            ? "var(--status-danger-border)"
            : severity === "warning"
              ? "var(--status-warning-border)"
              : "var(--border-primary)",
        color:
          severity === "blocking"
            ? "var(--status-danger-text)"
            : severity === "warning"
              ? "var(--status-warning-text)"
              : "var(--text-secondary)",
      }}
    >
      {severity}
    </span>
  );
}

function SelectedValueBlock({ selected }: { selected: SelectedOptionHelp }) {
  return (
    <div className="launcher-selected-value">
      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
        Selected
      </div>
      {selected.items && selected.items.length > 0 ? (
        <div className="grid" style={{ gap: 10 }}>
          {selected.items.map((item) => (
            <div key={item.valueLabel}>
              <strong>
                <code>{item.valueLabel}</code>
              </strong>
              <p className="muted" style={{ margin: "6px 0 0", fontSize: 13, lineHeight: 1.45 }}>
                {item.description}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <>
          <strong>
            <code>{selected.valueLabel}</code>
          </strong>
          <p className="muted" style={{ margin: "8px 0 0", fontSize: 14, lineHeight: 1.5 }}>
            {selected.description}
          </p>
        </>
      )}
    </div>
  );
}

function OptionsTable({
  help,
  selectedValues,
}: {
  help: LauncherFieldHelp;
  selectedValues: Set<string>;
}) {
  if (!help.options?.length) return null;
  return (
    <table className="launcher-help-options-table">
      <thead>
        <tr>
          <th scope="col">Value</th>
          <th scope="col">Meaning</th>
        </tr>
      </thead>
      <tbody>
        {help.options.map((option) => {
          const isSelected = selectedValues.has(option.value);
          return (
            <tr key={option.value || "__default__"} className={isSelected ? "launcher-option-selected" : undefined}>
              <td>
                <code>{option.label || option.value || "(default)"}</code>
              </td>
              <td className="muted">{option.description}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function FieldHelpContent({
  help,
  selected,
}: {
  help: LauncherFieldHelp;
  selected: SelectedOptionHelp | null;
}) {
  const [allOptionsExpanded, setAllOptionsExpanded] = useState(false);
  const selectedValues = useMemo((): Set<string> => {
    if (help.fieldId === "scenarios" && selected?.items) {
      return new Set(selected.items.map((item) => item.valueLabel));
    }
    if (selected?.valueLabel && !selected.items) {
      const map: Record<string, string> = {
        "Flow default": "",
        "Use flow default": "",
      };
      const mapped = map[selected.valueLabel];
      if (mapped !== undefined) return new Set<string>([mapped]);
      if (selected.valueLabel.startsWith("(")) return new Set<string>();
      return new Set<string>([selected.valueLabel]);
    }
    return new Set<string>();
  }, [help.fieldId, selected]);

  return (
    <>
      {selected ? <SelectedValueBlock selected={selected} /> : null}
      <p className="muted" style={{ margin: selected ? "14px 0 0" : 0, fontSize: 14, lineHeight: 1.5 }}>
        {help.whenToChange}
      </p>
      {help.constraints.length ? (
        <ul className="launcher-help-constraints">
          {help.constraints.map((line) => (
            <li key={line} className="muted">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
      {help.options && help.options.length > 0 ? (
        <div className="launcher-all-options">
          <button
            type="button"
            className="secondary launcher-all-options-toggle"
            onClick={() => setAllOptionsExpanded((prev) => !prev)}
            aria-expanded={allOptionsExpanded}
          >
            {allOptionsExpanded ? "Hide all options" : "All options"}
          </button>
          {allOptionsExpanded ? (
            <OptionsTable help={help} selectedValues={selectedValues} />
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function ResolvedScopeBlock({
  scope,
  isPending,
}: {
  scope: ResolvedLaunchScope | null;
  isPending: boolean;
}) {
  if (isPending) {
    return (
      <div className="launcher-resolved-scope" style={{ marginTop: 14 }}>
        <strong style={{ fontSize: 13 }}>Resolved scope</strong>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
          Updating resolved scope…
        </p>
      </div>
    );
  }

  if (!scope) {
    return (
      <div className="launcher-resolved-scope" style={{ marginTop: 14 }}>
        <strong style={{ fontSize: 13 }}>Resolved scope</strong>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
          Plan content unavailable for preview.
        </p>
      </div>
    );
  }

  const rows: Array<{ label: string; value: string; source?: string }> = [
    { label: "Plan", value: scope.planPath },
    {
      label: "Store",
      value: scope.storeSource === "random_plan_pool" ? "random from plan pool" : (scope.storeId || "(unset)"),
      source: formatActorSource(scope.storeSource),
    },
    {
      label: "Phone",
      value: scope.phoneSource === "random_plan_pool" ? "random from plan pool" : (scope.phone || "(unset)"),
      source: formatActorSource(scope.phoneSource),
    },
    {
      label: "User scope",
      value:
        scope.userScope === "all_plan_users"
          ? `All ${scope.planUserCount} plan users`
          : `Single user (${scope.planUserCount} in plan)`,
    },
    { label: "Timing", value: scope.timing },
  ];

  if (scope.users !== undefined) {
    rows.push(
      { label: "Load users", value: String(scope.users) },
      { label: "Load orders", value: String(scope.orders) },
      { label: "Load interval", value: `${scope.interval}s` },
      { label: "Load reject", value: String(scope.reject) },
    );
  }

  return (
    <div className="launcher-resolved-scope" style={{ marginTop: 14 }}>
      <strong style={{ fontSize: 13 }}>Resolved scope</strong>
      <dl className="launcher-resolved-scope-dl" style={{ margin: "8px 0 0", fontSize: 13 }}>
        {rows.map((row) => (
          <div key={row.label} style={{ display: "grid", gridTemplateColumns: "88px 1fr", gap: 8, marginTop: 6 }}>
            <dt className="muted" style={{ margin: 0 }}>
              {row.label}
            </dt>
            <dd style={{ margin: 0 }}>
              <code>{row.value}</code>
              {row.source ? (
                <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>
                  ({row.source})
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function RunSummarySection({
  impact,
  resolvedScope,
  isPending,
  expanded,
  onToggleExpanded,
}: {
  impact: ExecutionImpact;
  resolvedScope: ResolvedLaunchScope | null;
  isPending: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
}) {
  return (
    <section className="launcher-run-summary" aria-live="polite" aria-label="Run summary">
      <ResolvedScopeBlock scope={resolvedScope} isPending={isPending} />
      <div className="launcher-run-summary-header" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <strong>Run summary</strong>
          {!isPending ? <SeverityBadge severity={impact.severity} /> : null}
        </div>
        {!isPending ? (
          <button type="button" className="secondary launcher-run-summary-toggle" onClick={onToggleExpanded}>
            {expanded ? "Hide details" : "Show details"}
          </button>
        ) : null}
      </div>
      {isPending ? (
        <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>
          Updating run summary…
        </p>
      ) : (
        <>
          {impact.summaryLines.map((line, index) => (
            <p key={`summary-${index}`} className="muted" style={{ margin: "8px 0 0", fontSize: 13, lineHeight: 1.45 }}>
              {line}
            </p>
          ))}
          {impact.warnings.length ? (
            <div className="grid" style={{ gap: 4, marginTop: 8 }}>
              {impact.warnings.map((warning, index) => (
                <div key={`warning-${index}`} style={{ color: "var(--status-danger-text)", fontSize: 13 }}>
                  {warning}
                </div>
              ))}
            </div>
          ) : null}
          {expanded ? (
            <div className="grid" style={{ gap: 8, marginTop: 10 }}>
              {impact.detailBlocks.map((block) => (
                <div key={block.title} className="panel" style={{ padding: 10 }}>
                  <strong style={{ fontSize: 13 }}>{block.title}</strong>
                  {block.lines.map((line, index) => (
                    <div key={`${block.title}-${index}`} className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                      {line}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export default function RunLaunchHelpSidebar({
  focusedFieldId,
  helpContext,
  flowGuideSectionId = "flow-planner-guide",
}: RunLaunchHelpSidebarProps) {
  const [mobileExpanded, setMobileExpanded] = useState(true);
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  const help = useMemo(
    () => (focusedFieldId ? getLauncherFieldHelp(focusedFieldId, helpContext) : null),
    [focusedFieldId, helpContext],
  );

  const selected = useMemo(
    () => (focusedFieldId ? getSelectedOptionHelp(focusedFieldId, helpContext) : null),
    [focusedFieldId, helpContext],
  );

  const formSnapshot = useMemo(() => JSON.stringify(helpContext.form), [helpContext.form]);
  const debouncedFormSnapshot = useDebouncedValue(formSnapshot, 1000);
  const debouncedMode = useDebouncedValue(helpContext.resolvedMode, 1000);
  const isSummaryPending =
    debouncedFormSnapshot !== formSnapshot || debouncedMode !== helpContext.resolvedMode;

  const debouncedForm = useMemo(() => {
    try {
      return JSON.parse(debouncedFormSnapshot) as typeof helpContext.form;
    } catch {
      return helpContext.form;
    }
  }, [debouncedFormSnapshot, helpContext.form]);

  const debouncedCapability = useMemo((): FlowCapability | null => {
    return helpContext.flowCapabilities[debouncedForm.flow] || null;
  }, [helpContext.flowCapabilities, debouncedForm.flow]);

  const debouncedPlanContent = useMemo(() => {
    return helpContext.planOptions.find((plan) => plan.path === debouncedForm.plan)?.content ?? null;
  }, [helpContext.planOptions, debouncedForm.plan]);

  const resolvedScope = useMemo(
    () => resolveLaunchActors(debouncedForm, debouncedPlanContent, debouncedMode),
    [debouncedForm, debouncedPlanContent, debouncedMode],
  );

  const runSummary = useMemo(
    () => buildExecutionImpact(debouncedForm, debouncedMode, debouncedCapability),
    [debouncedForm, debouncedMode, debouncedCapability],
  );

  useEffect(() => {
    if (focusedFieldId) {
      setMobileExpanded(true);
    }
  }, [focusedFieldId]);

  const idleContent = (
    <>
      <p className="muted" style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>
        Select a field in the launch form to see what your current choice does. Run summary updates after you pause
        editing.
      </p>
      <ul className="launcher-help-links">
        <li>
          <Link href="/overview#which-simulation-flow">Which simulation should I run?</Link>
        </li>
        <li>
          <a href={`#${flowGuideSectionId}`}>Flow Planner &amp; Command Guide</a>
        </li>
      </ul>
    </>
  );

  return (
    <aside className="panel launcher-help-sidebar" aria-label="Launch field help">
      <div className="launcher-help-sidebar-header">
        <strong>{help?.title ?? "Field help"}</strong>
        <button
          type="button"
          className="secondary launcher-help-mobile-toggle"
          aria-expanded={mobileExpanded}
          onClick={() => setMobileExpanded((prev) => !prev)}
        >
          {mobileExpanded ? "Hide" : "Show"}
        </button>
      </div>
      <div className={`launcher-help-sidebar-body ${mobileExpanded ? "expanded" : ""}`}>
        {help ? <FieldHelpContent help={help} selected={selected} /> : idleContent}
        <RunSummarySection
          impact={runSummary}
          resolvedScope={resolvedScope}
          isPending={isSummaryPending}
          expanded={summaryExpanded}
          onToggleExpanded={() => setSummaryExpanded((prev) => !prev)}
        />
      </div>
    </aside>
  );
}

export function launcherFieldFocusHandlers(
  fieldId: LauncherFieldId,
  onFocusField: (fieldId: LauncherFieldId | null) => void,
): {
  onFocusCapture: () => void;
  onBlurCapture: (event: FocusEvent<HTMLElement>) => void;
} {
  return {
    onFocusCapture: () => onFocusField(fieldId),
    onBlurCapture: (event) => {
      const container = event.currentTarget;
      const next = event.relatedTarget as Node | null;
      if (container.contains(next)) return;
      onFocusField(null);
    },
  };
}

export function notifyLauncherField(
  fieldId: LauncherFieldId,
  onFocusField: (fieldId: LauncherFieldId | null) => void,
): void {
  onFocusField(fieldId);
}
