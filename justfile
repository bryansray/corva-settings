set shell := ["bash", "-cu"]

default:
    @just --list

sync:
    uv sync --dev

lint:
    uv run ruff check .

lint-fix:
    uv run ruff check --fix .

format:
    uv run ruff format --check .

format-fix:
    uv run ruff format .

type-check:
    uv run ty check src tests

validate: lint format type-check

build:
    uv build

test:
    uv run pytest -q
