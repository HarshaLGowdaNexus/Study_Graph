-- ==============================================================================
-- Migration 012: Token Logs, Cost Tracking & Privacy Optimization (Task T20)
-- Relies on Decisions D05 (PostgreSQL), D09 (Gemini Flash), Features F22, Rules 11
-- ==============================================================================

-- 1. Create token_logs table for tracking token consumption and cost estimation
CREATE TABLE IF NOT EXISTS token_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    operation TEXT NOT NULL, -- 'vision_ocr', 'topic_extraction', 'link_judging', 'topic_dedupe', 'chat_message', 'exam_parse', 'exam_answer', 'syllabus_parse'
    model TEXT NOT NULL,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Indexes for token logs analytics and user data cleanup
CREATE INDEX IF NOT EXISTS idx_token_logs_user_id ON token_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_token_logs_document_id ON token_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_token_logs_operation ON token_logs(user_id, operation);

-- 3. Query performance optimization indexes for low-latency graph and theory rendering
CREATE INDEX IF NOT EXISTS idx_topics_subject_module ON topics(subject_id, module_no);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_subject ON chat_messages(user_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_graph_cache_lookup ON graph_cache(cache_key, user_id);

