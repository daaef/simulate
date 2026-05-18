function normalizeToken(value: string): string {
  return value.trim();
}

function supportedSet(options: string[]): Set<string> {
  return new Set(options.map((item) => normalizeToken(item)).filter(Boolean));
}

export function normalizeScenarioSelection(value: string[], options: string[]): string[] {
  const allowed = supportedSet(options);
  const next: string[] = [];
  const seen = new Set<string>();
  for (const raw of value) {
    const token = normalizeToken(raw);
    if (!token || !allowed.has(token) || seen.has(token)) continue;
    seen.add(token);
    next.push(token);
  }
  return next;
}

export function getScenarioSuggestions(options: string[], selected: string[], query: string): string[] {
  const chosen = new Set(normalizeScenarioSelection(selected, options));
  const needle = normalizeToken(query).toLowerCase();
  return options.filter((option) => {
    if (chosen.has(option)) return false;
    if (!needle) return true;
    return option.toLowerCase().includes(needle);
  });
}

export function addScenarioSelection(selected: string[], candidate: string, options: string[]): string[] {
  const next = normalizeScenarioSelection(selected, options);
  const token = normalizeToken(candidate);
  if (!token) return next;
  const allowed = supportedSet(options);
  if (!allowed.has(token) || next.includes(token)) return next;
  return [...next, token];
}

export function removeScenarioSelection(selected: string[], candidate: string): string[] {
  const token = normalizeToken(candidate);
  if (!token) return selected;
  return selected.filter((item) => item !== token);
}
