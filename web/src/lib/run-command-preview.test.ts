import { describe, expect, it } from "vitest";
import { buildRunCommandPreview } from "./run-command-preview";
import type { RunCreateRequest } from "./api";

const baseForm: RunCreateRequest = {
  flow: "doctor",
  plan: "sim_actors.json",
  timing: "fast",
  scenarios: [],
  store_id: "",
  phone: "",
  all_users: false,
  strict_plan: false,
  skip_app_probes: false,
  skip_store_dashboard_probes: false,
  no_auto_provision: false,
  enforce_websocket_gates: false,
  timeout_fails: false,
  post_order_actions: false,
  continuous: false,
  extra_args: [],
};

describe("buildRunCommandPreview", () => {
  it("includes random-disable flags from extra_args", () => {
    const preview = buildRunCommandPreview({
      ...baseForm,
      extra_args: ["--no-random-phone", "--no-random-store"],
    });
    expect(preview).toContain("--no-random-phone");
    expect(preview).toContain("--no-random-store");
  });

  it("omits random-disable flags when not selected", () => {
    const preview = buildRunCommandPreview(baseForm);
    expect(preview).not.toContain("--no-random-phone");
    expect(preview).not.toContain("--no-random-store");
  });

  it("includes timeout-fails flag when enabled", () => {
    const preview = buildRunCommandPreview({
      ...baseForm,
      timeout_fails: true,
    });
    expect(preview).toContain("--timeout-fails");
  });

  it("includes orders for place-order trace runs", () => {
    const preview = buildRunCommandPreview({
      ...baseForm,
      flow: "place-order",
      orders: 3,
    });

    expect(preview).toContain("simulate place-order");
    expect(preview).toContain("--orders 3");
  });
});
