# Pre-polish baseline

**Branch**: `005-code-review-polish`
**Captured**: 2026-05-14
**Reviewer**: Sam Armstrong

The starting state the polish pass measures itself against. Every regression is detectable by diffing this file against `eval-final.md`.

## Lint

`uv run ruff check .` → exits 0 (no errors, no warnings) at branch creation.

`uv run ruff format --check .` → reports 3 files needing reformat (`src/rag/providers/gemini.py`, `src/rag/ui/routes.py`, `tests/unit/test_ui_brand_contract.py`). Closed by the format-autofix commit during foundational phase.

## Tests

`uv run pytest -q` → **9 failed, 118 passed, 8 deselected** at branch creation.

Failure list (root causes diagnosed during US1 sweep):

1. `tests/unit/test_current_doc.py` × 3 — template was rewritten (`current-doc-card` replaced the legacy `doc-chip` markup) and the test was not updated.
2. `tests/unit/test_gemini_judge.py` × 2 — pytest entry-point was resolving to the wrong virtualenv (`NymblTechAssessment\.venv`) because the `.venv/Scripts/*.exe` shims were copied from another workspace. Their hardcoded interpreter path pointed at the old project's stale `gemini.py` (which still raised `NotImplementedError("judge not implemented")`).
3. `tests/unit/test_ui_brand_contract.py` × 2 — test fixture asserted a legacy ink/paper/signal/stone palette that was never shipped; the actual `styles.css` uses navy/purple. Also one raw `#FFFFFF` literal in `--white`.
4. `tests/unit/test_ui_routes.py` × 1 — root page template no longer carries `id="chat-thread"` after the UI refactor.
5. `tests/unit/test_upload_progress.py` × 1 — terminal-success copy was "Upload complete"; test asserted legacy "Ingested".

## Secret scan

`docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact` → **17 findings**, all in `.venv/` (gitignored upstream package fixtures and RFC reference values mis-classified as keys) plus 1 in `.env` (user's local Gemini key — gitignored). Zero hits on the committed surface.

Resolved by committing `.gitleaks.toml` with an allowlist that excludes `.venv/`, `.env`, and bytecode caches — the post-polish rescan reports **0 leaks**.

## Eval

n/a — harness stubbed at baseline. First eval run lands in `eval-final.md`.

`evals/questions.jsonl` contained 2 entries (1 factoid + 1 out-of-scope), below Article III.1's ≥10 requirement.

## Repo state

```
$ git rev-parse HEAD
0ed91276dfb0ff04df4b6f5bf6e2eaba1fab8c00
```

Working tree contained only spec-kit setup artifacts (`.specify/feature.json`, `CLAUDE.md` plan-link bump, and the new `specs/005-code-review-polish/` directory) prior to first commit.
