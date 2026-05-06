"use client";

import { useState } from "react";
import { useAuth, LoginCredentials } from "../contexts/AuthContext";

interface LoginFormProps {
  onSuccess?: () => void;
  initialError?: string;
}

export default function LoginForm({ onSuccess, initialError = "" }: LoginFormProps) {
  const { login, sessionState } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(initialError);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    if (!event.defaultPrevented) {
      event.preventDefault();
    }

    event.stopPropagation();
    setError("");

    const cleanUsername = username.trim();

    if (!cleanUsername || !password) {
      setError("Username and password are required");
      return;
    }

    try {
      setSubmitting(true);

      const credentials: LoginCredentials = {
        username: cleanUsername,
        password,
      };

      await login(credentials);
      onSuccess?.();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel" style={{ maxWidth: "420px", margin: "0 auto", padding: "24px" }}>
      <h2 style={{ textAlign: "center", marginBottom: "12px", color: "var(--text-primary)" }}>
        Sign In
      </h2>

      <p style={{ textAlign: "center", margin: "0 0 24px", color: "var(--text-secondary)" }}>
        Admin-created accounts only.
      </p>

      {sessionState === "replaced" && !error ? (
        <div className="error-banner" style={{ marginBottom: "16px", padding: "12px" }}>
          Your last session was replaced by a newer login.
        </div>
      ) : null}

      {error ? (
        <div className="error-banner" style={{ marginBottom: "16px", padding: "12px" }}>
          {error}
        </div>
      ) : null}

      <form
        method="post"
        action="/api/v1/auth/login"
        onSubmit={handleSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "16px" }}
      >
        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "var(--text-secondary)" }}>
            Username
          </label>

          <input
            type="text"
            name="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            disabled={submitting}
            required
            autoComplete="username"
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid var(--border-primary)",
              borderRadius: "6px",
              backgroundColor: "var(--bg-secondary)",
              color: "var(--text-primary)",
              fontSize: "14px",
            }}
            placeholder="Enter your username"
          />
        </div>

        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "var(--text-secondary)" }}>
            Password
          </label>

          <input
            type="password"
            name="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            required
            autoComplete="current-password"
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid var(--border-primary)",
              borderRadius: "6px",
              backgroundColor: "var(--bg-secondary)",
              color: "var(--text-primary)",
              fontSize: "14px",
            }}
            placeholder="Enter your password"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          style={{
            padding: "12px 24px",
            backgroundColor: "var(--button-primary)",
            color: "var(--button-primary-text)",
            border: "none",
            borderRadius: "6px",
            fontSize: "16px",
            fontWeight: 600,
            cursor: submitting ? "not-allowed" : "pointer",
            opacity: submitting ? 0.7 : 1,
          }}
        >
          {submitting ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}