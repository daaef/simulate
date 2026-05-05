"use client";

import { ReactNode } from 'react';
import { useRole, Permission } from '../contexts/RoleContext';

interface RoleBasedComponentProps {
  children: ReactNode;
  requiredPermissions: Permission[];
  fallback?: ReactNode;
  requireAll?: boolean; // If true, requires all permissions; if false, requires any
}

export default function RoleBasedComponent({ 
  children, 
  requiredPermissions, 
  fallback = null,
  requireAll = true 
}: RoleBasedComponentProps) {
  const { hasAllPermissions, hasAnyPermission } = useRole();

  const hasRequiredPermissions = requireAll 
    ? hasAllPermissions(requiredPermissions)
    : hasAnyPermission(requiredPermissions);

  if (!hasRequiredPermissions) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

// Convenience components for common role checks
export function AdminOnly({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { isAdmin } = useRole();
  
  if (!isAdmin) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
}

export function UserOnly({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { isUser } = useRole();
  
  if (!isUser) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
}

export function CanCreateRuns({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { canCreateRuns } = useRole();
  
  if (!canCreateRuns) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
}

export function CanManageUsers({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { canManageUsers } = useRole();
  
  if (!canManageUsers) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
}

export function CanViewDashboard({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { canViewDashboard } = useRole();
  
  if (!canViewDashboard) {
    return <>{fallback}</>;
  }
  
  return <>{children}</>;
}
