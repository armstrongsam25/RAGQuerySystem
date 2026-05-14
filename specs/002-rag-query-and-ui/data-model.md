# Phase 1 Data Model: RAG Query Path + Minimal UI

**Feature**: [002-rag-query-and-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

## Scope

This feature's persistence-layer changes are additive to feature 001's schema. Migration **`0002_query_path.sql`** introduces:

1. `chunk.token_count INTEGER` — chunker bookkeeping (R-011).
2. An HNSW index on `chunk.embedding USING vector_cosine_ops` — retrieval hot path (R-014).
3. `source_document.file_hash TEXT UNIQUE` — content-based re-ingest detection (R-013 + spec FR-004).

No new tables. No drops. No changes to the Article II provenance fields — those remain exactly as feature 001 froze them.

Runtime entities (`Query Request`, `Query Response`, `Citation`, `Generation Prompt`) are pinned in spec.md → Key Entities. This document is persistence-only.

## Migration `0002_query_path.sql` — outline

```sql
-- Chunker bookkeeping: chunks track their token count for budgeting at
-- query time (top-k * mean(token_count) must fit Gemini 2.5 Flash input).
ALTER TABLE chunk
  ADD COLUMN token_count INTEGER
  CHECK (token_count IS NULL OR token_count > 0);

-- Retrieval hot path. pgvector HNSW with cosine ops; defaults for m and
-- ef_construction are correct for the low-thousands-of-chunks scale of a
-- small corpus (R-014).
CREATE INDEX idx_chunk_embedding_hnsw
  ON chunk
  USING hnsw (embedding vector_cosine_ops);

-- Content-addressed re-ingest detection. file_hash is the SHA-256 of the
-- PDF file content (stable across renames, distinct across edits).
-- The unique constraint catches re-ingests at the document level; the
-- chunk-level UNIQUE from migration 0001 catches them at the span level.
-- Both fire on `ON CONFLICT DO NOTHING` paths during idempotent ingest.
ALTER TABLE source_document
  ADD COLUMN file_hash TEXT;
ALTER TABLE source_document
  ADD CONSTRAINT source_document_file_hash_unique UNIQUE (file_hash);
```

Notes on the shape:

- `token_count` is **nullable**. Existing rows (there are none in feature 002 yet, but the migration must be safe against the case where someone has ingested via experimental code) get NULL; the ingest path always populates it for new rows. A future migration can flip to NOT NULL after a backfill, but this feature stops at "allowed to be null on legacy rows" so the migration is a pure ADD COLUMN, never a backfill DDL.
- The HNSW index is `CREATE INDEX`, not `CREATE INDEX CONCURRENTLY`. Concurrent index creation requires being outside a transaction and complicates the migration runner. At the corpus size we target, the synchronous build is sub-second and the trade is not worth it.
- `file_hash` is **nullable** on the column add, then a `UNIQUE` constraint is added. Nullable + UNIQUE in Postgres means multiple NULLs are allowed (one per document with no hash recorded), so legacy `source_document` rows without a hash don't violate the constraint. The ingest path always computes and persists the hash; the eventual NOT-NULL flip is a downstream-feature concern.

## Modified table: `chunk`

The post-migration shape, with the new column marked **NEW**:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | `PRIMARY KEY`, default `gen_random_uuid()` | Unchanged from feature 001. |
| `source_document_id` | `UUID` | `NOT NULL`, FK → `source_document(id) ON DELETE CASCADE` | Unchanged. |
| `page_number` | `INTEGER` | `NOT NULL`, `CHECK (page_number > 0)` | Unchanged. |
| `char_offset_start` | `INTEGER` | `NOT NULL`, `CHECK (char_offset_start >= 0)` | Unchanged. Offset is into the page's extracted text, not into a doc-wide stream — load-bearing for Art II (R-011). |
| `char_offset_end` | `INTEGER` | `NOT NULL`, `CHECK (char_offset_end > char_offset_start)` | Unchanged. |
| `raw_text` | `TEXT` | `NOT NULL`, `CHECK (length(raw_text) > 0)` | Unchanged. |
| `embedding` | `vector(768)` | nullable at column level | Unchanged. Populated by ingest after chunking. |
| **`token_count`** | **`INTEGER`** | **CHECK (`token_count IS NULL OR token_count > 0`)** | **NEW**. ~600 in steady state per R-011. Used for budgeting and surfaced in logs to make demo-time "how big are your chunks?" questions answerable from data. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | Unchanged. |

**Composite UNIQUE on `(source_document_id, page_number, char_offset_start, char_offset_end)`** — unchanged from feature 001. With page-bounded chunking (R-011), this constraint deduplicates re-ingests at the span level. Combined with the new `source_document.file_hash` UNIQUE, re-ingests are caught at both layers.

**Indexes**:
- `idx_chunk_source` on `(source_document_id)` — from feature 001, unchanged.
- **`idx_chunk_embedding_hnsw`** on `embedding USING hnsw (vector_cosine_ops)` — **NEW**, supports retrieval (R-014).

Indexes deliberately still not shipped:
- BM25/`tsvector` GIN index. Hybrid retrieval is constitution Art VII stretch and remains out of scope.
- A partial index on `embedding IS NOT NULL`. Not needed: ingest always populates `embedding` before commit, so the "embedding NULL after ingest" state is transient at most (page-extraction succeeded but embedding failed → ingest aborts and rolls back per spec FR-006). The retrieval SQL still includes `WHERE embedding IS NOT NULL` defensively (R-013).

## Modified table: `source_document`

The post-migration shape, with the new column marked **NEW**:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | `PRIMARY KEY`, default `gen_random_uuid()` | Unchanged. |
| `display_filename` | `TEXT` | `NOT NULL`, `CHECK (length(display_filename) > 0)` | Unchanged. |
| **`file_hash`** | **`TEXT`** | **`UNIQUE`** (nullable allowed; multiple NULLs OK in PG) | **NEW**. SHA-256 hex digest of the PDF file content. Computed by ingest before the first Gemini call so a re-ingest fails fast (`ON CONFLICT DO NOTHING` returns 0 rows, ingest reports "already ingested" and exits 0 per spec FR-004 acceptance scenario 2). |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | Unchanged. |

**Why SHA-256 specifically**: cheap, available in stdlib (`hashlib.sha256`), collision-resistant well beyond what a single-tenant assessment ever needs, and the hex digest fits cleanly in `TEXT` without base-encoding choices to bikeshed.

**Why not store the hash as `BYTEA`**: hex `TEXT` is human-readable in logs and SQL queries; storage cost (~64 bytes) is irrelevant at this scale.

## Schema version surfaced in `/health`

The boilerplate's `/health` endpoint reports the schema version (the highest-numbered applied migration in `schema_migrations`). After this feature lands, `/health` will report version `0002_query_path.sql`. The integration test from feature 001 (`tests/integration/test_health_live.py`) needs no change — it asserts a non-empty version string, not a specific value.

## State transitions

Still no formal state machine. The closest thing this feature introduces is the **ingest run lifecycle**, which lives in application state (logs) rather than the schema:

```text
ingest_started
   → file_hash_computed (may short-circuit to ingest_already_done if hash exists)
   → per-page extraction (loop)
   → chunks_produced
   → embeddings_computed (batched)
   → chunks_persisted (single transaction)
   → ingest_complete
```

Failure at any stage rolls back the database transaction (spec FR-006). The `source_document` row is created in the same transaction as the chunks, so a partial extraction leaves zero database state behind. The file_hash UNIQUE constraint provides the second layer: if a crash leaves an inconsistent state (extremely unlikely given the single-tx design), a retry will either re-create the same rows (no-op) or fail explicitly.

## Validation rules — spec → schema traceability (delta)

| Spec requirement (this feature) | Where enforced in the schema |
|---------------------------------|------------------------------|
| FR-004 (idempotent re-ingest, no duplicate chunks) | Existing `chunk` UNIQUE on `(source_document_id, page_number, char_offset_start, char_offset_end)` + new `source_document.file_hash` UNIQUE. Two layers of defense. |
| FR-006 (failed ingest leaves DB clean) | Application-level: ingest runs in a single transaction that wraps `source_document` insert + all `chunk` inserts. Implementation detail goes to /speckit-tasks; schema permits it (FK is `ON DELETE CASCADE` so even an out-of-band cleanup is safe). |
| FR-009 (vector similarity retrieval) | New HNSW index on `chunk.embedding USING vector_cosine_ops`. |
| FR-013 (citations have stable chunk_id) | Existing `chunk.id UUID PRIMARY KEY` from feature 001. |
| SC-005 (re-ingest 5x produces zero duplicates) | Same two-layer UNIQUE as FR-004. |

## Open seams (still deferred to future migrations)

- `chunk.token_count` NOT NULL flip — once every row has a token count, a future migration can tighten.
- `source_document.file_hash` NOT NULL flip — same pattern.
- BM25 / `tsvector` GIN index on `chunk.raw_text` — hybrid retrieval (Art VII stretch).
- `source_document.page_count`, `ingest_status`, `ingest_completed_at` — deferred; not load-bearing for the demo, can be added by a future feature without breaking the current API.
