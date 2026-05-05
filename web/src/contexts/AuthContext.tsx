"use client";

import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";

export interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
  created_at: string;
  last_login?: string;
  preferences: Record<string, any>;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  username: string;
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (userData: RegisterData) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const ACCESS_TOKEN_KEY = "simulator_access_token";
const REFRESH_TOKEN_KEY = "simulator_refresh_token";
const USER_KEY = "simulator_user";

function parseJWT(token: string) {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;

    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => `%${`00${c.charCodeAt(0).toString(16)}`.slice(-2)}`)
        .join("")
    );

    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

function isTokenExpired(payload: any) {
  if (!payload?.exp) return false;
  return Date.now() >= payload.exp * 1000;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const setTokens = (tokenResponse: TokenResponse, userData: User) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokenResponse.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokenResponse.refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify(userData));
    setUser(userData);
  };

  const clearTokens = () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setUser(null);
  };

  const refreshToken = async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);

    if (!storedRefreshToken) {
      clearTokens();
      return;
    }

    const response = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: storedRefreshToken }),
    });

    if (!response.ok) {
      clearTokens();
      return;
    }

    const tokenResponse: TokenResponse = await response.json();

    const userResponse = await fetch("/api/v1/auth/me", {
      headers: {
        Authorization: `Bearer ${tokenResponse.access_token}`,
      },
    });

    if (!userResponse.ok) {
      clearTokens();
      return;
    }

    const userData: User = await userResponse.json();
    setTokens(tokenResponse, userData);
  };

  useEffect(() => {
    const initAuth = async () => {
      try {
        const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
        const userData = localStorage.getItem(USER_KEY);

        if (!accessToken || !userData) {
          clearTokens();
          return;
        }

        const tokenPayload = parseJWT(accessToken);

        if (tokenPayload && isTokenExpired(tokenPayload)) {
          await refreshToken();
          return;
        }

        const parsedUser = JSON.parse(userData);
        setUser(parsedUser);
      } catch (error) {
        console.error("Auth bootstrap failed:", error);
        clearTokens();
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    setIsLoading(true);

    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail || "Login failed");
      }

      const tokenResponse: TokenResponse = await response.json();

      const userResponse = await fetch("/api/v1/auth/me", {
        headers: {
          Authorization: `Bearer ${tokenResponse.access_token}`,
        },
      });

      if (!userResponse.ok) {
        throw new Error("Failed to load user profile");
      }

      const userData: User = await userResponse.json();
      setTokens(tokenResponse, userData);
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (userData: RegisterData) => {
    setIsLoading(true);

    try {
      const response = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(userData),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail || "Registration failed");
      }

      await login({
        username: userData.username,
        password: userData.password,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);

    if (storedRefreshToken) {
      try {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ refresh_token: storedRefreshToken }),
        });
      } catch (error) {
        console.error("Logout error:", error);
      }
    }

    clearTokens();
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
    refreshToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}