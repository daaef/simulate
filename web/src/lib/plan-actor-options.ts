import type { SimulationPlanContent } from "./api";

export const ACTOR_SELECT_OTHER = "__other__";
export const ACTOR_SELECT_DEFAULT = "";

export type ActorSelectMode = "default" | "plan" | "other";

export type PlanStore = {
  store_id?: string;
  subentity_id?: number;
  owner?: string;
  name?: string;
  branch?: string;
  currency?: string;
  status?: number;
  mobile?: string;
  last_active_at?: string;
  created_at?: string;
  lat?: number;
  lng?: number;
};

export type PlanUser = {
  phone?: string;
  role?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  active?: boolean;
  created_at?: string;
  lat?: number;
  lng?: number;
};

export type ActorDetailRow = {
  label: string;
  value: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function planDefaults(content: SimulationPlanContent): Record<string, unknown> {
  return asRecord(content.defaults) ?? {};
}

export function listPlanStores(content: SimulationPlanContent | null): PlanStore[] {
  if (!content) return [];
  const stores = content.stores;
  if (!Array.isArray(stores)) return [];
  return stores.filter((store): store is PlanStore => Boolean(store && typeof store === "object"));
}

export function listPlanUsers(content: SimulationPlanContent | null): PlanUser[] {
  if (!content) return [];
  const users = content.users;
  if (!Array.isArray(users)) return [];
  return users.filter((user): user is PlanUser => Boolean(user && typeof user === "object"));
}

export function storeActorKey(store: PlanStore): string {
  return String(store.store_id ?? "").trim();
}

export function userActorKey(user: PlanUser): string {
  return String(user.phone ?? "").trim();
}

export function findPlanStore(content: SimulationPlanContent | null, storeId: string): PlanStore | null {
  const key = storeId.trim();
  if (!key || !content) return null;
  return listPlanStores(content).find((store) => storeActorKey(store) === key) ?? null;
}

export function findPlanUser(content: SimulationPlanContent | null, phone: string): PlanUser | null {
  const key = phone.trim();
  if (!key || !content) return null;
  return listPlanUsers(content).find((user) => userActorKey(user) === key) ?? null;
}

export function isPlanDefaultStore(content: SimulationPlanContent | null, storeId: string): boolean {
  if (!content) return false;
  const defaults = planDefaults(content);
  return String(defaults.store_id ?? "").trim() === storeId.trim();
}

export function isPlanDefaultUser(content: SimulationPlanContent | null, phone: string): boolean {
  if (!content) return false;
  const defaults = planDefaults(content);
  return String(defaults.user_phone ?? "").trim() === phone.trim();
}

export function deriveActorSelectMode(
  value: string | undefined,
  actors: Array<{ key: string }>,
): ActorSelectMode {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) return "default";
  if (actors.some((actor) => actor.key === trimmed)) return "plan";
  return "other";
}

function formatName(first?: string, last?: string): string {
  return [first, last].filter(Boolean).join(" ").trim();
}

function formatGps(lat?: number, lng?: number): string | null {
  if (lat === undefined || lng === undefined) return null;
  return `${lat}, ${lng}`;
}

function formatStatus(status?: number): string | null {
  if (status === undefined) return null;
  return String(status);
}

export function formatStoreOptionLabel(store: PlanStore, isDefault = false): string {
  const id = storeActorKey(store);
  const name = String(store.name ?? store.branch ?? "").trim();
  const suffix = isDefault ? " (plan default)" : "";
  if (name) return `${id} · ${name}${suffix}`;
  return `${id}${suffix}`;
}

export function formatUserOptionLabel(user: PlanUser, isDefault = false): string {
  const phone = userActorKey(user);
  const name = formatName(user.first_name, user.last_name);
  const role = String(user.role ?? "").trim();
  const suffix = isDefault ? " (plan default)" : "";
  const parts = [phone];
  if (name) parts.push(name);
  if (role) parts.push(role);
  return `${parts.join(" · ")}${suffix}`;
}

function pushRow(rows: ActorDetailRow[], label: string, value: unknown): void {
  if (value === undefined || value === null || value === "") return;
  rows.push({ label, value: String(value) });
}

export function buildStoreDetailRows(store: PlanStore): ActorDetailRow[] {
  const rows: ActorDetailRow[] = [];
  pushRow(rows, "Store ID", store.store_id);
  pushRow(rows, "Name", store.name);
  pushRow(rows, "Branch", store.branch);
  pushRow(rows, "Owner", store.owner);
  pushRow(rows, "Mobile", store.mobile);
  pushRow(rows, "Status", formatStatus(store.status));
  pushRow(rows, "Currency", store.currency);
  pushRow(rows, "Subentity ID", store.subentity_id);
  const gps = formatGps(store.lat, store.lng);
  if (gps) pushRow(rows, "GPS", gps);
  pushRow(rows, "Last active", store.last_active_at);
  pushRow(rows, "Created", store.created_at);
  return rows;
}

export function buildUserDetailRows(user: PlanUser): ActorDetailRow[] {
  const rows: ActorDetailRow[] = [];
  pushRow(rows, "Phone", user.phone);
  pushRow(rows, "Role", user.role);
  const name = formatName(user.first_name, user.last_name);
  if (name) pushRow(rows, "Name", name);
  pushRow(rows, "Email", user.email);
  if (user.active !== undefined) pushRow(rows, "Active", user.active ? "yes" : "no");
  const gps = formatGps(user.lat, user.lng);
  if (gps) pushRow(rows, "GPS", gps);
  pushRow(rows, "Created", user.created_at);
  return rows;
}

export function actorSelectValue(mode: ActorSelectMode, value: string | undefined): string {
  if (mode === "other") return ACTOR_SELECT_OTHER;
  if (mode === "default") return ACTOR_SELECT_DEFAULT;
  return String(value ?? "").trim();
}
