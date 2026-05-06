"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../contexts/AuthContext";

interface AuthGuardProps {
  children: ReactNode;
  redirectTo?: string;
}

const AUTH_GUARD_FAILSAFE_MS = 7000;

export default function AuthGuard({
  children,
  redirectTo = "/auth/login",
}: AuthGuardProps) {
  const router = useRouter();
  const { isAuthenticated, isLoading, refreshSession, sessionState } = useAuth();
  const [bootstrapExpired, setBootstrapExpired] = useState(false);
  const refreshStartedRef = useRef(false);

  useEffect(() => {
    if (refreshStartedRef.current) return;

    refreshStartedRef.current = true;
    void refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    if (!isLoading) {
      setBootstrapExpired(false);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setBootstrapExpired(true);
    }, AUTH_GUARD_FAILSAFE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace(redirectTo);
    }
  }, [isAuthenticated, isLoading, redirectTo, router]);

  if (isLoading && !bootstrapExpired) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "var(--bg-primary)",
          color: "var(--text-primary)",
        }}
      >
        Loading...
      </div>
    );
  }

  if (isLoading && bootstrapExpired) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "var(--bg-primary)",
          color: "var(--text-primary)",
          flexDirection: "column",
          gap: "12px",
          padding: "24px",
          textAlign: "center",
        }}
      >
        <strong>Session check is taking too long.</strong>
        <span style={{ color: "var(--text-secondary)" }}>
          Refresh the page. If this repeats, sign out and sign in again.
        </span>
        <button
          type="button"
          onClick={() => {
            void refreshSession();
            setBootstrapExpired(false);
          }}
          style={{
            padding: "10px 16px",
            borderRadius: "6px",
            border: "1px solid var(--border-primary)",
            backgroundColor: "var(--button-primary)",
            color: "var(--button-primary-text)",
            cursor: "pointer",
          }}
        >
          Retry session check
        </button>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "var(--bg-primary)",
          color: "var(--text-primary)",
        }}
      >
        {sessionState === "replaced" ? "Session replaced. Redirecting..." : "Redirecting..."}
      </div>
    );
  }

  return <>{children}</>;
}