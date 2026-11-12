-- ==============================================================================
-- Migration 011: Syllabus Ghost Nodes, Match Locking & Source Variants (Task T18)
-- Relies on Decisions D05 (pgvector), D10 (768-dim embeddings), Features F16, F17
-- Preserves universities, schemes, syllabus_subjects, syllabus_topics, subjects.source_preference
-- ==============================================================================

-- 1. Add semantic embedding & review flag to syllabus_topics for ghost node matching
ALTER TABLE syllabus_topics ADD COLUMN IF NOT EXISTS embedding vector(768);
ALTER TABLE syllabus_topics ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE;

-- 2. Add match lock protection (Rule 13.2) and per-source variant storage (F17) to topics
ALTER TABLE topics ADD COLUMN IF NOT EXISTS syllabus_match_locked BOOLEAN DEFAULT FALSE;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS source_variants JSONB DEFAULT '{}'::jsonb;

-- 3. Indexes for fast syllabus lookup and pgvector similarity matching
CREATE INDEX IF NOT EXISTS idx_syllabus_topics_subject_id ON syllabus_topics(syllabus_subject_id);
CREATE INDEX IF NOT EXISTS idx_syllabus_topics_module_no ON syllabus_topics(syllabus_subject_id, module_no);
CREATE INDEX IF NOT EXISTS idx_syllabus_topics_embedding_hnsw
    ON syllabus_topics USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_topics_syllabus_topic_id ON topics(syllabus_topic_id);

