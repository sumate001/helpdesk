# CLAUDE.md — Line IT Ticket System (Amarin)

## Project Overview

ระบบ IT Support Ticketing ที่รับปัญหาจาก Line Official Account แล้วแปลงเป็น e-ticket
อัตโนมัติ พร้อม AI First Response สำหรับปัญหาระดับ L1 และ Web Dashboard สำหรับ IT Staff

---

## Architecture

```
[User → Line OA]
       ↓
[FastAPI Webhook]
       ↓
[AI Classify: L1 / L2]  ← gemma4:12b via Ollama
      ↙              ↘
   L1                  L2
[AI ตอบ]          [เปิด Ticket]
[Quick Reply]           ↓
       ↓          [Line Group Notify]
[Follow-up @10min]      ↓
       ↓          [IT Dashboard]
[Auto Escalate @30min]
→ เปิด Ticket L2
```

---

## Server Info

| Server | Tailscale IP | Role |
|---|---|---|
| A5000 (Ubuntu) | 100.94.37.18 | Ollama inference |
| VM ใหม่ (Proxmox) | 100.94.37.52 | Line IT Ticket (this project) |

**Network:** ทั้งสองอยู่ใน LAN เดียวกัน — VM เรียก Ollama ผ่าน LAN IP ได้โดยตรง

**Dev Access:**
- Dashboard: `http://100.94.37.52:3000`
- Backend API: `http://100.94.37.52:8000`
- ngrok Inspector: `http://100.94.37.52:4040`
- MinIO Console: `http://100.94.37.52:9001`

เปิดจาก Mac ผ่าน Tailscale ได้เลยทุก URL

---



| Layer | Technology |
|---|---|
| Line Integration | Line Messaging API (OA Webhook + Group Notify) |
| Backend | FastAPI + Python 3.11 |
| AI Classify & Response | gemma4:12b via Ollama (http://100.94.37.18:11434) |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 + Alembic |
| Auth | JWT (IT Staff login) |
| Frontend | React 18 + TailwindCSS + Vite |
| Scheduler | APScheduler (follow-up / SLA / timeout tasks) |
| File Storage | MinIO (รูปภาพจาก Line) |
| Deploy | Docker Compose |

---

## Project Structure

```
line-it-ticket/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   └── versions/
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py          # settings จาก .env
│       │   ├── database.py        # SQLAlchemy engine + session
│       │   ├── security.py        # JWT + password hash
│       │   └── scheduler.py       # APScheduler setup
│       ├── models/
│       │   ├── user.py
│       │   ├── line_user.py
│       │   ├── ticket.py
│       │   ├── ticket_comment.py
│       │   ├── ticket_followup.py
│       │   ├── ticket_attachment.py
│       │   ├── equipment_request.py
│       │   └── sla_policy.py
│       ├── schemas/               # Pydantic schemas
│       ├── api/
│       │   ├── auth.py            # POST /auth/login, /auth/refresh
│       │   ├── webhook.py         # POST /webhook/line
│       │   ├── tickets.py         # CRUD tickets
│       │   ├── users.py           # IT Staff management
│       │   └── reports.py         # Dashboard stats
│       └── services/
│           ├── line_service.py    # Line Messaging API calls
│           ├── ai_service.py      # Ollama gemma4:12b integration
│           ├── ticket_service.py  # ticket business logic
│           ├── sla_service.py     # SLA calculation + breach check
│           ├── followup_service.py # follow-up scheduler jobs
│           └── storage_service.py # MinIO file upload
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── pages/
│       │   ├── Login.jsx
│       │   ├── Dashboard.jsx      # overview + stats
│       │   ├── TicketList.jsx     # all tickets + filter/search
│       │   ├── TicketDetail.jsx   # ticket detail + comments + approve
│       │   └── Reports.jsx        # charts + analytics
│       ├── components/
│       │   ├── TicketCard.jsx
│       │   ├── StatusBadge.jsx
│       │   ├── PriorityBadge.jsx
│       │   ├── SLATimer.jsx
│       │   └── CommentBox.jsx
│       └── hooks/
│           ├── useTickets.js
│           └── useAuth.js
└── nginx/
    └── nginx.conf
```

---

## Database Schema

### Table: `users` — IT Staff
```sql
id              SERIAL PRIMARY KEY
username        VARCHAR(50) UNIQUE NOT NULL
email           VARCHAR(100) UNIQUE NOT NULL
password_hash   TEXT NOT NULL
display_name    VARCHAR(100)
role            VARCHAR(20) DEFAULT 'staff'  -- admin | staff
is_active       BOOLEAN DEFAULT true
created_at      TIMESTAMP DEFAULT NOW()
```

### Table: `line_users` — ผู้แจ้งปัญหาจาก Line
```sql
id              SERIAL PRIMARY KEY
line_user_id    VARCHAR(100) UNIQUE NOT NULL
display_name    VARCHAR(100)
picture_url     TEXT
department      VARCHAR(100)
position        VARCHAR(100)
building        VARCHAR(100)
floor           VARCHAR(20)
created_at      TIMESTAMP DEFAULT NOW()
updated_at      TIMESTAMP DEFAULT NOW()
```

### Table: `sla_policies` — SLA per Priority
```sql
id                      SERIAL PRIMARY KEY
priority                VARCHAR(20) UNIQUE NOT NULL  -- low|medium|high|critical
response_time_minutes   INTEGER NOT NULL  -- เวลา IT ต้อง assign
resolve_time_minutes    INTEGER NOT NULL  -- เวลาต้อง resolve
created_at              TIMESTAMP DEFAULT NOW()
updated_at              TIMESTAMP DEFAULT NOW()
```

Default SLA values:
| Priority | Response | Resolve |
|---|---|---|
| critical | 15 min | 60 min |
| high | 30 min | 240 min |
| medium | 120 min | 1440 min |
| low | 240 min | 4320 min |

### Table: `tickets` — Ticket หลัก
```sql
id                  SERIAL PRIMARY KEY
ticket_no           VARCHAR(30) UNIQUE NOT NULL  -- TK-YYYYMMDD-XXXX
line_user_id        INTEGER REFERENCES line_users(id)
title               VARCHAR(255) NOT NULL
description         TEXT
category            VARCHAR(50)   -- hardware|software|network|account|service_request|equipment_request|other
type                VARCHAR(5)    -- L1|L2
priority            VARCHAR(20)   -- low|medium|high|critical
status              VARCHAR(30)   -- open|pending_approval|in_progress|resolved|closed
assigned_to         INTEGER REFERENCES users(id)
ai_response         TEXT          -- ข้อความที่ AI ตอบไปครั้งแรก
sla_policy_id       INTEGER REFERENCES sla_policies(id)
sla_response_due_at TIMESTAMP
sla_resolve_due_at  TIMESTAMP
sla_breached        BOOLEAN DEFAULT false
created_at          TIMESTAMP DEFAULT NOW()
updated_at          TIMESTAMP DEFAULT NOW()
resolved_at         TIMESTAMP
```

### Table: `ticket_attachments` — รูปภาพจาก Line
```sql
id               SERIAL PRIMARY KEY
ticket_id        INTEGER REFERENCES tickets(id)
file_name        VARCHAR(255)
file_path        TEXT          -- MinIO object path
mime_type        VARCHAR(100)
file_size        INTEGER
line_message_id  VARCHAR(100)  -- Line message ID อ้างอิง
created_at       TIMESTAMP DEFAULT NOW()
```

### Table: `ticket_comments` — Comments + Activity Log
```sql
id           SERIAL PRIMARY KEY
ticket_id    INTEGER REFERENCES tickets(id)
user_id      INTEGER REFERENCES users(id)
content      TEXT NOT NULL
is_internal  BOOLEAN DEFAULT false  -- true = IT เห็นอย่างเดียว
created_at   TIMESTAMP DEFAULT NOW()
```

### Table: `ticket_followups` — Follow-up Scheduler Tracking
```sql
id                SERIAL PRIMARY KEY
ticket_id         INTEGER REFERENCES tickets(id)
followup_sent_at  TIMESTAMP
user_responded    BOOLEAN DEFAULT false
escalated         BOOLEAN DEFAULT false
escalated_at      TIMESTAMP
```

### Table: `equipment_requests` — การเบิกอุปกรณ์
```sql
id            SERIAL PRIMARY KEY
ticket_id     INTEGER REFERENCES tickets(id) UNIQUE
item_name     VARCHAR(255) NOT NULL
quantity      INTEGER DEFAULT 1
reason        TEXT
status        VARCHAR(30) DEFAULT 'pending'  -- pending|approved|rejected|delivered
approved_by   INTEGER REFERENCES users(id)
approved_at   TIMESTAMP
```

### Table: `bot_messages` — message id ที่บอทส่ง (ใช้ดู quote-reply)
```sql
id               SERIAL PRIMARY KEY
line_message_id  VARCHAR(100) UNIQUE NOT NULL  -- id จาก sentMessages[].id
created_at       TIMESTAMP                     -- เก็บ 30 วันแล้วล้าง
```

### Table: `conversations` — multi-turn intake state (1-1 + กลุ่ม)
```sql
id              SERIAL PRIMARY KEY
channel         VARCHAR(10) NOT NULL   -- user | group
source_id       VARCHAR(100)           -- groupId/roomId (NULL ถ้า 1-1)
line_user_id    VARCHAR(100) NOT NULL
status          VARCHAR(10) NOT NULL   -- active | closed
transcript      TEXT NOT NULL          -- JSON: [{role, content}, ...]
pending_images  TEXT NOT NULL          -- JSON: รูปที่รอผูก ticket ตอนยังไม่เปิด
ticket_id       INTEGER REFERENCES tickets(id)
expires_at      TIMESTAMP NOT NULL     -- ต่ออายุทุก turn (CONVERSATION_MINUTES = 15)
created_at      TIMESTAMP NOT NULL
updated_at      TIMESTAMP NOT NULL
```

---

## Core Business Logic

### AI Classify (L1 / L2)

**L1 — AI จัดการได้ ไม่ต้อง IT มาดำเนินการทันที**
- ขอใช้บริการ IT (email, สิทธิ์เข้าระบบ, software license)
- ขอเบิกอุปกรณ์ (อุปกรณ์ทั่วไป)
- สอบถามขั้นตอน / IT policy

**L2 — ต้องส่ง IT ทันที**
- อุปกรณ์เสีย / ต้องซ่อม
- Network / ระบบล่ม
- ปัญหา Broadcast equipment
- ปัญหาที่ซับซ้อน / ส่งผลกระทบหลายคน

### Follow-up Flow (L1)

```
T+0   : AI ตอบ + ส่ง Quick Reply ["แก้ได้แล้ว ✅", "ยังไม่ได้ ❌"]
T+10m : ถ้าไม่มี response → AI ส่งข้อความถามซ้ำ
T+30m : ถ้ายังไม่มี response → Auto เปิด Ticket L2 + แจ้ง IT Group
```

User กด "แก้ได้แล้ว ✅":
- Auto สร้าง Ticket (status = resolved, type = L1)
- บันทึก AI response + timeline ลง DB
- ไม่แจ้ง IT Group

User กด "ยังไม่ได้ ❌":
- Escalate เป็น L2 ทันที
- เปิด Ticket (status = open)
- แจ้ง Line Group IT

### Approval Flow (L1 Service/Equipment Request)

```
User แจ้งขอ → AI รับเรื่อง → เปิด Ticket (status = pending_approval)
→ แจ้ง IT Group → IT Staff Approve/Reject บน Dashboard
→ Line OA แจ้ง User อัตโนมัติ
```

### Ticket Number Format
```
TK-YYYYMMDD-XXXX
ตัวอย่าง: TK-20240615-0001
```

### Intake Flow (multi-turn — ใช้ทั้ง 1-1 และกลุ่ม)

บอท **ไม่เปิด ticket จากข้อความเดียวทันที** แต่คุยเก็บข้อมูล/แก้ปัญหาก่อน ผ่าน `conversations`
(`ai_service.intake_turn` ขับด้วย gemma4:12b, JSON action = ask|resolved|open):

1. **แก้ L1 ก่อน** — ถามวินิจฉัยทีละข้อ + แนะนำให้ผู้ใช้ "ลองทำ" (restart, เช็คสาย ฯลฯ)
2. ผู้ใช้บอกว่าหาย → `resolved`: เก็บ ticket สถานะ `ai_answered` (สถิติ) ปิด conversation
3. แก้ไม่ได้/ต้องให้ IT → เก็บข้อมูลที่ขาด (อาการ, ตึก/ชั้น → อัปเดต `line_users`, เริ่มเมื่อไหร่, ขอรูป)
4. ข้อมูลครบ → สรุป + ปุ่มยืนยัน `เปิด Ticket ✅ / ยังไม่ต้อง ❌` (`needs_confirm`)
5. ผู้ใช้ยืนยัน → `open`: เปิด ticket (equipment/service → `pending_approval`, อื่นๆ → L2 `open`)
   + แจ้งทีม IT + ผูกรูปจาก `pending_images` เข้า `ticket_attachments`

conversation active ภายใน `CONVERSATION_MINUTES` (15 นาที) ต่ออายุทุก turn —
ระหว่างนี้ข้อความ/รูปถัดมาของผู้ใช้คนเดิมถือว่าอยู่ในบทสนทนานี้ (ไม่ต้อง @ ซ้ำ)

**ในกลุ่ม** บอทจะ "เริ่ม" บทสนทนาเมื่อถูกเรียกผ่าน 3 ทาง:
1. `@mention` บอท
2. **quote-reply** ข้อความบอท (เช็ก `quotedMessageId` เทียบ `bot_messages`)
3. ข้อความขึ้นต้นด้วย `GROUP_TRIGGER_KEYWORDS` (เช่น `itadmin`)

**รูปภาพ** (เช่น error screenshot — LINE แนบ caption ไม่ได้): 1-1 รับเสมอ, ในกลุ่มรับเมื่ออยู่ใน
บทสนทนา active หรือ quote-reply ข้อความบอท → **gemma อ่านรูป** (multimodal) ป้อนเข้า intake
ระหว่าง intake รูปเก็บใน MinIO ชั่วคราว (`pending_images`) แล้วผูกเข้า ticket ตอนเปิดจริง

---

## API Endpoints

### Auth
```
POST /api/auth/login          # { username, password } → { access_token, refresh_token }
POST /api/auth/refresh        # refresh token
POST /api/auth/logout
```

### Webhook
```
POST /webhook/line            # Line Messaging API webhook (no auth)
```

### Tickets
```
GET    /api/tickets           # list tickets (filter: status, priority, category, assigned_to, date)
GET    /api/tickets/{id}      # ticket detail + comments + attachments
POST   /api/tickets           # สร้าง ticket manual (IT Staff)
PATCH  /api/tickets/{id}      # update status, assign, priority
POST   /api/tickets/{id}/comments       # เพิ่ม comment
POST   /api/tickets/{id}/approve        # approve equipment/service request
POST   /api/tickets/{id}/reject         # reject request
```

### Users (Admin only)
```
GET    /api/users             # list IT staff
POST   /api/users             # สร้าง IT staff account
PATCH  /api/users/{id}        # update
DELETE /api/users/{id}        # deactivate
```

### Reports
```
GET /api/reports/summary      # ticket count by status/category/priority
GET /api/reports/sla          # SLA breach rate
GET /api/reports/top-issues   # หมวดที่เกิดบ่อย
GET /api/reports/resolution-time  # avg resolution time
```

---

## Environment Variables (.env)

```env
# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/it_ticket_db

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Line
LINE_CHANNEL_ACCESS_TOKEN=
LINE_CHANNEL_SECRET=
LINE_GROUP_IT_ID=              # Group ID สำหรับ notify IT staff

# Ollama (A5000 Server — ใช้ LAN IP ตรง latency ต่ำกว่า Tailscale)
OLLAMA_BASE_URL=http://100.94.37.18:11434
OLLAMA_MODEL=gemma4:12b

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET=it-ticket-attachments

# App
APP_ENV=production
FRONTEND_URL=http://localhost:3000
```

---

## Line Message Templates

### AI ตอบ L1 (Quick Reply)
```
ขอบคุณที่แจ้งมานะครับ 🙏

[AI Response ที่นี่]

ดำเนินการได้แล้วหรือยังครับ?
```
Quick Reply Buttons: `แก้ได้แล้ว ✅` | `ยังไม่ได้ ❌`

### Follow-up (T+10min)
```
สวัสดีครับ 👋 ขอติดตามเรื่องที่แจ้งไว้นะครับ
ดำเนินการได้แล้วหรือยังครับ?
```
Quick Reply Buttons: `แก้ได้แล้ว ✅` | `ยังไม่ได้ ❌`

### Auto Escalate (T+30min)
```
ทีม IT จะติดตามเรื่องนี้ให้นะครับ 🔧
หมายเลข Ticket: TK-YYYYMMDD-XXXX
```

### IT Group Notify (L2 / Escalate)
```
🎫 Ticket ใหม่: TK-YYYYMMDD-XXXX
👤 ผู้แจ้ง: [ชื่อ] ([แผนก] / [ตึก-ชั้น])
📂 หมวด: [category]
🔴 Priority: [priority]
📝 [รายละเอียดย่อ]
```

### แจ้ง User หลัง Approve/Reject
```
✅ อนุมัติแล้ว: [รายการ] จำนวน [X] ชิ้น
ทีม IT จะดำเนินการต่อไปครับ
```

---

## Docker Compose Services

```yaml
services:
  backend:     FastAPI (port 8000)
  frontend:    React/Nginx (port 3000)
  postgres:    PostgreSQL 15 (port 5432)
  minio:       MinIO (port 9000, console 9001)
  nginx:       Reverse proxy (port 80)
```

---

## Docker Setup (Dev & Production)

### Docker Compose — Dev (`docker-compose.dev.yml`)

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    volumes:
      - ./backend:/app          # hot reload
    ports:
      - "8000:8000"
    env_file: .env.dev
    depends_on:
      - postgres
      - minio
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    volumes:
      - ./frontend/src:/app/src  # hot reload
    ports:
      - "3000:3000"
    env_file: .env.dev
    command: npm run dev -- --host

  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: itticket
      POSTGRES_PASSWORD: itticket
      POSTGRES_DB: it_ticket_db
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data

  minio:
    image: minio/minio
    ports:
      - "9000:9000"
      - "9001:9001"             # MinIO Console UI
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_dev_data:/data
    command: server /data --console-address ":9001"

  ngrok:
    image: ngrok/ngrok:latest
    ports:
      - "4040:4040"             # ngrok inspector UI
    environment:
      NGROK_AUTHTOKEN: ${NGROK_AUTHTOKEN}
    command: http backend:8000
    depends_on:
      - backend

volumes:
  postgres_dev_data:
  minio_dev_data:
```

### Docker Compose — Production (`docker-compose.yml`)

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: .env
    depends_on:
      - postgres
      - minio
    expose:
      - "8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    expose:
      - "80"

  postgres:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  minio:
    image: minio/minio
    restart: unless-stopped
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    expose:
      - "9000"

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro   # SSL certs
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
  minio_data:
```

### Dockerfile — Backend Dev (`backend/Dockerfile.dev`)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ไม่ COPY source — ใช้ volume mount แทนเพื่อ hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### Dockerfile — Backend Production (`backend/Dockerfile`)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### Dockerfile — Frontend Dev (`frontend/Dockerfile.dev`)

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm install
# ไม่ COPY source — ใช้ volume mount แทนเพื่อ hot reload
CMD ["npm", "run", "dev", "--", "--host"]
```

### Dockerfile — Frontend Production (`frontend/Dockerfile`)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx-frontend.conf /etc/nginx/conf.d/default.conf
```

---

### Dev Workflow

```bash
# 1. copy env
cp .env.example .env.dev

# 2. start all services
docker compose -f docker-compose.dev.yml up -d

# 3. run migration
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head

# 4. ดู ngrok URL สำหรับ Line Webhook
#    เปิด http://localhost:4040 แล้วเอา URL ไปใส่ใน LINE Developers Console

# 5. ดู logs
docker compose -f docker-compose.dev.yml logs -f backend

# 6. เข้า MinIO Console
#    http://localhost:9001  (user: minioadmin / pass: minioadmin)
```

### Production Workflow

```bash
# 1. copy env
cp .env.example .env

# 2. build + start
docker compose up -d --build

# 3. run migration
docker compose exec backend alembic upgrade head
```

---

## Development Notes

- Hot reload ทั้ง backend (uvicorn --reload) และ frontend (vite dev) ผ่าน volume mount
- ngrok service รันอยู่ใน Docker ด้วย — ดู URL ได้ที่ http://localhost:4040
- **Schema จัดการด้วย Alembic เท่านั้น** — `Base.metadata.create_all()` ถูกเอาออกจาก `main.py` แล้ว
  ดังนั้นต้องรัน `alembic upgrade head` ก่อน start แอปทุกครั้งที่ขึ้น DB ใหม่ ไม่งั้นตารางจะไม่ถูกสร้าง
- ใช้ Alembic สำหรับ database migration ทุกครั้งที่แก้ schema:
  `alembic revision --autogenerate -m "..."` → ตรวจไฟล์ใน `alembic/versions/` → `alembic upgrade head`
- DB เดิมที่มีตารางอยู่แล้ว (เคยพึ่ง create_all) ให้ `alembic stamp head` ครั้งเดียวเพื่อ sync version
  ก่อนเริ่มใช้ migration ปกติ — baseline คือ `0001_initial`, ตาราง `bot_messages` อยู่ใน `0002_bot_messages`
- AI Prompt ต้องระบุภาษาไทยเป็นหลัก และให้ตอบกระชับ
- APScheduler ใช้ BackgroundScheduler + SQLAlchemy jobstore เพื่อให้ survive restart
- รูปภาพจาก Line ให้ download แล้วเก็บใน MinIO ทันที (Line จะลบหลัง 30 วัน)
- SLA timer เริ่มนับตั้งแต่ ticket ถูกสร้าง
- is_internal comment = IT เห็นอย่างเดียว ไม่ส่งกลับหา User
