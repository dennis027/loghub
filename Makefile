# LogHub developer tasks. Run `make` (or `make help`) for the list.
# Everything runs in containers; the host needs only Docker and make.

SHELL := /bin/bash
COMPOSE := docker compose
API := $(COMPOSE) exec -T django-api
UID := $(shell id -u)
GID := $(shell id -g)
RUFF = docker run --rm --user $(UID):$(GID) -e HOME=/tmp -v $(CURDIR)/backend:/src -w /src python:3.12.7-slim \
	sh -c 'pip install -q --user ruff==0.7.1 2>/dev/null && /tmp/.local/bin/ruff $(1)'
NODE := docker run --rm --user $(UID):$(GID) -e HOME=/tmp -e NG_CLI_ANALYTICS=false -v $(CURDIR)/frontend:/app -w /app node:22.11.0-alpine

.DEFAULT_GOAL := help

## ---- Stack -------------------------------------------------------------
env: ## Create .env with random secrets (once)
	./scripts/init-env.sh

up: ## Build and start the stack (dev overrides applied)
	$(COMPOSE) up -d --build

up-prod: ## Start with the base compose file only (no dev overrides)
	$(COMPOSE) -f docker-compose.yml up -d --build

down: ## Stop and remove containers (data volumes are kept)
	$(COMPOSE) down

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow logs (S=service to filter, e.g. make logs S=logstash)
	$(COMPOSE) logs -f --tail=100 $(S)

demo: ## Start the synthetic log generator
	$(COMPOSE) --profile demo up -d demo-generator

## ---- Backend -----------------------------------------------------------
migrate: ## Apply database migrations
	$(API) python manage.py migrate

migrations: ## Create migrations for model changes (files owned by you)
	$(COMPOSE) run --rm --no-deps --user "$(UID):$(GID)" -e HOME=/tmp django-api python manage.py makemigrations

shell: ## Django shell
	$(COMPOSE) exec django-api python manage.py shell

## ---- Quality -----------------------------------------------------------
test: test-backend test-frontend ## Run all unit tests

test-backend: ## Backend unit tests (pytest)
	$(API) env TESTING=true pytest -p no:cacheprovider

test-integration: ## End-to-end tests against the running stack
	$(API) env TESTING=true pytest -p no:cacheprovider -m integration

test-frontend: ## Frontend unit tests (headless Chromium)
	docker build -q -f frontend/Dockerfile.test -t loghub/frontend-test frontend >/dev/null
	docker run --rm loghub/frontend-test

lint: lint-backend lint-frontend ## Lint everything

lint-backend: ## Ruff lint + format check
	$(call RUFF,check --no-cache .)
	$(call RUFF,format --no-cache --check .)

lint-frontend: ## angular-eslint (TS + template accessibility rules)
	$(NODE) npx ng lint

fmt: ## Auto-format backend code
	$(call RUFF,check --no-cache --fix .)
	$(call RUFF,format --no-cache .)

check: lint test ## Everything CI runs

## ---- Operations --------------------------------------------------------
backup: ## Back up Postgres, Elasticsearch, Grafana, Graylog to ./backups
	./scripts/backup.sh

restore: ## Restore a backup: make restore B=backups/<timestamp>
	./scripts/restore.sh $(B)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^## ----/ {s = substr($$0, 9); gsub(/ *-+$$/, "", s); printf "\n\033[1m%s\033[0m\n", s} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: env up up-prod down ps logs demo migrate migrations shell test test-backend test-integration test-frontend \
	lint lint-backend lint-frontend fmt check backup restore help
