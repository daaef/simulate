import { describe, expect, it } from "vitest";
import { getOrderItemNames } from "./orders-display";

describe("orders display helpers", () => {
  it("returns only trimmed order item names", () => {
    const names = getOrderItemNames({
      menu: [
        { menu: { name: " Donut ドーナツ " } },
        { menu: { name: "Coffee" } },
        { menu: { name: "" } },
      ],
    });

    expect(names).toEqual(["Donut ドーナツ", "Coffee"]);
  });
});
