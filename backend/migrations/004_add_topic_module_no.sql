-- ==============================================================================
-- StudyGraph Database Migration 004
-- Purpose: Add module_no to 'topics' table for T05: Topic Extraction
-- Allows assigning and tracking the subject module directly on topics
-- ==============================================================================

ALTER TABLE topics 
ADD COLUMN IF NOT EXISTS module_no INTEGER;

CREATE INDEX IF NOT EXISTS idx_topics_subject_module ON topics (subject_id, module_no);

