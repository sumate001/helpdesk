#!/usr/bin/env bash
# deploy.sh — deploy Line IT Ticket System ด้วยคำสั่งเดียว
#   ./deploy.sh          → build + up + migrate (production, docker-compose.yml)
#   ./deploy.sh dev      → เหมือนกันแต่ใช้ docker-compose.dev.yml + .env.dev
#   ./deploy.sh down     → หยุดทุก service (คง volume ไว้)
#   ./deploy.sh logs     → ตาม log ของ backend
set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-prod}"

if [ "$MODE" = "dev" ]; then
  COMPOSE_FILE="docker-compose.dev.yml"
  ENV_FILE=".env.dev"
else
  COMPOSE_FILE="docker-compose.yml"
  ENV_FILE=".env"
fi

# docker compose (v2) หรือ docker-compose (v1)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi
COMPOSE="$DC -f $COMPOSE_FILE"

log() { printf '\033[1;36m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[deploy] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

case "${1:-}" in
  down) log "หยุด service…"; exec $COMPOSE down ;;
  logs) exec $COMPOSE logs -f backend ;;
esac

# 1. ต้องมีไฟล์ env
if [ ! -f "$ENV_FILE" ]; then
  if [ "$MODE" = "dev" ]; then
    die "ไม่พบ $ENV_FILE — คัดลอกจาก .env.example: cp .env.example $ENV_FILE"
  fi
  log "ไม่พบ $ENV_FILE — สร้างจาก .env.example ให้ (อย่าลืมกรอกค่า LINE_*/JWT_SECRET_KEY)"
  cp .env.example "$ENV_FILE"
  die "กรอกค่าใน $ENV_FILE (LINE token/secret, JWT_SECRET_KEY, ฯลฯ) แล้วรัน deploy อีกครั้ง"
fi

# เตือนถ้ายังใช้ค่า default ที่ไม่ปลอดภัยใน production
if [ "$MODE" != "dev" ] && grep -q '^JWT_SECRET_KEY=change-me-in-production' "$ENV_FILE"; then
  die "JWT_SECRET_KEY ยังเป็นค่า default — เปลี่ยนใน $ENV_FILE ก่อน deploy production"
fi

# 2. build + start
log "build image + start service ($COMPOSE_FILE)…"
$COMPOSE up -d --build

# 3. รอ postgres พร้อมรับ connection
log "รอ postgres พร้อม…"
for i in $(seq 1 30); do
  if $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-itticket}" >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 30 ] && die "postgres ไม่พร้อมภายใน 60 วินาที"
  sleep 2
done

# 4. รัน migration (schema จัดการด้วย Alembic เท่านั้น — main.py ไม่ auto-migrate)
log "รัน alembic upgrade head…"
$COMPOSE exec -T backend alembic upgrade head

log "เสร็จแล้ว 🎉  ดู log: ./deploy.sh ${MODE/prod/}logs"
$COMPOSE ps
