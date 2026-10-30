.PHONY: setup rodar test lint

setup:   ## instala o projeto e as dependências de desenvolvimento
	pip install -e ".[dev]"

rodar:   ## sobe a API + simulador em http://localhost:8000
	python -m uvicorn lojabot.app:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check .
