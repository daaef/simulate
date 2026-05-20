import { describe, expect, it } from "vitest";
import type { RunCreateRequest, SimulationPlanContent } from "./api";
import { buildExecutionImpact } from "./run-impact-explainer";
import {
  buildResolvedScopeSummaryLine,
  resolveLaunchActors,
} from "./resolve-launch-actors";

const fixturePlan: SimulationPlanContent = {
  defaults: {
    user_phone: "+2348166675609",
    store_id: "FZY_926025",
  },
  runtime_defaults: {
    users: 2,
    orders: 5,
    interval_seconds: 15,
    reject_rate: 0.2,
  },
  users: [
    { phone: "+2349077777740", role: "customer" },
    { phone: "+2348000001111", role: "staff" },
  ],
  stores: [
    { store_id: "FZY_111" },
    { store_id: "FZY_926025" },
  ],
};

const baseForm: RunCreateRequest = {
  flow: "doctor",
  plan: "sim_actors.json",
  timing: "fast",
  store_id: "",
  phone: "",
  all_users: false,
};

describe("resolveLaunchActors", () => {
  it("returns null when plan content is missing", () => {
    expect(resolveLaunchActors(baseForm, null, "trace")).toBeNull();
  });

  it("uses explicit store override", () => {
    const scope = resolveLaunchActors({ ...baseForm, store_id: "FZY_999" }, fixturePlan, "trace");
    expect(scope?.storeId).toBe("FZY_999");
    expect(scope?.storeSource).toBe("form");
  });

  it("resolves empty store from plan defaults", () => {
    const scope = resolveLaunchActors(baseForm, fixturePlan, "trace");
    expect(scope?.storeId).toBe("");
    expect(scope?.storeSource).toBe("random_plan_pool");
  });

  it("resolves empty phone from plan defaults", () => {
    const scope = resolveLaunchActors(baseForm, fixturePlan, "trace");
    expect(scope?.phone).toBe("");
    expect(scope?.phoneSource).toBe("random_plan_pool");
  });

  it("resolves deterministic store when random-store is disabled", () => {
    const scope = resolveLaunchActors({ ...baseForm, extra_args: ["--no-random-store"] }, fixturePlan, "trace");
    expect(scope?.storeId).toBe("FZY_926025");
    expect(scope?.storeSource).toBe("plan_default");
  });

  it("resolves deterministic phone when random-phone is disabled", () => {
    const scope = resolveLaunchActors({ ...baseForm, extra_args: ["--no-random-phone"] }, fixturePlan, "trace");
    expect(scope?.phone).toBe("+2348166675609");
    expect(scope?.phoneSource).toBe("plan_default");
  });

  it("resolves first user when defaults omit user_phone", () => {
    const plan: SimulationPlanContent = {
      ...fixturePlan,
      defaults: { store_id: "FZY_926025" },
    };
    const scope = resolveLaunchActors({ ...baseForm, extra_args: ["--no-random-phone"] }, plan, "trace");
    expect(scope?.phone).toBe("+2349077777740");
    expect(scope?.phoneSource).toBe("plan_first_user");
  });

  it("resolves first store when defaults omit store_id", () => {
    const plan: SimulationPlanContent = {
      ...fixturePlan,
      defaults: { user_phone: "+2348166675609" },
    };
    const scope = resolveLaunchActors({ ...baseForm, extra_args: ["--no-random-store"] }, plan, "trace");
    expect(scope?.storeId).toBe("FZY_111");
    expect(scope?.storeSource).toBe("plan_first_store");
  });

  it("marks all plan users when all_users is set", () => {
    const scope = resolveLaunchActors({ ...baseForm, all_users: true }, fixturePlan, "trace");
    expect(scope?.userScope).toBe("all_plan_users");
    expect(scope?.planUserCount).toBe(2);
  });

  it("reads load knobs from runtime_defaults when unset", () => {
    const scope = resolveLaunchActors({ ...baseForm, flow: "load" }, fixturePlan, "load");
    expect(scope?.users).toBe(2);
    expect(scope?.orders).toBe(5);
    expect(scope?.interval).toBe(15);
    expect(scope?.reject).toBe(0.2);
  });

  it("prefers form load values over runtime_defaults", () => {
    const scope = resolveLaunchActors(
      { ...baseForm, flow: "load", users: 8, orders: 3, interval: 1, reject: 0.5 },
      fixturePlan,
      "load",
    );
    expect(scope?.users).toBe(8);
    expect(scope?.orders).toBe(3);
    expect(scope?.interval).toBe(1);
    expect(scope?.reject).toBe(0.5);
  });
});

describe("buildExecutionImpact without resolved scope in impact", () => {
  it("does not duplicate resolved scope when scope is omitted", () => {
    const scope = resolveLaunchActors({ ...baseForm, store_id: "FZY_999" }, fixturePlan, "trace");
    const impact = buildExecutionImpact(baseForm, "trace", null);
    expect(impact.detailBlocks.some((block) => block.title === "Resolved scope")).toBe(false);
    expect(impact.summaryLines[0]).not.toBe(buildResolvedScopeSummaryLine(scope!));
  });
});
