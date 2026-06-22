import { formatDateTime } from "./time-format";
import type { SocketStatusResponse, SocketMonitorStatus } from "./api";

export type { SocketStatusResponse, SocketMonitorStatus };

function normalized(status: SocketMonitorStatus | null | undefined): string {
  return String(status || "unknown").toLowerCase();
}

export function socketBadgeLabel(status: Pick<SocketStatusResponse, "status"> | null | undefined): string {
  const value = normalized(status?.status);
  if (value === "up") return "Sockets Up";
  if (value === "degraded") return "Sockets Degraded";
  if (value === "down") return "Sockets Down";
  return "Sockets Unknown";
}

export function socketBadgeClass(status: Pick<SocketStatusResponse, "status"> | null | undefined): string {
  const value = normalized(status?.status);
  if (value === "up") return "socket-status-badge socket-status-badge--up";
  if (value === "degraded") return "socket-status-badge socket-status-badge--degraded";
  if (value === "down") return "socket-status-badge socket-status-badge--down";
  return "socket-status-badge socket-status-badge--unknown";
}

export function socketStatusTooltip(status: SocketStatusResponse | null | undefined): string {
  if (!status) return "Socket status unavailable";
  const lines = [socketBadgeLabel(status)];
  if (status.checked_at) lines.push(`Last checked: ${formatDateTime(status.checked_at)}`);
  const failing = status.required.filter((row) => normalized(row.status) === "down" || normalized(row.status) === "degraded");
  if (failing.length) {
    lines.push(
      `Attention: ${failing
        .map((row) => `${row.label || row.key}${row.reason ? ` (${row.reason})` : ""}`)
        .join(", ")}`
    );
  }
  return lines.join(" · ");
}

export function socketStatusTone(status: SocketMonitorStatus | null | undefined): "success" | "warning" | "danger" | "info" {
  const value = normalized(status);
  if (value === "up") return "success";
  if (value === "degraded") return "warning";
  if (value === "down") return "danger";
  return "info";
}
