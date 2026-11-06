-- ==============================================================================
-- StudyGraph Database Migration 007
-- Purpose: Edge Visibility & Evidence Flexibility for Task T09 (RULEBOOK 13.8)
--
-- 1. Adds 'is_visible' column to edges table. Cross-subject links with strength < 3
--    can be marked visible = false by default, keeping weak cross-links hidden.
-- 2. Ensures edge_evidence has an independent primary key (id) rather than a composite
--    (edge_id, chunk_id), allowing multiple evidence snippets even if two topics
--    originated from the same source chunk.
-- ==============================================================================

-- Add is_visible column to edges table
ALTER TABLE edges ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE;

-- Add index on edges for fast graph queries
CREATE INDEX IF NOT EXISTS idx_edges_topics ON edges (topic_a, topic_b);
CREATE INDEX IF NOT EXISTS idx_edges_visibility ON edges (is_visible, scope, strength);

-- Ensure edge_evidence can hold multiple snippets per chunk without composite key collisions
DO $$
BEGIN
    -- Check if edge_evidence has id column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'edge_evidence' AND column_name = 'id'
    ) THEN
        ALTER TABLE edge_evidence ADD COLUMN id UUID DEFAULT gen_random_uuid();
    END IF;

    -- If the existing primary key is composite, drop it and set id as primary key
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'edge_evidence' AND constraint_type = 'PRIMARY KEY' AND constraint_name = 'edge_evidence_pkey'
    ) THEN
        ALTER TABLE edge_evidence DROP CONSTRAINT edge_evidence_pkey;
        ALTER TABLE edge_evidence ADD PRIMARY KEY (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_edge_evidence_edge_id ON edge_evidence (edge_id);

