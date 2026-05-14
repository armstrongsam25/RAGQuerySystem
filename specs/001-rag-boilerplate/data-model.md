# Phase 1 Data Model: RAG System Boilerplate

**Feature**: [001-rag-boilerplate](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-11

## Scope

This boilerplate creates the schema that every later feature builds on. Three tables ship in migration `0001_init_vector_store.sql`:

1. `source_document` — one row per ingested PDF.
2. `chunk` — one row per retrievable text span; carries the Article II provenance fields and the embedding vector.
3. `schema_migrations` — the migration runner's bookkeeping (R-002).

No data is inserted at boilerplate stage. The schema's job is to make later feature work impossible-to-do-wrong: a chunk row cannot be inserted without provenance; an embedding cannot be inserted with the wrong dimensionality.

## Extension prerequisites

Migration `0001` runs `CREATE EXTENSION IF NOT EXISTS vector;` as its first statement. The `pgvector/pgvector:pg16` image bundles the extension, so this is a one-line activation, not an install.

## Tables

### `source_document`

One row per ingested PDF. Stays tiny — richer metadata (page count, ingest timestamp, file hash) is a downstream-feature concern, but the column set leaves room for it without breaking changes.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | `PRIMARY KEY`, default `gen_random_uuid()` | Stable identifier; chunk rows reference this. Boilerplate uses `gen_random_uuid()` (pgcrypto is bundled with pg16). |
| `display_filename` | `TEXT` | `NOT NULL`, `CHECK (length(display_filename) > 0)` | Human-readable name for the README's example queries and the eventual UI. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | Set on insert; immutable. |

**Why no `file_hash` / `page_count` / `ingest_status` here yet**: those are the ingest feature's invariants. Adding them now would mean stubbing values or making them nullable; both are worse than waiting for the feature that owns them to add them with proper defaults and constraints.

### `chunk`

One row per retrievable text span. This table is where Article II (Citations Carry Real Provenance) lives — every column except the embedding is NOT NULL, so it is **structurally impossible** to persist a chunk without the provenance a citation needs.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | `PRIMARY KEY`, default `gen_random_uuid()` | The "stable chunk id" the API contract returns. Stable across re-ingests of the same chunk text (downstream feature concern; boilerplate just creates the column). |
| `source_document_id` | `UUID` | `NOT NULL`, `REFERENCES source_document(id) ON DELETE CASCADE` | Provenance — Article II.1. |
| `page_number` | `INTEGER` | `NOT NULL`, `CHECK (page_number > 0)` | Provenance — Article II.1. 1-indexed (matches PDF page numbering UX). |
| `char_offset_start` | `INTEGER` | `NOT NULL`, `CHECK (char_offset_start >= 0)` | Provenance — Article II.1. Inclusive, 0-indexed against the extracted plaintext for the source document. |
| `char_offset_end` | `INTEGER` | `NOT NULL`, `CHECK (char_offset_end > char_offset_start)` | Provenance — Article II.1. Exclusive. Cross-column check ensures the span is non-empty. |
| `raw_text` | `TEXT` | `NOT NULL`, `CHECK (length(raw_text) > 0)` | Provenance — Article II.1. The literal text span, so a reviewer can verify a citation without re-extracting the PDF. |
| `embedding` | `vector(768)` | `NULL` allowed at column level; logically required by retrieval feature | Pinned to the constitution-mandated 768 dimensions (Gemini `text-embedding-004`). pgvector enforces dimensionality on insert — wrong-dim writes fail with a clear error (spec User Story 3, scenario #3). Nullable so an ingest pipeline can insert text first and embed in a second pass without a temporary sentinel value; the retrieval feature will add a partial index that excludes NULL embeddings. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | Set on insert; immutable. |

**Composite uniqueness**: `UNIQUE (source_document_id, page_number, char_offset_start, char_offset_end)`. A chunk is uniquely identified by where it came from. Re-ingesting the same PDF should not produce duplicate chunks; this constraint catches the bug at the DB layer rather than in application code.

**Indexes shipped in `0001`**:
- `idx_chunk_source` on `(source_document_id)` — supports the retrieval feature's "filter to this document" path and is cheap. The PK already covers single-id lookups.

**Indexes deliberately NOT shipped in `0001`**:
- **HNSW or IVFFlat on `embedding`** — pgvector indexes have a real footprint (build time, memory, recall/speed tradeoffs) and the right parameters depend on the corpus size and the retrieval feature's k. Adding the index now would either pick parameters in the dark or pick the wrong defaults; either way, the retrieval feature would re-do it. Deferred.
- **GIN on `raw_text` for BM25-style search** — only relevant once hybrid retrieval is on (constitution stretch, Art VII). Deferred.

### `schema_migrations`

The migration runner's bookkeeping table (R-002). Created lazily by the runner on first invocation rather than by `0001` itself — this matters because the runner's idempotency check needs to query this table *before* attempting any migration, including `0001`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `name` | `TEXT` | `PRIMARY KEY` | Filename of the applied migration, e.g. `0001_init_vector_store.sql`. |
| `applied_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | Wall-clock time the migration was committed. Surfaced in the `/health` response for transparency. |

**Why not version everything inside a `version` integer column**: filenames are self-documenting; `0001_init_vector_store.sql` tells a reviewer what was done without joining to anything. An integer column would force a second lookup or a parallel comment file. The constitution's "load-bearing rule: a reviewer must be able to walk the code without spelunking" applies to schema too.

## Migration: `0001_init_vector_store.sql` — outline

```sql
-- pgvector lives outside the public schema; activate it first.
CREATE EXTENSION IF NOT EXISTS vector;

-- source_document
CREATE TABLE source_document (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  display_filename TEXT NOT NULL CHECK (length(display_filename) > 0),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- chunk (with all Article II provenance fields NOT NULL)
CREATE TABLE chunk (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id  UUID NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  page_number         INTEGER NOT NULL CHECK (page_number > 0),
  char_offset_start   INTEGER NOT NULL CHECK (char_offset_start >= 0),
  char_offset_end     INTEGER NOT NULL CHECK (char_offset_end > char_offset_start),
  raw_text            TEXT NOT NULL CHECK (length(raw_text) > 0),
  embedding           vector(768),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_document_id, page_number, char_offset_start, char_offset_end)
);

CREATE INDEX idx_chunk_source ON chunk (source_document_id);
```

(The `schema_migrations` table is created by the migration runner code, not by `0001` — see R-002 for the runner algorithm.)

## State transitions

No state machine at boilerplate stage. Rows are inserted by downstream features and read by retrieval; the only "state" a chunk has is "embedding present" vs "embedding NULL," and that's a property exposed via partial indexes the retrieval feature will add — not a workflow.

## Validation rules — spec → schema traceability

| Spec requirement | Where enforced in the schema |
|------------------|------------------------------|
| FR-005: chunk carries source doc id, page, char start/end, raw text, embedding with pinned dim, stable id | `chunk` table — all listed columns; embedding is `vector(768)`; PK is UUID. |
| FR-006 (idempotent migrations) | `schema_migrations.name PRIMARY KEY` — runner checks membership before applying. |
| SC-003: 100% of inserted chunks carry every provenance field | NOT NULL on every provenance column + CHECK constraints; the schema makes omission impossible. |
| Edge case: wrong-dim embedding rejected | pgvector's column-level dimensionality enforcement — insert fails with a typed error naming the dimension mismatch. |
| Edge case: config-vs-schema dim drift surfaced at startup | Not enforced in schema; enforced by the app's startup check (R-004) that reads `pg_attribute.atttypmod` and compares to `settings.EMBEDDING_DIM`. |

## Open seams for downstream features

These are deliberate places where the boilerplate schema **does not** constrain a downstream feature's design — the column exists, but the rules around it are theirs to set:

- `chunk.embedding` is nullable. The retrieval feature will decide whether to enforce NOT NULL via a later migration once embedding is mandatory at insert time.
- `chunk.raw_text` length is unbounded. The chunking feature owns the chunk-size policy and will likely add a soft length limit then.
- `source_document` carries no file hash. The ingest feature will add it (and a unique constraint on it, to dedupe re-ingests).

Each of these is the kind of decision that would be wrong to make speculatively now and easy to add via a new migration once the owning feature exists.
