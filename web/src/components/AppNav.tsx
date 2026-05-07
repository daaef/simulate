"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/overview", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/config", label: "Config" },
  { href: "/schedules", label: "Schedules" },
  { href: "/archives", label: "Archives" },
  { href: "/retention", label: "Retention" },
  { href: "/admin/users", label: "Admin" },
];

function isActivePath(pathname: string, href: string): boolean {
  if (href === "/overview") return pathname === href || pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppNav() {
  const pathname = usePathname() || "/overview";

  return (
    <nav className="app-nav" aria-label="Primary navigation">
      {navItems.map((item) => {
        const active = isActivePath(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`app-nav-link${active ? " active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
