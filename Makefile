.PHONY: install api test lint format persistence persistence-up persistence-down verify-persistence check-fresh

install:
	uv sync --all-extras

check-fresh:
	@git fetch origin develop --quiet 2>/dev/null || true; \
	BEHIND=$$(git rev-list HEAD..origin/develop --count 2>/dev/null || echo 0); \
	if [ "$$BEHIND" != "0" ]; then \
		echo "WARNING: your local develop is $$BEHIND commit(s) behind origin/develop -- run 'git pull' or you may be serving stale API behavior."; \
	fi

persistence-up:
	docker compose -f docker-compose.persistence.yml up -d
	@echo "Waiting for DynamoDB Local..."
	@sleep 2
	$(MAKE) persistence

persistence-down:
	docker compose -f docker-compose.persistence.yml down

persistence:
	set -a && [ -f .env.local ] && . ./.env.local; set +a && \
	uv run python scripts/ensure_dev_persistence.py

verify-persistence:
	set -a && [ -f .env.local ] && . ./.env.local; set +a && \
	uv run python scripts/verify_persistence.py

api: check-fresh
	set -a && [ -f .env.local ] && . ./.env.local; set +a && \
	uv run uvicorn civilai_platform.app:create_app --factory --reload --port 8001

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

openapi:
	uv run python scripts/generate_openapi.py
