import { describe, expect, it } from "vitest";
import {
  applyLoadPaceSelection,
  LOAD_PACE_PRESET_INTERVALS,
  resolveLoadPaceSelection,
} from "./load-mode-controls";

describe("resolveLoadPaceSelection", () => {
  it("maps preset intervals", () => {
    expect(resolveLoadPaceSelection(LOAD_PACE_PRESET_INTERVALS.slow)).toBe("slow");
    expect(resolveLoadPaceSelection(LOAD_PACE_PRESET_INTERVALS.normal)).toBe("normal");
    expect(resolveLoadPaceSelection(LOAD_PACE_PRESET_INTERVALS.fast)).toBe("fast");
  });

  it("returns custom for undefined or non-preset intervals", () => {
    expect(resolveLoadPaceSelection(undefined)).toBe("custom");
    expect(resolveLoadPaceSelection(2)).toBe("custom");
  });
});

describe("applyLoadPaceSelection", () => {
  it("applies selected preset interval", () => {
    const next = applyLoadPaceSelection({
      selected: "slow",
      currentInterval: undefined,
      manualInterval: undefined,
    });
    expect(next).toEqual({
      interval: LOAD_PACE_PRESET_INTERVALS.slow,
      manualInterval: undefined,
    });
  });

  it("preserves manual interval override when switching to preset and back to custom", () => {
    const fromCustom = applyLoadPaceSelection({
      selected: "fast",
      currentInterval: 2.5,
      manualInterval: undefined,
    });
    expect(fromCustom).toEqual({ interval: LOAD_PACE_PRESET_INTERVALS.fast, manualInterval: 2.5 });

    const backToCustom = applyLoadPaceSelection({
      selected: "custom",
      currentInterval: fromCustom.interval,
      manualInterval: fromCustom.manualInterval,
    });
    expect(backToCustom).toEqual({ interval: 2.5, manualInterval: 2.5 });
  });

  it("keeps existing manual override while preset interval is active", () => {
    const next = applyLoadPaceSelection({
      selected: "normal",
      currentInterval: LOAD_PACE_PRESET_INTERVALS.fast,
      manualInterval: 2.2,
    });
    expect(next).toEqual({ interval: LOAD_PACE_PRESET_INTERVALS.normal, manualInterval: 2.2 });
  });

  it("falls back to current interval when custom is selected without manual override", () => {
    const next = applyLoadPaceSelection({
      selected: "custom",
      currentInterval: LOAD_PACE_PRESET_INTERVALS.slow,
      manualInterval: undefined,
    });
    expect(next).toEqual({ interval: LOAD_PACE_PRESET_INTERVALS.slow, manualInterval: undefined });
  });
});
