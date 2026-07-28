.PHONY: bootstrap up down migrate seed fmt lint typecheck test contracts check

API_DIR := apps/api
WEB_DIR := apps/web

bootstrap:
	cd $(API_DIR) && uv sync --extra dev
	pnpm install

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd $(API_DIR) && uv run alembic -c alembic.ini upgrade head

seed:
	cd $(API_DIR) && uv run alembic -c alembic.ini upgrade head

fmt:
	cd $(API_DIR) && uv run ruff format .
	pnpm --filter @kairos/web exec prettier --write . || true

lint:
	cd $(API_DIR) && uv run ruff format --check . && uv run ruff check .
	pnpm --filter @kairos/web lint

typecheck:
	cd $(API_DIR) && uv run mypy app
	pnpm --filter @kairos/web typecheck

test:
	cd $(API_DIR) && uv run pytest

contracts:
	cd $(API_DIR) && uv run python -m app.export_openapi ../../packages/contracts/openapi.json
	pnpm --filter @kairos/contracts generate

check: lint typecheck test
