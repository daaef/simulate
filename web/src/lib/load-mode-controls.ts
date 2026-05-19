export const LOAD_PACE_PRESET_INTERVALS = {
  slow: 10,
  normal: 3,
  fast: 1,
} as const;

export type LoadPacePreset = keyof typeof LOAD_PACE_PRESET_INTERVALS;
export type LoadPaceSelection = LoadPacePreset | "custom";

function normalizeInterval(value: number | null | undefined): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return undefined;
  }
  return value;
}

export function resolveLoadPaceSelection(interval: number | null | undefined): LoadPaceSelection {
  const normalized = normalizeInterval(interval);
  if (normalized === undefined) return "custom";
  if (normalized === LOAD_PACE_PRESET_INTERVALS.slow) return "slow";
  if (normalized === LOAD_PACE_PRESET_INTERVALS.normal) return "normal";
  if (normalized === LOAD_PACE_PRESET_INTERVALS.fast) return "fast";
  return "custom";
}

export function applyLoadPaceSelection(input: {
  selected: LoadPaceSelection;
  currentInterval: number | null | undefined;
  manualInterval: number | null | undefined;
}): { interval: number | undefined; manualInterval: number | undefined } {
  const currentInterval = normalizeInterval(input.currentInterval);
  const manualInterval = normalizeInterval(input.manualInterval);

  if (input.selected === "custom") {
    return {
      interval: manualInterval ?? currentInterval,
      manualInterval,
    };
  }

  const currentSelection = resolveLoadPaceSelection(currentInterval);
  const nextManualInterval =
    currentSelection === "custom" ? currentInterval : manualInterval;

  return {
    interval: LOAD_PACE_PRESET_INTERVALS[input.selected],
    manualInterval: nextManualInterval,
  };
}
