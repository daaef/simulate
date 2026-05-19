export type PlanDraft = {
  name: string;
  content: Record<string, unknown>;
};

function clonePlanContent(content: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(content)) as Record<string, unknown>;
}

export function buildNewPlanDraft(
  editorValue: string,
  fallbackContent: Record<string, unknown>,
  nextName = "Plan Copy",
): PlanDraft {
  try {
    const parsed = JSON.parse(editorValue);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return {
        name: nextName,
        content: parsed as Record<string, unknown>,
      };
    }
  } catch {
    // Ignore parse failures and use selected plan content.
  }

  return {
    name: nextName,
    content: clonePlanContent(fallbackContent),
  };
}
