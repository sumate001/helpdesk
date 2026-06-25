# Line IT Ticket System (Amarin)

ระบบ IT Support Ticketing รับปัญหาจาก Line OA → แปลงเป็น e-ticket อัตโนมัติ พร้อม AI First
Response (qwen3:8b ผ่าน Ollama) และ Web Dashboard สำหรับ IT Staff

ดูรายละเอียดสถาปัตยกรรม/สเปกเต็มได้ที่ [`CLAUDE.md`](./CLAUDE.md)

## Quick Start (Dev)

```bash
# 1. เตรียม env (แก้ค่า LINE_*, OLLAMA_* ตามจริง)
cp .env.example .env.dev

# 2. start ทุก service
docker compose -f docker-compose.dev.yml up -d --build

# 3. สร้าง admin user คนแรก
docker compose -f docker-compose.dev.yml exec backend python -m scripts.seed_admin

# 4. (ทางเลือก) ใช้ alembic migration แทน auto create_all
docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "init"
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| Backend API + Swagger | http://localhost:8000/docs |
| ngrok Inspector (Line webhook URL) | http://localhost:4040 |
| MinIO Console | http://localhost:9001 (minioadmin/minioadmin) |

Line Webhook URL = `https://<ngrok>.ngrok.app/webhook/line`

Login เริ่มต้น: `admin` / `admin123`

## Production

```bash
cp .env.example .env   # แก้ secret ให้เรียบร้อย
docker compose up -d --build
docker compose exec backend python -m scripts.seed_admin admin you@example.com 'strong-pass'
```

## โครงสร้าง

- `backend/` — FastAPI + SQLAlchemy + APScheduler (webhook, AI classify, SLA, follow-up)
- `frontend/` — React 18 + Vite + Tailwind (dashboard, tickets, reports)
- `nginx/` — reverse proxy (prod)

## หมายเหตุ

- Backend ตอน startup จะ `create_all` ตาราง + seed SLA policy ให้อัตโนมัติ
  (ใช้ alembic เมื่อต้องการ migration จริงจัง)
- Follow-up/Escalation/SLA-breach ทำงานผ่าน APScheduler tick ทุก 1 นาที
  (ปรับเวลาได้ที่ `FOLLOWUP_DELAY_MINUTES`, `ESCALATE_DELAY_MINUTES`)
- ถ้า Ollama เรียกไม่ติด AI จะ fallback เป็น L2 อัตโนมัติ
