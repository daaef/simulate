import { describe, expect, it } from "vitest";
import {
  addScenarioSelection,
  getScenarioSuggestions,
  normalizeScenarioSelection,
  removeScenarioSelection,
} from "./scenario-chip-utils";

const OPTIONS = ["completed", "store_reject", "store_dashboard", "auto_cancel"];

describe("scenario-chip-utils", () => {
  it("normalizes selection by trimming, deduping, and filtering unsupported values", () => {
    const result = normalizeScenarioSelection(
      [" completed ", "store_reject", "completed", "", "unknown", "store_reject", "auto_cancel"],
      OPTIONS,
    );
    expect(result).toEqual(["completed", "store_reject", "auto_cancel"]);
  });

  it("filters suggestions case-insensitively and excludes already selected values", () => {
    const result = getScenarioSuggestions(OPTIONS, ["store_reject"], "StoRE");
    expect(result).toEqual(["store_dashboard"]);
  });

  it("adds only supported unique scenarios and preserves order", () => {
    const initial = ["completed"];
    const appended = addScenarioSelection(initial, " store_reject ", OPTIONS);
    expect(appended).toEqual(["completed", "store_reject"]);

    const duplicate = addScenarioSelection(appended, "store_reject", OPTIONS);
    expect(duplicate).toEqual(["completed", "store_reject"]);

    const unsupported = addScenarioSelection(appended, "not_supported", OPTIONS);
    expect(unsupported).toEqual(["completed", "store_reject"]);
  });

  it("removes a selected scenario and preserves remaining order", () => {
    const result = removeScenarioSelection(["completed", "store_reject", "auto_cancel"], "store_reject");
    expect(result).toEqual(["completed", "auto_cancel"]);
  });
});
