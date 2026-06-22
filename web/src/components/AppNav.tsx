"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchDashboardSummary, fetchSocketStatus, type SocketStatusResponse } from "../lib/api";
import { socketBadgeClass, socketBadgeLabel, socketStatusTooltip } from "../lib/socket-status";

const navItems = [
  { href: "/overview", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/orders", label: "Orders" },
  { href: "/config", label: "Config" },
  { href: "/schedules", label: "Schedules" },
  { href: "/archives", label: "Archives" },
  { href: "/admin/users", label: "Admin", title: "Users & system settings" },
];

function isActivePath(pathname: string, href: string): boolean {
  if (href === "/overview") return pathname === href || pathname === "/";
  if (href === "/admin/users") return pathname.startsWith("/admin");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppNav() {
  const pathname = usePathname() || "/overview";
  const [activeRunCount, setActiveRunCount] = useState(0);
  const [socketStatus, setSocketStatus] = useState<SocketStatusResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetchDashboardSummary()
        .then((summary) => {
          if (!cancelled) {
            setActiveRunCount(summary.active_runs ?? 0);
          }
        })
        .catch(() => {
          if (!cancelled) setActiveRunCount(0);
        });
    };

    refresh();
    const timer = window.setInterval(refresh, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetchSocketStatus()
        .then((payload) => {
          if (!cancelled) setSocketStatus(payload);
        })
        .catch(() => {
          if (!cancelled) setSocketStatus(null);
        });
    };

    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <nav className="app-nav" aria-label="Primary navigation">
      {navItems.map((item) => {
        const active = isActivePath(pathname, item.href);
        const showLiveBadge = item.href === "/runs" && activeRunCount > 0;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`app-nav-link${active ? " active" : ""}`}
            aria-current={active ? "page" : undefined}
            title={item.title}
          >
            <span className="app-nav-link__label">{item.label}</span>
            {showLiveBadge ? (
              <span
                className="app-nav-live-badge"
                aria-label={`${activeRunCount} active run${activeRunCount === 1 ? "" : "s"}`}
                title={`${activeRunCount} active run${activeRunCount === 1 ? "" : "s"}`}
              />
            ) : null}
          </Link>
        );
      })}
      <Link
        href="/overview#socket-service"
        className={socketBadgeClass(socketStatus)}
        title={socketStatusTooltip(socketStatus)}
        aria-label={socketBadgeLabel(socketStatus)}
      >
        {socketBadgeLabel(socketStatus)}
      </Link>
    </nav>
  );
}
