# Orders Update Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Orders second tab a direct status-update flow and show readable raw order JSON on the right side of both tabs.

**Architecture:** Keep all API behavior unchanged. Add one small display helper for item-name extraction, then update `web/src/app/(app)/orders/page.tsx` to share a raw JSON pane and simplify the second tab layout. The second tab must not render the current `Store` or `Items Ordered` detail cards.

**Tech Stack:** Next.js 14 App Router, React 18, TypeScript 5.8, Vitest.

---

### Task 1: Add Item Display Helper Coverage

**Files:**
- Create: `web/src/lib/orders-display.ts`
- Create: `web/src/lib/orders-display.test.ts`

- [x] **Step 1: Write the failing helper test**

Create `web/src/lib/orders-display.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getOrderItemNames } from "./orders-display";

describe("orders display helpers", () => {
  it("returns only trimmed order item names", () => {
    const names = getOrderItemNames({
      menu: [
        { menu: { name: " Donut ドーナツ " } },
        { menu: { name: "Coffee" } },
        { menu: { name: "" } },
      ],
    });

    expect(names).toEqual(["Donut ドーナツ", "Coffee"]);
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd web && npm test -- orders-display.test.ts
```

Expected: fail because `./orders-display` does not exist.

- [x] **Step 3: Add minimal helper implementation**

Create `web/src/lib/orders-display.ts`:

```ts
type OrderItemNameSource = {
  menu?: Array<{
    menu?: {
      name?: string | null;
    } | null;
  } | null>;
};

export function getOrderItemNames(order: OrderItemNameSource): string[] {
  return (order.menu ?? [])
    .map((item) => item?.menu?.name?.trim() ?? "")
    .filter((name) => name.length > 0);
}
```

- [x] **Step 4: Run helper test to verify it passes**

Run:

```bash
cd web && npm test -- orders-display.test.ts
```

Expected: pass.

### Task 2: Simplify Orders Second Tab and Add JSON Pane

**Files:**
- Modify: `web/src/app/(app)/orders/page.tsx`
- Modify: `web/src/lib/orders-display.ts` only if type alignment needs a narrow adjustment.

- [x] **Step 1: Import the helper**

In `web/src/app/(app)/orders/page.tsx`, add:

```ts
import { getOrderItemNames } from "../../../lib/orders-display";
```

- [x] **Step 2: Add shared raw JSON component**

In `web/src/app/(app)/orders/page.tsx`, near existing formatting helpers, add:

```tsx
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
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-primary)", fontSize: "12px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Order JSON
      </div>
      <pre style={{ margin: 0, padding: "12px", maxHeight: "520px", overflow: "auto", fontSize: "12px", lineHeight: 1.45, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {JSON.stringify(order, null, 2)}
      </pre>
    </aside>
  );
}
```

- [x] **Step 3: Add a responsive result layout component**

In `web/src/app/(app)/orders/page.tsx`, add:

```tsx
function OrderResultLayout({
  order,
  children,
}: {
  order: FainzyOrder;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: "16px", alignItems: "start" }}>
      <div style={{ minWidth: 0 }}>{children}</div>
      <OrderJsonViewer order={order} />
    </div>
  );
}
```

If TypeScript needs `React.ReactNode` without a namespace import, update the React import to:

```ts
import { type ReactNode, useEffect, useRef, useState } from "react";
```

and use `children: ReactNode`.

- [x] **Step 4: Wrap Summary tab result content with JSON layout**

In `OrderSummaryTab`, when `order` exists, wrap the existing summary and update panels in:

```tsx
<OrderResultLayout order={order}>
  {/* existing summary panel and Update Status panel */}
</OrderResultLayout>
```

Keep the `Order Summary` tab content otherwise unchanged.

- [x] **Step 5: Replace second tab result content**

In `OrderItemsTab`, replace the current three panels (`Store`, `Items Ordered`, and the final status panel) with:

```tsx
<OrderResultLayout order={order}>
  <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <p style={{ margin: 0, fontSize: "12px", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Order
      </p>
      {getOrderItemNames(order).length === 0 ? (
        <p style={{ margin: 0, color: "var(--text-secondary)" }}>No items.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {getOrderItemNames(order).map((name, index) => (
            <p key={`${name}-${index}`} style={{ margin: 0, fontSize: "16px", fontWeight: 650 }}>
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
        {updating ? "Updating..." : "Update Status"}
      </button>
    </div>
    {updateSuccess && <p style={{ margin: 0, color: "var(--status-success-text)", fontSize: "13px" }}>Updated to {statusLabel(selectedStatus)}.</p>}
    {updateError && <p style={{ margin: 0, color: "var(--status-danger-text)", fontSize: "13px" }}>{updateError}</p>}
  </div>
</OrderResultLayout>
```

Ensure the old `Store` block, `Items Ordered` heading, item quantity line, item price, and item total row are gone from the second tab.

- [x] **Step 6: Rename the second tab**

Change the tab button text from:

```tsx
Items &amp; Store
```

to:

```tsx
Update Status
```

### Task 3: Verify and Record Results

**Files:**
- Modify: `implementation/tracker/README.md`
- Modify: `implementation/tracker/tasks.md`
- Modify: `implementation/tracker/session_log.md`

- [x] **Step 1: Run focused web tests**

Run:

```bash
cd web && npm test -- orders-display.test.ts orders-api.test.ts
```

Expected: pass.

- [x] **Step 2: Run TypeScript**

Run:

```bash
cd web && npx tsc --noEmit
```

Expected: pass.

- [x] **Step 3: Run full web suite if time allows**

Run:

```bash
cd web && npm test
```

Expected: pass.

- [x] **Step 4: Rebuild web service**

Run:

```bash
docker compose up -d --build web
```

Expected: web image rebuilds and `simulate-web-1` starts.

- [x] **Step 5: Smoke-check route**

Run:

```bash
curl -sS -i http://localhost:8080/orders
```

Expected: HTTP 200.

- [x] **Step 6: Update tracker**

Record Phase 40 completion in:

- `implementation/tracker/README.md`
- `implementation/tracker/tasks.md`
- `implementation/tracker/session_log.md`

Include the verification commands and the remaining manual browser check: open `/orders`, second tab should read `Update Status`, old store/items detail cards should be absent, raw JSON should appear on the right after lookup.
