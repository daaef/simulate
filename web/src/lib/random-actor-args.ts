export const NO_RANDOM_PHONE_FLAG = "--no-random-phone";
export const NO_RANDOM_STORE_FLAG = "--no-random-store";

function normalise(extraArgs: string[] | undefined): string[] {
  const values = (extraArgs ?? [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  return Array.from(new Set(values));
}

function setFlag(extraArgs: string[] | undefined, flag: string, enabled: boolean): string[] {
  const values = normalise(extraArgs).filter((item) => item !== flag);
  return enabled ? [...values, flag] : values;
}

export function hasNoRandomPhone(extraArgs: string[] | undefined): boolean {
  return normalise(extraArgs).includes(NO_RANDOM_PHONE_FLAG);
}

export function hasNoRandomStore(extraArgs: string[] | undefined): boolean {
  return normalise(extraArgs).includes(NO_RANDOM_STORE_FLAG);
}

export function setNoRandomPhone(extraArgs: string[] | undefined, disabled: boolean): string[] {
  return setFlag(extraArgs, NO_RANDOM_PHONE_FLAG, disabled);
}

export function setNoRandomStore(extraArgs: string[] | undefined, disabled: boolean): string[] {
  return setFlag(extraArgs, NO_RANDOM_STORE_FLAG, disabled);
}

export function clearRandomActorFlags(extraArgs: string[] | undefined): string[] {
  return normalise(extraArgs).filter(
    (item) => item !== NO_RANDOM_PHONE_FLAG && item !== NO_RANDOM_STORE_FLAG,
  );
}
