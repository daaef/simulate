"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import LoginForm from "../../../components/LoginForm";
import { useAuth } from "../../../contexts/AuthContext";

export default function LoginPageClient({ initialError }: { initialError: string }) {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/overview");
    }
  }, [isAuthenticated, isLoading, router]);

  return (
    <main style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px",
      backgroundColor: "var(--bg-primary)",
    }}>
      <div style={{ width: "100%", maxWidth: "480px" }}>
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <h1 style={{ margin: "0 0 8px", color: "var(--text-primary)", fontSize: "42px" }}>
            Fainzy Simulator
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "18px" }}>
            Operations platform access
          </p>
        </div>
        <LoginForm initialError={initialError} onSuccess={() => router.replace("/overview")} />
      </div>
    </main>
  );
}
