import Link from "next/link";
import type { ReactNode } from "react";
import { AppNav } from "../../components/AppNav";
import AuthGuard from "../../components/AuthGuard";
import UserProfile from "../../components/UserProfile";
import { ThemeToggle } from "../../components/ThemeToggle";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard redirectTo="/auth/login">
      <div
        style={{
          minHeight: "100vh",
          backgroundColor: "var(--bg-primary)",
          color: "var(--text-primary)",
        }}
      >
        <header
          style={{
            position: "sticky",
            top: 0,
            zIndex: 20,
            borderBottom: "1px solid var(--border-primary)",
            backgroundColor: "var(--bg-primary)",
          }}
        >
          <div
            className="app-header-inner"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "16px",
              padding: "16px 24px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "24px",
                flexWrap: "wrap",
              }}
            >
              <Link href="/overview" className="app-brand">
                <span className="app-brand__full">Fainzy Simulator</span>
                <span className="app-brand__short">Fainzy</span>
              </Link>

              <AppNav />
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
