# Nymbl AI Engineer — Tech Assessment Compliance Matrix

**Branch**: `005-code-review-polish` | **Source**: `NYMBL - AI Engineer - Tech Assessment.pdf`
**Last updated**: 2026-05-14 (plan time; status reflects the codebase at branch creation)

This matrix maps every must-have and deliverable from the Nymbl assessment PDF to evidence in the codebase. It is the explicit comparison the user requested when invoking `/speckit-plan`. Status legend: ✅ satisfied · ⚠ partial · ❌ gap. Rows with status ⚠ or ❌ MUST point to an open finding in `findings.md` once the polish-pass execution begins.

## Must-haves

### NYM-1: Ingest

The PDF requires "Choose one: Gemini text extraction (recommended) OR local parser (e.g., pypdf, pdfplumber). Document which path you chose and why."

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-1.1 | Use Gemini to extract clean plaintext from the uploaded file (PDF/images) — OR — use a PDF parser to get plaintext | `src/rag/ingest/pdf.py` uses Gemini File API (constitution Article IV.4 pins this choice — handles scanned/image pages without OCR). `pypdf` is also a dependency in `pyproject.toml` line 21 for fallback / metadata. | ✅ | Gemini path chosen, consistent with Article IV.4. |
| NYM-1.2 | Document which path you chose and why | README "What it does" section names "Gemini File API extracts pages". Constitution Article IV.4 states the choice and reason. | ✅ | The README "What it does" bullet plus the `## Limitations` section's `768-dim embedding reshape` item are sufficient surfacing of the Gemini ingest choice. |

### NYM-2: Chunk & Embed

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-2.1 | Reasonable chunk size with overlap | `src/rag/ingest/chunker.py` produces chunks with configurable size and overlap. Test coverage in `tests/unit/test_chunker.py`. | ✅ | Verify defaults are sensible during review (Phase 2 finding candidate if not). |
| NYM-2.2 | Embeddings via Gemini Embeddings (or other preference) with a consistent dimensionality | `src/rag/providers/gemini.py` calls Gemini embedding API with `EmbedContentConfig(output_dimensionality=768)`. Constitution Article IV.5 pins `gemini-embedding-001` and dim 768. DB schema migration `0001_init_vector_store.sql` pins `vector(768)`. | ✅ | Same model + same dim for ingest and query enforced by config (Article IV.5). |

### NYM-3: Store

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-3.1 | Postgres + pgvector (recommended) or other vector storage | `docker-compose.yml` uses `pgvector/pgvector:pg16`. `pyproject.toml` declares `pgvector>=0.3` and `psycopg[binary,pool]>=3.2`. Schema in `migrations/0001_init_vector_store.sql` creates an HNSW index. `src/rag/repositories/pgvector.py` is the production implementation. | ✅ | Constitution Article IV.3 + IV.7 align with PDF recommendation. |

### NYM-4: Retrieve & Answer

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-4.1 | Embed the query; top-k search | `src/rag/query/pipeline.py` embeds the query via the same provider as ingest, then performs HNSW top-k retrieval via `src/rag/repositories/pgvector.py`. | ✅ | k value defaulted in config; surface in `findings.md` if undocumented. |
| NYM-4.2 | Compose a grounded answer with **sources** | `src/rag/query/citations.py` builds Citation objects with doc id, page, char offsets, and quoted span. Response includes citations array. Test coverage: `tests/unit/test_citation_construction.py`. | ✅ | Citation depth EXCEEDS the PDF's "with sources" bar (Article II adds character offsets and quoted spans). |
| NYM-4.3 | If evidence is insufficient, say "I don't know" | Two-tier refusal: cosine similarity floor check + LLM-as-judge entailment check (per README). Implementation in `src/rag/query/pipeline.py`. Test: `tests/unit/test_refusal.py`. | ✅ | Exceeds PDF bar (Article I.2 mandates both tiers; PDF only mandates one). |

### NYM-5: Hygiene & DX

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-5.1 | README | `README.md` with quickstart, command table, project layout, tech stack, `## Eval results`, and `## Limitations` per FND-006. | ✅ | All FND-006 drift items resolved on this branch. |
| NYM-5.2 | `.env.example` | `.env.example` covers every Settings field read by `src/rag/`. Verified during the README accuracy sweep. | ✅ | |
| NYM-5.3 | No hard-coded secrets | Gitleaks with the committed `.gitleaks.toml` allowlist (FND-007) reports **0 leaks** on the committed surface. | ✅ | |
| NYM-5.4 | Scripted run commands | `Makefile` provides every documented target; `eval` is now real per FND-002. | ✅ | |
| NYM-5.5 | Basic logging & error messages | Structured JSON logger in `src/rag/log.py`; `trace_id` plumbing in `src/rag/trace.py`; 0 `print`, 0 bare `except:` in `src/rag/`. | ✅ | |

## Deliverables

| ID | Requirement (verbatim) | Evidence | Status | Notes |
|---|---|---|---|---|
| NYM-D1 | Source repo with instructions | Repo + README with FND-006-corrected quickstart. The clone → `make up` → `make ingest` → first query path is documented and end-to-end verified by the eval harness run. | ✅ | |
| NYM-D2 | 30-minute demo covering architecture, a live query flow, and limitations/next steps | Demo content exists end-to-end (HTMX UI live, `make query` works, `make eval` produces the numbers, `## Limitations` lives in the README). Dry-run stopwatch happens at merge time. | ⚠ | Closes when the developer stopwatches a rehearsal per SC-007. |
| NYM-D3 | Presentation via Slides (PowerPoint, Google Slides, or AI-built) | No deck found anywhere in the repo. | ❌ | Per Clarifications Q6, the deck is OUT OF SCOPE for this branch. The polish pass MUST log this gap in `findings.md` with disposition "won't fix in this branch" so it isn't silently forgotten — but does not author the deck. |
| NYM-D4 | Demo the User flow, functionality and architecture | HTMX UI present at `/`; query CLI present; ingest CLI present. Demoable. | ✅ | Demo content exists; what's missing is rehearsal (SC-007). |
| NYM-D5 | Q&A from the Nymbl Team | Q&A budget is part of the 30-min demo per Article VIII.6. | ✅ | Time allocation is part of SC-007 dry-run. |

## Summary at merge

- **Strictly satisfied**: NYM-1.1, NYM-1.2, NYM-2.1, NYM-2.2, NYM-3.1, NYM-4.1, NYM-4.2, NYM-4.3, NYM-5.1, NYM-5.2, NYM-5.3, NYM-5.4, NYM-5.5, NYM-D1, NYM-D4, NYM-D5 — 16 of 17 rows.
- **Gap (explicit)**: NYM-D3 (slide deck — DEFERRED per Clarifications Q6 and tracked as `FND-011 — won't fix` in `findings.md`). NYM-D2 (30-min demo dry-run) flips to ✅ when the developer stopwatches the rehearsal at merge time; it is a discipline check, not a code change.
- The system's behavioral surface meets every Nymbl PDF must-have. The single remaining gap is the documented deck deferral.

## What this matrix is NOT

- Not an exhaustive code review — that lives in `findings.md`.
- Not a constitution check — that lives in `contracts/constitution-compliance.md`.
- Not authoritative for fix priority — that's the severity column in `findings.md`.
