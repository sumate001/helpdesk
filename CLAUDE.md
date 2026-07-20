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
[AI Classify: L1 / L2]  ← qwen3.6:35b via Ollama
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

| Server | LAN IP | Role |
|---|---|---|
| A5000 (Ubuntu) | 10.1.250.68 | Ollama inference (qwen3.6:35b + bge-m3) |
| VM (Proxmox) | 10.7.255.228 | Line IT Ticket (this project) |

**Network:** VM เรียก Ollama ผ่าน LAN IP ได้โดยตรง

**Access (production stack ผ่าน nginx):**
- Dashboard: `http://10.7.255.228` (nginx port 80)
- ngrok Inspector: `http://10.7.255.228:4040`
- Line Webhook (public): `https://untemptable-rosamond-bivoltine.ngrok-free.dev/webhook/line`
  (ngrok free static domain — รันเป็น service `ngrok` ใน docker-compose.yml, forward → backend:8000)

---



| Layer | Technology |
|---|---|
| Line Integration | Line Messaging API (OA Webhook + Group Notify) |
| Backend | FastAPI + Python 3.11 |
| AI Classify & Response | qwen3.6:35b via Ollama (http://10.1.250.68:11434) |
| RAG | pgvector + Ollama embedding (bge-m3) — ความรู้ระบบ/นโยบาย IT |
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
│           ├── ai_service.py      # Ollama qwen3.6:35b integration
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
employee_id     INTEGER       -- id ใน Amarin Employee DB (migration 0011)
emp_code        VARCHAR(20)   -- key ที่ใช้ lookup — ยิง /api/employees/lookup สดทุกครั้ง ไม่ cache
emp_email       VARCHAR(100)
emp_name        VARCHAR(100)  -- ชื่อจริงจาก Employee DB (display_name โดน LINE profile ทับได้)
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
status              VARCHAR(30)   -- open|pending_approval|in_progress|resolved|closed|ai_answered
                                  -- ai_answered = AI แนะนำแล้วผู้ใช้บอกว่าหาย (เก็บสถิติ ไม่แจ้ง IT)
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

### Table: `kb_chunks` — knowledge base สำหรับ RAG
```sql
id          SERIAL PRIMARY KEY
title       VARCHAR(255)              -- หัวข้อ เช่น "การขอใช้ VPN"
content     TEXT NOT NULL            -- เนื้อหา (1 หัวข้อ/1 chunk)
category    VARCHAR(50)              -- map เข้ากับ category ticket ได้
source      VARCHAR(255)             -- ที่มา ไว้ debug
embedding   vector(EMBED_DIM)        -- pgvector (bge-m3 = 1024) + HNSW cosine index
is_active   BOOLEAN DEFAULT true
created_at  TIMESTAMP
updated_at  TIMESTAMP
```
ต้องใช้ Postgres image ที่มี extension vector (`pgvector/pgvector:pg15`) —
migration `0005_kb_chunks` รัน `CREATE EXTENSION vector` + สร้าง HNSW index ให้

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
followup_sent_at TIMESTAMP             -- follow-up: ส่งถามซ้ำไปเมื่อไหร่ (NULL = ยังไม่ส่ง)
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

### Follow-up Flow (ผู้ใช้เงียบกลางบทสนทนา intake)

เกาะกับตาราง `conversations` — ทำงานเมื่อบอทถาม/แนะนำไว้แล้วผู้ใช้ "เงียบ"
(conversation ยัง active, ยังไม่มี ticket, ข้อความสุดท้ายเป็นของบอท):

```
T+10m : ส่งข้อความถามซ้ำ + Quick Reply ["แก้ได้แล้ว ✅", "ยังไม่ได้ ❌"]
        (push เข้ากลุ่มเดิมถ้าเป็นบทสนทนากลุ่ม / หาผู้ใช้ตรงๆ ถ้า 1-1)
        + ต่ออายุ conversation ให้อยู่ถึงรอบ escalate
T+30m : ยังเงียบต่อ → เปิด Ticket L2 (description = transcript ทั้งบทสนทนา)
        + ผูก pending_images + แจ้ง IT Group + ปิด conversation
```

- ผู้ใช้ตอบกลับระหว่างนี้ (รวมกดปุ่ม quick reply) → ข้อความเข้าบทสนทนา intake เดิมตามปกติ
  (`updated_at` ขยับ → ไม่ escalate)
- **สวิตช์เปิด/ปิดทั้ง flow**: setting `FOLLOWUP_ENABLED` — ค่าตั้งต้นจาก .env,
  override สดได้จากหน้า Settings (เก็บใน `app_settings` ไม่ต้อง restart)
- record การ escalate เก็บลง `ticket_followups` ไว้ทำสถิติ
- `conversations.followup_sent_at` (migration `0008`) ใช้กันส่งถามซ้ำซ้ำสอง

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

### Registration Flow (ผูก LINE user เข้ากับ Employee DB — 1-1 เท่านั้น)

Employee DB (`EMPLOYEE_DB_URL` = http://10.7.255.227:5100) มี exact lookup แล้ว
(`GET /api/employees/lookup?emp_code=...|email=...` — ดู `docs/employee-api-spec.md`)
ฝั่งเรา **ไม่ cache** — ยิง lookup สดทุกครั้งที่ต้องใช้:

- `follow` event + ยังไม่ผูก (`employee_id` NULL) → ทักให้พิมพ์รหัสพนักงาน/อีเมล
- ข้อความ 1-1 นอกบทสนทนา ที่หน้าตาเป็นรหัส (มีตัวเลข, 4-10 ตัว) หรืออีเมล →
  `_try_register`: lookup → ผูก `employee_id/emp_code/emp_email/emp_name` + เติม
  department/position (+building/floor ถ้ามี) ลง `line_users` — พิมพ์รหัสใหม่ = rebind ได้
- `_known_info` ใช้ `emp_name` ก่อน `display_name` → AI ไม่ถามชื่อซ้ำ และส่ง
  `registered`/`emp_code`/`department`/`can_register_here` เข้า system prompt ด้วย →
  ผู้ใช้ถาม "ลงทะเบียนหรือยัง" บอทตอบจากค่านี้ได้ (ไม่เดา/ไม่เปิด ticket).
  ในกลุ่มลงทะเบียนไม่ได้ → บอทบอกให้ไปทัก 1-1 แทน
- `mirror_ticket` ใช้ exact lookup จาก key ที่ผูกไว้ก่อน (ได้ phone/department สด)
  แล้วค่อย fallback ค้นชื่อ `?q=`

### Intake Flow (multi-turn — ใช้ทั้ง 1-1 และกลุ่ม)

บอท **ไม่เปิด ticket จากข้อความเดียวทันที** แต่คุยเก็บข้อมูล/แก้ปัญหาก่อน ผ่าน `conversations`
(`ai_service.intake_turn` ขับด้วย qwen3.6:35b, JSON action = ask|resolved|open):

1. **ลอง L1 สั้นๆ** — แนะนำวิธีแก้ง่ายๆ ได้ไม่เกิน 1-2 ครั้ง (ไม่ถามวินิจฉัยวนยืดเยื้อ)
2. ผู้ใช้บอกว่าหาย → `resolved`: เก็บ ticket สถานะ `ai_answered` (สถิติ) ปิด conversation
3. **ตัดสินว่าต้องให้ IT → หยุด troubleshoot ทันที** เก็บข้อมูลที่จำเป็น "รวมในข้อความเดียว":
   ชื่อ-นามสกุล + อาคาร + ชั้น (เฉพาะที่ยังไม่ทราบ) → อัปเดต `line_users`.
   ส่ง `known_info` (ชื่อ/ตึก/ชั้นจาก DB) ให้ AI เพื่อไม่ถามซ้ำ
4. ข้อมูลครบ → สรุป + ปุ่มยืนยัน `เปิด Ticket ✅ / ยังไม่ต้อง ❌` (`needs_confirm`)
5. ผู้ใช้ยืนยัน → `open`: เปิด ticket (equipment/service → `pending_approval`, อื่นๆ → L2 `open`)
   + แจ้งทีม IT + ผูกรูปจาก `pending_images` เข้า `ticket_attachments`

conversation active ภายใน `CONVERSATION_MINUTES` (15 นาที) ต่ออายุทุก turn —
ระหว่างนี้ข้อความ/รูปถัดมาของผู้ใช้คนเดิมถือว่าอยู่ในบทสนทนานี้ (ไม่ต้อง @ ซ้ำ)

**ถามสถานะ Ticket เดิม:** `_known_info` ส่ง `tickets` (5 เคสล่าสุดของผู้แจ้งคนนั้น จาก
`ticket_service.recent_tickets` — ทุกสถานะรวม closed, มี ticket_no/สถานะไทย/ผู้ดูแล/เวลา)
เข้า system prompt เหมือน `registered` → ผู้ใช้ถาม "เคสที่แจ้งไปถึงไหนแล้ว" / ระบุเลข
`TK-...` บอทตอบจากค่านี้ได้เลย (`action="ask"` ไม่เปิด ticket ซ้ำ ไม่ถามชื่อ/ตึก/ชั้น)
— prompt ห้ามบอทตอบว่า "เข้าถึงสถานะไม่ได้/ไปถาม IT เอง/ดูใน Portal"

**น้ำเสียงบอท (voice):** `INTAKE_SYSTEM_PROMPT` มีบล็อก "[วิธีพูด]" คุมโทนให้คุยเหมือน
เพื่อนร่วมงาน ไม่ใช่ฟอร์ม — ห้าม Markdown (LINE ไม่เรนเดอร์), ห้ามลิสต์เลขข้อ, ถามครั้งละ
ไม่เกิน 2-3 อย่าง, ห้ามเล่าขั้นตอนหลังบ้าน, ห้ามถามซ้ำสิ่งที่รู้อยู่แล้ว และ **ห้ามสัญญาเกินบทบาท**
(บอทเปิดเคสได้อย่างเดียว โทรตามช่าง/เร่งคิว/เตรียมของเองไม่ได้ → พูดได้แค่ "โน้ตความเร่งด่วนให้")
มีตัวอย่าง ❌/✅ เทียบให้ดู พร้อมกำกับว่าตัวอย่างสอนแค่ "วิธีเขียน" ห้ามลอกเนื้อหาข้ามปัญหา
(ไม่งั้นเคสเน็ตช้าจะโดนถาม Asset Tag ของจอ)

`ai_service.clean_for_line()` ลอก Markdown (`**ตัวหนา**`/`###`/bullet) ออกจาก reply ทุกครั้ง
ก่อนส่ง — พรอมป์ตห้ามแล้วแต่โมเดลยังหลุดเป็นครั้งคราว จึงกันซ้ำแบบ deterministic

**กับดักคำว่า "ยืนยัน":** `_CONFIRM_HINTS`/`_CONFIRM_QUESTION_HINTS` ห้ามมีคำว่า "ยืนยัน"
โดดๆ เพราะบอทใช้ในความหมาย "ช่วยยืนยันข้อเท็จจริงหน่อย" ด้วย (เช่น "รบกวนยืนยันว่าเป็น
Outlook หรือ Webmail?") → ปุ่มเปิดเคสจะเด้งกลางบทสนทนาที่ยังถามข้อมูลอยู่. ต้องใช้รูปที่มี
บริบทเปิดเคสติดมา ("ยืนยันเปิด"/"ยืนยันการเปิด"). และ `_NO_CONFIRM_HINTS` ดักประโยคปฏิเสธ
("ไม่ต้องเปิดเคสใหม่" ตอนเจอว่าซ้ำกับเคสเดิม) ไม่ให้ถูกนับเป็นการขอยืนยัน

**เจอเรื่องซ้ำกับเคสที่ค้างอยู่:** ผู้ใช้แจ้งเรื่องเดิมซ้ำ → บอทบอกสถานะเคสเดิม + ถามว่า
"ตัวเดิมใช่ไหม" แทนการเปิด ticket ใหม่ (ยืนยันว่าคนละเรื่องค่อยเปิด) กันเคสซ้ำที่ช่างต้องมาไล่ปิดเอง

**RAG ระหว่าง intake:** ก่อนเรียก `intake_turn` จะ `rag_service.retrieve_context` ค้น
`kb_chunks` จากข้อความผู้ใช้ แล้วป้อน `kb_context` ให้ AI (ช่วยทั้งตอบและ classify เช่น
รู้ว่า VPN/WiFi ต้องขออนุมัติ) — embed/retrieve ล่ม → context ว่าง intake เดินต่อปกติ

**กันบอทเข้าใจผิดในกลุ่ม:** เมื่อ conv active ในกลุ่ม ถ้าข้อความถัดมา "ไม่ได้คุยกับบอท"
(คุยกับคนอื่น/เปลี่ยนเรื่อง) บอทจะเงียบ — ตัดสินด้วย `intake_turn(allow_ignore=True)` →
`action="ignore"` (ไม่ตอบ/ไม่บันทึก/ไม่ต่ออายุ); ข้อความที่ `@mention` คนอื่นตัดทิ้งก่อน
ไม่เรียก AI. ถ้าถูกเรียกตรงๆ (`@mention`/quote-reply/keyword) ถือว่าคุยกับบอทเสมอ

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

### Knowledge Base (RAG — Admin only)
```
GET    /api/kb            # list KB chunks
POST   /api/kb            # เพิ่ม chunk (auto-embed)
PATCH  /api/kb/{id}       # แก้ (re-embed ถ้าแก้ content/title) หรือ toggle is_active
DELETE /api/kb/{id}       # ลบ chunk
```

### Settings (Runtime AI config — Admin only)
```
GET   /api/settings                # ค่า effective ปัจจุบัน (+ EMBED_DIM read-only + list override)
PATCH /api/settings                # แก้ OLLAMA_MODEL/EMBED_MODEL/BASE_URL/RAG_TOP_K/MIN_SIMILARITY/FOLLOWUP_ENABLED/TICKET_CONFIRM_REQUIRED/ITAMTV_ENABLED/EMPLOYEE_LOOKUP_ENABLED
                                   #   TICKET_CONFIRM_REQUIRED: ต้องกดยืนยันก่อนเปิด ticket ไหม (ปิด = เปิดเคสทันทีเมื่อข้อมูลครบ)
                                   #   ส่งค่าว่าง/null = ล้าง override กลับไปใช้ค่า .env
GET   /api/settings/ollama-models  # รายชื่อ model ที่ pull ไว้บนเครื่อง Ollama (/api/tags)
GET   /api/settings/integrations   # ระบบภายนอก (itamtv / Employee DB): สวิตช์ + ping สถานะสด
                                   #   สวิตช์ = ITAMTV_ENABLED / EMPLOYEE_LOOKUP_ENABLED (toggle ผ่าน PATCH ปกติ)
```
override เก็บใน DB (`app_settings`) → โหลดเข้า in-memory cache ตอน start +
อัปเดต cache ทุกครั้งที่ PATCH. `ai_service`/`rag_service` อ่านค่าผ่าน
`settings_service.get(key)` ทำให้เปลี่ยน model/RAG params มีผลทันทีไม่ต้อง restart

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
OLLAMA_BASE_URL=http://10.1.250.68:11434
OLLAMA_MODEL=qwen3.6:35b

# RAG embedding (ต้อง `ollama pull bge-m3` ที่ A5000 ก่อน)
OLLAMA_EMBED_MODEL=bge-m3
EMBED_DIM=1024              # bge-m3=1024, nomic-embed-text=768
RAG_TOP_K=4
RAG_MIN_SIMILARITY=0.4     # cosine similarity ต่ำกว่านี้ตัดทิ้ง
# ค่าด้านบน (OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_EMBED_MODEL, RAG_TOP_K,
# RAG_MIN_SIMILARITY) เป็น "ค่าตั้งต้น" — override ได้สดๆ จากหน้า Settings ใน
# dashboard (เก็บใน DB ตาราง app_settings) ไม่ต้อง restart. EMBED_DIM แก้ผ่าน UI
# ไม่ได้ เพราะผูกกับ vector column — เปลี่ยนต้องทำ migration + re-embed

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
# ต้อง 1 worker เท่านั้น — APScheduler รันใน lifespan ของทุก worker ถ้า >1 จะส่ง follow-up/เปิด ticket ซ้ำ
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
