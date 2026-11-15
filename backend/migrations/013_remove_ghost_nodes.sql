-- ==============================================================================
-- Migration 013: Remove Syllabus Ghost Nodes & Preserving Source Preference (Task T18B)
-- Drops syllabus ghost node tracking from topics while preserving:
--   - topics.source_variants (F17: Notes vs. Textbook content variants)
--   - subjects.source_preference (F17: Preferred source per subject)
-- ==============================================================================

-- 1. Drop syllabus foreign keys, columns and indexes from topics table
DROP INDEX IF EXISTS idx_topics_syllabus_topic_id;
ALTER TABLE topics DROP COLUMN IF EXISTS syllabus_topic_id CASCADE;
ALTER TABLE topics DROP COLUMN IF EXISTS syllabus_match_locked CASCADE;

-- 2. Drop syllabus_topics table and its indexes if present
DROP INDEX IF EXISTS idx_syllabus_topics_subject_id;
DROP INDEX IF EXISTS idx_syllabus_topics_module_no;
DROP INDEX IF EXISTS idx_syllabus_topics_embedding_hnsw;
DROP TABLE IF EXISTS syllabus_topics CASCADE;
