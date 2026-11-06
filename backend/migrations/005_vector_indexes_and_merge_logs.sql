-- ==============================================================================
-- StudyGraph Database Migration 005
-- Purpose: Vector indexes (HNSW) and Merge Audit Log for T07 (Decision D05, D10)
-- 
-- 1. HNSW Vector Indexes:
--    - Speeds up cosine distance queries (<=> operator) for both note chunks 
--      and extracted topics without doing exhaustive table scans.
-- 
-- 2. topic_merges Audit Table:
--    - Stores every merge (auto or manual) so that merges can be inspected and
--      split (undone) cleanly without losing original keywords, explanations,
--      or chunk source citations.
-- ==============================================================================

-- 1. HNSW index on chunks embedding for fast semantic retrieval
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON chunks USING hnsw (embedding vector_cosine_ops);

-- 2. HNSW index on topics embedding for fast duplicate & candidate finding
CREATE INDEX IF NOT EXISTS idx_topics_embedding_hnsw 
ON topics USING hnsw (embedding vector_cosine_ops);

-- 3. topic_merges audit table
CREATE TABLE IF NOT EXISTS topic_merges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    surviving_topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    merged_topic_id UUID NOT NULL,
    merged_keyword TEXT NOT NULL,
    merged_explanation TEXT NOT NULL,
    merged_real_world_use TEXT,
    merged_module_no INTEGER,
    similarity_score FLOAT,
    merge_type TEXT NOT NULL CHECK (merge_type IN ('auto', 'manual')),
    transferred_chunk_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    undone_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_topic_merges_subject ON topic_merges (subject_id);
CREATE INDEX IF NOT EXISTS idx_topic_merges_surviving ON topic_merges (surviving_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_aliases_topic_id ON topic_aliases (topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_aliases_alias ON topic_aliases (alias);

