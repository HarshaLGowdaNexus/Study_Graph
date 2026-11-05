-- ==============================================================================
-- StudyGraph Database Migration 003
-- Purpose: Add metadata fields to 'chunks' table for T04: Text Extraction
-- Fields:
--   - module_no: INTEGER (stores subject module number directly for fast lookup)
--   - method: TEXT CHECK (method IN ('direct', 'vision')) (tracks extraction route)
-- ==============================================================================

ALTER TABLE chunks 
ADD COLUMN IF NOT EXISTS module_no INTEGER;

ALTER TABLE chunks 
ADD COLUMN IF NOT EXISTS method TEXT CHECK (method IN ('direct', 'vision'));

-- Index on document_id and page for fast citation retrieval
CREATE INDEX IF NOT EXISTS idx_chunks_document_page ON chunks (document_id, page);

