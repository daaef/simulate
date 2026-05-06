"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";

export interface User {
  id: number;
  username: string;
  email?: string | null;
  role: string;
  created_at: string;
  last_login?: string | null;
  preferences: Record<string, unknown>;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export type SessionState = "loading" | "authenticated" | "anonymous" | "replaced";

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  sessionState: SessionState;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function isSessionReplaced(detail: string | null): boolean {
  if (!detail) return false;
  return detail.toLowerCase().includes("no longer active");
}

async function parseError(response: Response): Promise<Error> {
  try {
    const payload = await response.json();
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : typeof payload?.message === "string"
          ? payload.message
          : "Request failed";

    return new Error(detail);
  } catch {
    return new Error("Request failed");
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionState, setSessionState] = useState<SessionState>("loading");

  const setAnonymous = useCallback((state: SessionState = "anonymous") => {
    setUser(null);
    setSessionState(state);
  }, []);

  const setAuthenticatedUser = useCallback((nextUser: User) => {
    setUser(nextUser);
    setSessionState("authenticated");
  }, []);

  const refreshSession = useCallback(async () => {
    setIsLoading(true);

    try {
      const response = await fetch("/api/v1/auth/session", {
        credentials: "include",
        cache: "no-store",
      });

      if (response.status === 401) {
        const payload = await response.json().catch(() => null);
        const detail = typeof payload?.detail === "string" ? payload.detail : null;

        setAnonymous(isSessionReplaced(detail) ? "replaced" : "anonymous");
        return;
      }

      if (!response.ok) {
        throw await parseError(response);
      }

      const currentUser = (await response.json()) as User;
      setAuthenticatedUser(currentUser);
    } catch (error) {
      console.error("Failed to refresh auth session:", error);
      setAnonymous("anonymous");
    } finally {
      setIsLoading(false);
    }
  }, [setAnonymous, setAuthenticatedUser]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      setIsLoading(true);

      try {
        const response = await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify(credentials),
        });

        if (!response.ok) {
          throw await parseError(response);
        }

        const payload = await response.json();

        if (!payload?.user) {
          throw new Error("Login succeeded but no user profile was returned");
        }

        setAuthenticatedUser(payload.user as User);
      } catch (error) {
        setAnonymous("anonymous");
        throw error;
      } finally {
        setIsLoading(false);
      }
    },
    [setAnonymous, setAuthenticatedUser],
  );

  const logout = useCallback(async () => {
    setIsLoading(true);

    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      setAnonymous("anonymous");
      setIsLoading(false);
    }
  }, [setAnonymous]);

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      isLoading,
      isAuthenticated: sessionState === "authenticated" && !!user,
      sessionState,
      login,
      logout,
      refreshSession,
    }),
    [isLoading, login, logout, refreshSession, sessionState, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}