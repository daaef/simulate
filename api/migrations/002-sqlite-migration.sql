-- Migration script for existing SQLite data
-- This script handles importing data from SQLite to PostgreSQL
-- Run this after the initial schema is created

-- Note: This migration assumes you'll export SQLite data externally
-- and import it using the Python migration script

-- Create a temporary staging table for SQLite data
CREATE TEMPORARY TABLE sqlite_runs_import (
    id INTEGER,
    flow VARCHAR(50),
    plan VARCHAR(255),
    timing VARCHAR(20),
    mode VARCHAR(20),
    store_id VARCHAR(50),
    phone VARCHAR(20),
    all_users BOOLEAN,
    no_auto_provision BOOLEAN,
    enforce_websocket_gates BOOLEAN,
    post_order_actions BOOLEAN,
    extra_args JSONB,
    status VARCHAR(20),
    command TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    exit_code INTEGER,
    log_path TEXT,
    report_path TEXT,
    story_path TEXT,
    events_path TEXT,
    error TEXT
);

-- Function to safely insert SQLite data
CREATE OR REPLACE FUNCTION import_sqlite_run(
    p_id INTEGER,
    p_flow VARCHAR(50),
    p_plan VARCHAR(255),
    p_timing VARCHAR(20),
    p_mode VARCHAR(20),
    p_store_id VARCHAR(50),
    p_phone VARCHAR(20),
    p_all_users BOOLEAN,
    p_no_auto_provision BOOLEAN,
    p_enforce_websocket_gates BOOLEAN,
    p_post_order_actions BOOLEAN,
    p_extra_args JSONB,
    p_status VARCHAR(20),
    p_command TEXT,
    p_created_at TIMESTAMP WITH TIME ZONE,
    p_started_at TIMESTAMP WITH TIME ZONE,
    p_finished_at TIMESTAMP WITH TIME ZONE,
    p_exit_code INTEGER,
    p_log_path TEXT,
    p_report_path TEXT,
    p_story_path TEXT,
    p_events_path TEXT,
    p_error TEXT
) RETURNS VOID AS $$
BEGIN
    INSERT INTO runs (
        id, flow, plan, timing, mode, store_id, phone, all_users, no_auto_provision, enforce_websocket_gates,
        post_order_actions, extra_args, status, command, created_at, started_at,
        finished_at, exit_code, log_path, report_path, story_path, events_path, error
    ) VALUES (
        p_id, p_flow, p_plan, p_timing, p_mode, p_store_id, p_phone, p_all_users,
        p_no_auto_provision, p_enforce_websocket_gates, p_post_order_actions, p_extra_args, p_status, p_command,
        p_created_at, p_started_at, p_finished_at, p_exit_code, p_log_path,
        p_report_path, p_story_path, p_events_path, p_error
    ) ON CONFLICT (id) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- Create sequence for runs ID to continue from existing SQLite data
-- This will be set dynamically based on the max ID from SQLite

COMMENT ON TABLE users IS 'User accounts for authentication and authorization';
COMMENT ON TABLE user_sessions IS 'Refresh tokens for user sessions';
COMMENT ON TABLE runs IS 'Simulator run records with user association';
COMMENT ON COLUMN runs.user_id IS 'Optional user ID - NULL for migrated runs';
COMMENT ON COLUMN runs.search_vector IS 'Full-text search index for runs';
COMMENT ON COLUMN runs.duration_ms IS 'Auto-calculated duration in milliseconds';

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_runs_user_status ON runs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_created_status ON runs(created_at DESC, status);
CREATE INDEX IF NOT EXISTS idx_runs_flow_status ON runs(flow, status);

-- Create function to clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions 
    WHERE expires_at < NOW()
    RETURNING 1 INTO deleted_count;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create function to get user statistics
CREATE OR REPLACE FUNCTION get_user_statistics(p_user_id INTEGER)
RETURNS TABLE(
    total_runs BIGINT,
    succeeded_runs BIGINT,
    failed_runs BIGINT,
    success_rate NUMERIC,
    avg_duration_ms NUMERIC,
    last_run_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*) as total_runs,
        COUNT(*) FILTER (WHERE status = 'succeeded') as succeeded_runs,
        COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
        ROUND(
            (COUNT(*) FILTER (WHERE status = 'succeeded') * 100.0 / NULLIF(COUNT(*), 0)), 2
        ) as success_rate,
        AVG(duration_ms) as avg_duration_ms,
        MAX(created_at) as last_run_at
    FROM runs 
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update search vector
CREATE OR REPLACE FUNCTION update_run_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.flow, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.plan, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.store_id, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.phone, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_runs_search_vector_trigger
    BEFORE INSERT OR UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION update_run_search_vector();

-- Create view for recent runs with user info
CREATE OR REPLACE VIEW recent_runs_with_users AS
SELECT 
    r.id,
    r.flow,
    r.plan,
    r.timing,
    r.status,
    r.created_at,
    r.started_at,
    r.finished_at,
    r.exit_code,
    r.store_id,
    r.phone,
    u.username,
    u.email,
    CASE 
        WHEN u.id IS NOT NULL THEN u.username
        ELSE 'System'
    END as runner
FROM runs r
LEFT JOIN users u ON r.user_id = u.id
ORDER BY r.created_at DESC;

-- Create function to search runs
CREATE OR REPLACE FUNCTION search_runs(p_query TEXT, p_user_id INTEGER DEFAULT NULL)
RETURNS TABLE(
    id INTEGER,
    flow VARCHAR(50),
    plan VARCHAR(255),
    status VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE,
    username VARCHAR(50),
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.flow,
        r.plan,
        r.status,
        r.created_at,
        u.username,
        ts_rank(r.search_vector, plainto_tsquery('english', p_query)) as rank
    FROM runs r
    LEFT JOIN users u ON r.user_id = u.id
    WHERE 
        r.search_vector @@ plainto_tsquery('english', p_query)
        AND (p_user_id IS NULL OR r.user_id = p_user_id)
    ORDER BY rank DESC, r.created_at DESC;
END;
$$ LANGUAGE plpgsql;
