"use client";

import { useState } from 'react';
import { useAuth, LoginCredentials, RegisterData } from '../contexts/AuthContext';

interface LoginFormProps {
  onClose?: () => void;
}

export default function LoginForm({ onClose }: LoginFormProps) {
  const { login, register, isLoading } = useAuth();
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError('');
    setSuccess('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (isRegisterMode) {
      // Validate registration form
      if (!formData.username || !formData.email || !formData.password) {
        setError('All fields are required');
        return;
      }

      if (formData.password !== formData.confirmPassword) {
        setError('Passwords do not match');
        return;
      }

      if (formData.password.length < 6) {
        setError('Password must be at least 6 characters long');
        return;
      }

      try {
        const registerData: RegisterData = {
          username: formData.username,
          email: formData.email,
          password: formData.password,
        };
        await register(registerData);
        setSuccess('Registration successful! You are now logged in.');
        if (onClose) setTimeout(onClose, 1500);
      } catch (error: any) {
        setError(error.message || 'Registration failed');
      }
    } else {
      // Validate login form
      if (!formData.username || !formData.password) {
        setError('Username and password are required');
        return;
      }

      try {
        const credentials: LoginCredentials = {
          username: formData.username,
          password: formData.password,
        };
        await login(credentials);
        setSuccess('Login successful!');
        if (onClose) setTimeout(onClose, 1000);
      } catch (error: any) {
        setError(error.message || 'Login failed');
      }
    }
  };

  const toggleMode = () => {
    setIsRegisterMode(!isRegisterMode);
    setError('');
    setSuccess('');
    setFormData({
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    });
  };

  return (
    <div className="panel" style={{ maxWidth: '400px', margin: '0 auto', padding: '24px' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '24px', color: 'var(--text-primary)' }}>
        {isRegisterMode ? 'Create Account' : 'Sign In'}
      </h2>
      
      {error && (
        <div className="error-banner" style={{ marginBottom: '16px', padding: '12px' }}>
          {error}
        </div>
      )}
      
      {success && (
        <div style={{ 
          backgroundColor: 'var(--method-get-bg)', 
          color: 'var(--method-get-text)', 
          padding: '12px', 
          borderRadius: '6px', 
          marginBottom: '16px',
          textAlign: 'center'
        }}>
          {success}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '4px', color: 'var(--text-secondary)' }}>
            Username
          </label>
          <input
            type="text"
            name="username"
            value={formData.username}
            onChange={handleInputChange}
            disabled={isLoading}
            required
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid var(--border-primary)',
              borderRadius: '4px',
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              fontSize: '14px',
            }}
            placeholder="Enter your username"
          />
        </div>

        {isRegisterMode && (
          <div>
            <label style={{ display: 'block', marginBottom: '4px', color: 'var(--text-secondary)' }}>
              Email
            </label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleInputChange}
              disabled={isLoading}
              required
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid var(--border-primary)',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                fontSize: '14px',
              }}
              placeholder="Enter your email"
            />
          </div>
        )}

        <div>
          <label style={{ display: 'block', marginBottom: '4px', color: 'var(--text-secondary)' }}>
            Password
          </label>
          <input
            type="password"
            name="password"
            value={formData.password}
            onChange={handleInputChange}
            disabled={isLoading}
            required
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid var(--border-primary)',
              borderRadius: '4px',
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              fontSize: '14px',
            }}
            placeholder="Enter your password"
          />
        </div>

        {isRegisterMode && (
          <div>
            <label style={{ display: 'block', marginBottom: '4px', color: 'var(--text-secondary)' }}>
              Confirm Password
            </label>
            <input
              type="password"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleInputChange}
              disabled={isLoading}
              required
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid var(--border-primary)',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                fontSize: '14px',
              }}
              placeholder="Confirm your password"
            />
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading}
          style={{
            padding: '12px 24px',
            backgroundColor: 'var(--button-primary)',
            color: 'var(--button-primary-text)',
            border: 'none',
            borderRadius: '4px',
            fontSize: '16px',
            fontWeight: '600',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            opacity: isLoading ? 0.7 : 1,
            transition: 'all 0.3s ease',
          }}
        >
          {isLoading ? 'Processing...' : (isRegisterMode ? 'Create Account' : 'Sign In')}
        </button>
      </form>

      <div style={{ textAlign: 'center', marginTop: '20px' }}>
        <span style={{ color: 'var(--text-secondary)' }}>
          {isRegisterMode ? 'Already have an account?' : "Don't have an account?"}
        </span>
        <button
          type="button"
          onClick={toggleMode}
          disabled={isLoading}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--button-primary)',
            cursor: 'pointer',
            textDecoration: 'underline',
            marginLeft: '4px',
            fontSize: '14px',
          }}
        >
          {isRegisterMode ? 'Sign In' : 'Create Account'}
        </button>
      </div>

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          disabled={isLoading}
          style={{
            position: 'absolute',
            top: '12px',
            right: '12px',
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '18px',
            padding: '4px',
          }}
        >
          ×
        </button>
      )}
    </div>
  );
}
