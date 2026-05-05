"use client";

import { createContext, useContext, ReactNode } from 'react';
import { useAuth } from './AuthContext';

export type Role = 'admin' | 'user' | 'viewer';

export interface Permission {
  resource: string;
  action: string;
}

export type RolePermissions = {
  [K in Role]: Permission[];
};

// Define role-based permissions
export const ROLE_PERMISSIONS: RolePermissions = {
  admin: [
    // User management
    { resource: 'users', action: 'create' },
    { resource: 'users', action: 'read' },
    { resource: 'users', action: 'update' },
    { resource: 'users', action: 'delete' },
    // Run management
    { resource: 'runs', action: 'create' },
    { resource: 'runs', action: 'read' },
    { resource: 'runs', action: 'update' },
    { resource: 'runs', action: 'delete' },
    { resource: 'runs', action: 'cancel' },
    // System management
    { resource: 'system', action: 'read' },
    { resource: 'system', action: 'configure' },
    // Dashboard access
    { resource: 'dashboard', action: 'read' },
  ],
  user: [
    // Run management (own runs only)
    { resource: 'runs', action: 'create' },
    { resource: 'runs', action: 'read' },
    { resource: 'runs', action: 'delete' },
    { resource: 'runs', action: 'cancel' },
    // Dashboard access (own data only)
    { resource: 'dashboard', action: 'read' },
  ],
  viewer: [
    // Read-only access
    { resource: 'runs', action: 'read' },
    { resource: 'dashboard', action: 'read' },
  ],
};

export interface RoleContextType {
  userRole: Role | null;
  hasPermission: (resource: string, action: string) => boolean;
  hasAnyPermission: (permissions: Permission[]) => boolean;
  hasAllPermissions: (permissions: Permission[]) => boolean;
  canCreateRuns: boolean;
  canManageUsers: boolean;
  canViewDashboard: boolean;
  isAdmin: boolean;
  isUser: boolean;
  isViewer: boolean;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userRole = user?.role as Role || null;

  const hasPermission = (resource: string, action: string): boolean => {
    if (!userRole) return false;
    
    const permissions = ROLE_PERMISSIONS[userRole];
    return permissions.some(
      permission => permission.resource === resource && permission.action === action
    );
  };

  const hasAnyPermission = (permissions: Permission[]): boolean => {
    if (!userRole) return false;
    
    const userPermissions = ROLE_PERMISSIONS[userRole];
    return permissions.some((permission: Permission) =>
      userPermissions.some(
        (userPermission: Permission) => 
          userPermission.resource === permission.resource && 
          userPermission.action === permission.action
      )
    );
  };

  const hasAllPermissions = (permissions: Permission[]): boolean => {
    if (!userRole) return false;
    
    const userPermissions = ROLE_PERMISSIONS[userRole];
    return permissions.every((permission: Permission) =>
      userPermissions.some(
        (userPermission: Permission) => 
          userPermission.resource === permission.resource && 
          userPermission.action === permission.action
      )
    );
  };

  const value: RoleContextType = {
    userRole,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canCreateRuns: hasPermission('runs', 'create'),
    canManageUsers: hasPermission('users', 'create'),
    canViewDashboard: hasPermission('dashboard', 'read'),
    isAdmin: userRole === 'admin',
    isUser: userRole === 'user',
    isViewer: userRole === 'viewer',
  };

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole() {
  const context = useContext(RoleContext);
  if (context === undefined) {
    throw new Error('useRole must be used within a RoleProvider');
  }
  return context;
}

// Higher-order component for role-based rendering
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
