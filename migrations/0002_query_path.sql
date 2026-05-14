-- Feature 002: query path + minimal UI.
-- See specs/002-rag-query-and-ui/data-model.md for the full rationale.

-- 1. Chunker bookkeeping. Nullable so existing rows (if any) survive the
--    migration; ingest path always populates it for new rows.
ALTER TABLE chunk
  ADD COLUMN token_count INTEGER
  CHECK (token_count IS NULL OR token_count > 0);

-- 2. Retrieval hot path. HNSW with cosine ops; pgvector defaults for
--    m / ef_construction. Sized for low-thousands-of-chunks corpora.
CREATE INDEX idx_chunk_embedding_hnsw
  ON chunk
  USING hnsw (embedding vector_cosine_ops);

-- 3. Content-addressed re-ingest detection. SHA-256 hex of file bytes.
--    Nullable + UNIQUE allows multiple NULLs (legacy rows) without
--    violating the constraint; ingest path always populates the hash.
ALTER TABLE source_document
  ADD COLUMN file_hash TEXT;

ALTER TABLE source_document
  ADD CONSTRAINT source_document_file_hash_unique UNIQUE (file_hash);
