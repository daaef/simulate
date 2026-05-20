import type { RunCreateRequest, SimulationPlanContent } from "./api";
import { hasNoRandomPhone, hasNoRandomStore } from "./random-actor-args";

export type ActorSource =
  | "form"
  | "random_plan_pool"
  | "plan_default"
  | "plan_first_store"
  | "plan_first_user"
  | "plan_runtime_default";

export type ResolvedLaunchScope = {
  planPath: string;
  storeId: string;
  storeSource: ActorSource;
  phone: string;
  phoneSource: ActorSource;
  userScope: "single" | "all_plan_users";
  planUserCount: number;
  planStoreCount: number;
  timing: string;
  users?: number | string;
  orders?: number | string;
  interval?: number | string;
  reject?: number | string;
};

type PlanUser = { phone?: string; role?: string };
type PlanStore = { store_id?: string };

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function planUsers(content: SimulationPlanContent): PlanUser[] {
  const users = content.users;
  return Array.isArray(users) ? (users as PlanUser[]) : [];
}

function planStores(content: SimulationPlanContent): PlanStore[] {
  const stores = content.stores;
  return Array.isArray(stores) ? (stores as PlanStore[]) : [];
}

function planDefaults(content: SimulationPlanContent): Record<string, unknown> {
  return asRecord(content.defaults) ?? {};
}

function planRuntimeDefaults(content: SimulationPlanContent): Record<string, unknown> {
  return asRecord(content.runtime_defaults) ?? {};
}

function findActorUser(users: PlanUser[], phone: string | null): PlanUser | null {
  if (phone) {
    const match = users.find((user) => String(user.phone ?? "") === phone);
    if (match) return match;
  }
  return users[0] ?? null;
}

function findActorStore(stores: PlanStore[], storeId: string | null): PlanStore | null {
  if (storeId) {
    const match = stores.find((store) => String(store.store_id ?? "") === storeId);
    if (match) return match;
  }
  return stores[0] ?? null;
}

function resolveLoadNumeric(
  formValue: number | undefined,
  runtimeKey: string,
  runtime: Record<string, unknown>,
  label: string,
): number | string {
  if (formValue !== undefined) return formValue;
  const fromPlan = runtime[runtimeKey];
  if (fromPlan !== undefined && fromPlan !== null && fromPlan !== "") {
    return typeof fromPlan === "number" ? fromPlan : String(fromPlan);
  }
  return label;
}

export function formatActorSource(source: ActorSource): string {
  switch (source) {
    case "form":
      return "form override";
    case "random_plan_pool":
      return "random from plan pool";
    case "plan_default":
      return "plan default";
    case "plan_first_store":
      return "first store in plan";
    case "plan_first_user":
      return "first user in plan";
    case "plan_runtime_default":
      return "plan runtime default";
    default:
      return source;
  }
}

export function resolveLaunchActors(
  form: RunCreateRequest,
  planContent: SimulationPlanContent | null,
  resolvedMode: "trace" | "load",
): ResolvedLaunchScope | null {
  if (!planContent) return null;

  const planPath = form.plan || "sim_actors.json";
  const defaults = planDefaults(planContent);
  const runtime = planRuntimeDefaults(planContent);
  const users = planUsers(planContent);
  const stores = planStores(planContent);

  const explicitStore = String(form.store_id ?? "").trim();
  const explicitPhone = String(form.phone ?? "").trim();
  const disableRandomStore = hasNoRandomStore(form.extra_args);
  const disableRandomPhone = hasNoRandomPhone(form.extra_args);

  let storeId = "";
  let storeSource: ActorSource = "plan_first_store";
  if (explicitStore) {
    storeId = explicitStore;
    storeSource = "form";
  } else if (!disableRandomStore && stores.length > 0) {
    storeId = "";
    storeSource = "random_plan_pool";
  } else {
    const defaultStoreId = defaults.store_id != null ? String(defaults.store_id) : "";
    if (defaultStoreId) {
      storeId = defaultStoreId;
      storeSource = "plan_default";
    } else {
      const firstStore = findActorStore(stores, null);
      storeId = firstStore?.store_id ? String(firstStore.store_id) : "";
      storeSource = "plan_first_store";
    }
  }

  let phone = "";
  let phoneSource: ActorSource = "plan_first_user";
  if (explicitPhone) {
    phone = explicitPhone;
    phoneSource = "form";
  } else if (!disableRandomPhone && users.length > 0) {
    phone = "";
    phoneSource = "random_plan_pool";
  } else {
    const defaultPhone = defaults.user_phone != null ? String(defaults.user_phone) : "";
    if (defaultPhone) {
      phone = defaultPhone;
      phoneSource = "plan_default";
    } else {
      const selectedUser = findActorUser(users, null);
      phone = selectedUser?.phone ? String(selectedUser.phone) : "";
      phoneSource = "plan_first_user";
    }
  }

  const scope: ResolvedLaunchScope = {
    planPath,
    storeId,
    storeSource,
    phone,
    phoneSource,
    userScope: form.all_users ? "all_plan_users" : "single",
    planUserCount: users.length,
    planStoreCount: stores.length,
    timing: form.timing,
  };

  if (resolvedMode === "load") {
    scope.users = resolveLoadNumeric(form.users, "users", runtime, "plan/env default");
    scope.orders = form.continuous
      ? "continuous"
      : resolveLoadNumeric(form.orders, "orders", runtime, "plan/env default");
    scope.interval = resolveLoadNumeric(form.interval, "interval_seconds", runtime, "plan/env default");
    scope.reject = resolveLoadNumeric(form.reject, "reject_rate", runtime, "plan/env default");
  }

  return scope;
}

function actorValueForDisplay(
  value: string,
  source: ActorSource,
): string {
  if (source === "random_plan_pool") {
    return "random from plan pool";
  }
  return value || "unset";
}

export function buildResolvedScopeLines(scope: ResolvedLaunchScope): string[] {
  const storeValue = actorValueForDisplay(scope.storeId, scope.storeSource);
  const phoneValue = actorValueForDisplay(scope.phone, scope.phoneSource);
  const lines: string[] = [
    `Plan: ${scope.planPath}`,
    `Store: ${storeValue} (${formatActorSource(scope.storeSource)})`,
    `Phone: ${phoneValue} (${formatActorSource(scope.phoneSource)})`,
    scope.userScope === "all_plan_users"
      ? `User scope: all ${scope.planUserCount} users in plan`
      : `User scope: single user (${scope.planUserCount} users in plan)`,
    `Timing: ${scope.timing}`,
  ];
  if (scope.users !== undefined) {
    lines.push(`Load users: ${scope.users}`);
    lines.push(`Load orders: ${scope.orders}`);
    lines.push(`Load interval (sec): ${scope.interval}`);
    lines.push(`Load reject rate: ${scope.reject}`);
  }
  return lines;
}

export function buildResolvedScopeSummaryLine(scope: ResolvedLaunchScope): string {
  const storeValue = actorValueForDisplay(scope.storeId, scope.storeSource);
  const phoneValue = actorValueForDisplay(scope.phone, scope.phoneSource);
  const parts = [
    `Plan ${scope.planPath}`,
    `store ${storeValue}`,
    `phone ${phoneValue}`,
  ];
  if (scope.userScope === "all_plan_users") {
    parts.push(`all ${scope.planUserCount} plan users`);
  }
  return parts.join(" · ");
}
