import { describe, expect, it } from "vitest";
import {
  NO_RANDOM_PHONE_FLAG,
  NO_RANDOM_STORE_FLAG,
  hasNoRandomPhone,
  hasNoRandomStore,
  setNoRandomPhone,
  setNoRandomStore,
} from "./random-actor-args";

describe("random-actor-args helpers", () => {
  it("adds and removes no-random-phone flag", () => {
    const withFlag = setNoRandomPhone([], true);
    expect(withFlag).toContain(NO_RANDOM_PHONE_FLAG);
    expect(hasNoRandomPhone(withFlag)).toBe(true);

    const withoutFlag = setNoRandomPhone(withFlag, false);
    expect(withoutFlag).not.toContain(NO_RANDOM_PHONE_FLAG);
    expect(hasNoRandomPhone(withoutFlag)).toBe(false);
  });

  it("adds and removes no-random-store flag", () => {
    const withFlag = setNoRandomStore([], true);
    expect(withFlag).toContain(NO_RANDOM_STORE_FLAG);
    expect(hasNoRandomStore(withFlag)).toBe(true);

    const withoutFlag = setNoRandomStore(withFlag, false);
    expect(withoutFlag).not.toContain(NO_RANDOM_STORE_FLAG);
    expect(hasNoRandomStore(withoutFlag)).toBe(false);
  });

  it("does not duplicate flags when toggled repeatedly", () => {
    const once = setNoRandomPhone([NO_RANDOM_PHONE_FLAG], true);
    const twice = setNoRandomPhone(once, true);
    expect(twice.filter((item) => item === NO_RANDOM_PHONE_FLAG)).toHaveLength(1);
  });
});
