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
NPM := npm

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# =============================================================================
# HELP
# =============================================================================
.PHONY: help gcp-init gcp-plan gcp-up gcp-down gcp-status gcp-ssh-cloud gcp-ssh-agent gcp-log-cloud gcp-log-agent
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
	@echo "  $(YELLOW)install-node-deps$(NC) - Install Node dependencies"
	@echo ""
	@echo "  $(YELLOW)test$(NC)            - Run tests"
	@echo "  $(YELLOW)test-cov$(NC)        - Run tests with coverage"
	@echo "  $(YELLOW)lint$(NC)            - Run linters"
	@echo ""
	@echo "  $(YELLOW)api-shell$(NC)       - Open API shell"
	@echo "  $(YELLOW)db-shell$(NC)         - Open PostgreSQL shell"
	@echo ""
	@echo "  $(YELLOW)format$(NC)          - Format code"
	@echo ""
	@echo "GCP test environment:"
	@echo "  $(YELLOW)gcp-init$(NC)        - Initialize Terraform"
	@echo "  $(YELLOW)gcp-plan$(NC)        - Dry-run Terraform plan"
	@echo "  $(YELLOW)gcp-up$(NC)          - Provision GCP test environment"
	@echo "  $(YELLOW)gcp-down$(NC)        - Destroy GCP test environment"
	@echo "  $(YELLOW)gcp-status$(NC)      - Show VM IPs and URLs"
	@echo "  $(YELLOW)gcp-ssh-cloud$(NC)   - SSH into cloud-vm"
	@echo "  $(YELLOW)gcp-ssh-agent$(NC)   - SSH into agent-vm"
	@echo "  $(YELLOW)gcp-log-cloud$(NC)   - Tail cloud-vm startup log"
	@echo "  $(YELLOW)gcp-log-agent$(NC)   - Tail agent-vm startup log"
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
install-node-deps:
	cd services/frontend && $(NPM) install

test:
	$(COMPOSE) exec api pytest tests/ -v

test-cov:
	$(COMPOSE) exec api pytest tests/ --cov=app --cov-report=html --cov-report=term

lint:
	$(COMPOSE) exec api flake8 app --max-line-length=120 --ignore=E501,W503
	$(COMPOSE) exec api black --check app
	$(COMPOSE) exec frontend npm run lint

format:
	$(COMPOSE) exec api black app
	$(COMPOSE) exec frontend npm run format

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

# =============================================================================
# GCP TEST ENVIRONMENT
# =============================================================================
# Prerequisites: gcloud CLI authenticated, terraform installed, terraform.tfvars
# filled in at infra/gcp/terraform.tfvars (see terraform.tfvars.example).
# =============================================================================
GCP_ZONE ?= $(shell cd infra/gcp && terraform output -raw zone 2>/dev/null || echo "us-central1-a")
GCP_PROJECT ?= $(shell cd infra/gcp && terraform output -raw project_id 2>/dev/null || echo "not-initialized")

gcp-init:
	cd infra/gcp && terraform init

gcp-plan:
	cd infra/gcp && terraform plan

gcp-up:
	cd infra/gcp && terraform apply -auto-approve
	@echo ""
	@echo "Startup scripts are running on the VMs. Monitor with:"
	@echo "  make gcp-log-cloud"
	@echo "  make gcp-log-agent"

gcp-down:
	cd infra/gcp && terraform destroy -auto-approve

gcp-status:
	cd infra/gcp && terraform output

gcp-ssh-cloud:
	gcloud compute ssh cloud-vm --zone=$(GCP_ZONE) --tunnel-through-iap

gcp-ssh-agent:
	gcloud compute ssh agent-vm --zone=$(GCP_ZONE) --tunnel-through-iap

gcp-log-cloud:
	gcloud compute ssh cloud-vm --zone=$(GCP_ZONE) --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'

gcp-log-agent:
	gcloud compute ssh agent-vm --zone=$(GCP_ZONE) --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'
