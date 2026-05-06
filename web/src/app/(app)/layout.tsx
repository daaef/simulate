import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import AuthGuard from "../../components/AuthGuard";
import UserProfile from "../../components/UserProfile";
import { ThemeToggle } from "../../components/ThemeToggle";

const navItems = [
  { href: "/overview", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/schedules", label: "Schedules" },
  { href: "/archives", label: "Archives" },
  { href: "/retention", label: "Retention" },
  { href: "/admin/users", label: "Admin" },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const hasSessionCookieHint = cookies().has("simulator_session");
  return (
    <AuthGuard hasSessionCookieHint={hasSessionCookieHint} redirectTo="/auth/login">
      <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
        <header style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          borderBottom: "1px solid var(--border-primary)",
          backgroundColor: "var(--bg-primary)",
        }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
            padding: "16px 24px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "24px", flexWrap: "wrap" }}>
              <Link href="/overview" style={{
                color: "var(--text-primary)",
                textDecoration: "none",
                fontSize: "24px",
                fontWeight: 700,
              }}>
                Fainzy Simulator
              </Link>
              <nav style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}>
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      color: "var(--text-secondary)",
                      textDecoration: "none",
                      fontSize: "14px",
                      fontWeight: 600,
                    }}
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <ThemeToggle />
              <UserProfile />
            </div>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </AuthGuard>
  );
}
