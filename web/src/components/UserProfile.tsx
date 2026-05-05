"use client";

import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';

export default function UserProfile() {
  const { user, logout, isLoading } = useAuth();
  const [showProfile, setShowProfile] = useState(false);

  if (!user) {
    return null;
  }

  const handleLogout = async () => {
    try {
      await logout();
      setShowProfile(false);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setShowProfile(!showProfile)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 12px',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-primary)',
          borderRadius: '6px',
          color: 'var(--text-primary)',
          cursor: 'pointer',
          fontSize: '14px',
          transition: 'all 0.3s ease',
        }}
      >
        <div style={{
          width: '24px',
          height: '24px',
          borderRadius: '50%',
          backgroundColor: 'var(--button-primary)',
          color: 'var(--button-primary-text)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '12px',
          fontWeight: 'bold',
        }}>
          {user.username.charAt(0).toUpperCase()}
        </div>
        <span>{user.username}</span>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          ▼
        </span>
      </button>

      {showProfile && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: '0',
          marginTop: '8px',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-primary)',
          borderRadius: '6px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          minWidth: '280px',
          overflow: 'hidden',
        }}>
          <div style={{ padding: '16px' }}>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '16px', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>
                {user.username}
              </div>
              <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '2px' }}>
                {user.email || 'No email'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Role: <span style={{ textTransform: 'capitalize' }}>{user.role}</span>
              </div>
            </div>

            <div style={{ 
              borderTop: '1px solid var(--border-primary)', 
              paddingTop: '12px',
              fontSize: '12px',
              color: 'var(--text-secondary)',
              marginBottom: '16px'
            }}>
              <div style={{ marginBottom: '4px' }}>
                Member since: {new Date(user.created_at).toLocaleDateString()}
              </div>
              {user.last_login && (
                <div>
                  Last login: {new Date(user.last_login).toLocaleDateString()}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                onClick={handleLogout}
                disabled={isLoading}
                style={{
                  padding: '8px 16px',
                  backgroundColor: 'var(--method-delete-bg)',
                  color: 'var(--method-delete-text)',
                  border: '1px solid var(--method-delete-border)',
                  borderRadius: '4px',
                  fontSize: '14px',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  opacity: isLoading ? 0.7 : 1,
                  transition: 'all 0.3s ease',
                }}
              >
                {isLoading ? 'Logging out...' : 'Sign Out'}
              </button>
            </div>
          </div>

          {/* Click outside to close */}
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: -1,
            }}
            onClick={() => setShowProfile(false)}
          />
        </div>
      )}
    </div>
  );
}
