.PHONY: run dev start migrate upgrade downgrade revision test test-unit test-integration test-coverage test-fast load replay-dlq lint fmt

export DATABASE_URL ?= postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb
export APP_ENV ?= local
export PORT ?= 8000

run:
	uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

start:
	docker compose up -d
	docker compose exec router alembic upgrade head

migrate:
	alembic upgrade head

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

revision:
	alembic revision -m "manual change"

test:
	pytest -v --cov=app --cov-report=term-missing

test-unit:
	pytest tests/ -v -m "not integration"

test-integration:
	pytest tests/ -v -m "integration"

test-coverage:
	pytest --cov=app --cov-report=html --cov-report=term-missing --cov-fail-under=90

test-fast:
	pytest tests/ -x -v

load:
	python db/load_test.py

replay-dlq:
	python3 db/replay_dlq.py --limit $${LIMIT:-100}

lint:
	echo "lint placeholder"

fmt:
	echo "format placeholder"
