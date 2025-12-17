-- Real-time AI Backend Database Schema for Supabase
-- Execute these commands in your Supabase SQL Editor

-- ============================================
-- Sessions Table
-- ============================================
-- Stores high-level session metadata
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER,
    summary TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes for common queries
    CONSTRAINT sessions_session_id_key UNIQUE (session_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);

-- Add comment to table
COMMENT ON TABLE sessions IS 'Stores high-level metadata for each conversation session';
COMMENT ON COLUMN sessions.session_id IS 'Unique identifier for the session';
COMMENT ON COLUMN sessions.user_id IS 'Identifier for the user';
COMMENT ON COLUMN sessions.duration_seconds IS 'Total session duration in seconds';
COMMENT ON COLUMN sessions.summary IS 'AI-generated summary of the session';
COMMENT ON COLUMN sessions.status IS 'Session status: active, completed, summarized';

-- ============================================
-- Session Events Table
-- ============================================
-- Stores granular, chronological log of all session events
CREATE TABLE IF NOT EXISTS session_events (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Foreign key relationship
    CONSTRAINT fk_session
        FOREIGN KEY (session_id)
        REFERENCES sessions(session_id)
        ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_session_events_session_id ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_session_events_event_type ON session_events(event_type);
CREATE INDEX IF NOT EXISTS idx_session_events_timestamp ON session_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_session_events_data ON session_events USING GIN (data);

-- Add comments
COMMENT ON TABLE session_events IS 'Chronological log of all events during a session';
COMMENT ON COLUMN session_events.event_type IS 'Type of event: user_message, assistant_response, function_call, etc.';
COMMENT ON COLUMN session_events.data IS 'Event payload data stored as JSON';
COMMENT ON COLUMN session_events.metadata IS 'Additional metadata for the event';

-- ============================================
-- Updated At Trigger
-- ============================================
-- Automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Useful Views
-- ============================================

-- View: Active sessions with event counts
CREATE OR REPLACE VIEW active_sessions_with_stats AS
SELECT 
    s.session_id,
    s.user_id,
    s.start_time,
    s.status,
    COUNT(se.id) as total_events,
    COUNT(CASE WHEN se.event_type = 'user_message' THEN 1 END) as user_messages,
    COUNT(CASE WHEN se.event_type = 'assistant_response' THEN 1 END) as assistant_responses,
    COUNT(CASE WHEN se.event_type = 'function_call' THEN 1 END) as function_calls
FROM sessions s
LEFT JOIN session_events se ON s.session_id = se.session_id
WHERE s.status = 'active'
GROUP BY s.session_id, s.user_id, s.start_time, s.status;

-- View: Recent sessions summary
CREATE OR REPLACE VIEW recent_sessions_summary AS
SELECT 
    s.session_id,
    s.user_id,
    s.start_time,
    s.end_time,
    s.duration_seconds,
    s.status,
    s.summary,
    COUNT(se.id) as total_events
FROM sessions s
LEFT JOIN session_events se ON s.session_id = se.session_id
GROUP BY s.session_id, s.user_id, s.start_time, s.end_time, s.duration_seconds, s.status, s.summary
ORDER BY s.start_time DESC
LIMIT 50;

-- ============================================
-- Row Level Security (RLS) - Optional
-- ============================================
-- Enable RLS if you want user-level access control
-- Uncomment these lines if needed

-- ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE session_events ENABLE ROW LEVEL SECURITY;

-- Example policy: Users can only see their own sessions
-- CREATE POLICY "Users can view own sessions" ON sessions
--     FOR SELECT
--     USING (auth.uid()::text = user_id);

-- CREATE POLICY "Users can view own session events" ON session_events
--     FOR SELECT
--     USING (
--         session_id IN (
--             SELECT session_id FROM sessions WHERE user_id = auth.uid()::text
--         )
--     );

-- ============================================
-- Sample Queries for Testing
-- ============================================

-- Get all sessions for a user
-- SELECT * FROM sessions WHERE user_id = 'user_123' ORDER BY start_time DESC;

-- Get conversation history for a session
-- SELECT event_type, timestamp, data->>'content' as content
-- FROM session_events
-- WHERE session_id = 'session_xxx'
--   AND event_type IN ('user_message', 'assistant_response')
-- ORDER BY timestamp;

-- Get session statistics
-- SELECT 
--     session_id,
--     COUNT(*) as total_events,
--     COUNT(CASE WHEN event_type = 'function_call' THEN 1 END) as function_calls
-- FROM session_events
-- WHERE session_id = 'session_xxx'
-- GROUP BY session_id;

-- ============================================
-- Indexes for Analytics (Optional)
-- ============================================

-- Index for analyzing event patterns
CREATE INDEX IF NOT EXISTS idx_session_events_type_timestamp 
    ON session_events(event_type, timestamp);

-- Index for user activity analysis
CREATE INDEX IF NOT EXISTS idx_sessions_user_start 
    ON sessions(user_id, start_time DESC);

-- ============================================
-- Cleanup Functions (Optional)
-- ============================================

-- Function to delete old sessions (useful for data retention)
CREATE OR REPLACE FUNCTION cleanup_old_sessions(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM sessions
    WHERE end_time < NOW() - INTERVAL '1 day' * days_old
    RETURNING COUNT(*) INTO deleted_count;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Usage: SELECT cleanup_old_sessions(30); -- Delete sessions older than 30 days

-- ============================================
-- Performance Monitoring
-- ============================================

-- View to monitor table sizes
CREATE OR REPLACE VIEW table_sizes AS
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================
-- Verification Queries
-- ============================================

-- Verify tables were created
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Verify indexes
-- SELECT indexname FROM pg_indexes WHERE schemaname = 'public';

-- Check table comments
-- SELECT 
--     c.table_name, 
--     c.column_name, 
--     pgd.description
-- FROM pg_catalog.pg_statio_all_tables AS st
-- INNER JOIN pg_catalog.pg_description pgd ON (pgd.objoid = st.relid)
-- INNER JOIN information_schema.columns c ON (
--     pgd.objsubid = c.ordinal_position AND
--     c.table_schema = st.schemaname AND
--     c.table_name = st.relname
-- )
-- WHERE table_schema = 'public';