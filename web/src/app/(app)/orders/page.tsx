"use client";

import { type ReactNode, useMemo, useState } from "react";
import {
  ApiRequestError,
  FAINZY_ORDER_STATUSES,
  fetchFainzyOrder,
  updateFainzyOrderStatus,
  type FainzyOrder,
} from "../../../lib/api";
import { getOrderItemNames } from "../../../lib/orders-display";
import { useOrders } from "../../../contexts/OrdersContext";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = "summary" | "items" | "recent";
type StatusFilter = "all" | "completed" | "pending" | "missed" | "cancelled" | "rejected";
type DateFilter = "today" | "yesterday" | "7d" | "30d" | "all";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(amount);
}

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch { return value; }
}

function statusPillClass(status: string): string {
  if (status === "completed") return "status-pill status-success";
  if (["pending", "payment_processing", "order_processing", "ready", "enroute_pickup",
    "robot_arrived_for_pickup", "enroute_delivery", "robot_arrived_for_delivery"].includes(status))
    return "status-pill status-info";
  if (["cancelled", "rejected", "missed", "refunded"].includes(status)) return "status-pill status-danger";
  return "status-pill";
}

function statusLabel(status: string): string {
  return FAINZY_ORDER_STATUSES.find((s) => s.value === status)?.label ?? status;
}

function startOfDay(d: Date): Date {
  const r = new Date(d); r.setHours(0, 0, 0, 0); return r;
}

function filterByDate(orders: FainzyOrder[], filter: DateFilter): FainzyOrder[] {
  if (filter === "all") return orders;
  const now = new Date();
  const todayStart = startOfDay(now);
  const yesterdayStart = new Date(todayStart); yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  return orders.filter((o) => {
    const t = new Date(o.created).getTime();
    if (filter === "today") return t >= todayStart.getTime();
    if (filter === "yesterday") return t >= yesterdayStart.getTime() && t < todayStart.getTime();
    if (filter === "7d") return t >= todayStart.getTime() - 7 * 86400000;
    if (filter === "30d") return t >= todayStart.getTime() - 30 * 86400000;
    return true;
  });
}

function filterByStatus(orders: FainzyOrder[], filter: StatusFilter): FainzyOrder[] {
  if (filter === "all") return orders;
  return orders.filter((o) => o.status === filter);
}

function filterBySearch(orders: FainzyOrder[], q: string): FainzyOrder[] {
  if (!q.trim()) return orders;
  const lower = q.toLowerCase();
  return orders.filter((o) =>
    o.order_id.toLowerCase().includes(lower) ||
    `${o.user.first_name} ${o.user.last_name}`.toLowerCase().includes(lower)
  );
}

// ---------------------------------------------------------------------------
// JSON viewer with search
// ---------------------------------------------------------------------------

function OrderJsonViewer({ order }: { order: FainzyOrder }) {
  const [search, setSearch] = useState("");
  const raw = JSON.stringify(order, null, 2);
  const lines = raw.split("\n");
  const q = search.trim().toLowerCase();
  const filtered = q ? lines.filter((l) => l.toLowerCase().includes(q)) : lines;

  return (
    <aside aria-label="Raw order JSON" style={{ border: "1px solid var(--border-primary)", borderRadius: "8px", background: "var(--surface-secondary)", minWidth: 0, overflow: "hidden" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", flexShrink: 0 }}>Order JSON</span>
        <input type="text" placeholder="Search fields…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: 1, fontSize: "12px", padding: "3px 7px", minWidth: 0 }} />
        {search && <button onClick={() => setSearch("")} className="secondary" style={{ fontSize: "11px", padding: "2px 7px", width: "auto", flexShrink: 0 }}>Clear</button>}
      </div>
      {search && <div style={{ padding: "4px 12px", fontSize: "11px", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-primary)" }}>{filtered.length} line{filtered.length !== 1 ? "s" : ""} matched</div>}
      <pre style={{ margin: 0, padding: "12px", maxHeight: "520px", overflow: "auto", fontSize: "12px", lineHeight: 1.45, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {filtered.join("\n")}
      </pre>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Shared split layout
// ---------------------------------------------------------------------------

function OrderResultLayout({ order, children }: { order: FainzyOrder; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: "16px", alignItems: "start" }}>
      <div style={{ minWidth: 0 }}>{children}</div>
      <OrderJsonViewer order={order} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reauth wrapper
// ---------------------------------------------------------------------------

async function withReauth<T>(fn: () => Promise<T>, onAuthError: () => void): Promise<T> {
  try { return await fn(); }
  catch (err) {
    if (err instanceof ApiRequestError && (err.status === 401 || err.status === 403)) onAuthError();
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Status update panel
// ---------------------------------------------------------------------------

function StatusUpdatePanel({ order, onAuthError, onUpdated }: { order: FainzyOrder; onAuthError: () => void; onUpdated: (s: string) => void }) {
  const [sel, setSel] = useState(order.status);
  const [updating, setUpdating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function handleUpdate() {
    setUpdating(true); setErr(null); setOk(false);
    try {
      await withReauth(() => updateFainzyOrderStatus(order.id, sel), onAuthError);
      onUpdated(sel); setOk(true);
    } catch (e) { setErr(formatError(e)); }
    finally { setUpdating(false); }
  }

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <p style={{ margin: 0, fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Update Status</p>
      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
        <select value={sel} onChange={(e) => { setSel(e.target.value); setOk(false); }} disabled={updating} style={{ width: "auto", minWidth: "200px" }}>
          {FAINZY_ORDER_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <button onClick={handleUpdate} disabled={updating || sel === order.status} style={{ width: "auto", flexShrink: 0, whiteSpace: "nowrap" }}>
          {updating ? "Updating…" : "Update Order"}
        </button>
      </div>
      {ok && <p style={{ margin: 0, color: "var(--status-success-text)", fontSize: "13px" }}>Updated to {statusLabel(sel)}.</p>}
      {err && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lookup input
// ---------------------------------------------------------------------------

function LookupInput({ onResult, onAuthError }: { onResult: (o: FainzyOrder) => void; onAuthError: () => void }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLookup() {
    const v = input.trim(); if (!v) return;
    setLoading(true); setError(null);
    try { const o = await withReauth(() => fetchFainzyOrder(v), onAuthError); onResult(o); }
    catch (e) { setError(formatError(e)); }
    finally { setLoading(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <label style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Order ID or Reference</label>
      <div style={{ display: "flex", gap: "8px" }}>
        <input type="text" placeholder="e.g. 1900 or #164235" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLookup()} style={{ flex: 1, minWidth: 0, width: "auto" }} disabled={loading} />
        <button onClick={handleLookup} disabled={loading || !input.trim()} style={{ width: "auto", flexShrink: 0, whiteSpace: "nowrap" }}>{loading ? "Looking up…" : "Look Up"}</button>
      </div>
      {error && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Order detail shared block
// ---------------------------------------------------------------------------

function OrderDetailBlock({ order, onAuthError, onUpdated }: { order: FainzyOrder; onAuthError: () => void; onUpdated: (s: string) => void }) {
  return (
    <OrderResultLayout order={order}>
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div className="panel">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "16px" }}>
            {([
              { label: "Status", content: <span className={statusPillClass(order.status)}>{statusLabel(order.status)}</span> },
              { label: "Reference", content: <strong>{order.order_id}</strong> },
              { label: "Store", content: <strong>{order.restaurant.name}</strong> },
              { label: "Customer", content: <strong>{order.user.first_name} {order.user.last_name}</strong> },
              { label: "Total", content: <strong>{order.is_free ? "Free" : formatCurrency(order.total_price)}</strong> },
              { label: "Placed", content: <strong>{formatDate(order.created)}</strong> },
            ] as { label: string; content: ReactNode }[]).map(({ label, content }) => (
              <div key={label}>
                <p style={{ margin: "0 0 4px", fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
                {content}
              </div>
            ))}
          </div>
        </div>
        <StatusUpdatePanel order={order} onAuthError={onAuthError} onUpdated={onUpdated} />
      </div>
    </OrderResultLayout>
  );
}

// ---------------------------------------------------------------------------
// Tab 1 — Order Summary
// ---------------------------------------------------------------------------

function OrderSummaryTab({ onAuthError }: { onAuthError: () => void }) {
  const [order, setOrder] = useState<FainzyOrder | null>(null);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div className="panel"><LookupInput onResult={setOrder} onAuthError={onAuthError} /></div>
      {order && <OrderDetailBlock order={order} onAuthError={onAuthError} onUpdated={(s) => setOrder({ ...order, status: s })} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2 — Items
// ---------------------------------------------------------------------------

function OrderItemsTab({ onAuthError }: { onAuthError: () => void }) {
  const [order, setOrder] = useState<FainzyOrder | null>(null);
  const itemNames = order ? getOrderItemNames(order) : [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div className="panel"><LookupInput onResult={setOrder} onAuthError={onAuthError} /></div>
      {order && (
        <OrderResultLayout order={order}>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <p style={{ margin: 0, fontSize: "12px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Order</p>
              {itemNames.length === 0
                ? <p style={{ margin: 0, color: "var(--text-secondary)" }}>No items.</p>
                : itemNames.map((n, i) => <p key={`${n}-${i}`} style={{ margin: 0, fontSize: "16px", fontWeight: 650, overflowWrap: "anywhere" }}>{n}</p>)}
              <p style={{ margin: "8px 0 0", fontSize: "16px", fontWeight: 700 }}>Total: {order.is_free ? "Free" : formatCurrency(order.total_price)}</p>
            </div>
            <StatusUpdatePanel order={order} onAuthError={onAuthError} onUpdated={(s) => setOrder({ ...order, status: s })} />
          </div>
        </OrderResultLayout>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3 — Recent Orders (full UI)
// ---------------------------------------------------------------------------

const DATE_OPTIONS: { label: string; value: DateFilter }[] = [
  { label: "Today", value: "today" },
  { label: "Yesterday", value: "yesterday" },
  { label: "Last 7 days", value: "7d" },
  { label: "Last 30 days", value: "30d" },
  { label: "All time", value: "all" },
];

const STATUS_TABS: { label: string; value: StatusFilter }[] = [
  { label: "All", value: "all" },
  { label: "Completed", value: "completed" },
  { label: "Missed", value: "missed" },
  { label: "Cancelled", value: "cancelled" },
  { label: "Rejected", value: "rejected" },
];

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <p style={{ margin: 0, fontSize: "11px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
      <p style={{ margin: 0, fontSize: "24px", fontWeight: 700 }}>{value}</p>
      {sub && <p style={{ margin: 0, fontSize: "12px", color: "var(--text-secondary)" }}>{sub}</p>}
    </div>
  );
}

function StatusChip({ label, count, tone }: { label: string; count: number; tone: "success" | "info" | "danger" | "neutral" }) {
  const bg = tone === "success" ? "var(--status-success-bg)" : tone === "danger" ? "var(--status-danger-bg)" : tone === "info" ? "var(--status-info-bg)" : "var(--surface-secondary)";
  const color = tone === "success" ? "var(--status-success-text)" : tone === "danger" ? "var(--status-danger-text)" : tone === "info" ? "var(--status-info-text)" : "var(--text-primary)";
  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "4px", minWidth: 0 }}>
      <p style={{ margin: 0, fontSize: "11px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
      <p style={{ margin: 0, fontSize: "20px", fontWeight: 700, color }}>{count}</p>
    </div>
  );
}

function RecentOrdersTab({ onAuthError }: { onAuthError: () => void }) {
  const { orders: allOrders, loading, loadingMore, error, reload, updateOrder } = useOrders();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<FainzyOrder | null>(null);

  const datePassed = useMemo(() => filterByDate(allOrders, dateFilter), [allOrders, dateFilter]);
  const filtered = useMemo(() => filterBySearch(filterByStatus(datePassed, statusFilter), search), [datePassed, statusFilter, search]);

  const metrics = useMemo(() => {
    const total = datePassed.length;
    const grossSales = datePassed.reduce((s, o) => s + (o.is_free ? 0 : o.total_price), 0);
    const avgValue = total > 0 ? grossSales / total : 0;
    const exceptions = datePassed.filter((o) => ["missed", "cancelled", "rejected"].includes(o.status)).length;
    const exceptionRate = total > 0 ? Math.round((exceptions / total) * 100) : 0;
    return {
      total, grossSales, avgValue, exceptionRate, exceptions,
      completed: datePassed.filter((o) => o.status === "completed").length,
      pending: datePassed.filter((o) => ["pending", "payment_processing", "order_processing", "ready", "enroute_pickup", "robot_arrived_for_pickup", "enroute_delivery", "robot_arrived_for_delivery"].includes(o.status)).length,
      missed: datePassed.filter((o) => o.status === "missed").length,
      cancelled: datePassed.filter((o) => o.status === "cancelled").length,
      rejected: datePassed.filter((o) => o.status === "rejected").length,
    };
  }, [datePassed]);

  // Keep selected order in sync when updateOrder is called
  const handleOrderUpdated = (id: number, newStatus: string) => {
    updateOrder(id, { status: newStatus });
    setSelected((prev) => prev?.id === id ? { ...prev, status: newStatus } : prev);
  };

  if (selected) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div>
          <button className="secondary" onClick={() => setSelected(null)} style={{ width: "auto", fontSize: "12px", padding: "4px 10px" }}>← Back to orders</button>
        </div>
        <OrderDetailBlock
          order={selected}
          onAuthError={onAuthError}
          onUpdated={(s) => handleOrderUpdated(selected.id, s)}
        />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>

      {/* Filters row */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <div className="tabs" role="tablist" style={{ margin: 0 }}>
          {STATUS_TABS.map((t) => (
            <button key={t.value} role="tab" aria-selected={statusFilter === t.value}
              className={statusFilter !== t.value ? "secondary" : undefined}
              onClick={() => setStatusFilter(t.value)}
              style={{ width: "auto" }}>
              {t.label}
            </button>
          ))}
        </div>
        <select value={dateFilter} onChange={(e) => setDateFilter(e.target.value as DateFilter)} style={{ width: "auto", minWidth: "140px" }}>
          {DATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <input
          type="text"
          placeholder="Search orders…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: "160px" }}
        />
        <button className="secondary" onClick={() => { reload(); setSelected(null); }} disabled={loading} style={{ width: "auto", fontSize: "12px", padding: "4px 10px", flexShrink: 0 }}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Metrics */}
      {!loading && allOrders.length > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px" }}>
            <MetricCard label="Orders" value={String(metrics.total)} sub={loadingMore ? "Loading more…" : undefined} />
            <MetricCard label="Gross Sales" value={formatCurrency(metrics.grossSales)} sub="Total value across visible orders" />
            <MetricCard label="Avg Order Value" value={formatCurrency(metrics.avgValue)} sub="Per visible order" />
            <MetricCard label="Exception Rate" value={`${metrics.exceptionRate}%`} sub={`${metrics.exceptions} orders need attention`} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: "12px" }}>
            <StatusChip label="Completed" count={metrics.completed} tone="success" />
            <StatusChip label="Pending" count={metrics.pending} tone="info" />
            <StatusChip label="Missed" count={metrics.missed} tone="danger" />
            <StatusChip label="Cancelled" count={metrics.cancelled} tone="danger" />
            <StatusChip label="Rejected" count={metrics.rejected} tone="danger" />
          </div>
        </>
      )}

      {/* Order Activity table */}
      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-primary)", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" }}>
          <div>
            <p style={{ margin: "0 0 2px", fontSize: "11px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Order Activity</p>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--text-secondary)" }}>
              {loading ? "Loading orders…"
                : error ? "Failed to load orders."
                : filtered.length > 0 ? "Open any order to inspect detail and update its status."
                : "No orders match the current filters."}
            </p>
          </div>
          {loadingMore && <span style={{ fontSize: "12px", color: "var(--text-secondary)", flexShrink: 0 }}>Loading more…</span>}
        </div>

        {error && <p style={{ margin: "12px 16px", color: "var(--status-danger-text)", fontSize: "13px" }}>{error}</p>}

        {!loading && !error && filtered.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-primary)" }}>
                  {["Order ID", "Status", "Customer", "Amount", "Date"].map((h) => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: "11px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((order) => (
                  <tr key={order.id}
                    onClick={() => setSelected(order)}
                    style={{ borderBottom: "1px solid var(--border-primary)", cursor: "pointer", transition: "background 0.1s" }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "var(--surface-hover)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = ""; }}
                  >
                    <td style={{ padding: "10px 16px", whiteSpace: "nowrap" }}>
                      <span style={{ color: "var(--status-info-text)", fontWeight: 600 }}>{order.order_id}</span>
                    </td>
                    <td style={{ padding: "10px 16px", whiteSpace: "nowrap" }}>
                      <span className={statusPillClass(order.status)}>{statusLabel(order.status)}</span>
                    </td>
                    <td style={{ padding: "10px 16px" }}>{order.user.first_name} {order.user.last_name}</td>
                    <td style={{ padding: "10px 16px", whiteSpace: "nowrap" }}>{order.is_free ? "Free" : formatCurrency(order.total_price)}</td>
                    <td style={{ padding: "10px 16px", whiteSpace: "nowrap", color: "var(--text-secondary)" }}>{formatDate(order.created)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OrdersPage() {
  const [tab, setTab] = useState<Tab>("summary");
  const { session, sessionError, reload: reloadOrders } = useOrders();

  function handleAuthError() {
    reloadOrders();
  }

  return (
    <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "20px", maxWidth: "1180px" }}>
      <div className="page-header">
        <h1 className="page-title">Orders</h1>
        <p className="page-subtitle">Look up orders by ID or reference and update their status.</p>
      </div>

      {sessionError ? (
        <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "10px", maxWidth: "480px" }}>
          <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{sessionError}</p>
          <button className="secondary" onClick={reloadOrders} style={{ width: "auto", fontSize: "12px", padding: "4px 10px" }}>Retry</button>
        </div>
      ) : !session ? (
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "13px" }}>Connecting to orders service…</p>
      ) : (
        <>
          <div className="tabs" role="tablist">
            {(["summary", "items", "recent"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab !== t ? "secondary" : undefined} onClick={() => setTab(t)} style={{ width: "auto" }}>
                {t === "summary" ? "Order Summary" : t === "items" ? "Update Status" : "Recent Orders"}
              </button>
            ))}
          </div>
          {tab === "summary" && <OrderSummaryTab onAuthError={handleAuthError} />}
          {tab === "items" && <OrderItemsTab onAuthError={handleAuthError} />}
          {tab === "recent" && <RecentOrdersTab onAuthError={handleAuthError} />}
        </>
      )}
    </div>
  );
}
