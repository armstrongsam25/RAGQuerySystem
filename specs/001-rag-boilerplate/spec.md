# Feature Specification: RAG System Boilerplate

**Feature Branch**: `001-rag-boilerplate`
**Created**: 2026-05-11
**Status**: Draft
**Input**: User description: "Create the boilerplate for the tiny RAG system. Use Python, Docker, and a scalable vector database to accomplish this task."

## Overview

Establish the structural foundation for the small Retrieval-Augmented Generation system described in the project constitution. This feature scopes the **boilerplate only**: the repository layout, container topology, configuration surface, vector database schema, and entry-point scaffolding that downstream features (PDF ingestion, retrieval, answer generation, evaluation harness) will build on. No retrieval logic, no LLM calls, and no eval execution are implemented here — those are subsequent features.

A reviewer who pulls a clean checkout should be able to run a single command, watch the application and database containers come up healthy, hit a stubbed health endpoint, and inspect a versioned vector-store schema that already pins the embedding dimensionality required by the constitution.

## Clarifications

### Session 2026-05-11

- Q: When do migrations run relative to the stack-up command? → A: The application service runs the migration runner on its own startup, before serving traffic; the health endpoint only reports healthy once pending migrations have been applied. `compose up` remains the single user-visible command.
- Q: What does the `/health` endpoint check on each call with respect to the database? → A: Each `/health` call executes a trivial round-trip query (`SELECT 1`) against the database; the endpoint reports unhealthy if the query fails or times out. A single endpoint, no Kubernetes-style liveness/readiness split.
- Q: How deeply does the boilerplate validate the Gemini API key at startup? → A: Present-and-non-empty only. The boilerplate makes no Gemini calls; live validity (typo'd key, revoked key, wrong project) is deferred to the first downstream feature that actually calls Gemini, where the failure mode is naturally surfaced.
- Q: Does the boilerplate include a frontend (Streamlit page or HTMX route)? → A: No. The health endpoint is the only user-visible surface in this feature; any UI is deferred to the query feature, which will own a real endpoint for the UI to call.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Command Local Stand-Up (Priority: P1)

A senior engineer reviewing this codebase for the first time clones the repo, copies `.env.example` to `.env`, fills in a Gemini API key, and runs a single command. Within a couple of minutes both the application service and the vector database service are running, the database has the vector-store schema applied, and a `GET /health` request returns a payload showing both services are reachable.

**Why this priority**: The constitution (Article V.1) requires that the entire system reach a queryable state on a fresh machine with only Docker and a Gemini API key. Without this, none of the downstream RAG features can be demonstrated or evaluated. This is the smallest slice that turns the repo from "files on disk" into a runnable system, and it is what a reviewer encounters first.

**Independent Test**: On a machine with only Docker and a Gemini API key available, run the documented stand-up command. Verify (a) both containers reach a healthy state, (b) the database contains the vector-store schema with the embedding dimension fixed at the constitutionally-mandated value, and (c) the application health endpoint reports both itself and the database as reachable.

**Acceptance Scenarios**:

1. **Given** a clean machine with Docker installed and a Gemini API key, **When** the developer copies `.env.example` to `.env`, fills in the key, and runs the stand-up command, **Then** both containers reach a healthy state within 3 minutes and the application health endpoint responds with HTTP 200.
2. **Given** a running stack, **When** the developer queries the application health endpoint, **Then** the response indicates both the application and the vector database are reachable, and includes the schema version that has been applied.
3. **Given** the stack is brought down and back up, **When** the database container restarts, **Then** previously-applied schema migrations are not re-applied and no data is lost from persisted volumes.
4. **Given** the developer has not provided a Gemini API key in `.env`, **When** the stack starts, **Then** the application surfaces a clear, actionable startup error naming the missing variable rather than failing silently or crashing with an opaque traceback.

---

### User Story 2 - Scripted Developer Commands (Priority: P2)

A developer working on the project needs a small set of canonical commands — for running the stack, running tests, running the linter, and invoking the (yet-to-be-built) ingest, query, and eval workflows. The boilerplate exposes these as a single set of scripted entry points so that downstream feature work plugs into existing slots rather than inventing new ones, and so that the README's setup section stays short.

**Why this priority**: The constitution (Article V.2) requires scripted commands for `ingest`, `query`, `eval`, `test`, and `lint`. Wiring up the **slots** now (as no-op stubs that print a clear "not yet implemented" message and exit non-zero) prevents later features from each defining their own ad-hoc invocation style, and gives the README a stable surface to document immediately.

**Independent Test**: Run each scripted command from a fresh checkout. The stack-up, test, and lint commands must perform real work and exit zero on success. The ingest, query, and eval commands must exist, be discoverable from a single help listing, and exit non-zero with a "not yet implemented" message that names the feature that will deliver them.

**Acceptance Scenarios**:

1. **Given** a fresh checkout, **When** the developer runs the lint command, **Then** the linter executes against the project source tree and reports zero violations on the boilerplate code.
2. **Given** a fresh checkout, **When** the developer runs the test command, **Then** the test runner executes the boilerplate's tests and reports zero failures.
3. **Given** a fresh checkout, **When** the developer runs the ingest, query, or eval command, **Then** the command exits non-zero with a message identifying which downstream feature will implement it, rather than crashing with an import error or running silently.

---

### User Story 3 - Versioned Vector Schema with Provenance Fields (Priority: P2)

A reviewer opens the database migrations directory and sees a single, versioned migration that creates the vector store. The schema pins the embedding dimensionality (per the constitution), and the chunk table already carries the provenance fields that Article II requires of every persisted chunk: source document id, page number, character offsets, and the raw text span. The migration is idempotent across container restarts.

**Why this priority**: Article II ("Citations Carry Real Provenance") is load-bearing for the hiring signal. The schema is the foundation that makes Article II achievable; if it's missing fields, every later feature has to retrofit them. Locking it in at boilerplate time prevents downstream features from inventing inconsistent provenance shapes. Treated as P2 because it sits behind the P1 stand-up flow — but it MUST be present in this feature, not deferred.

**Independent Test**: Inspect the schema in the running database. Verify the chunk table has columns for source document id, page number, character span (start and end offsets), raw text, and an embedding column whose dimensionality matches the constitution-mandated embedding model. Verify the migration runner refuses to re-apply an already-applied migration.

**Acceptance Scenarios**:

1. **Given** a freshly initialized database, **When** the migration runner applies its migrations, **Then** the chunk table exists with columns for source document id, page number, character offsets (start and end), raw text span, embedding vector with pinned dimensionality, and a stable chunk identifier.
2. **Given** a database that already has all migrations applied, **When** the application restarts and the migration runner is invoked again, **Then** no migration is re-applied and the runner exits cleanly.
3. **Given** the schema is in place, **When** an attempt is made to insert a chunk whose embedding vector has the wrong dimensionality, **Then** the database rejects the write with an error that names the dimensionality mismatch.

---

### Edge Cases

- The Gemini API key is missing or empty in `.env`: the application MUST refuse to start with an explicit error naming the missing variable, rather than starting and failing later on the first request. A present-but-invalid key (typo, revoked, wrong project) is **not** detected at boilerplate stage; surfacing that condition is a downstream feature's responsibility.
- The database container is slow to become ready: the application MUST wait for the database to be reachable, then apply pending migrations, before declaring itself healthy — rather than reporting healthy and then erroring on the first request.
- A developer attempts to run the stack on a machine without Docker: the documented stand-up command MUST fail with an error that names Docker as the missing prerequisite.
- A developer attempts to apply a migration that has already been applied: the migration runner MUST be a no-op rather than failing or re-running.
- A developer changes the embedding dimensionality in configuration without updating the schema: the system MUST surface this mismatch at startup, not at query time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide a single documented command that brings the application and vector database containers up to a healthy state on a machine with only Docker and a Gemini API key installed.
- **FR-002**: The application service MUST expose an HTTP health endpoint that, on every call, executes a trivial round-trip query against the vector database and reports unhealthy if the query fails or times out. The response MUST include the currently-applied vector-store schema version. The endpoint MUST NOT report healthy until pending migrations have been applied.
- **FR-003**: The application MUST refuse to start when required environment variables (at minimum, the Gemini API key) are missing or empty, surfacing an error message that names the missing variable. The boilerplate MUST NOT make a live Gemini API call to validate key validity at startup; live validation is the responsibility of the first downstream feature that calls Gemini.
- **FR-004**: The repository MUST contain `.env.example` enumerating every environment variable the boilerplate reads, with safe placeholder values; the real `.env` MUST be excluded from version control.
- **FR-005**: The vector database MUST be provisioned with a versioned migration that creates a chunk table carrying, at minimum: a stable chunk identifier, source document identifier, page number, character offset start, character offset end, raw text span, and an embedding vector column whose dimensionality is pinned to the constitution-mandated value.
- **FR-006**: The migration runner MUST be idempotent — re-running it against an already-migrated database MUST be a no-op rather than an error or a re-application. The application service MUST invoke the migration runner on its own startup, before binding the health endpoint to a healthy state.
- **FR-007**: The boilerplate MUST provide scripted command entry points for: stack stand-up, stack tear-down, test execution, lint execution, ingest, query, and eval. The ingest, query, and eval entry points MUST exist as discoverable stubs that exit non-zero with a clear "not yet implemented" message naming the downstream feature responsible for them.
- **FR-008**: The lint command MUST execute against the boilerplate source tree and report zero violations on the as-shipped code.
- **FR-009**: The test command MUST execute a non-empty test suite that, at minimum, exercises: configuration loading (including the missing-key refusal path), the health endpoint's success response, and migration idempotency. All boilerplate tests MUST pass on a fresh checkout.
- **FR-010**: The application MUST emit structured log records (not free-form prints) for startup, shutdown, configuration load, and health check events.
- **FR-011**: Persistent database state MUST survive container restarts via a named volume; bringing the stack down and back up MUST NOT lose previously-applied schema state.
- **FR-012**: The repository MUST contain a README that includes, at minimum: a one-paragraph problem statement, a section listing prerequisites, the stand-up command, the URL of the health endpoint, and a list of the scripted commands with one-line descriptions of each.
- **FR-013**: All source files added by this feature MUST be type-annotated on public functions and pass the linter's type-related checks where the linter enforces them.
- **FR-014**: The boilerplate MUST NOT include any committed secret values; every credential MUST be sourced from environment variables at runtime.
- **FR-015**: The boilerplate MUST NOT include a frontend (no Streamlit page, no HTMX route, no static HTML beyond what the framework default provides). The health endpoint is the only user-visible surface in this feature; UI work is deferred to the downstream query feature.

### Key Entities *(include if feature involves data)*

- **Chunk**: A unit of text persisted to the vector store, representing a span of source content along with its provenance. Required attributes at the boilerplate stage: stable chunk identifier, source document identifier, page number, character offset start, character offset end, raw text span, and an embedding vector of the constitution-mandated dimensionality. Downstream features will populate this table; the boilerplate only defines the shape.
- **Source Document**: The originating PDF. Identified by a stable identifier that chunk rows reference. The boilerplate need only carry the identifier and the document's display filename; richer metadata (page count, ingest timestamp) is a downstream concern but the schema MUST leave room for it without requiring a breaking migration.
- **Schema Version**: A record of which versioned migrations have been applied to the database. Used by the migration runner to decide which migrations to skip on subsequent runs and surfaced in the health endpoint so a reviewer can confirm the database is at the expected version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer with only Docker and a Gemini API key on a fresh machine can bring the full boilerplate stack to a healthy state in under 5 minutes from clone to a green response on the health endpoint, following only the README.
- **SC-002**: All scripted commands defined by the boilerplate are discoverable from a single help listing, and the test and lint commands exit zero on a fresh checkout 100% of the time.
- **SC-003**: 100% of chunk rows that can be inserted into the vector store carry every constitutionally-mandated provenance field (source document id, page number, character offsets, raw text span); the schema makes it structurally impossible to omit them.
- **SC-004**: Tearing the stack down and bringing it back up preserves applied schema state across at least 10 consecutive restarts with zero schema re-applications and zero data loss.
- **SC-005**: When a required environment variable is missing, the application surfaces a clear, actionable error within 10 seconds of the stand-up command, naming the specific variable rather than producing a generic crash.
- **SC-006**: A reviewer who has never seen the repo can identify, from the README alone, every prerequisite, the stand-up command, and the next feature that will be built on top of this boilerplate — in under 5 minutes of reading.

## Assumptions

- The technology choices in the constitution (Article IV) are binding for this feature. "Scalable vector database" in the user prompt is interpreted as the constitutionally-mandated Postgres + pgvector pairing, which scales horizontally via standard Postgres tooling and is the stack the rest of the project is built against. No deviation is required.
- The Gemini API key is the only third-party credential the boilerplate needs to read at this stage; embedding model identifiers and other Gemini configuration values are read as plain environment variables, not secrets.
- Downstream features (PDF ingestion via Gemini File API, retrieval, generation, evaluation harness) will be specified and built in subsequent `/speckit-specify` invocations and are out of scope here. The boilerplate's job is to leave correctly-shaped slots for them, not to implement them.
- A minimal Streamlit page or single HTMX route is sufficient as the eventual frontend per Article VII, but it is explicitly out of scope for this feature (see FR-015) and will be delivered alongside the query feature that gives the UI something real to call.
- The vector database dimensionality is pinned to the embedding model named in the constitution (768). If the constitution is later amended to change the embedding model, the schema and the configuration default in this feature MUST be updated together.
- The reviewer's machine has internet access to pull base images and Python dependencies on first stand-up; offline operation is not a goal of this feature.
