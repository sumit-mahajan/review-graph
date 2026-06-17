.PHONY: install dev dev-api dev-worker check lint typecheck test eval \
        db-migrate db-upgrade db-downgrade clean

# ── Setup ────────────────────────────────────────────────────────────────────
install:
	cd backend && uv sync
	cd frontend && npm ci
	pre-commit install
	@echo "✓ Dependencies installed. Copy .env.example → .env and fill in values."

# ── Local development ─────────────────────────────────────────────────────────
# docker-compose runs api + worker; Neon + Upstash come from .env (same as prod).
dev:
	docker compose up --build

dev-api:
	cd backend && uv run uvicorn src.api.main:app --reload --port 8000

dev-worker:
	cd backend && uv run uvicorn worker.http:app --reload --host 0.0.0.0 --port 8001

dev-frontend:
	cd frontend && npm run dev

# ── Quality checks ────────────────────────────────────────────────────────────
check: lint typecheck test

lint:
	cd backend && uv run ruff check src/ tests/
	cd backend && uv run ruff format --check src/ tests/
	cd frontend && npx eslint src/ --ext .ts,.tsx --max-warnings 0

typecheck:
	cd backend && uv run mypy src/
	cd frontend && npx tsc --noEmit

test:
	cd backend && uv run pytest tests/ -v
	cd frontend && npx vitest run

test-backend:
	cd backend && uv run pytest tests/ -v --cov=src --cov-report=term-missing

test-frontend:
	cd frontend && npx vitest run --coverage

# ── Evaluation ────────────────────────────────────────────────────────────────
eval:
	cd backend && uv run python -m evals.runner

# ── Database ──────────────────────────────────────────────────────────────────
db-migrate:
	cd backend && uv run alembic revision --autogenerate -m "$(message)"

db-upgrade:
	cd backend && uv run alembic upgrade head

db-downgrade:
	cd backend && uv run alembic downgrade -1

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	cd frontend && rm -rf dist node_modules/.cache 2>/dev/null || true
