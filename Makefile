.PHONY: setup test demo lint

setup:
	python3.12 -m venv .venv || python -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	docker compose up -d db
	.venv/bin/python -m app.seed

test:
	.venv/bin/python -m pytest -q

demo:
	.venv/bin/python -m app.seed
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

lint:
	.venv/bin/ruff check .
