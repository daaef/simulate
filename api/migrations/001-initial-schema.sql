-- Initial database schema for Fainzy Simulator
-- This script creates the enhanced schema with user support

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- User sessions table for refresh tokens
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_agent TEXT,
    ip_address INET
);

-- Enhanced runs table with user association
CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    flow VARCHAR(50) NOT NULL,
    plan VARCHAR(255) NOT NULL,
    timing VARCHAR(20) NOT NULL CHECK (timing IN ('fast', 'realistic')),
    mode VARCHAR(20) CHECK (mode IN ('trace', 'load')),
    store_id VARCHAR(50),
    phone VARCHAR(20),
    all_users BOOLEAN NOT NULL DEFAULT FALSE,
    no_auto_provision BOOLEAN NOT NULL DEFAULT FALSE,
    enforce_websocket_gates BOOLEAN NOT NULL DEFAULT FALSE,
    post_order_actions BOOLEAN,
    extra_args JSONB DEFAULT '[]',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'queued', 'running', 'cancelling', 'succeeded', 'failed', 'cancelled')),
    command TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    exit_code INTEGER,
    log_path TEXT,
    report_path TEXT,
    story_path TEXT,
    events_path TEXT,
    error TEXT,
    -- Metadata for better querying
    duration_ms INTEGER GENERATED ALWAYS AS (
        CASE 
            WHEN finished_at IS NOT NULL AND started_at IS NOT NULL 
            THEN EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000 
            ELSE NULL 
        END
    ) STORED,
    -- Full-text search fields
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(flow, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(plan, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(store_id, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(phone, '')), 'C')
    ) STORED
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_flow ON runs(flow);
CREATE INDEX IF NOT EXISTS idx_runs_search_vector ON runs USING GIN(search_vector);

-- Create indexes for user sessions
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);

-- Create indexes for users
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update timestamps
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_runs_updated_at 
    BEFORE UPDATE ON runs 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default admin user (password: admin123)
-- This should be changed in production
INSERT INTO users (username, email, password_hash, role) 
VALUES (
    'admin', 
    'admin@simulator.local', 
    '$2b$12$MlaNrujpG.T6AJGHXi6kC.w.lB4tJdrrdiYl5WTk1CzzQKuE3x66C', -- bcrypt hash of "admin123"
    'admin'
) ON CONFLICT (username) DO NOTHING;

-- Create view for run statistics
CREATE OR REPLACE VIEW run_statistics AS
SELECT 
    COUNT(*) as total_runs,
    COUNT(*) FILTER (WHERE status = 'succeeded') as succeeded_runs,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
    COUNT(*) FILTER (WHERE status = 'running') as running_runs,
    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled_runs,
    ROUND(
        (COUNT(*) FILTER (WHERE status = 'succeeded') * 100.0 / NULLIF(COUNT(*), 0)), 2
    ) as success_rate,
    AVG(duration_ms) as avg_duration_ms,
    MIN(created_at) as first_run_at,
    MAX(created_at) as last_run_at
FROM runs;

-- Create view for user run statistics
CREATE OR REPLACE VIEW user_run_statistics AS
SELECT 
    u.id as user_id,
    u.username,
    u.email,
    COUNT(r.id) as total_runs,
    COUNT(r.id) FILTER (WHERE r.status = 'succeeded') as succeeded_runs,
    COUNT(r.id) FILTER (WHERE r.status = 'failed') as failed_runs,
    ROUND(
        (COUNT(r.id) FILTER (WHERE r.status = 'succeeded') * 100.0 / NULLIF(COUNT(r.id), 0)), 2
    ) as success_rate,
    MAX(r.created_at) as last_run_at
FROM users u
LEFT JOIN runs r ON u.id = r.user_id
GROUP BY u.id, u.username, u.email;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO simulator;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO simulator;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO simulator;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO simulator;
