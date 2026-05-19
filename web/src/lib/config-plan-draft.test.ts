import { describe, expect, it } from "vitest";
import { buildNewPlanDraft } from "./config-plan-draft";

describe("buildNewPlanDraft", () => {
  it("clones parsed editor JSON when editor is valid", () => {
    const editorValue = JSON.stringify({
      defaults: {
        user_phone: "+2348166675609",
      },
      users: [{ phone: "+2349000000000" }],
    });
    const fallbackContent = {
      defaults: {
        user_phone: "+2348111111111",
      },
      users: [{ phone: "+2348222222222" }],
    };

    const draft = buildNewPlanDraft(editorValue, fallbackContent);

    expect(draft).toEqual({
      name: "Plan Copy",
      content: {
        defaults: {
          user_phone: "+2348166675609",
        },
        users: [{ phone: "+2349000000000" }],
      },
    });
    expect(draft.content).not.toBe(fallbackContent);
  });

  it.each(["[]", "1", "null"])(
    "falls back to selected content when parsed editor value is invalid object: %s",
    (editorValue) => {
      const fallbackContent = {
        defaults: {
          store_id: "FZY_926025",
        },
        stores: [{ store_id: "FZY_926025" }],
      };

      const draft = buildNewPlanDraft(editorValue, fallbackContent);

      expect(draft).toEqual({
        name: "Plan Copy",
        content: fallbackContent,
      });
      expect(draft.content).not.toBe(fallbackContent);
    },
  );

  it("falls back to selected content when editor JSON is invalid", () => {
    const fallbackContent = {
      defaults: {
        store_id: "FZY_926025",
      },
      stores: [{ store_id: "FZY_926025" }],
    };

    const draft = buildNewPlanDraft("{invalid-json", fallbackContent, "Copied from selected");

    expect(draft).toEqual({
      name: "Copied from selected",
      content: fallbackContent,
    });
    expect(draft.content).not.toBe(fallbackContent);

    const draftContent = draft.content as {
      defaults: { store_id: string };
      stores: Array<{ store_id: string }>;
    };
    draftContent.defaults.store_id = "FZY_MUTATED";
    draftContent.stores[0]!.store_id = "FZY_MUTATED";

    expect(fallbackContent.defaults.store_id).toBe("FZY_926025");
    expect(fallbackContent.stores[0]!.store_id).toBe("FZY_926025");
  });
});
