# ──────────────────────────────────────────────────────────────────────────────
# ⚔️ EOLE.ME — SC2 BUILD ORDER FORGE
# ──────────────────────────────────────────────────────────────────────────────
# Description : Extraction de build orders StarCraft II depuis les replays.
#               Développement local et déploiement automatisé sur le VPS.
# Author      : Julien (Éole) Avarre <hi@eole.me>
# License     : MIT
# ──────────────────────────────────────────────────────────────────────────────

COLOR_RESET   := \033[0m
COLOR_BOLD    := \033[1m
COLOR_CYAN    := \033[1;36m
COLOR_GREEN   := \033[1;32m
COLOR_YELLOW  := \033[1;33m
COLOR_RED     := \033[1;31m
COLOR_MAGENTA := \033[1;35m

RESET             := $(COLOR_RESET)
BOLD              := $(COLOR_BOLD)
STYLE_TITLE       ?= $(COLOR_CYAN)
STYLE_SECTION     ?= $(COLOR_MAGENTA)
STYLE_PHASE       ?= $(COLOR_CYAN)
STYLE_DISCREET    ?= $(COLOR_RESET)
STYLE_INSTRUCTION ?= $(COLOR_GREEN)
STYLE_RESULT      ?= $(COLOR_GREEN)
STYLE_WARNING     ?= $(COLOR_YELLOW)
STYLE_ERROR       ?= $(COLOR_RED)

# ⚙️ INFRASTRUCTURE
VPS_SSH          ?= eole.me
VPS_PROJECT_NAME := $(shell git config --get remote.origin.url 2>/dev/null | sed 's/.*\///; s/\.git$$//' || echo eoleme-sc2-build-order)
VPS_PROJECT_TAG  := $(shell git rev-parse --short HEAD 2>/dev/null || echo "dev")
VPS_PATH         ?= ~/projects/$(VPS_PROJECT_NAME)

PROJECT_NAME := SC2 Build Order Forge
VERSION      := $(shell cat VERSION 2>/dev/null || echo "0.0.0")

# 🔑 SECRETS (DOPPLER)
DOPPLER_PROJECT     := eole-me
DOPPLER_CONFIG_DEV  := dev
DOPPLER_CONFIG_PROD := prd
DOPPLER := $(shell which doppler 2>/dev/null || ( [ -f $(HOME)/bin/doppler ] && echo $(HOME)/bin/doppler ) || echo doppler)

# 🛠️ DOCKER
DOCKER_DIR      := docker
COMPOSE_DEV     := $(DOCKER_DIR)/docker-compose.yml
COMPOSE_PROD    := $(DOCKER_DIR)/docker-compose.prod.yml
DOCKER_SERVICES := sc2-build-order
LOCAL_PORT      := 3050

.PHONY: help dev up down restart logs test venv extract deploy _deploy checklogs

help:
	@printf "\n  $(BOLD)$(STYLE_TITLE)⚔️  $(PROJECT_NAME) $(STYLE_DISCREET)v$(VERSION)$(RESET)\n"
	@printf "  $(STYLE_DISCREET)────────────────────────────────────────────────────────────$(RESET)\n\n"
	@printf "  $(BOLD)$(STYLE_SECTION)❯ Développement local :$(RESET)\n"
	@printf "    $(STYLE_INSTRUCTION)make up$(RESET)          $(STYLE_DISCREET)•$(RESET) Construire et démarrer le conteneur sur http://localhost:$(LOCAL_PORT)\n"
	@printf "    $(STYLE_INSTRUCTION)make down$(RESET)        $(STYLE_DISCREET)•$(RESET) Arrêter le conteneur\n"
	@printf "    $(STYLE_INSTRUCTION)make restart$(RESET)     $(STYLE_DISCREET)•$(RESET) Arrêter puis redémarrer\n"
	@printf "    $(STYLE_INSTRUCTION)make logs$(RESET)        $(STYLE_DISCREET)•$(RESET) Suivre les logs du conteneur local\n"
	@printf "\n  $(BOLD)$(STYLE_SECTION)❯ Qualité :$(RESET)\n"
	@printf "    $(STYLE_INSTRUCTION)make venv$(RESET)        $(STYLE_DISCREET)•$(RESET) Créer l'environnement Python de développement\n"
	@printf "    $(STYLE_INSTRUCTION)make test$(RESET)        $(STYLE_DISCREET)•$(RESET) Lancer la suite de tests\n"
	@printf "\n  $(BOLD)$(STYLE_SECTION)❯ En ligne de commande :$(RESET)\n"
	@printf "    $(STYLE_INSTRUCTION)make extract$(RESET)     $(STYLE_DISCREET)•$(RESET) Extraire le dernier replay joué (variables : ARGS=...)\n"
	@printf "    $(STYLE_DISCREET)   ex. make extract ARGS=\"--last 3 --cutoff 8:00 --clip\"$(RESET)\n"
	@printf "\n  $(BOLD)$(STYLE_SECTION)❯ Production (VPS $(VPS_SSH)) :$(RESET)\n"
	@printf "    $(STYLE_INSTRUCTION)make deploy$(RESET)      $(STYLE_DISCREET)•$(RESET) Déployer sur sc2.eole.me\n"
	@printf "    $(STYLE_INSTRUCTION)make checklogs$(RESET)   $(STYLE_DISCREET)•$(RESET) Suivre les logs de production\n"
	@printf "\n"

# ──────────────────────────────────────────────────────────────────────────────
# 🧪 DÉVELOPPEMENT
# ──────────────────────────────────────────────────────────────────────────────

dev: up

up:
	@printf "$(STYLE_TITLE)✨ Démarrage de l'environnement local...$(RESET)\n"
	@if $(DOPPLER) --version >/dev/null 2>&1; then \
		printf "$(STYLE_PHASE)🔑 Synchronisation des secrets de développement depuis Doppler...$(RESET)\n"; \
		if $(DOPPLER) secrets download --project $(DOPPLER_PROJECT) --config $(DOPPLER_CONFIG_DEV) --no-file --format env > .env.temp 2>/dev/null; then \
			sed 's/="true"/=true/g; s/="false"/=false/g; s/^DOCKER_NETWORK_NAME="\(.*\)"/DOCKER_NETWORK_NAME=\1/g' .env.temp > .env; \
			rm -f .env.temp; \
			printf "$(STYLE_RESULT)✅ Secrets synchronisés.$(RESET)\n"; \
		else \
			rm -f .env.temp; \
			printf "$(STYLE_WARNING)⚠️  Doppler n'a rien renvoyé, on garde le .env existant.$(RESET)\n"; \
			[ -f .env ] || cp $(DOCKER_DIR)/.env.example .env; \
		fi; \
	else \
		printf "$(STYLE_WARNING)⚠️  Doppler absent — utilisation du .env local.$(RESET)\n"; \
		[ -f .env ] || cp $(DOCKER_DIR)/.env.example .env; \
	fi
	@NETWORK_NAME=$$(grep '^DOCKER_NETWORK_NAME=' .env 2>/dev/null | cut -d'=' -f2 | tr -d "\"'"); \
	if [ -n "$$NETWORK_NAME" ] && docker network inspect $$NETWORK_NAME >/dev/null 2>&1; then \
		printf "$(STYLE_RESULT)🔌 Réseau partagé '$$NETWORK_NAME' détecté, intégration à la pile eole.me.$(RESET)\n"; \
		DOCKER_NETWORK_EXTERNAL=true docker compose -f $(COMPOSE_DEV) --env-file .env up -d --build; \
	else \
		printf "$(STYLE_WARNING)ℹ️  Pas de réseau partagé : mode autonome.$(RESET)\n"; \
		DOCKER_NETWORK_NAME=sc2-build-order-standalone DOCKER_NETWORK_EXTERNAL=false \
			docker compose -f $(COMPOSE_DEV) up -d --build; \
	fi
	@printf "$(STYLE_RESULT)🚀 $(PROJECT_NAME) est prêt sur http://localhost:$(LOCAL_PORT)$(RESET)\n"

down:
	@printf "$(STYLE_WARNING)🛑 Arrêt du conteneur local...$(RESET)\n"
	@docker compose -f $(COMPOSE_DEV) --env-file .env down 2>/dev/null \
		|| docker compose -f $(COMPOSE_DEV) down

restart: down up

logs:
	@docker compose -f $(COMPOSE_DEV) logs -f

# ──────────────────────────────────────────────────────────────────────────────
# 🧬 QUALITÉ
# ──────────────────────────────────────────────────────────────────────────────

venv:
	@printf "$(STYLE_PHASE)🐍 Création de l'environnement Python...$(RESET)\n"
	@uv venv
	@uv pip install -r requirements-dev.txt
	@printf "$(STYLE_RESULT)✅ Prêt. Lancez 'make test'.$(RESET)\n"

test:
	@printf "$(STYLE_PHASE)🧪 Tests...$(RESET)\n"
	@if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest -q; \
	else printf "$(STYLE_WARNING)⚠️  Pas d'environnement : lancez 'make venv'.$(RESET)\n"; exit 1; fi

extract:
	@uv run cli.py $(ARGS)

# ──────────────────────────────────────────────────────────────────────────────
# 🚀 DÉPLOIEMENT (VPS)
# ──────────────────────────────────────────────────────────────────────────────

deploy:
	@"$(MAKE)" --no-print-directory _deploy SERVICES="$(DOCKER_SERVICES)"

_deploy:
	@printf "$(STYLE_PHASE)🚀 [1/4]$(RESET) Préparation de l'espace de déploiement sur $(BOLD)$(VPS_SSH)$(RESET)...\n"
	@ssh $(VPS_SSH) "mkdir -p $(VPS_PATH)" >/dev/null
	@printf "$(STYLE_PHASE)📦 [2/4]$(RESET) Envoi de la configuration...\n"
	@scp $(COMPOSE_PROD) $(VPS_SSH):$(VPS_PATH)/docker-compose.prod.yml >/dev/null
	@printf "$(STYLE_PHASE)🔑 [3/4]$(RESET) Transfert des secrets de production depuis Doppler...\n"
	@if $(DOPPLER) --version >/dev/null 2>&1; then \
		if $(DOPPLER) secrets download --project $(DOPPLER_PROJECT) --config $(DOPPLER_CONFIG_PROD) --no-file --format env > .env.prod.temp 2>/dev/null; then \
			sed 's/="true"/=true/g; s/="false"/=false/g; s/^DOCKER_NETWORK_NAME="\(.*\)"/DOCKER_NETWORK_NAME=\1/g' .env.prod.temp > .env.prod.clean; \
			scp .env.prod.clean $(VPS_SSH):$(VPS_PATH)/.env >/dev/null; \
			rm -f .env.prod.temp .env.prod.clean; \
		else \
			printf "$(STYLE_ERROR)❌ Échec du téléchargement des secrets Doppler.$(RESET)\n"; \
			rm -f .env.prod.temp; exit 1; \
		fi; \
	else \
		printf "$(STYLE_ERROR)❌ Doppler introuvable dans le PATH.$(RESET)\n"; exit 1; \
	fi
	@printf "$(STYLE_PHASE)🐳 [4/4]$(RESET) Récupération de l'image et redémarrage...\n"
	@ssh $(VPS_SSH) "cd $(VPS_PATH) && docker compose -f docker-compose.prod.yml pull" >/dev/null
	@ssh $(VPS_SSH) "docker rm -f eole-me-sc2-build-order-prod-container 2>/dev/null || true" >/dev/null
	@ssh $(VPS_SSH) "cd $(VPS_PATH) && docker compose -f docker-compose.prod.yml up -d --remove-orphans" >/dev/null
	@printf "$(STYLE_RESULT)✅ $(PROJECT_NAME) [$(VERSION) / $(VPS_PROJECT_TAG)] déployé sur https://sc2.eole.me$(RESET)\n"

checklogs:
	@printf "$(STYLE_PHASE)📟 Logs de production [$(VPS_SSH)]...$(RESET)\n"
	@ssh $(VPS_SSH) "cd $(VPS_PATH) && docker compose -f docker-compose.prod.yml logs -f"
