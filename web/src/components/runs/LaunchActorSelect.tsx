"use client";

import { useMemo } from "react";
import type { SimulationPlanContent } from "../../lib/api";
import {
  ACTOR_SELECT_DEFAULT,
  ACTOR_SELECT_OTHER,
  actorSelectValue,
  deriveActorSelectMode,
  formatStoreOptionLabel,
  formatUserOptionLabel,
  isPlanDefaultStore,
  isPlanDefaultUser,
  listPlanStores,
  listPlanUsers,
  storeActorKey,
  userActorKey,
} from "../../lib/plan-actor-options";

type LaunchActorFieldId = "store" | "phone";

interface LaunchActorSelectProps {
  fieldId: LaunchActorFieldId;
  planContent: SimulationPlanContent | null;
  value: string | undefined;
  onChange: (value: string) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  onTouch?: () => void;
}

export default function LaunchActorSelect({
  fieldId,
  planContent,
  value,
  onChange,
  onFocus,
  onBlur,
  onTouch,
}: LaunchActorSelectProps) {
  const isStore = fieldId === "store";

  const storeActors = useMemo(
    () =>
      listPlanStores(planContent)
        .map((store) => ({ key: storeActorKey(store), store }))
        .filter((entry) => entry.key),
    [planContent],
  );

  const userActors = useMemo(
    () =>
      listPlanUsers(planContent)
        .map((user) => ({ key: userActorKey(user), user }))
        .filter((entry) => entry.key),
    [planContent],
  );

  const actors = isStore ? storeActors : userActors;

  const mode = useMemo(() => deriveActorSelectMode(value, actors), [value, actors]);

  const selectValue = actorSelectValue(mode, value);

  const placeholder = isStore ? "e.g. FZY_926025" : "e.g. +2348166675609";

  function handleSelectChange(nextSelectValue: string) {
    onTouch?.();
    if (nextSelectValue === ACTOR_SELECT_DEFAULT) {
      onChange("");
      return;
    }
    if (nextSelectValue === ACTOR_SELECT_OTHER) {
      onChange(String(value ?? "").trim());
      return;
    }
    onChange(nextSelectValue);
  }

  return (
    <div className="launcher-actor-select grid" style={{ gap: 8 }}>
      <select
        value={selectValue}
        onFocus={onFocus}
        onBlur={onBlur}
        onChange={(event) => handleSelectChange(event.target.value)}
      >
        <option value={ACTOR_SELECT_DEFAULT}>Plan default</option>
        {isStore
          ? storeActors.map((entry) => (
              <option key={entry.key} value={entry.key}>
                {formatStoreOptionLabel(entry.store, isPlanDefaultStore(planContent, entry.key))}
              </option>
            ))
          : userActors.map((entry) => (
              <option key={entry.key} value={entry.key}>
                {formatUserOptionLabel(entry.user, isPlanDefaultUser(planContent, entry.key))}
              </option>
            ))}
        <option value={ACTOR_SELECT_OTHER}>Other (custom value)</option>
      </select>

      {!planContent ? (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          Plan content unavailable — choose Other or select a different plan.
        </p>
      ) : null}

      {mode === "other" ? (
        <input
          type="text"
          value={value ?? ""}
          placeholder={placeholder}
          onFocus={onFocus}
          onBlur={onBlur}
          onChange={(event) => {
            onTouch?.();
            onChange(event.target.value);
          }}
        />
      ) : null}
    </div>
  );
}
