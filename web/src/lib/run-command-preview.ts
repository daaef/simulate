import type { RunCreateRequest } from "./api";

export function buildRunCommandPreview(form: RunCreateRequest): string {
  const parts: string[] = [
    "python3",
    "-m",
    "simulate",
    form.flow || "doctor",
    "--plan",
    form.plan || "sim_actors.json",
    "--timing",
    form.timing,
  ];

  if (form.mode) parts.push("--mode", form.mode);
  if (form.suite && form.suite.trim()) parts.push("--suite", form.suite.trim());
  for (const scenario of form.scenarios || []) {
    if (scenario.trim()) parts.push("--scenario", scenario.trim());
  }
  if (form.store_id && form.store_id.trim()) parts.push("--store", form.store_id.trim());
  if (form.phone && form.phone.trim()) parts.push("--phone", form.phone.trim());
  if (form.all_users) parts.push("--all-users");
  if (form.strict_plan) parts.push("--strict-plan");
  if (form.skip_app_probes) parts.push("--skip-app-probes");
  if (form.skip_store_dashboard_probes) parts.push("--skip-store-dashboard-probes");
  if (form.no_auto_provision) parts.push("--no-auto-provision");
  if (form.enforce_websocket_gates) parts.push("--enforce-websocket-gates");
  if (form.post_order_actions) parts.push("--post-order-actions");
  if (form.users !== undefined) parts.push("--users", String(form.users));
  if (form.orders !== undefined) parts.push("--orders", String(form.orders));
  if (form.interval !== undefined) parts.push("--interval", String(form.interval));
  if (form.reject !== undefined) parts.push("--reject", String(form.reject));
  if (form.continuous) parts.push("--continuous");
  if (form.extra_args && form.extra_args.length) {
    parts.push(...form.extra_args);
  }
  return parts.join(" ");
}
