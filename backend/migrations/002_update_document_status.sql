-- ==============================================================================
-- Migration 002: Update Document Status Values & Add Storage Tracking
-- Relies on Decision D05, D06, and Build Plan Task T03
-- ==============================================================================

-- 1. Drop existing check constraint on documents.status if present
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;

-- 2. Update default value to 'queued'
ALTER TABLE documents ALTER COLUMN status SET DEFAULT 'queued';

-- 3. Add updated status check constraint matching pipeline requirements
-- Valid statuses: 'queued', 'extracting', 'done', 'failed'
ALTER TABLE documents ADD CONSTRAINT documents_status_check 
    CHECK (status IN ('queued', 'extracting', 'done', 'failed'));

-- 4. Add cloud storage path and error message tracking columns if they do not exist
ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_path TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;

