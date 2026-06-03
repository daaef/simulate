import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  FAINZY_ORDER_STATUSES,
  clearOrdersSession,
  fetchFainzyOrder,
  getOrdersSession,
  loginAsStore,
} from "./api";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  clear(): void {
    this.values.clear();
  }
}

const storage = new MemoryStorage();

beforeEach(() => {
  storage.clear();
  vi.stubGlobal("localStorage", storage);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("orders api helpers", () => {
  it("logs in through the simulator API and persists the returned store session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session: {
            storeId: "FZY_926025",
            storeName: "Ask Me Restaurant Jos",
            token: "store-token",
            subentityId: 7,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const session = await loginAsStore("fzy_926025");

    expect(session).toEqual({
      storeId: "FZY_926025",
      storeName: "Ask Me Restaurant Jos",
      token: "store-token",
      subentityId: 7,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/orders/store-login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ store_id: "FZY_926025" }),
      }),
    );
    expect(getOrdersSession()).toEqual(session);

    clearOrdersSession();
    expect(getOrdersSession()).toBeNull();
  });

  it("looks up one query value through the unified orders endpoint with the stored token", async () => {
    storage.setItem(
      "fainzy_orders_session",
      JSON.stringify({
        storeId: "FZY_926025",
        storeName: "Ask Me Restaurant Jos",
        token: "store-token",
        subentityId: 7,
      }),
    );
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ order: { id: 1850, order_id: "#156382" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchFainzyOrder("156382");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/orders/lookup?query=156382&subentity_id=7",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({
          "x-fainzy-token": "store-token",
        }),
      }),
    );
  });

  it("includes the full simulator order lifecycle status list", () => {
    expect(FAINZY_ORDER_STATUSES.map((item) => item.value)).toEqual([
      "pending",
      "payment_processing",
      "order_processing",
      "ready",
      "enroute_pickup",
      "robot_arrived_for_pickup",
      "enroute_delivery",
      "robot_arrived_for_delivery",
      "completed",
      "cancelled",
      "rejected",
      "missed",
      "refunded",
    ]);
  });
});
