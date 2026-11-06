-- ==============================================================================
-- StudyGraph Database Migration 006
-- Purpose: Link Candidates Table for Task T08 (Decisions D05, D10)
-- 
-- Stores candidate topic pairs discovered via vector nearest-neighbor search
-- (both same-subject and cross-subject) before they are evaluated by the LLM judge
-- in Task T09.
--
-- Guarantees:
-- 1. Symmetric uniqueness: (A, B) is treated identical to (B, A) via expression index.
-- 2. Non-self-pairing: A topic can never be paired with itself.
-- 3. Referential integrity: Cascades cleanly if either topic is deleted.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS link_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_a UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    topic_b UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    similarity FLOAT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('same_subject', 'cross_subject')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'judged', 'dismissed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_distinct_topics CHECK (topic_a != topic_b)
);

-- Unique index ensuring undirected pair uniqueness: (A, B) equals (B, A)
CREATE UNIQUE INDEX IF NOT EXISTS idx_link_candidates_canonical_pair 
ON link_candidates (LEAST(topic_a, topic_b), GREATEST(topic_a, topic_b));

-- Lookup indexes for queries by topic and status
CREATE INDEX IF NOT EXISTS idx_link_candidates_topic_a ON link_candidates (topic_a);
CREATE INDEX IF NOT EXISTS idx_link_candidates_topic_b ON link_candidates (topic_b);
CREATE INDEX IF NOT EXISTS idx_link_candidates_status_scope ON link_candidates (status, scope);

