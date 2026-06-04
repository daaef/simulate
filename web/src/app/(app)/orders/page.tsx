"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  autoLoginForOrders,
  clearOrdersSession,
  FAINZY_ORDER_STATUSES,
  fetchFainzyOrder,
  getOrdersSession,
  updateFainzyOrderStatus,
  type FainzyOrder,
  type OrdersStoreSession,
} from "../../../lib/api";
import { getOrderItemNames } from "../../../lib/orders-display";

type Tab = "summary" | "items";

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
  if (["pending", "payment_processing", "order_processing", "ready", "enroute_pickup", "robot_arrived_for_pickup", "enroute_delivery", "robot_arrived_for_delivery"].includes(status)) return "status-pill status-info";
  if (["cancelled", "rejected", "missed", "refunded"].includes(status)) return "status-pill status-danger";
  return "status-pill";
}

function statusLabel(status: string): string {
  return FAINZY_ORDER_STATUSES.find((s) => s.value === status)?.label ?? status;
}

function OrderJsonViewer({ order }: { order: FainzyOrder }) {
  return (
    <aside
      aria-label="Raw order JSON"
      style={{
        border: "1px solid var(--border-primary)",
        borderRadius: "8px",
        background: "var(--surface-secondary)",
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 12px",
          borderBottom: "1px solid var(--border-primary)",
          fontSize: "12px",
          fontWeight: 700,
          color: "var(--text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        Order JSON
      </div>
      <pre
        style={{
          margin: 0,
          padding: "12px",
          maxHeight: "520px",
          overflow: "auto",
          fontSize: "12px",
          lineHeight: 1.45,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {JSON.stringify(order, null, 2)}
      </pre>
    </aside>
  );
}

function OrderResultLayout({
  order,
  children,
}: {
  order: FainzyOrder;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))",
        gap: "16px",
        alignItems: "start",
      }}
    >
      <div style={{ minWidth: 0 }}>{children}</div>
      <OrderJsonViewer order={order} />
    </div>
  );
}

async function withReauth<T>(fn: () => Promise<T>, onAuthError: () => void): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiRequestError && (err.status === 401 || err.status === 403)) {
      onAuthError();
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Shared lookup input
// ---------------------------------------------------------------------------

function LookupInput({
  onResult,
  onAuthError,
}: {
  onResult: (order: FainzyOrder) => void;
  onAuthError: () => void;
}) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLookup() {
    const value = input.trim();
    if (!value) return;
    setLoading(true);
    setError(null);
    try {
      const order = await withReauth(
        () => fetchFainzyOrder(value),
        onAuthError,
      );
      onResult(order);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <label style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Order ID or Reference
      </label>
      <div style={{ display: "flex", gap: "8px" }}>
        <input
          type="text"
          placeholder="e.g. 1900 or #164235"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLookup()}
          style={{ flex: 1, minWidth: 0, width: "auto" }}
          disabled={loading}
        />
        <button
          onClick={handleLookup}
          disabled={loading || !input.trim()}
          style={{ width: "auto", flexShrink: 0, whiteSpace: "nowrap" }}
        >
          {loading ? "Looking up…" : "Look Up"}
        </button>
      </div>
      {error && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 1 — Order Summary
// ---------------------------------------------------------------------------

function OrderSummaryTab({ onAuthError }: { onAuthError: () => void }) {
  const [order, setOrder] = useState<FainzyOrder | null>(null);
  const [selectedStatus, setSelectedStatus] = useState("");
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState(false);

  function handleResult(fetched: FainzyOrder) {
    setOrder(fetched);
    setSelectedStatus(fetched.status);
    setUpdateError(null);
    setUpdateSuccess(false);
  }

  async function handleUpdate() {
    if (!order || !selectedStatus) return;
    setUpdating(true);
    setUpdateError(null);
    setUpdateSuccess(false);
    try {
      await withReauth(() => updateFainzyOrderStatus(order.id, selectedStatus), onAuthError);
      setOrder({ ...order, status: selectedStatus });
      setUpdateSuccess(true);
    } catch (err) {
      setUpdateError(formatError(err));
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div className="panel">
        <LookupInput onResult={handleResult} onAuthError={onAuthError} />
      </div>

      {order && (
        <OrderResultLayout order={order}>
          <div className="panel">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "16px" }}>
              {[
                { label: "Status", content: <span className={statusPillClass(order.status)}>{statusLabel(order.status)}</span> },
                { label: "Reference", content: <strong>{order.order_id}</strong> },
                { label: "Store", content: <strong>{order.restaurant.name}</strong> },
                { label: "Customer", content: <strong>{order.user.first_name} {order.user.last_name}</strong> },
                { label: "Total", content: <strong>{order.is_free ? "Free" : formatCurrency(order.total_price)}</strong> },
                { label: "Placed", content: <strong>{formatDate(order.created)}</strong> },
              ].map(({ label, content }) => (
                <div key={label}>
                  <p style={{ margin: "0 0 4px", fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
                  {content}
                </div>
              ))}
            </div>
          </div>

          <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <p style={{ margin: 0, fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Update Status
            </p>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              <select
                value={selectedStatus}
                onChange={(e) => { setSelectedStatus(e.target.value); setUpdateSuccess(false); }}
                disabled={updating}
                style={{ width: "auto", minWidth: "200px" }}
              >
                {FAINZY_ORDER_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
              <button
                onClick={handleUpdate}
                disabled={updating || selectedStatus === order.status}
                style={{ width: "auto", flexShrink: 0, whiteSpace: "nowrap" }}
              >
                {updating ? "Updating…" : "Update Order"}
              </button>
            </div>
            {updateSuccess && <p style={{ margin: 0, color: "var(--status-success-text)", fontSize: "13px" }}>Updated to {statusLabel(selectedStatus)}.</p>}
            {updateError && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{updateError}</p>}
          </div>
        </OrderResultLayout>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2 — Update Status
// ---------------------------------------------------------------------------

function OrderItemsTab({ onAuthError }: { onAuthError: () => void }) {
  const [order, setOrder] = useState<FainzyOrder | null>(null);
  const [selectedStatus, setSelectedStatus] = useState("");
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState(false);

  function handleResult(fetched: FainzyOrder) {
    setOrder(fetched);
    setSelectedStatus(fetched.status);
    setUpdateError(null);
    setUpdateSuccess(false);
  }

  async function handleUpdate() {
    if (!order || !selectedStatus) return;
    setUpdating(true);
    setUpdateError(null);
    setUpdateSuccess(false);
    try {
      await withReauth(() => updateFainzyOrderStatus(order.id, selectedStatus), onAuthError);
      setOrder({ ...order, status: selectedStatus });
      setUpdateSuccess(true);
    } catch (err) {
      setUpdateError(formatError(err));
    } finally {
      setUpdating(false);
    }
  }

  const itemNames = order ? getOrderItemNames(order) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div className="panel">
        <LookupInput onResult={handleResult} onAuthError={onAuthError} />
      </div>

      {order && (
        <OrderResultLayout order={order}>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <p style={{ margin: 0, fontSize: "12px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Order
              </p>
              {itemNames.length === 0 ? (
                <p style={{ margin: 0, color: "var(--text-secondary)" }}>No items.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  {itemNames.map((name, index) => (
                    <p key={`${name}-${index}`} style={{ margin: 0, fontSize: "16px", fontWeight: 650, overflowWrap: "anywhere" }}>
                      {name}
                    </p>
                  ))}
                </div>
              )}
              <p style={{ margin: "8px 0 0", fontSize: "16px", fontWeight: 700 }}>
                Total: {order.is_free ? "Free" : formatCurrency(order.total_price)}
              </p>
            </div>

            <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              <select
                value={selectedStatus}
                onChange={(e) => { setSelectedStatus(e.target.value); setUpdateSuccess(false); }}
                disabled={updating}
                style={{ width: "auto", minWidth: "200px" }}
              >
                {FAINZY_ORDER_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
              <button
                className="secondary"
                onClick={handleUpdate}
                disabled={updating || selectedStatus === order.status}
                style={{ width: "auto", flexShrink: 0, whiteSpace: "nowrap" }}
              >
                {updating ? "Updating…" : "Update Status"}
              </button>
            </div>
            {updateSuccess && <p style={{ margin: 0, color: "var(--status-success-text)", fontSize: "13px" }}>Updated to {statusLabel(selectedStatus)}.</p>}
            {updateError && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{updateError}</p>}
          </div>
        </OrderResultLayout>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OrdersPage() {
  const [session, setSession] = useState<OrdersStoreSession | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [autoLoginError, setAutoLoginError] = useState<string | null>(null);
  const initialised = useRef(false);

  async function doAutoLogin() {
    setAutoLoginError(null);
    try {
      const s = await autoLoginForOrders();
      setSession(s);
    } catch (err) {
      clearOrdersSession();
      setSession(null);
      setAutoLoginError(formatError(err));
    }
  }

  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;
    void doAutoLogin();
  }, []);

  function handleAuthError() {
    clearOrdersSession();
    setSession(null);
    void doAutoLogin();
  }

  return (
    <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "20px", maxWidth: "1180px" }}>
      <div className="page-header">
        <h1 className="page-title">Orders</h1>
        <p className="page-subtitle">Look up orders by ID or reference and update their status.</p>
      </div>

      {autoLoginError ? (
        <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "10px", maxWidth: "480px" }}>
          <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{autoLoginError}</p>
          <button
            className="secondary"
            onClick={() => { void doAutoLogin(); }}
            style={{ width: "auto", fontSize: "12px", padding: "4px 10px" }}
          >
            Retry
          </button>
        </div>
      ) : !session ? (
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "13px" }}>Connecting to orders service…</p>
      ) : (
        <>
          <div className="tabs" role="tablist">
            <button
              role="tab"
              aria-selected={tab === "summary"}
              className={tab !== "summary" ? "secondary" : undefined}
              onClick={() => setTab("summary")}
              style={{ width: "auto" }}
            >
              Order Summary
            </button>
            <button
              role="tab"
              aria-selected={tab === "items"}
              className={tab !== "items" ? "secondary" : undefined}
              onClick={() => setTab("items")}
              style={{ width: "auto" }}
            >
              Update Status
            </button>
          </div>

          {tab === "summary"
            ? <OrderSummaryTab onAuthError={handleAuthError} />
            : <OrderItemsTab onAuthError={handleAuthError} />}
        </>
      )}
    </div>
  );
}
