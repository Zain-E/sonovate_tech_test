-include .env
export

DBT = uv run dbt --no-use-colors
DBT_ARGS = --project-dir transform --profiles-dir transform

.PHONY: install run ingest transform answers app test lint format docs

install:            ## install dependencies
	uv sync

run: ingest transform answers  ## full pipeline: API -> DuckDB -> dbt -> ANSWERS.md

ingest:             ## load Companies House search results into raw_companies_house
	uv run python -m ingestion.pipeline

transform:          ## build + test all dbt models (staging -> warehouse -> analytics)
	$(DBT) build $(DBT_ARGS)

answers:            ## write ANSWERS.md from the analytics layer
	uv run python -m reporting.answers

app:                ## launch the Streamlit dashboard
	uv run streamlit run app/streamlit_app.py

test:               ## unit tests + end-to-end test against a recorded API response
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

docs:               ## browse dbt docs and lineage
	$(DBT) docs generate $(DBT_ARGS) && $(DBT) docs serve $(DBT_ARGS)
