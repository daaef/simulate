import type { FlowCapability, RunCreateRequest, SimulationPlan, SimulationPlanContent } from "./api";
import { GUIDE_FLAG_ROWS, GUIDE_FLOW_MATRIX } from "./command-guide";
import { LOAD_PACE_PRESET_INTERVALS } from "./load-mode-controls";
import {
  buildStoreDetailRows,
  buildUserDetailRows,
  deriveActorSelectMode,
  findPlanStore,
  findPlanUser,
  formatStoreOptionLabel,
  formatUserOptionLabel,
  isPlanDefaultStore,
  isPlanDefaultUser,
  listPlanStores,
  listPlanUsers,
  storeActorKey,
  userActorKey,
} from "./plan-actor-options";
import { hasNoRandomPhone, hasNoRandomStore } from "./random-actor-args";

export type LauncherFieldId =
  | "flow"
  | "timing"
  | "plan"
  | "mode"
  | "suite"
  | "scenarios"
  | "store"
  | "phone"
  | "users"
  | "orders"
  | "interval"
  | "reject"
  | "all_users"
  | "strict_plan"
  | "skip_app_probes"
  | "skip_store_dashboard_probes"
  | "no_auto_provision"
  | "post_order_actions"
  | "continuous"
  | "enforce_websocket_gates"
  | "timeout_fails"
  | "wait_for_store_action"
  | "store_auto_cancel";

export type LauncherFieldOption = {
  value: string;
  label?: string;
  description: string;
};

export type LauncherFieldHelp = {
  fieldId: LauncherFieldId | null;
  title: string;
  whenToChange: string;
  constraints: string[];
  options?: LauncherFieldOption[];
};

export type LauncherHelpContext = {
  flows: string[];
  flowCapabilities: Record<string, FlowCapability>;
  form: RunCreateRequest;
  resolvedMode: "trace" | "load";
  planOptions: SimulationPlan[];
  planContent: SimulationPlanContent | null;
};

export type SelectedOptionHelp = {
  valueLabel: string;
  description: string;
  items?: Array<{ valueLabel: string; description: string }>;
};

export type FieldValue = string | string[] | boolean | number | undefined;

const FLOW_MATRIX_BY_NAME = Object.fromEntries(GUIDE_FLOW_MATRIX.map((row) => [row.flow, row]));

const FLAG_BY_NAME = Object.fromEntries(GUIDE_FLAG_ROWS.map((row) => [row.flag, row]));

export const SUITE_HELP: Record<string, string> = {
  core: "Fast proof of completed, rejected, and cancelled paths. Lower cost than doctor.",
  payments: "Paid-no-coupon, paid-with-coupon, and free-with-coupon payment branches.",
  menus: "Menu availability states: available, unavailable, sold out, store closed.",
  store: "Store setup, accept, and reject scenarios.",
  audit: "Broad audit coverage: bootstrap, menus, payments, store, robot, post-order.",
  doctor: "Daily operator health sweep: bootstrap through receipt/review/reorder.",
  full: "Widest standard trace suite including new-user and coupon branches.",
};

export const SCENARIO_HELP: Record<string, string> = {
  completed: "Happy-path order through store accept and robot completion.",
  rejected: "Order rejected by store; validates rejection handling.",
  cancelled: "User-initiated cancellation while order is still pending.",
  backend_auto_cancel:
    "Store idle on pending: countdown in the run log, then observe cancelled from backend or customer (primary backend auto-cancel test).",
  auto_cancel:
    "Store accept, withhold payment, awaiting-payment countdown in the run log, then observe cancelled (optional; may time out if backend only cancels pending orders).",
  new_user_setup: "OTP/signup path and first-order readiness for a new phone.",
  returning_paid_no_coupon: "Returning user paid order without coupon (Stripe).",
  returning_paid_with_coupon: "Returning user paid order with coupon discount.",
  returning_free_with_coupon: "Coupon order that resolves to zero payable amount.",
  menu_available: "Order when menu item is available.",
  menu_unavailable: "Order blocked or handled when menu item is unavailable.",
  menu_sold_out: "Menu sold-out branch behavior.",
  menu_store_closed: "Store-closed menu gate behavior.",
  store_first_setup: "Store profile/menu setup and preflight mutations.",
  store_accept: "Store accepts order and progression to completion.",
  store_reject: "Store rejects order; rejection assertions.",
  robot_complete: "Robot delivery lifecycle through completed.",
  app_bootstrap: "Config, pricing, cards, coupons, and active-order probes.",
  store_dashboard: "Store dashboard APIs: stats, revenue, top customers.",
  receipt_review_reorder: "Receipt fetch, review/rating, and reorder after completion.",
  place_order: "Seed pending live orders for manual store-app inspection.",
};

const FIELD_META: Record<
  LauncherFieldId,
  { title: string; whenToChange: string; flagKey?: string }
> = {
  flow: {
    title: "Flow",
    whenToChange:
      "Pick the simulation preset that matches what you want to prove. Each flow sets a default mode (trace vs load) and typical suite/scenarios.",
  },
  timing: {
    title: "Timing",
    whenToChange:
      "Use fast for quick validation and CI-style checks. Use realistic when you need human-like delays and auto-cancel windows closer to production pacing.",
    flagKey: "--timing",
  },
  plan: {
    title: "Plan",
    whenToChange:
      "Select the JSON actor plan that supplies users, stores, phones, and defaults. The run fails early if the chosen store or phone is not in this plan.",
    flagKey: "--plan",
  },
  mode: {
    title: "Mode override",
    whenToChange:
      "Leave empty to use the flow’s default mode. Override only when you intentionally want trace suite execution or load workers on a different mode than the preset implies.",
    flagKey: "--mode",
  },
  suite: {
    title: "Suite",
    whenToChange:
      "Trace-only: selects a named bundle of scenarios. Leave empty to use the flow default suite (see run summary in the sidebar).",
    flagKey: "--suite",
  },
  scenarios: {
    title: "Scenarios",
    whenToChange:
      "Trace-only: run explicit scenarios in order (deduped). Empty means the runtime resolves the suite or flow default list.",
    flagKey: "--scenario",
  },
  store: {
    title: "Store ID",
    whenToChange:
      "Leave blank for random plan-store selection. Set a value only when you need to pin a specific store from plan stores[].",
    flagKey: "--store",
  },
  phone: {
    title: "Phone",
    whenToChange:
      "Leave blank for random plan-phone selection. Set a value only when you need to pin a specific user phone.",
    flagKey: "--phone",
  },
  users: {
    title: "Users",
    whenToChange: "Load-only: number of concurrent user workers placing orders.",
    flagKey: "--users",
  },
  orders: {
    title: "Orders",
    whenToChange:
      "Load-only for bounded load; for place-order trace, number of pending orders to seed for manual inspection (max 10).",
    flagKey: "--orders",
  },
  interval: {
    title: "Interval (sec)",
    whenToChange:
      "Load-only: seconds between order attempts per worker. Pace presets are slow=10, normal=3, fast=1.",
    flagKey: "--interval",
  },
  reject: {
    title: "Reject rate",
    whenToChange: "Load-only: probability (0–1) that the store rejects an order.",
    flagKey: "--reject",
  },
  all_users: {
    title: "All users",
    whenToChange: "Fan out across every user in the plan instead of a single selected phone.",
    flagKey: "--all-users",
  },
  strict_plan: {
    title: "Strict plan",
    whenToChange: "Fail fast when plan entries are incomplete instead of tolerating missing fields.",
    flagKey: "--strict-plan",
  },
  skip_app_probes: {
    title: "Skip app probes",
    whenToChange: "Narrow diagnostics by skipping bootstrap API probes (config, cards, coupons).",
    flagKey: "--skip-app-probes",
  },
  skip_store_dashboard_probes: {
    title: "Skip store dashboard probes",
    whenToChange: "Skip store dashboard API checks when those endpoints are out of scope.",
    flagKey: "--skip-store-dashboard-probes",
  },
  no_auto_provision: {
    title: "No auto provision",
    whenToChange: "Disable simulator setup/menu repair mutations for negative or strict readiness tests.",
    flagKey: "--no-auto-provision",
  },
  post_order_actions: {
    title: "Post-order actions",
    whenToChange: "Run receipt, review, and reorder probes after completed orders.",
    flagKey: "--post-order-actions",
  },
  continuous: {
    title: "Continuous",
    whenToChange: "Load-only soak: keep placing traffic until you stop the run manually.",
    flagKey: "--continuous",
  },
  enforce_websocket_gates: {
    title: "Enforce websocket gates",
    whenToChange:
      "When enabled, missing required websocket status events fail the run. When off, gaps are recorded as warnings and the run continues.",
    flagKey: "--enforce-websocket-gates / --no-enforce-websocket-gates",
  },
  timeout_fails: {
    title: "Timeout fails",
    whenToChange:
      "When enabled, requests use timeout protection and timeout events fail the run. When off, requests wait indefinitely for endpoint responses.",
    flagKey: "--timeout-fails",
  },
  wait_for_store_action: {
    title: "Wait for real store",
    whenToChange:
      "Trace only: disables simulator store actions and waits for a real store operator to accept, reject, or mark orders ready from their app. Use when testing the actual store app against a live run.",
    flagKey: "--wait-for-store-action",
  },
  store_auto_cancel: {
    title: "Store auto cancel",
    whenToChange:
      "Trace only: adds the auto_cancel scenario — store accepts the order, payment is withheld, then the simulator watches to see whether the backend cancels the awaiting-payment order. Off by default.",
    flagKey: "--scenario",
  },
};

function flagConstraints(flagKey: string | undefined): string[] {
  if (!flagKey) return [];
  const row = FLAG_BY_NAME[flagKey];
  if (!row) return [];
  const lines: string[] = [];
  if (row.effect) lines.push(row.effect);
  if (row.constraints) lines.push(`Constraint: ${row.constraints}`);
  return lines;
}

function traceOnlyConstraint(resolvedMode: "trace" | "load"): string[] {
  if (resolvedMode === "load") {
    return ["Only available when resolved mode is trace."];
  }
  return [];
}

function loadOnlyConstraint(resolvedMode: "trace" | "load"): string[] {
  if (resolvedMode === "trace") {
    return ["Only available when resolved mode is load."];
  }
  return [];
}

function flowOptions(flows: string[]): LauncherFieldOption[] {
  const list = flows.length ? flows : ["doctor"];
  return list.map((flow) => {
    const row = FLOW_MATRIX_BY_NAME[flow];
    return {
      value: flow,
      description: row
        ? `${row.what_it_tests} Prerequisites: ${row.prerequisites}`
        : `Simulation preset "${flow}".`,
    };
  });
}

export function getFieldValue(form: RunCreateRequest, fieldId: LauncherFieldId): FieldValue {
  switch (fieldId) {
    case "flow":
      return form.flow;
    case "timing":
      return form.timing;
    case "plan":
      return form.plan;
    case "mode":
      return form.mode ?? "";
    case "suite":
      return form.suite ?? "";
    case "scenarios":
      return form.scenarios ?? [];
    case "store":
      return form.store_id;
    case "phone":
      return form.phone;
    case "users":
      return form.users;
    case "orders":
      return form.orders;
    case "interval":
      return form.interval;
    case "reject":
      return form.reject;
    case "all_users":
      return form.all_users;
    case "strict_plan":
      return Boolean(form.strict_plan);
    case "skip_app_probes":
      return Boolean(form.skip_app_probes);
    case "skip_store_dashboard_probes":
      return Boolean(form.skip_store_dashboard_probes);
    case "no_auto_provision":
      return form.no_auto_provision;
    case "post_order_actions":
      return Boolean(form.post_order_actions);
    case "continuous":
      return Boolean(form.continuous);
    case "enforce_websocket_gates":
      return Boolean(form.enforce_websocket_gates);
    case "timeout_fails":
      return Boolean(form.timeout_fails);
    case "wait_for_store_action":
      return Boolean(form.wait_for_store_action);
    case "store_auto_cancel":
      return Boolean(form.store_auto_cancel);
    default:
      return undefined;
  }
}

function optionDescription(
  fieldId: LauncherFieldId,
  context: LauncherHelpContext,
  rawValue: string,
): string | null {
  const help = getLauncherFieldHelp(fieldId, context);
  const match = help?.options?.find((option) => option.value === rawValue);
  return match?.description ?? null;
}

function checkboxSelectedHelp(
  fieldId: LauncherFieldId,
  checked: boolean,
  context: LauncherHelpContext,
): SelectedOptionHelp {
  const meta = FIELD_META[fieldId];
  const flagRow = meta.flagKey ? FLAG_BY_NAME[meta.flagKey] : undefined;
  if (fieldId === "enforce_websocket_gates") {
    return checked
      ? {
          valueLabel: "On",
          description:
            "Missing required websocket status events fail the run instead of being recorded as warnings.",
        }
      : {
          valueLabel: "Off",
          description:
            "Missing websocket gate events are recorded as warnings and the run continues (default in many environments).",
        };
  }
  if (fieldId === "timeout_fails") {
    return checked
      ? {
          valueLabel: "On",
          description:
            "HTTP request timeouts are enforced and timeout events fail the run.",
        }
      : {
          valueLabel: "Off",
          description:
            "HTTP requests wait indefinitely for endpoint responses; timeout failures are not enforced.",
        };
  }
  return {
    valueLabel: checked ? "On" : "Off",
    description: checked
      ? flagRow?.effect || meta.whenToChange
      : `Disabled. ${flagRow?.effect ? `When enabled: ${flagRow.effect}` : meta.whenToChange}`,
  };
}

export function getSelectedOptionHelp(
  fieldId: LauncherFieldId,
  context: LauncherHelpContext,
): SelectedOptionHelp | null {
  const meta = FIELD_META[fieldId];
  if (!meta) return null;

  const value = getFieldValue(context.form, fieldId);

  if (fieldId === "scenarios") {
    const selected = (value as string[]) || [];
    if (!selected.length) {
      return {
        valueLabel: "(none selected)",
        description:
          "Runtime resolves scenarios from the chosen suite or the flow default list. Pick explicit scenarios to narrow coverage.",
      };
    }
    return {
      valueLabel: `${selected.length} scenario${selected.length === 1 ? "" : "s"} selected`,
      description: "Runs only the selected scenarios, in order (deduped).",
      items: selected.map((scenario) => ({
        valueLabel: scenario,
        description: SCENARIO_HELP[scenario] || `Trace scenario "${scenario}".`,
      })),
    };
  }

  const checkboxFields: LauncherFieldId[] = [
    "all_users",
    "strict_plan",
    "skip_app_probes",
    "skip_store_dashboard_probes",
    "no_auto_provision",
    "post_order_actions",
    "continuous",
    "enforce_websocket_gates",
    "timeout_fails",
    "wait_for_store_action",
    "store_auto_cancel",
  ];
  if (checkboxFields.includes(fieldId)) {
    return checkboxSelectedHelp(fieldId, Boolean(value), context);
  }

  if (fieldId === "store" || fieldId === "phone") {
    const text = String(value ?? "").trim();
    if (!text) {
      const randomDisabled = fieldId === "store"
        ? hasNoRandomStore(context.form.extra_args)
        : hasNoRandomPhone(context.form.extra_args);
      return {
        valueLabel: "Plan default",
        description: randomDisabled
          ? fieldId === "store"
            ? "Deterministic actor resolution: uses defaults.store_id, then first store in plan."
            : "Deterministic actor resolution: uses defaults.user_phone, then first user in plan."
          : fieldId === "store"
            ? "Auto-random actor resolution: runtime picks a random store from plan stores[]."
            : "Auto-random actor resolution: runtime picks a random phone from plan users[].",
      };
    }

    const isStore = fieldId === "store";
    const actors = isStore
      ? listPlanStores(context.planContent).map((store) => ({ key: storeActorKey(store) }))
      : listPlanUsers(context.planContent).map((user) => ({ key: userActorKey(user) }));
    const mode = deriveActorSelectMode(text, actors.filter((entry) => entry.key));

    if (mode === "plan" && context.planContent) {
      if (isStore) {
        const store = findPlanStore(context.planContent, text);
        if (store) {
          const rows = buildStoreDetailRows(store);
          return {
            valueLabel: formatStoreOptionLabel(store, isPlanDefaultStore(context.planContent, text)),
            description: "Store pinned from the selected plan.",
            items: rows.map((row) => ({
              valueLabel: row.label,
              description: row.value,
            })),
          };
        }
      } else {
        const user = findPlanUser(context.planContent, text);
        if (user) {
          const rows = buildUserDetailRows(user);
          return {
            valueLabel: formatUserOptionLabel(user, isPlanDefaultUser(context.planContent, text)),
            description: "User pinned from the selected plan.",
            items: rows.map((row) => ({
              valueLabel: row.label,
              description: row.value,
            })),
          };
        }
      }
    }

    return {
      valueLabel: text,
      description:
        mode === "other"
          ? isStore
            ? "Custom store ID (not in the selected plan). Must authenticate in the target environment."
            : "Custom phone (not in the selected plan). Use for strict new-user branches or external test numbers."
          : isStore
            ? "Overrides the plan store. The ID must exist in the selected plan’s stores[] and authenticate in the target environment."
            : "Overrides the plan user phone. Must exist in the plan unless you are testing a strict new-user branch.",
    };
  }

  if (fieldId === "users" || fieldId === "orders" || fieldId === "interval" || fieldId === "reject") {
    if (value === undefined || value === "") {
      return {
        valueLabel: "(not set)",
        description:
          fieldId === "orders" && context.resolvedMode === "trace" && context.form.flow === "place-order"
            ? "Uses the place-order default of 1 pending order."
            : "Uses the flow or environment default for this load parameter.",
      };
    }
    const numericLabel = String(value);
    const fromOption = optionDescription(fieldId, context, numericLabel);
    return {
      valueLabel: numericLabel,
      description: fromOption || FIELD_META[fieldId].whenToChange,
    };
  }

  const stringValue = String(value ?? "");
  const description =
    optionDescription(fieldId, context, stringValue) ||
    (fieldId === "flow" && FLOW_MATRIX_BY_NAME[stringValue]
      ? `${FLOW_MATRIX_BY_NAME[stringValue].what_it_tests} Prerequisites: ${FLOW_MATRIX_BY_NAME[stringValue].prerequisites}`
      : null);

  if (fieldId === "suite" && !stringValue) {
    const capability = context.flowCapabilities[context.form.flow] || null;
    return {
      valueLabel: "Flow default",
      description: capability?.default_suite
        ? `Uses the "${capability.default_suite}" suite from the ${context.form.flow} preset.`
        : "Runtime picks the flow’s default suite.",
    };
  }

  if (fieldId === "mode" && !stringValue) {
    const capability = context.flowCapabilities[context.form.flow] || null;
    return {
      valueLabel: "Use flow default",
      description: capability
        ? `Inherits ${capability.resolved_mode} mode from the "${context.form.flow}" preset.`
        : "Uses the selected flow’s default execution mode.",
    };
  }

  return {
    valueLabel:
      fieldId === "plan" && stringValue === "sim_actors.json"
        ? "sim_actors.json"
        : stringValue || "(empty)",
    description: description || meta.whenToChange,
  };
}

export function getLauncherFieldHelp(
  fieldId: LauncherFieldId | null,
  context: LauncherHelpContext,
): LauncherFieldHelp | null {
  if (!fieldId) return null;

  const meta = FIELD_META[fieldId];
  if (!meta) return null;

  const capability = context.flowCapabilities[context.form.flow] || null;
  const isPlaceOrderOrders =
    fieldId === "orders" && context.resolvedMode === "trace" && context.form.flow === "place-order";
  const constraints: string[] = isPlaceOrderOrders ? [] : [...flagConstraints(meta.flagKey)];

  let options: LauncherFieldOption[] | undefined;

  switch (fieldId) {
    case "flow":
      options = flowOptions(context.flows);
      break;
    case "timing":
      options = [
        { value: "fast", description: "Shorter delays; best for quick validation and CI." },
        { value: "realistic", description: "Human-like pacing and auto-cancel windows." },
      ];
      break;
    case "plan": {
      const planRows: LauncherFieldOption[] = [
        {
          value: "sim_actors.json",
          description: "Default actor plan from the simulator environment (SIM_ACTORS_PATH).",
        },
      ];
      for (const plan of context.planOptions) {
        planRows.push({
          value: plan.path,
          label: plan.name,
          description: `GUI-registered plan at ${plan.path}.`,
        });
      }
      options = planRows;
      break;
    }
    case "mode":
      options = [
        {
          value: "",
          label: "Use flow default",
          description: capability
            ? `Inherits ${capability.resolved_mode} from the "${context.form.flow}" preset.`
            : "Uses the selected flow’s default mode.",
        },
        { value: "trace", description: "Deterministic scenario/suite execution with ordered steps." },
        { value: "load", description: "Concurrent workers, orders, and optional continuous soak." },
      ];
      break;
    case "suite":
      constraints.push(...traceOnlyConstraint(context.resolvedMode));
      options = [
        {
          value: "",
          label: "Flow default",
          description: capability?.default_suite
            ? `Default suite for this flow: ${capability.default_suite}.`
            : "Runtime picks the flow’s default suite.",
        },
        ...(capability?.available_suites || []).map((suite) => ({
          value: suite,
          description: SUITE_HELP[suite] || `Trace suite "${suite}".`,
        })),
      ];
      break;
    case "scenarios":
      constraints.push(...traceOnlyConstraint(context.resolvedMode));
      options = (capability?.available_scenarios || []).map((scenario) => ({
        value: scenario,
        description: SCENARIO_HELP[scenario] || `Trace scenario "${scenario}".`,
      }));
      break;
    case "store": {
      const stores = listPlanStores(context.planContent);
      options = [
        {
          value: "",
          label: "Plan default",
          description:
            "Default behavior is random selection from plan stores[]. If random is disabled, fallback is defaults.store_id then first store.",
        },
        ...stores
          .filter((store) => storeActorKey(store))
          .map((store) => {
            const key = storeActorKey(store);
            return {
              value: key,
              label: formatStoreOptionLabel(store, isPlanDefaultStore(context.planContent, key)),
              description: "Pin this store for the run.",
            };
          }),
        {
          value: "__other__",
          label: "Other",
          description: "Enter a custom store ID not listed in the plan.",
        },
      ];
      break;
    }
    case "phone": {
      const users = listPlanUsers(context.planContent);
      options = [
        {
          value: "",
          label: "Plan default",
          description:
            "Default behavior is random selection from plan users[]. If random is disabled, fallback is defaults.user_phone then first user.",
        },
        ...users
          .filter((user) => userActorKey(user))
          .map((user) => {
            const key = userActorKey(user);
            return {
              value: key,
              label: formatUserOptionLabel(user, isPlanDefaultUser(context.planContent, key)),
              description: "Pin this user phone for the run.",
            };
          }),
        {
          value: "__other__",
          label: "Other",
          description: "Enter a custom phone not listed in the plan.",
        },
      ];
      break;
    }
    case "users":
      constraints.push(...loadOnlyConstraint(context.resolvedMode));
      break;
    case "orders":
      if (context.resolvedMode === "trace" && context.form.flow === "place-order") {
        constraints.push("Place-order trace only; value must be between 1 and 10.");
      } else {
        constraints.push(...loadOnlyConstraint(context.resolvedMode));
      }
      break;
    case "reject":
    case "continuous":
      constraints.push(...loadOnlyConstraint(context.resolvedMode));
      break;
    case "interval":
      constraints.push(...loadOnlyConstraint(context.resolvedMode));
      options = [
        {
          value: String(LOAD_PACE_PRESET_INTERVALS.slow),
          label: "slow",
          description: "Slower pacing: 10 seconds between order attempts.",
        },
        {
          value: String(LOAD_PACE_PRESET_INTERVALS.normal),
          label: "normal",
          description: "Balanced pacing: 3 seconds between order attempts.",
        },
        {
          value: String(LOAD_PACE_PRESET_INTERVALS.fast),
          label: "fast",
          description: "Aggressive pacing: 1 second between order attempts.",
        },
      ];
      break;
    default:
      break;
  }

  return {
    fieldId,
    title: meta.title,
    whenToChange: meta.whenToChange,
    constraints,
    options,
  };
}

/** @deprecated Use getLauncherFieldHelp via the help sidebar instead of inline labels. */
export const LAUNCHER_FIELD_HINTS: Record<string, string> = Object.fromEntries(
  Object.entries(FIELD_META).map(([key, value]) => [key, value.whenToChange.split(".")[0] + "."]),
);
