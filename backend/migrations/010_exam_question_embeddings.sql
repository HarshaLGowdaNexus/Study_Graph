-- ==============================================================================
-- Migration 010: Exam Question Embeddings & Canonical Cluster Labeling (Task T17)
-- Relies on Decisions D05 (pgvector), D10 (768-dim embeddings), Features F18-F19
-- ==============================================================================

-- 1. Add semantic embedding & canonical question wording to exam_questions
ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS embedding vector(768);
ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS canonical_question TEXT;

-- 2. Indexes for fast subject/paper lookup & semantic clustering
CREATE INDEX IF NOT EXISTS idx_exam_papers_subject_id ON exam_papers(subject_id);
CREATE INDEX IF NOT EXISTS idx_exam_papers_document_id ON exam_papers(document_id);
CREATE INDEX IF NOT EXISTS idx_exam_questions_paper_id ON exam_questions(paper_id);
CREATE INDEX IF NOT EXISTS idx_exam_questions_cluster_key ON exam_questions(cluster_key);
CREATE INDEX IF NOT EXISTS idx_exam_questions_embedding_hnsw
    ON exam_questions USING hnsw (embedding vector_cosine_ops);

