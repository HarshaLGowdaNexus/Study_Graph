-- ==============================================================================
-- Migration: 001_initial_schema.sql
-- Project: StudyGraph
-- Description: Initial schema creation matching docs/DATA_MODEL.md strictly.
-- Relies on: Decision D05 (Supabase PostgreSQL + pgvector), D10 (768-dim embeddings)
-- ==============================================================================

-- 1. Enable pgvector extension for AI semantic search & embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Drop existing tables if re-running (in reverse dependency order)
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS share_links CASCADE;
DROP TABLE IF EXISTS exam_questions CASCADE;
DROP TABLE IF EXISTS exam_papers CASCADE;
DROP TABLE IF EXISTS graph_versions CASCADE;
DROP TABLE IF EXISTS edge_evidence CASCADE;
DROP TABLE IF EXISTS edges CASCADE;
DROP TABLE IF EXISTS topic_aliases CASCADE;
DROP TABLE IF EXISTS topic_sources CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS clusters CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS subjects CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS syllabus_topic_map CASCADE;
DROP TABLE IF EXISTS syllabus_topics CASCADE;
DROP TABLE IF EXISTS syllabus_subjects CASCADE;
DROP TABLE IF EXISTS schemes CASCADE;
DROP TABLE IF EXISTS universities CASCADE;

-- ------------------------------------------------------------------------------
-- Table 1: universities (Multi-university support from day 1 - F25)
-- ------------------------------------------------------------------------------
CREATE TABLE universities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL
);

-- ------------------------------------------------------------------------------
-- Table 2: schemes (Syllabus versioning - F24)
-- ------------------------------------------------------------------------------
CREATE TABLE schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    university_id UUID NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    name TEXT NOT NULL, -- e.g. '2022 scheme'
    valid_from DATE,
    valid_to DATE
);

-- ------------------------------------------------------------------------------
-- Table 3: syllabus_subjects (Official university subject curriculum)
-- ------------------------------------------------------------------------------
CREATE TABLE syllabus_subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id UUID NOT NULL REFERENCES schemes(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    semester INTEGER,
    branch TEXT
);

-- ------------------------------------------------------------------------------
-- Table 4: syllabus_topics (Official syllabus skeleton for ghost nodes)
-- ------------------------------------------------------------------------------
CREATE TABLE syllabus_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    syllabus_subject_id UUID NOT NULL REFERENCES syllabus_subjects(id) ON DELETE CASCADE,
    module_no INTEGER,
    title TEXT NOT NULL,
    parent_id UUID REFERENCES syllabus_topics(id) ON DELETE SET NULL
);

-- ------------------------------------------------------------------------------
-- Table 5: syllabus_topic_map (Maps old scheme topics to new scheme topics)
-- ------------------------------------------------------------------------------
CREATE TABLE syllabus_topic_map (
    old_topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    new_topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    relation TEXT,
    PRIMARY KEY (old_topic_id, new_topic_id)
);

-- ------------------------------------------------------------------------------
-- Table 6: users (Student account records)
-- ------------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Table 7: subjects (Student personal study spaces / subjects)
-- ------------------------------------------------------------------------------
CREATE TABLE subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    syllabus_subject_id UUID REFERENCES syllabus_subjects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    source_preference TEXT DEFAULT 'notes' CHECK (source_preference IN ('notes', 'textbook'))
);

-- ------------------------------------------------------------------------------
-- Table 8: documents (Uploaded lecture notes, textbooks, and past papers)
-- ------------------------------------------------------------------------------
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    module_no INTEGER,
    filename TEXT NOT NULL,
    type TEXT NOT NULL, -- e.g. 'pdf', 'pptx', 'image'
    source_kind TEXT NOT NULL CHECK (source_kind IN ('notes', 'textbook', 'paper')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Table 9: chunks (Text segments with embeddings for citations & retrieval)
-- ------------------------------------------------------------------------------
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(768) -- 768 dimensions for Google text-embedding-004
);

-- ------------------------------------------------------------------------------
-- Table 15: clusters (Topic hierarchy for zoomable graph navigation)
-- Note: Created before topics so topics.cluster_id can reference it
-- ------------------------------------------------------------------------------
CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    label TEXT NOT NULL
);

-- ------------------------------------------------------------------------------
-- Table 10: topics (Knowledge graph nodes extracted from student notes)
-- ------------------------------------------------------------------------------
CREATE TABLE topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    explanation VARCHAR(1000) NOT NULL, -- At most 4 lines rule
    real_world_use TEXT,
    embedding vector(768), -- 768 dimensions for semantic similarity
    syllabus_topic_id UUID REFERENCES syllabus_topics(id) ON DELETE SET NULL,
    reviewed BOOLEAN DEFAULT FALSE,
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL
);

-- ------------------------------------------------------------------------------
-- Table 11: topic_sources (Evidence mapping topics back to document chunks)
-- ------------------------------------------------------------------------------
CREATE TABLE topic_sources (
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, chunk_id)
);

-- ------------------------------------------------------------------------------
-- Table 12: topic_aliases (Merged names / synonyms for topics)
-- ------------------------------------------------------------------------------
CREATE TABLE topic_aliases (
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    PRIMARY KEY (topic_id, alias)
);

-- ------------------------------------------------------------------------------
-- Table 13: edges (Graph links between topics with strict evidence rules)
-- ------------------------------------------------------------------------------
CREATE TABLE edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_a UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    topic_b UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    reason TEXT NOT NULL,
    industry_example TEXT NOT NULL,
    strength INTEGER NOT NULL CHECK (strength BETWEEN 1 AND 5),
    scope TEXT NOT NULL CHECK (scope IN ('same_subject', 'cross_subject')),
    status TEXT DEFAULT 'auto' CHECK (status IN ('auto', 'edited', 'deleted')),
    locked BOOLEAN DEFAULT FALSE,
    graph_version INTEGER DEFAULT 1
);

-- ------------------------------------------------------------------------------
-- Table 14: edge_evidence (Source snippets proving every link - Rule 13.1)
-- ------------------------------------------------------------------------------
CREATE TABLE edge_evidence (
    edge_id UUID NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    snippet TEXT NOT NULL,
    PRIMARY KEY (edge_id, chunk_id)
);

-- ------------------------------------------------------------------------------
-- Table 16: graph_versions (Snapshots of graph state across incremental uploads)
-- ------------------------------------------------------------------------------
CREATE TABLE graph_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    summary TEXT
);

-- ------------------------------------------------------------------------------
-- Table 17: exam_papers (Uploaded past university question papers)
-- ------------------------------------------------------------------------------
CREATE TABLE exam_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    year INTEGER,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE
);

-- ------------------------------------------------------------------------------
-- Table 18: exam_questions (Individual questions extracted from exam papers)
-- ------------------------------------------------------------------------------
CREATE TABLE exam_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES exam_papers(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    marks INTEGER,
    cluster_key TEXT,
    topic_id UUID REFERENCES topics(id) ON DELETE SET NULL
);

-- ------------------------------------------------------------------------------
-- Table 19: share_links (Secure, tokenized read-only links for graph sharing)
-- ------------------------------------------------------------------------------
CREATE TABLE share_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

-- ------------------------------------------------------------------------------
-- Table 20: chat_messages (Chat history with honest citations - Rule 13.4)
-- ------------------------------------------------------------------------------
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    text TEXT NOT NULL,
    citations_json JSONB,
    answered_from TEXT CHECK (answered_from IN ('notes', 'general')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Useful Indexes for Graph Traversals & Search
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_topics_subject ON topics(subject_id);
CREATE INDEX IF NOT EXISTS idx_edges_topic_a ON edges(topic_a);
CREATE INDEX IF NOT EXISTS idx_edges_topic_b ON edges(topic_b);
CREATE INDEX IF NOT EXISTS idx_edges_scope ON edges(scope);

