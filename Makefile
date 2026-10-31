# Developer entry points. `make check` runs everything CI runs except the secret scan and audits.

PYTHON ?= python3
FRONTEND := cd frontend &&

.DEFAULT_GOAL := help
.PHONY: help install dev lint fmt typecheck test audit check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install Python + frontend dependencies and the git hooks
	$(PYTHON) -m pip install -r requirements-dev.txt pre-commit pip-audit
	$(FRONTEND) npm ci
	pre-commit install

dev: ## Run the web demo with Vite
	$(FRONTEND) npm run dev

lint: ## Check Python lint and formatting
	ruff check .
	ruff format --check .

fmt: ## Fix Python lint findings and formatting
	ruff check --fix .
	ruff format .

typecheck: ## Run mypy --strict and the frontend type check
	mypy agent.py
	$(FRONTEND) npm run typecheck

test: ## Run the Python and frontend tests
	pytest -q
	$(FRONTEND) npm test

audit: ## Audit Python and npm dependencies
	pip-audit -r requirements-dev.txt
	$(FRONTEND) npm audit --audit-level=high

check: lint typecheck test ## Everything that must pass before pushing
	$(FRONTEND) npm run build
