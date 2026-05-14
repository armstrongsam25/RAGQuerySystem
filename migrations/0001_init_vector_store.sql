-- Migration 0001 — initial vector store schema.
--
-- Implements the data model defined in
--   specs/001-rag-boilerplate/data-model.md
-- and satisfies the Article II provenance requirements
-- (constitution v1.0.1).
--
-- Idempotency: this file is applied exactly once by the runner in
-- src/rag/migrations.py. Re-running the runner skips the file because
-- its filename is recorded in schema_migrations.

-- pgvector lives outside the public schema; activate it first.
CREATE EXTENSION IF NOT EXISTS vector;

-- pgcrypto provides gen_random_uuid(). pg16's contrib bundle includes it,
-- but CREATE EXTENSION is idempotent under IF NOT EXISTS so we belt-and-brace.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- source_document — one row per ingested PDF.
-- ---------------------------------------------------------------------------
CREATE TABLE source_document (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    display_filename  TEXT         NOT NULL CHECK (length(display_filename) > 0),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- chunk — one row per retrievable text span.
--
-- Article II is structurally enforced here: every provenance column is
-- NOT NULL with a CHECK constraint, and the composite UNIQUE on
-- (source_document_id, page_number, char_offset_start, char_offset_end)
-- prevents duplicate provenance.
-- ---------------------------------------------------------------------------
CREATE TABLE chunk (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id  UUID         NOT NULL
                                     REFERENCES source_document(id) ON DELETE CASCADE,
    page_number         INTEGER      NOT NULL CHECK (page_number > 0),
    char_offset_start   INTEGER      NOT NULL CHECK (char_offset_start >= 0),
    char_offset_end     INTEGER      NOT NULL CHECK (char_offset_end > char_offset_start),
    raw_text            TEXT         NOT NULL CHECK (length(raw_text) > 0),
    embedding           vector(768),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (source_document_id, page_number, char_offset_start, char_offset_end)
);

CREATE INDEX idx_chunk_source ON chunk (source_document_id);

-- The HNSW/IVFFlat index on `embedding` is deferred to the retrieval feature,
-- which will pick parameters once `k` and corpus size are known.
