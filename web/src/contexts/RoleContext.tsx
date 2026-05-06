"use client";

import { createContext, useContext, ReactNode } from "react";
import { useAuth } from "./AuthContext";

export type Role = "admin" | "operator" | "runner" | "viewer" | "auditor";

export interface Permission {
  resource: string;
  action: string;
}

export type RolePermissions = {
  [K in Role]: Permission[];
};

const LEGACY_ROLE_ALIASES: Record<string, Role> = {
  user: "operator",
};

function normalizeRole(role: string | null | undefined): Role | null {
  if (!role) return null;

  const normalized = role.trim().toLowerCase();
  return (LEGACY_ROLE_ALIASES[normalized] || normalized) as Role;
}

export const ROLE_PERMISSIONS: RolePermissions = {
  admin: [
    { resource: "users", action: "create" },
    { resource: "users", action: "read" },
    { resource: "users", action: "update" },
    { resource: "users", action: "delete" },
    { resource: "users", action: "reset_password" },

    { resource: "runs", action: "create" },
    { resource: "runs", action: "read" },
    { resource: "runs", action: "update" },
    { resource: "runs", action: "cancel" },
    { resource: "runs", action: "delete" },

    { resource: "dashboard", action: "read" },

    { resource: "archives", action: "read" },
    { resource: "archives", action: "delete" },

    { resource: "retention", action: "read" },
    { resource: "retention", action: "update" },

    { resource: "system", action: "read" },
    { resource: "system", action: "configure" },
  ],

  operator: [
    { resource: "runs", action: "create" },
    { resource: "runs", action: "read" },
    { resource: "runs", action: "cancel" },

    { resource: "dashboard", action: "read" },

    { resource: "archives", action: "read" },
    { resource: "retention", action: "read" },
  ],

  runner: [
    { resource: "runs", action: "create" },
    { resource: "runs", action: "read" },

    { resource: "dashboard", action: "read" },
  ],

  viewer: [
    { resource: "runs", action: "read" },

    { resource: "dashboard", action: "read" },
    { resource: "archives", action: "read" },
  ],

  auditor: [
    { resource: "runs", action: "read" },

    { resource: "dashboard", action: "read" },
    { resource: "archives", action: "read" },
    { resource: "retention", action: "read" },
  ],
};

export interface RoleContextType {
  userRole: Role | null;
  hasPermission: (resource: string, action: string) => boolean;
  hasAnyPermission: (permissions: Permission[]) => boolean;
  hasAllPermissions: (permissions: Permission[]) => boolean;

  canCreateRuns: boolean;
  canCancelRuns: boolean;
  canDeleteRuns: boolean;
  canManageUsers: boolean;
  canViewDashboard: boolean;
  canViewArchives: boolean;
  canManageRetention: boolean;

  isAdmin: boolean;
  isOperator: boolean;
  isRunner: boolean;
  isAuditor: boolean;
  isViewer: boolean;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userRole = normalizeRole(user?.role);

  const hasPermission = (resource: string, action: string): boolean => {
    if (!userRole) return false;

    const permissions = ROLE_PERMISSIONS[userRole] || [];
    return permissions.some(
      (permission) => permission.resource === resource && permission.action === action
    );
  };

  const hasAnyPermission = (permissions: Permission[]): boolean => {
    if (!userRole) return false;

    return permissions.some((permission) =>
      hasPermission(permission.resource, permission.action)
    );
  };

  const hasAllPermissions = (permissions: Permission[]): boolean => {
    if (!userRole) return false;

    return permissions.every((permission) =>
      hasPermission(permission.resource, permission.action)
    );
  };

  const value: RoleContextType = {
    userRole,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,

    canCreateRuns: hasPermission("runs", "create"),
    canCancelRuns: hasPermission("runs", "cancel"),
    canDeleteRuns: hasPermission("runs", "delete"),
    canManageUsers: hasPermission("users", "create"),
    canViewDashboard: hasPermission("dashboard", "read"),
    canViewArchives: hasPermission("archives", "read"),
    canManageRetention: hasPermission("retention", "update"),

    isAdmin: userRole === "admin",
    isOperator: userRole === "operator",
    isRunner: userRole === "runner",
    isAuditor: userRole === "auditor",
    isViewer: userRole === "viewer",
  };

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole() {
  const context = useContext(RoleContext);

  if (context === undefined) {
    throw new Error("useRole must be used within a RoleProvider");
  }

  return context;
}

export function withRoleCheck<P extends object>(
  Component: React.ComponentType<P>,
  requiredPermissions: Permission[]
) {
  return function RoleCheckedComponent(props: P) {
    const { hasAllPermissions } = useRole();

    if (!hasAllPermissions(requiredPermissions)) {
      return null;
    }

    return <Component {...props} />;
  };
}