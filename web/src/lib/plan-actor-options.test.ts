import { describe, expect, it } from "vitest";
import type { SimulationPlanContent } from "./api";
import {
  ACTOR_SELECT_OTHER,
  buildStoreDetailRows,
  buildUserDetailRows,
  deriveActorSelectMode,
  findPlanStore,
  findPlanUser,
  formatStoreOptionLabel,
  formatUserOptionLabel,
  listPlanStores,
  listPlanUsers,
} from "./plan-actor-options";

const fixturePlan: SimulationPlanContent = {
  defaults: {
    user_phone: "+2348166675609",
    store_id: "FZY_926025",
  },
  users: [
    {
      phone: "+2349077777740",
      role: "customer",
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.test",
      lat: 35.1,
      lng: 136.9,
    },
    { phone: "+2348166675609", role: "returning_default", first_name: "Fainzy", last_name: "Simulator" },
  ],
  stores: [
    { store_id: "FZY_111", name: "Alpha Store", branch: "Main", owner: "Owner A", status: 1 },
    {
      store_id: "FZY_926025",
      name: "Ask Me Restaurant Jos",
      mobile: "+2348166675609",
      lat: 9.9,
      lng: 8.8,
    },
  ],
};

describe("plan-actor-options", () => {
  it("lists stores and users from plan content", () => {
    expect(listPlanStores(fixturePlan)).toHaveLength(2);
    expect(listPlanUsers(fixturePlan)).toHaveLength(2);
    expect(listPlanStores(null)).toEqual([]);
    expect(listPlanUsers(null)).toEqual([]);
  });

  it("derives select mode from value and actor keys", () => {
    const stores = listPlanStores(fixturePlan).map((store) => ({ key: String(store.store_id) }));
    expect(deriveActorSelectMode("", stores)).toBe("default");
    expect(deriveActorSelectMode("FZY_926025", stores)).toBe("plan");
    expect(deriveActorSelectMode("FZY_UNKNOWN", stores)).toBe("other");
  });

  it("finds plan actors by key", () => {
    expect(findPlanStore(fixturePlan, "FZY_926025")?.name).toBe("Ask Me Restaurant Jos");
    expect(findPlanUser(fixturePlan, "+2349077777740")?.role).toBe("customer");
    expect(findPlanStore(fixturePlan, "missing")).toBeNull();
  });

  it("formats option labels with plan default marker", () => {
    const store = listPlanStores(fixturePlan)[1];
    expect(formatStoreOptionLabel(store, true)).toContain("(plan default)");
    expect(formatStoreOptionLabel(store)).toContain("Ask Me Restaurant Jos");

    const user = listPlanUsers(fixturePlan)[0];
    expect(formatUserOptionLabel(user)).toContain("Ada Lovelace");
    expect(formatUserOptionLabel(user, true)).toContain("(plan default)");
  });

  it("builds detail rows for store and user", () => {
    const storeRows = buildStoreDetailRows(listPlanStores(fixturePlan)[1]);
    expect(storeRows.some((row) => row.label === "Store ID" && row.value === "FZY_926025")).toBe(true);
    expect(storeRows.some((row) => row.label === "GPS")).toBe(true);

    const userRows = buildUserDetailRows(listPlanUsers(fixturePlan)[0]);
    expect(userRows.some((row) => row.label === "Email" && row.value === "ada@example.test")).toBe(true);
    expect(userRows.some((row) => row.label === "GPS")).toBe(true);
  });

  it("uses other sentinel only in UI layer", () => {
    expect(ACTOR_SELECT_OTHER).toBe("__other__");
  });
});
