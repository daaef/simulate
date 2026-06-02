import { describe, expect, it } from "vitest";
import {
  getLauncherFieldHelp,
  getSelectedOptionHelp,
  SCENARIO_HELP,
  SUITE_HELP,
} from "./run-launcher-config";
import type { FlowCapability, RunCreateRequest, SimulationPlanContent } from "./api";

const fixturePlan: SimulationPlanContent = {
  defaults: {
    user_phone: "+2348166675609",
    store_id: "FZY_926025",
  },
  users: [
    { phone: "+2349077777740", role: "customer", first_name: "Ada", last_name: "Lovelace" },
    { phone: "+2348166675609", role: "returning_default", first_name: "Fainzy", last_name: "Simulator" },
  ],
  stores: [
    { store_id: "FZY_111", name: "Alpha Store" },
    { store_id: "FZY_926025", name: "Ask Me Restaurant Jos", mobile: "+2348166675609" },
  ],
};

const baseForm: RunCreateRequest = {
  flow: "doctor",
  plan: "sim_actors.json",
  timing: "fast",
  store_id: "",
  phone: "",
  all_users: false,
  no_auto_provision: false,
  timeout_fails: false,
};

const doctorCapability: FlowCapability = {
  flow: "doctor",
  resolved_mode: "trace",
  default_suite: "doctor",
  default_scenarios: [],
  allowed_optional_flags: [],
  available_suites: ["core", "doctor", "full"],
  available_scenarios: ["completed", "store_reject"],
};

function context(overrides: Partial<{
  flows: string[];
  form: RunCreateRequest;
  resolvedMode: "trace" | "load";
  capability: FlowCapability | null;
  planContent: SimulationPlanContent | null;
}> = {}) {
  const form = overrides.form ?? baseForm;
  const capability = overrides.capability ?? doctorCapability;
  return {
    flows: overrides.flows ?? ["doctor", "load"],
    flowCapabilities: capability ? { [form.flow]: capability } : {},
    form,
    resolvedMode: overrides.resolvedMode ?? "trace",
    planOptions: [],
    planContent: overrides.planContent ?? null,
  };
}

describe("getLauncherFieldHelp", () => {
  it("returns null when field id is null", () => {
    expect(getLauncherFieldHelp(null, context())).toBeNull();
  });

  it("includes all flows in flow field options", () => {
    const help = getLauncherFieldHelp("flow", context({ flows: ["doctor", "load", "menus"] }));
    expect(help?.options?.map((o) => o.value)).toEqual(["doctor", "load", "menus"]);
    expect(help?.options?.[0]?.description).toContain("daily broad trace baseline");
  });

  it("marks suite as trace-only when resolved mode is load", () => {
    const help = getLauncherFieldHelp(
      "suite",
      context({
        resolvedMode: "load",
        form: { ...baseForm, flow: "load", mode: "load" },
        capability: {
          ...doctorCapability,
          flow: "load",
          resolved_mode: "load",
          available_suites: [],
          available_scenarios: [],
        },
      }),
    );
    expect(help?.constraints.some((c) => c.includes("trace"))).toBe(true);
  });

  it("lists suite options from capability", () => {
    const help = getLauncherFieldHelp("suite", context());
    const values = help?.options?.map((o) => o.value) ?? [];
    expect(values).toContain("");
    expect(values).toContain("doctor");
    expect(help?.options?.find((o) => o.value === "doctor")?.description).toBe(SUITE_HELP.doctor);
  });

  it("lists scenario options with SCENARIO_HELP descriptions", () => {
    const help = getLauncherFieldHelp("scenarios", context());
    const completed = help?.options?.find((o) => o.value === "completed");
    expect(completed?.description).toBe(SCENARIO_HELP.completed);
  });

  it("treats orders as valid for place-order trace flow", () => {
    const help = getLauncherFieldHelp(
      "orders",
      context({
        form: { ...baseForm, flow: "place-order", orders: 3 },
        resolvedMode: "trace",
        capability: {
          ...doctorCapability,
          flow: "place-order",
          default_suite: null,
          default_scenarios: ["place_order"],
          allowed_optional_flags: ["orders"],
          available_scenarios: ["place_order"],
        },
      }),
    );

    expect(help?.constraints.join(" ")).not.toContain("load mode");
    expect(help?.whenToChange).toContain("place-order");
  });

  it("lists plan stores and users for actor fields", () => {
    const storeHelp = getLauncherFieldHelp("store", context({ planContent: fixturePlan }));
    const storeValues = storeHelp?.options?.map((o) => o.value) ?? [];
    expect(storeValues).toContain("");
    expect(storeValues).toContain("FZY_926025");
    expect(storeValues).toContain("__other__");

    const phoneHelp = getLauncherFieldHelp("phone", context({ planContent: fixturePlan }));
    const phoneValues = phoneHelp?.options?.map((o) => o.value) ?? [];
    expect(phoneValues).toContain("+2349077777740");
    expect(phoneValues).toContain("__other__");
  });
});

describe("getSelectedOptionHelp", () => {
  it("returns doctor-specific description for flow field", () => {
    const selected = getSelectedOptionHelp("flow", context());
    expect(selected?.valueLabel).toBe("doctor");
    expect(selected?.description).toContain("daily broad trace baseline");
  });

  it("returns off state for unchecked enforce websocket gates", () => {
    const selected = getSelectedOptionHelp(
      "enforce_websocket_gates",
      context({ form: { ...baseForm, enforce_websocket_gates: false } }),
    );
    expect(selected?.valueLabel).toBe("Off");
    expect(selected?.description.toLowerCase()).toContain("warning");
  });

  it("returns off state for unchecked timeout fails", () => {
    const selected = getSelectedOptionHelp(
      "timeout_fails",
      context({ form: { ...baseForm, timeout_fails: false } }),
    );
    expect(selected?.valueLabel).toBe("Off");
    expect(selected?.description.toLowerCase()).toContain("wait indefinitely");
  });

  it("returns per-scenario items when scenarios are selected", () => {
    const selected = getSelectedOptionHelp(
      "scenarios",
      context({ form: { ...baseForm, scenarios: ["completed", "store_reject"] } }),
    );
    expect(selected?.items).toHaveLength(2);
    expect(selected?.items?.[0]?.description).toBe(SCENARIO_HELP.completed);
  });

  it("returns plan default label when store and phone are empty", () => {
    const store = getSelectedOptionHelp("store", context({ planContent: fixturePlan }));
    const phone = getSelectedOptionHelp("phone", context({ planContent: fixturePlan }));
    expect(store?.valueLabel).toBe("Plan default");
    expect(phone?.valueLabel).toBe("Plan default");
    expect(store?.description.toLowerCase()).toContain("auto-random");
    expect(phone?.description.toLowerCase()).toContain("auto-random");
  });

  it("describes deterministic actor resolution when random flags are disabled", () => {
    const store = getSelectedOptionHelp(
      "store",
      context({ planContent: fixturePlan, form: { ...baseForm, extra_args: ["--no-random-store"] } }),
    );
    const phone = getSelectedOptionHelp(
      "phone",
      context({ planContent: fixturePlan, form: { ...baseForm, extra_args: ["--no-random-phone"] } }),
    );
    expect(store?.description.toLowerCase()).toContain("deterministic");
    expect(phone?.description.toLowerCase()).toContain("deterministic");
  });

  it("returns detail rows when a plan store is selected", () => {
    const selected = getSelectedOptionHelp(
      "store",
      context({ planContent: fixturePlan, form: { ...baseForm, store_id: "FZY_926025" } }),
    );
    expect(selected?.valueLabel).toContain("FZY_926025");
    expect(selected?.items?.some((item) => item.valueLabel === "Name")).toBe(true);
  });

  it("describes custom store as other", () => {
    const selected = getSelectedOptionHelp(
      "store",
      context({ planContent: fixturePlan, form: { ...baseForm, store_id: "FZY_CUSTOM" } }),
    );
    expect(selected?.description.toLowerCase()).toContain("custom");
  });
});
