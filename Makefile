# =============================================================================
# HADES — developer entrypoints. Everything runs through Docker; nothing is
# installed on the host. (Linux/Docker only — see hades.md.)
# =============================================================================
.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: init
init: ## Create .env from the template (first-time setup)
	@test -f .env || cp .env.example .env
	@echo "-> .env ready. Edit secrets before starting."

.PHONY: up
up: ## Start the full stack in the background
	$(COMPOSE) up -d

.PHONY: up-all
up-all: ## Start everything incl. analytics + observability profiles
	$(COMPOSE) --profile analytics --profile observability up -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

.PHONY: build
build: ## Rebuild images
	$(COMPOSE) build

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) run --rm api alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration:  make revision m="add x"
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

.PHONY: test
test: ## Run the backend test suite
	$(COMPOSE) run --rm api pytest

.PHONY: lint
lint: ## Run ruff + mypy
	$(COMPOSE) run --rm api sh -c "ruff check . && mypy src"

.PHONY: fmt
fmt: ## Auto-format the codebase
	$(COMPOSE) run --rm api ruff format .

.PHONY: shell
shell: ## Open a shell in the api container
	$(COMPOSE) run --rm api sh

.PHONY: ps
ps: ## Show service status
	$(COMPOSE) ps

.PHONY: backup
backup: ## Create a backup now (DB + config + models + research + docs)
	$(COMPOSE) run --rm scheduler hades-backup

.PHONY: logs-service
logs-service: ## Tail one service's logs:  make logs-service s=watchdog
	$(COMPOSE) logs -f --tail=100 $(s)
