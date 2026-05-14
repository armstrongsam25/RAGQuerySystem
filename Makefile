# Single dispatcher for every command in this project. Each target is a
# single docker-compose or uv invocation. `make help` lists every target.

.DEFAULT_GOAL := help
.PHONY: help up down logs test test-integration lint fmt ingest reingest query eval serve sample-pdf

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make <target>\n\nTargets:\n"} \
	/^[a-zA-Z_-]+:.*##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

up: ## Build the app image and start the full stack (app + db).
	docker compose up -d --build

down: ## Stop and remove the stack containers. Named volumes are preserved.
	docker compose down

logs: ## Tail the app container logs.
	docker compose logs -f app

test: ## Run the hermetic unit-test tier (no Docker required).
	uv run pytest

test-integration: ## Run the integration tier (requires `make up` already running).
	RUN_INTEGRATION=1 uv run pytest -m integration

lint: ## Run ruff lint + formatter check.
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Apply ruff's auto-formatter and import sorter.
	uv run ruff check --fix .
	uv run ruff format .

sample-pdf: ## Generate data/sample.pdf (one-time after fresh clone).
	uv run python scripts/make_sample_pdf.py

ingest: ## Ingest the committed sample PDF. Override with `uv run rag ingest <path>`.
	docker compose exec app rag ingest data/sample.pdf

reingest: ## Re-ingest the sample PDF, overwriting any prior state (--force).
	docker compose exec app rag ingest --force data/sample.pdf

query: ## Ask a question. Usage: make query QUESTION='your question here'
	docker compose exec app rag query "$(QUESTION)"

eval: ## Run the eval set against the running stack and write evals/results.{jsonl,md}.
	docker compose exec app rag eval

serve: ## Run the FastAPI service via uvicorn directly (non-Docker dev).
	uv run rag serve
