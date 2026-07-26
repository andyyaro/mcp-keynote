# Keynote-MCP Makefile (uv-based)

.PHONY: help sync test test-cov test-integration lint format check build clean server

help: ## Show help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install/refresh the venv from uv.lock (incl. dev group)
	uv sync --dev

test: ## Run unit tests (no Keynote needed)
	uv run pytest tests/

test-cov: ## Unit tests with coverage report
	uv run pytest tests/ --cov=keynote_mcp --cov-report=term-missing

test-integration: ## Run integration tests against a REAL Keynote (local only - never in CI; needs Automation + Accessibility permission, steals window focus while running)
	uv run pytest -m keynote

lint: ## Ruff lint + mypy strict
	uv run ruff check src/ tests/
	uv run mypy

format: ## Auto-format with ruff
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

check: ## Everything CI runs: lint, format check, unit tests + coverage gate
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy
	uv run pytest tests/ --cov=keynote_mcp --cov-fail-under=85

build: ## Build sdist + wheel
	uv build

clean: ## Remove build/test artifacts
	rm -rf dist/ build/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +

server: ## Run the MCP server on stdio (for manual protocol poking)
	uv run keynote-mcp
