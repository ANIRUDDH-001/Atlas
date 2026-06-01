.PHONY: up down test smoke ci lint typecheck clean

# Start all services
up:
	docker compose up -d

# Stop all services and remove volumes
down:
	docker compose down -v --remove-orphans

# Run unit tests
test:
	python3 -m pytest tests/ -v --tb=short

# Run smoke tests against live services
smoke: up
	@sleep 10
	bash scripts/smoke_test.sh

# Lint
lint:
	python3 -m ruff check pipeline/ app/ tests/

# Type check
typecheck:
	python3 -m mypy pipeline/ app/ --ignore-missing-imports

# Full CI: lint + typecheck + tests + smoke
ci: lint typecheck test smoke
	@echo "All CI checks passed"

# Clean generated files
clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f data/events.jsonl
