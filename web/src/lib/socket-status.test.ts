import { describe, expect, it } from "vitest";
import {
  socketBadgeClass,
  socketBadgeLabel,
  socketStatusTooltip,
  type SocketStatusResponse,
} from "./socket-status";

const baseStatus: SocketStatusResponse = {
  enabled: true,
  status: "up",
  checked_at: "2026-06-18T12:00:00+00:00",
  target: { store_id: "FZY_1", source: "SIM_SOCKET_MONITOR_STORE_ID", base_url: "https://lastmile.fainzy.tech" },
  required: [
    { key: "store_orders", label: "Orders", status: "up", latency_ms: 10, failure_streak: 0, reason: null },
    { key: "store_stats", label: "Stats", status: "up", latency_ms: 12, failure_streak: 0, reason: null },
  ],
  reason: null,
  latest_run_evidence: { status: "up", run_id: 1, run_status: "succeeded", matched: 2, expected: 2, missed: 0 },
};

describe("socket status formatting", () => {
  it("returns badge labels by status", () => {
    expect(socketBadgeLabel({ ...baseStatus, status: "up" })).toBe("Sockets Up");
    expect(socketBadgeLabel({ ...baseStatus, status: "degraded" })).toBe("Sockets Degraded");
    expect(socketBadgeLabel({ ...baseStatus, status: "down" })).toBe("Sockets Down");
    expect(socketBadgeLabel({ ...baseStatus, status: "unknown" })).toBe("Sockets Unknown");
  });

  it("returns badge classes by status", () => {
    expect(socketBadgeClass({ ...baseStatus, status: "up" })).toBe("socket-status-badge socket-status-badge--up");
    expect(socketBadgeClass({ ...baseStatus, status: "down" })).toBe("socket-status-badge socket-status-badge--down");
  });

  it("includes failing socket names in tooltip", () => {
    const tooltip = socketStatusTooltip({
      ...baseStatus,
      status: "down",
      required: [
        { key: "store_orders", label: "Orders", status: "down", latency_ms: null, failure_streak: 2, reason: "timeout" },
        { key: "store_stats", label: "Stats", status: "up", latency_ms: 12, failure_streak: 0, reason: null },
      ],
    });

    expect(tooltip).toContain("Sockets Down");
    expect(tooltip).toContain("Orders");
    expect(tooltip).toContain("timeout");
  });
});
