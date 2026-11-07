-- ==============================================================================
-- Migration 009: Graph Caching, Incremental Tracking & Louvain Clustering Support
-- Relies on Decisions D05, D07, D11, and Build Plan Task T11
-- ==============================================================================

-- 1. Add summary to documents table to record 'what changed' on each upload
ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary TEXT;

-- 2. Add version_number and subject_id to graph_versions table
ALTER TABLE graph_versions ADD COLUMN IF NOT EXISTS version_number INTEGER DEFAULT 1;
ALTER TABLE graph_versions ADD COLUMN IF NOT EXISTS subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE;

-- 3. Create graph_cache table to store compiled graph JSON for instant loading and offline demo mode (R17)
CREATE TABLE IF NOT EXISTS graph_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key TEXT UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE,
    graph_version_id UUID REFERENCES graph_versions(id) ON DELETE SET NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Create performance indexes
CREATE INDEX IF NOT EXISTS idx_graph_cache_user_id ON graph_cache(user_id);
CREATE INDEX IF NOT EXISTS idx_graph_cache_subject_id ON graph_cache(subject_id);
CREATE INDEX IF NOT EXISTS idx_graph_versions_subject_user ON graph_versions(user_id, subject_id);

