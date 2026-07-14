# Makefile — Line IT Ticket System
# ครอบ deploy.sh + คำสั่ง docker compose ที่ใช้บ่อย
.DEFAULT_GOAL := help

COMPOSE      := docker compose -f docker-compose.yml
COMPOSE_DEV  := docker compose -f docker-compose.dev.yml

.PHONY: help deploy deploy-dev down down-dev logs logs-dev ps migrate rebuild clean

help: ## แสดงคำสั่งทั้งหมด
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

deploy: ## deploy production (build + up + migrate)
	@./deploy.sh

deploy-dev: ## deploy dev (docker-compose.dev.yml + .env.dev)
	@./deploy.sh dev

down: ## หยุดทุก service (คง volume)
	@./deploy.sh down

down-dev: ## หยุด service dev
	@$(COMPOSE_DEV) down

logs: ## ตาม log ของ backend (prod)
	@./deploy.sh logs

logs-dev: ## ตาม log ของ backend (dev)
	@$(COMPOSE_DEV) logs -f backend

ps: ## แสดงสถานะ service
	@$(COMPOSE) ps

migrate: ## รัน alembic upgrade head (prod)
	@$(COMPOSE) exec -T backend alembic upgrade head

rebuild: ## build ใหม่แบบไม่ใช้ cache แล้ว up
	@$(COMPOSE) build --no-cache && $(COMPOSE) up -d

clean: ## หยุด + ลบ volume ทั้งหมด (⚠️ ลบข้อมูล DB/MinIO)
	@$(COMPOSE) down -v
