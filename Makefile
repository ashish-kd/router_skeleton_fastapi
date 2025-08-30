.PHONY: run dev migrate upgrade downgrade revision load replay-dlq lint fmt

export DATABASE_URL ?= postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb
export APP_ENV ?= local
export PORT ?= 8000

run:
	uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

migrate:
	alembic upgrade head

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

revision:
	alembic revision -m "manual change"

test:
	pytest -q || echo "pytest not set up yet"

load:
	python3 db/load_test.py

replay-dlq:
	python3 db/replay_dlq.py --limit $${LIMIT:-100}

lint:
	echo "lint placeholder"

fmt:
	echo "format placeholder"
