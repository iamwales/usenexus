.PHONY: help dev stop migrate lint test test-unit test-integration smoke eval

help:
	@echo "Nexus development commands"
	@echo ""
	@echo "  make dev          Start full local stack"
	@echo "  make stop         Stop all containers"
	@echo "  make migrate      Run DB migrations"
	@echo "  make lint         Run ruff + mypy"
	@echo "  make test         Run unit + integration tests"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make smoke        Check local service health"
	@echo "  make eval         Run RAGAS evaluation suite"

dev:
	cp -n .env.example .env || true
	docker compose up -d
	@echo "Waiting for services..."
	sleep 8
	$(MAKE) migrate
	@echo ""
	@echo "✓ Nexus running at http://localhost:8000"
	@echo "  API docs:   http://localhost:8000/docs"
	@echo "  Grafana:    http://localhost:3001"
	@echo "  Qdrant UI:  http://localhost:6333/dashboard"

stop:
	docker compose down

migrate:
	docker compose exec api uv run alembic -c services/api/alembic.ini upgrade head

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/ services/ --ignore-missing-imports

format:
	uv run ruff format .
	uv run ruff check --fix .

test-unit:
	uv run pytest tests/unit packages/ services/ \
		--ignore=tests/integration --ignore=tests/e2e \
		-v --tb=short

test-integration:
	docker compose -f docker-compose.test.yml up -d
	uv run pytest tests/integration -v --tb=short
	docker compose -f docker-compose.test.yml down

test: test-unit test-integration

smoke:
	uv run python scripts/smoke_local.py

eval:
	uv run python evals/run_ragas.py \
		--dataset evals/golden/ \
		--output evals/results/

logs:
	docker compose logs -f api ingestion worker

shell:
	docker compose exec api uv run python

create-org:
	@read -p "Org name: " name; \
	curl -s -X POST http://localhost:8000/v1/internal/organizations \
		-H "Content-Type: application/json" \
		-d "{\"name\": \"$$name\", \"slug\": \"$$(echo $$name | tr ' ' '-' | tr '[:upper:]' '[:lower:]')\"}" | python3 -m json.tool
