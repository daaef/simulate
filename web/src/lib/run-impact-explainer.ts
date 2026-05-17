import type { FlowCapability, RunCreateRequest } from "./api";
import {
  buildResolvedScopeLines,
  buildResolvedScopeSummaryLine,
  type ResolvedLaunchScope,
} from "./resolve-launch-actors";

export type ImpactSeverity = "info" | "warning" | "blocking";

export type ExecutionImpact = {
  summaryLines: string[];
  detailBlocks: Array<{
    title: string;
    lines: string[];
  }>;
  warnings: string[];
  severity: ImpactSeverity;
};

function scenarioList(form: RunCreateRequest, capability: FlowCapability | null): string[] {
  const seen = new Set<string>();
  const scenarios: string[] = [];

  if (form.suite && capability?.available_suites?.includes(form.suite)) {
    // Suite expansion is handled by backend runtime; here we show explicit picks plus suite context.
  }
  for (const item of form.scenarios || []) {
    const key = String(item || "").trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    scenarios.push(key);
  }
  return scenarios;
}

function hasFlag(extraArgs: string[] | undefined, name: string): boolean {
  return Boolean(extraArgs?.includes(name));
}

function prettyMode(form: RunCreateRequest, resolvedMode: "trace" | "load"): string {
  return form.mode ? `${resolvedMode} (mode override active)` : `${resolvedMode} (flow default)`;
}

function buildWarnings(form: RunCreateRequest, resolvedMode: "trace" | "load"): string[] {
  const warnings: string[] = [];
  if (resolvedMode === "trace" && form.continuous) {
    warnings.push("Continuous is invalid in trace mode.");
  }
  if (
    resolvedMode === "trace" &&
    (form.users !== undefined || form.orders !== undefined || form.interval !== undefined || form.reject !== undefined)
  ) {
    warnings.push("users/orders/interval/reject are load-only controls.");
  }
  if (resolvedMode === "load" && ((form.scenarios || []).length > 0 || Boolean(form.suite?.trim()))) {
    warnings.push("suite/scenarios are trace-only controls.");
  }
  if (form.users !== undefined && form.users < 1) warnings.push("Users must be >= 1.");
  if (form.orders !== undefined && form.orders < 1) warnings.push("Orders must be >= 1.");
  if (form.reject !== undefined && (form.reject < 0 || form.reject > 1)) {
    warnings.push("Reject rate must be between 0 and 1.");
  }
  return warnings;
}

function paymentSummary(flow: string): string | null {
  if (flow === "paid-no-coupon") return "Payment branch: Stripe paid flow without coupon.";
  if (flow === "paid-coupon") return "Payment branch: Stripe paid flow with coupon discount path.";
  if (flow === "free-coupon") return "Payment branch: free-order coupon path (payable should resolve to zero).";
  if (flow === "payments") return "Payment suite: paid-no-coupon + paid-with-coupon + free-with-coupon coverage.";
  return null;
}

export function buildExecutionImpact(
  form: RunCreateRequest,
  resolvedMode: "trace" | "load",
  capability: FlowCapability | null,
  resolvedScope?: ResolvedLaunchScope | null,
): ExecutionImpact {
  const warnings = buildWarnings(form, resolvedMode);
  const selectedScenarios = scenarioList(form, capability);
  const modeLabel = prettyMode(form, resolvedMode);

  const summaryLines: string[] = [];
  const detailBlocks: ExecutionImpact["detailBlocks"] = [];

  if (resolvedMode === "trace") {
    const suiteLabel = form.suite?.trim() || capability?.default_suite || "core (default)";
    summaryLines.push(`Trace run using ${suiteLabel} suite context in deterministic order.`);
    if (selectedScenarios.length) {
      summaryLines.push(`Explicit scenarios: ${selectedScenarios.join(", ")} (deduped, in declaration order).`);
    } else {
      summaryLines.push("No explicit scenarios selected; runtime resolves suite/default scenario list.");
    }
    summaryLines.push(
      form.enforce_websocket_gates
        ? "Websocket gates enforced: missing required status events will fail the run."
        : "Websocket gates relaxed: missing required status events are recorded as warnings and run continues.",
    );

    const payment = paymentSummary(form.flow);
    if (payment) summaryLines.push(payment);

    detailBlocks.push({
      title: "What Will Run",
      lines: [
        `Flow: ${form.flow}.`,
        `Mode: ${modeLabel}.`,
        `Suite selector: ${suiteLabel}.`,
        selectedScenarios.length
          ? `Scenario override list: ${selectedScenarios.join(", ")}.`
          : "Scenario override list: none.",
      ],
    });

    detailBlocks.push({
      title: "Execution Behavior",
      lines: [
        form.skip_app_probes
          ? "App probes are skipped by flag; diagnostics on bootstrap APIs are reduced."
          : "App probes are enabled; config/cards/coupon/active-order checks are included when scenario paths call them.",
        form.skip_store_dashboard_probes
          ? "Store dashboard probes are skipped by flag."
          : "Store dashboard probes are enabled when relevant scenarios run.",
        form.no_auto_provision
          ? "Auto-provision is disabled; missing store/menu/setup prerequisites will fail fast."
          : "Auto-provision is enabled; runtime may repair setup/menu prerequisites before assertions.",
        form.post_order_actions
          ? "Post-order actions are enabled (receipt/review/reorder verification)."
          : "Post-order actions are disabled unless scenario preset forces them.",
      ],
    });

    detailBlocks.push({
      title: "Expected Artifacts And Signals",
      lines: [
        "Artifacts: events.json, report.md, story.md.",
        "Common blocking signatures: websocket gate timeout (enforced mode), missing Stripe/coupon prerequisites, invalid plan scope.",
        "Informational decision context may include unsupported_profile_fetch_contract when cached-token profile hydration is intentionally skipped.",
      ],
    });
  } else {
    const bounded = hasFlag(form.extra_args, "--bounded-load-smoke-policy");
    const users = form.users ?? "plan/env default";
    const orders = form.continuous ? "continuous" : (form.orders ?? "plan/env default");

    summaryLines.push(`Load run with ${users} user workers and ${orders} order target.`);
    summaryLines.push(`Inter-order interval: ${form.interval ?? "plan/env default"} seconds, reject rate: ${form.reject ?? "plan/env default"}.`);
    summaryLines.push(
      bounded
        ? "Bounded-load smoke policy detected: baseline accepted completion required before reject/cancel tail pressure."
        : "Standard load behavior: concurrent user/store/robot flow with configured pressure knobs.",
    );

    detailBlocks.push({
      title: "What Will Run",
      lines: [
        `Flow: ${form.flow}.`,
        `Mode: ${modeLabel}.`,
        `Workers/users: ${users}.`,
        `Orders: ${orders}.`,
        `Continuous: ${form.continuous ? "enabled" : "disabled"}.`,
      ],
    });

    detailBlocks.push({
      title: "Execution Behavior",
      lines: [
        form.all_users
          ? "All plan users are eligible for worker assignment."
          : "Single selected/default user scope is used unless load orchestration expands internally.",
        form.no_auto_provision
          ? "Auto-provision disabled: missing setup/menu prerequisites may fail workers early."
          : "Auto-provision enabled: setup/menu prerequisites can be repaired during preflight.",
        form.enforce_websocket_gates
          ? "Websocket gates enforced for gated paths; missing status events become hard failures."
          : "Websocket gate failures recorded as warnings when applicable.",
      ],
    });

    if (bounded) {
      detailBlocks.push({
        title: "Bounded Load Smoke Policy",
        lines: [
          "Baseline phase: requires accepted/completed baseline before tail pressure.",
          "Tail phase: reject/cancel pressure applies after baseline is met.",
          "Failure signature: accepted_baseline_not_met when baseline cannot be reached within configured attempts.",
        ],
      });
    }
  }

  if (resolvedScope) {
    summaryLines.unshift(buildResolvedScopeSummaryLine(resolvedScope));
    detailBlocks.unshift({
      title: "Resolved scope",
      lines: buildResolvedScopeLines(resolvedScope),
    });
  }

  const severity: ImpactSeverity = warnings.length > 0 ? "blocking" : form.enforce_websocket_gates ? "warning" : "info";

  return {
    summaryLines: summaryLines.slice(0, resolvedScope ? 5 : 4),
    detailBlocks,
    warnings,
    severity,
  };
}

export { LAUNCHER_FIELD_HINTS } from "./run-launcher-config";
