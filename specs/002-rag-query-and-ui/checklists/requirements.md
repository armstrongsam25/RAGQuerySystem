# Specification Quality Checklist: RAG Query Path + Minimal UI

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-12
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Validation Notes

### Content Quality

- **References to constitutionally-pinned tech (Gemini, pgvector, Postgres) appear in the Assumptions section, not in the Functional Requirements.** This is intentional and matches the pattern established in feature 001 (`specs/001-rag-boilerplate/spec.md`): the constitution binds the stack, so the spec acknowledges it rather than pretending the choice is open. Article IV is the canonical justification.
- **`vector(768)` is named in FR-003 by way of "constitutionally-pinned dimensionality."** The phrase abstracts the value behind a constitutional reference, so the requirement remains testable ("does the column dimensionality match the schema?") without leaking the literal number into the requirements text. The number itself is documented in the Assumptions section and in feature 001's data model.
- **Status-field values (`answered`, `refused`, `no_documents`) appear in FR-007, FR-010, FR-014, FR-015.** These are domain-level outcome labels surfaced through the API, not implementation details — a reviewer reading the spec needs to know what outcomes exist. They are equivalent to status codes in any contract-level spec.

### Requirement Completeness

- Zero `[NEEDS CLARIFICATION]` markers. Three areas that could have been clarification points were resolved with informed guesses and documented in **Assumptions**: (1) frontend implementation choice between Streamlit and HTMX-in-FastAPI — deferred to `/speckit-plan`; (2) grounding-check approach — spec mandates **both** threshold and entailment check, with the entailment check's implementation deferred to `/speckit-plan`; (3) chunking strategy — deferred to `/speckit-plan` since the requirement is on the observable property (every chunk has provenance), not the algorithm.
- Each FR is independently testable. FR-013's invariant ("answered → ≥1 citation; refused → 0 citations") is the load-bearing example: it's a single line, structurally enforced, and lifts the "no citation, no answer" rule from Article II.3 into a constraint a test can assert.
- Success criteria are user-observable. SC-001 (ingest in 3 min), SC-002 (query in 10 s), SC-005 (5-run idempotency), SC-006 (clone-to-answer in 10 min), SC-007 (UI state distinguishability) all describe behavior a reviewer can verify without reading code. SC-003 and SC-004 lean on the constitution's load-bearing articles (I and II) without naming the underlying model or schema.

### Feature Readiness

- Four user stories, two at P1 (US1 query + cited answer, US2 refusal — both demo-bearing), one at P1 (US3 ingest — precondition without which US1/US2 are theoretical), one at P2 (US4 minimal UI — backed up by the same API the curl path exercises). All four are independently testable; US3 is an upstream precondition, but its independent test is "inspect the chunk table after running the command" — observable without US1 existing.
- Edge cases cover the failure modes that would silently corrupt the demo: empty corpus rendered as a refusal (would falsely advertise "I don't know" on a perfectly answerable question once content is added), upstream model failures masked as refusals (would corrupt Article I's grounding signal), and re-ingest duplicates (would corrupt retrieval ranking by inflating per-chunk weight).
- Scope boundary is explicit on both sides: **in scope** = ingest + query + grounding + citations + minimal UI; **out of scope** = eval harness (deferred to feature 003), hybrid retrieval, rerankers, polished frontend, multi-document, auth, streaming. The Assumptions section binds these.

## Result

All checklist items pass on first iteration. No spec revisions required before `/speckit-clarify` or `/speckit-plan`.

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- The two `/speckit-plan` decisions deferred from this spec (frontend mechanism, entailment-check implementation) are deliberate — they are technical-detail forks, not scope forks, and the constitution leaves both open.
