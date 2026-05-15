"use client";

import { useEffect, useMemo, useState } from "react";
import type { RunActionCount } from "../../lib/api";

const OUTCOME_CHIPS: { label: string; actions: string[] }[] = [
  { label: "Orders placed", actions: ["place_order"] },
  { label: "Orders rejected", actions: ["rejected_order"] },
  { label: "Receipts generated", actions: ["generate_receipt"] },
  { label: "Coupons probed", actions: ["probe_coupons"] },
  { label: "User OTP verified", actions: ["verify_user_otp"] },
  { label: "User token fetched", actions: ["fetch_user_token"] },
];

const VIEW_STORAGE_KEY = "run-action-metrics-view";
const METRIC_VIEWS = ["business", "operations", "engineering"] as const;
type MetricsView = (typeof METRIC_VIEWS)[number];

const FRIENDLY_ACTION_LABELS: Record<string, string> = {
  app_bootstrap: "App bootstrap checks",
  complete_free_order: "Free order completed",
  completed_order: "Order completed",
  fetch_active_orders: "Active orders fetched",
  fetch_cards: "Saved cards fetched",
  fetch_reorder: "Reorder options fetched",
  fetch_store_dashboard: "Store dashboard fetched",
  fetch_user_token: "User token fetched",
  generate_receipt: "Receipt generated",
  mark_ready: "Store marked order ready",
  place_order: "Order placed",
  probe_coupons: "Coupons checked",
  rejected_order: "Order rejected",
  submit_review: "Review submitted",
  verify_user_otp: "User OTP verified",
  websocket_message: "WebSocket message observed",
};

function countForActions(rows: RunActionCount[], names: readonly string[]): number {
  const map = new Map(rows.map((r) => [r.action, r.count]));
  return names.reduce((sum, a) => sum + (map.get(a) ?? 0), 0);
}

function toTitleCaseFromSnakeCase(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function friendlyLabelForAction(action: string): string {
  return FRIENDLY_ACTION_LABELS[action] ?? toTitleCaseFromSnakeCase(action);
}

function toPercent(numerator: number, denominator: number): string {
  if (denominator <= 0) return "0.0%";
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function getActionCountMap(rows: RunActionCount[]): Map<string, number> {
  return new Map(rows.map((r) => [r.action, r.count]));
}

function sumActions(map: Map<string, number>, actions: readonly string[]): number {
  return actions.reduce((sum, action) => sum + (map.get(action) ?? 0), 0);
}

function countActorsByPattern(topActors: Record<string, number>, pattern: RegExp): number {
  return Object.keys(topActors).filter((name) => pattern.test(name)).length;
}

function loadInitialView(): MetricsView {
  if (typeof window === "undefined") return "business";
  const saved = window.localStorage.getItem(VIEW_STORAGE_KEY);
  return METRIC_VIEWS.includes(saved as MetricsView) ? (saved as MetricsView) : "business";
}

interface MetricCardData {
  label: string;
  value: string | number;
  tone?: "default" | "success" | "warning" | "danger";
}

function MetricCard({ label, value, tone = "default" }: MetricCardData) {
  return (
    <article className={`metrics-kpi-card tone-${tone}`}>
      <p className="metrics-kpi-label">{label}</p>
      <p className="metrics-kpi-value">{value}</p>
    </article>
  );
}

export default function RunActionCountsPanel({
  action_counts,
  total_events,
  failed_events = 0,
  http_calls = 0,
  websocket_events = 0,
  top_actors,
  title = "All actions in this run",
  defaultCollapsed = false,
  showOutcomeChips = true,
}: {
  action_counts: RunActionCount[] | undefined;
  total_events: number;
  failed_events?: number;
  http_calls?: number;
  websocket_events?: number;
  top_actors?: Record<string, number>;
  title?: string;
  defaultCollapsed?: boolean;
  showOutcomeChips?: boolean;
}) {
  const [filter, setFilter] = useState("");
  const [panelCollapsed, setPanelCollapsed] = useState(defaultCollapsed);
  const [drilldownCollapsed, setDrilldownCollapsed] = useState(true);
  const [view, setView] = useState<MetricsView>("business");

  const rows = action_counts ?? [];
  const total = total_events > 0 ? total_events : rows.reduce((s, r) => s + r.count, 0);
  const actorMap = top_actors ?? {};
  const actionCountMap = useMemo(() => getActionCountMap(rows), [rows]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.action.toLowerCase().includes(q));
  }, [rows, filter]);

  useEffect(() => {
    setView(loadInitialView());
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    }
  }, [view]);

  const chips = useMemo(() => {
    if (!showOutcomeChips || !rows.length) return [];
    return OUTCOME_CHIPS.map(({ label, actions }) => ({
      label,
      count: countForActions(rows, actions),
    })).filter((c) => c.count > 0);
  }, [rows, showOutcomeChips]);

  const ordersPlaced = sumActions(actionCountMap, ["place_order"]);
  const ordersCompleted = sumActions(actionCountMap, [
    "completed_order",
    "verify_completed",
    "robot_completed",
  ]);
  const ordersRejected = sumActions(actionCountMap, [
    "rejected_order",
    "verify_rejected",
    "store_rejected",
  ]);
  const ordersCancelled = sumActions(actionCountMap, [
    "cancel_order",
    "cancelled_order",
    "verify_cancelled",
    "user_cancelled",
  ]);
  const couponsUsed = sumActions(actionCountMap, ["select_coupon", "apply_coupon", "probe_coupons"]);
  const receiptsGenerated = sumActions(actionCountMap, ["generate_receipt"]);
  const reviewsSubmitted = sumActions(actionCountMap, ["submit_review"]);
  const reordersFetched = sumActions(actionCountMap, ["fetch_reorder"]);
  const paymentFailures = sumActions(actionCountMap, [
    "complete_payment_failed",
    "fetch_cards_failed",
    "payment_failed",
  ]);
  const storeReadyEvents = sumActions(actionCountMap, ["mark_ready", "store_ready"]);
  const completionRate = toPercent(ordersCompleted, Math.max(ordersPlaced, 1));

  const activeUsers = countActorsByPattern(actorMap, /(^|[_\s-])user([_\s-]|$)/i);
  const activeStores = countActorsByPattern(actorMap, /(^|[_\s-])store([_\s-]|$)/i);
  const actorsCovered = Object.keys(actorMap).length;

  const businessCards: MetricCardData[] = [
    { label: "Orders Placed", value: ordersPlaced },
    { label: "Orders Completed", value: ordersCompleted, tone: "success" },
    { label: "Orders Rejected", value: ordersRejected, tone: ordersRejected > 0 ? "warning" : "default" },
    { label: "Orders Cancelled", value: ordersCancelled, tone: ordersCancelled > 0 ? "warning" : "default" },
    { label: "Completion Rate", value: completionRate, tone: ordersCompleted > 0 ? "success" : "default" },
    { label: "Coupons Used", value: couponsUsed },
    { label: "Receipts Generated", value: receiptsGenerated },
    { label: "Reviews Submitted", value: reviewsSubmitted },
    { label: "Active Users", value: activeUsers },
    { label: "Active Stores", value: activeStores },
    { label: "Actors Covered", value: actorsCovered },
  ];

  const operationsCards: MetricCardData[] = [
    { label: "Run Events", value: total },
    { label: "Failed Events", value: failed_events, tone: failed_events > 0 ? "danger" : "default" },
    { label: "WebSocket Events", value: websocket_events },
    { label: "HTTP Calls", value: http_calls },
    { label: "Order Rejections", value: ordersRejected, tone: ordersRejected > 0 ? "warning" : "default" },
    { label: "Order Cancellations", value: ordersCancelled, tone: ordersCancelled > 0 ? "warning" : "default" },
    { label: "Payment Failures", value: paymentFailures, tone: paymentFailures > 0 ? "danger" : "default" },
    { label: "Store Ready Events", value: storeReadyEvents },
  ];

  const engineeringCards: MetricCardData[] = [
    { label: "Distinct Actions", value: rows.length },
    { label: "Top Action Count", value: rows.length ? rows[0].count : 0 },
    { label: "Auth Token Fetches", value: sumActions(actionCountMap, ["fetch_user_token", "fetch_store_token"]) },
    { label: "OTP Verifications", value: sumActions(actionCountMap, ["verify_user_otp"]) },
    { label: "Reorder Fetch Calls", value: reordersFetched },
    { label: "Receipt Calls", value: receiptsGenerated },
    { label: "Coupon Probe Calls", value: sumActions(actionCountMap, ["probe_coupons"]) },
    { label: "Action Coverage", value: `${rows.length} actions / ${total} events` },
  ];

  const visibleCards = view === "business" ? businessCards : view === "operations" ? operationsCards : engineeringCards;

  if (!rows.length) {
    return (
      <div className="panel">
        <h3 style={{ margin: "0 0 8px" }}>{title}</h3>
        <p className="muted" style={{ margin: 0 }}>
          No action breakdown is available yet (events artifact missing or empty).
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="run-action-counts-header">
        <h3 className="run-action-counts-title">{title}</h3>
        {defaultCollapsed ? (
          <button
            type="button"
            className="secondary"
            onClick={() => setPanelCollapsed((c) => !c)}
            aria-expanded={!panelCollapsed}
            style={{ width: "auto", fontSize: 13 }}
          >
            {panelCollapsed ? "Show metrics" : "Hide metrics"}
          </button>
        ) : null}
      </div>
      <p className="muted run-action-counts-copy">
        Dashboard KPI cards are derived from run metrics and action taxonomy. Use drill-down for full technical actions.
      </p>

      {chips.length > 0 ? (
        <div className="run-action-counts-chips">
          {chips.map((c) => (
            <span key={c.label} className="chip" title="Subset of actions below">
              {c.label}: <strong>{c.count}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {!panelCollapsed ? (
        <>
          <div className="metrics-view-switch" role="tablist" aria-label="Metrics views">
            {METRIC_VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                className={`secondary metrics-view-button${view === v ? " active" : ""}`}
                role="tab"
                aria-selected={view === v}
                onClick={() => setView(v)}
              >
                {toTitleCaseFromSnakeCase(v)}
              </button>
            ))}
          </div>

          <div className="metrics-kpi-grid" role="list" aria-label={`${view} metrics`}>
            {visibleCards.map((card) => (
              <MetricCard key={card.label} {...card} />
            ))}
          </div>

          <div className="run-action-counts-footnote muted">
            View preference is saved in this browser. Business is the default audience-focused KPI view.
          </div>

          <div className="run-action-counts-drilldown">
            <button
              type="button"
              className="secondary run-action-counts-drilldown-toggle"
              onClick={() => setDrilldownCollapsed((c) => !c)}
              aria-expanded={!drilldownCollapsed}
            >
              {drilldownCollapsed ? "Show technical action drill-down" : "Hide technical action drill-down"}
            </button>

            {!drilldownCollapsed ? (
              <>
                <label className="muted run-action-counts-search-label">
                  Search action keys
                  <input
                    type="search"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="e.g. place_order"
                    className="run-action-counts-search-input"
                    autoComplete="off"
                  />
                </label>
                <div className="run-action-counts-grid" role="list" aria-label="Action counts drill-down">
                  {filtered.map((row) => (
                    <article key={row.action} className="run-action-card" role="listitem">
                      <p className="run-action-card-label">{friendlyLabelForAction(row.action)}</p>
                      <p className="run-action-card-key">
                        <code>{row.action}</code>
                      </p>
                      <div className="run-action-card-metrics">
                        <span className="run-action-card-count">{row.count}</span>
                        {total > 0 ? (
                          <span className="muted run-action-card-percent">{((row.count / total) * 100).toFixed(1)}%</span>
                        ) : null}
                      </div>
                    </article>
                  ))}
                </div>
                {filtered.length === 0 ? (
                  <p className="muted run-action-counts-empty">
                    No actions match this search.
                  </p>
                ) : null}
                <div className="run-action-counts-footnote muted">
                  Raw action keys remain visible for technical traceability.
                </div>
              </>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
