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

# ไม่มี docker → ติดตั้งให้เลย (ใช้ script ทางการ, จะถาม sudo password)
if ! command -v docker >/dev/null 2>&1; then
  printf '\033[1;36m[deploy]\033[0m ไม่พบ docker — กำลังติดตั้งให้ (ต้องใช้ sudo)…\n'
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  sudo systemctl enable --now docker
fi

# docker compose (v2) หรือ docker-compose (v1)
if docker compose version >/dev/null 2>&1 || sudo docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  printf '\033[1;31m[deploy] ERROR:\033[0m ติดตั้ง docker compose ไม่สำเร็จ\n' >&2
  exit 1
fi

# ยังไม่อยู่ใน group docker (เพิ่ง usermod, ยังไม่ logout) → ใช้ sudo ไปก่อน
if ! docker info >/dev/null 2>&1; then
  DC="sudo $DC"
  printf '\033[1;36m[deploy]\033[0m ใช้ sudo เรียก docker รอบนี้ (logout/login ใหม่แล้วจะไม่ต้อง)\n'
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

# โหลดตัวแปรจาก env file มาใช้ในสคริปต์ (POSTGRES_USER/DB, ADMIN_* ฯลฯ)
set -a; . "./$ENV_FILE"; set +a

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

# 5. seed admin เริ่มต้นถ้ายังไม่มี user เลย (ตั้งรหัสผ่าน ADMIN_PASSWORD ใน env ได้)
USER_COUNT=$($COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-itticket}" -d "${POSTGRES_DB:-it_ticket_db}" -tAc "SELECT count(*) FROM users;" 2>/dev/null || echo 0)
if [ "$USER_COUNT" = "0" ]; then
  ADMIN_USER="${ADMIN_USERNAME:-admin}"
  ADMIN_PASS="${ADMIN_PASSWORD:-admin123}"
  log "ยังไม่มี user — สร้าง admin เริ่มต้น ($ADMIN_USER)…"
  $COMPOSE exec -T backend python -m scripts.seed_admin "$ADMIN_USER" "${ADMIN_EMAIL:-admin@example.com}" "$ADMIN_PASS"
  if [ "$ADMIN_PASS" = "admin123" ] && [ "$MODE" != "dev" ]; then
    log "⚠️  รหัสผ่าน admin เป็นค่า default (admin123) — เปลี่ยนทันทีหลัง login ครั้งแรก"
  fi
fi

log "เสร็จแล้ว 🎉  ดู log: ./deploy.sh ${MODE/prod/}logs"
$COMPOSE ps
