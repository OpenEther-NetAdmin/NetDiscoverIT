# =============================================================================
# NetDiscoverIT Makefile
# =============================================================================
# Common development tasks
# Usage: make <target>
# =============================================================================

# =============================================================================
# VARIABLES
# =============================================================================
COMPOSE := docker compose
COMPOSE_PROD := docker compose -f docker-compose.prod.yml
PYTHON := python3
PIP := pip3
NODE := node
NPM := npm

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# =============================================================================
# HELP
# =============================================================================
.PHONY: help
help:
	@echo ""
	@echo "$(GREEN)NetDiscoverIT Makefile$(NC)"
	@echo ""
	@echo "Available targets:"
	@echo "  $(YELLOW)setup$(NC)           - Initial setup (install deps, create env)"
	@echo "  $(YELLOW)up$(NC)              - Start all services"
	@echo "  $(YELLOW)down$(NC)            - Stop all services"
	@echo "  $(YELLOW)restart$(NC)         - Restart all services"
	@echo "  $(YELLOW)logs$(NC)            - View logs"
	@echo "  $(YELLOW)logs-api$(NC)        - View API logs"
	@echo "  $(YELLOW)logs-agent$(NC)      - View agent logs"
	@echo "  $(YELLOW)clean$(NC)           - Clean up containers and volumes"
	@echo "  $(YELLOW)rebuild$(NC)         - Rebuild Docker images"
	@echo ""
	@echo "  $(YELLOW)install-deps$(NC)    - Install Python dependencies"
	@echo "  $(YELLOW)install-node-deps$(NC) - Install Node dependencies"
	@echo ""
	@echo "  $(YELLOW)test$(NC)            - Run tests"
	@echo "  $(YELLOW)test-cov$(NC)        - Run tests with coverage"
	@echo "  $(YELLOW)lint$(NC)            - Run linters"
	@echo ""
	@echo "  $(YELLOW)api-shell$(NC)       - Open API shell"
	@echo "  $(YAME)db-shell$(NC)         - Open PostgreSQL shell"
	@echo ""
	@echo "  $(YELLOW)format$(NC)          - Format code"
	@echo ""

# =============================================================================
# DOCKER
# =============================================================================
setup:
	@echo "Setting up development environment..."
	cp .env.example .env
	mkdir -p data logs
	@echo "Setup complete. Edit .env file and run 'make up'"

up:
	$(COMPOSE) up -d
	@echo "Services started. API: http://localhost:8000"
	@echo "Frontend: http://localhost:3000"

up-build:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

logs-agent:
	$(COMPOSE) logs -f agent

logs-frontend:
	$(COMPOSE) logs -f frontend

clean:
	$(COMPOSE) down -v
	rm -rf data/* logs/*
	@echo "Cleaned up containers and volumes"

rebuild:
	$(COMPOSE) build --no-cache

# =============================================================================
# DATABASE
# =============================================================================
db-migrate:
	$(COMPOSE) exec api alembic upgrade head

db-migrate-create:
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(MESSAGE)"

db-shell:
	$(COMPOSE) exec postgres psql -U netdiscoverit -d netdiscoverit

db-backup:
	$(COMPOSE) exec postgres pg_dump -U netdiscoverit netdiscoverit > backup_$$(date +%Y%m%d_%H%M%S).sql

# =============================================================================
# DEVELOPMENT
# =============================================================================
install-deps:
	$(PIP) install -r services/api/requirements.txt

install-node-deps:
	cd services/frontend && $(NPM) install

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=services/api --cov-report=html --cov-report=term

lint:
	flake8 services/api --max-line-length=120 --ignore=E501,W503
	black --check services/api
	cd services/frontend && npm run lint

format:
	black services/api
	cd services/frontend && npm run format

# =============================================================================
# SHELLS
# =============================================================================
api-shell:
	$(COMPOSE) exec api /bin/bash

agent-shell:
	$(COMPOSE) exec agent /bin/bash

# =============================================================================
# BUILD
# =============================================================================
build:
	$(COMPOSE) build

build-prod:
	$(COMPOSE_PROD) build

push:
	$(COMPOSE) push

# =============================================================================
# RELEASE
# =============================================================================
release:
	@echo "Creating release..."
	git tag -a v$$(cat VERSION) -m "Release v$$(cat VERSION)"
	git push origin v$$(cat VERSION)
	@echo "Release v$$(cat VERSION) pushed. CD will run automatically."
