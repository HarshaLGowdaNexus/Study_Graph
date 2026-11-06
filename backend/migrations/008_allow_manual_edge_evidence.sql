-- ==============================================================================
-- StudyGraph Database Migration 008
-- Purpose: Support Manual Edges, Evidence, and Fast Lock Checking (Task T10)
--
-- 1. Alters edge_evidence.chunk_id to DROP NOT NULL so manual links can store
--    optional snippets labeled 'manual' without requiring an existing document chunk.
-- 2. Adds an index on edges(locked, status) to optimize pipeline checks before writes.
-- 3. Adds an index on edges(topic_a, topic_b) and canonical pairs for instant lookup.
-- ==============================================================================

-- 1. Allow chunk_id to be NULL in edge_evidence for manual citations
ALTER TABLE edge_evidence ALTER COLUMN chunk_id DROP NOT NULL;

-- 2. Index for rapid lock and status queries by pipeline workers
CREATE INDEX IF NOT EXISTS idx_edges_locked_status ON edges (locked, status);

-- 3. Unique index ensuring only one edge exists per canonical pair (A, B) = (B, A)
-- This protects against duplicate edge creation during concurrent or manual additions
CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_canonical_pair
ON edges (LEAST(topic_a, topic_b), GREATEST(topic_a, topic_b));

