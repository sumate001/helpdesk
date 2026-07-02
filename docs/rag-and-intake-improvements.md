# RAG + Intake Improvements

เอกสารสรุปการเปลี่ยนแปลงรอบนี้ — 3 เรื่องหลัก: (1) แก้บอทเข้าใจผิดว่าคุยด้วยในกลุ่ม,
(2) แก้ปุ่มยืนยันเปิดเคสไม่ขึ้น, (3) เพิ่ม RAG ให้ AI ตอบตามนโยบาย IT ของบริษัท + หน้าจัดการ KB

---

## 1. แก้: ในกลุ่ม บอทคิดว่ายังคุยด้วย ทั้งที่ user หันไปคุยกับคนอื่น

**อาการเดิม:** เมื่อมี `conversation` active (ภายใน `CONVERSATION_MINUTES` = 15 นาที)
ทุกข้อความของ user คนนั้นในกลุ่มจะถูกป้อนเข้า intake หมด แม้จะเปลี่ยนไปคุยกับเพื่อนแล้ว

**วิธีแก้:** เพิ่ม action `ignore` ให้ AI ตัดสินว่าข้อความ "คุยกับบอท" จริงไหม + short-circuit ด้วย mention

ลำดับการตัดสินใน `_handle_group_text` (`backend/app/api/webhook.py`):

| สถานการณ์ | พฤติกรรม |
|---|---|
| ยังไม่มี conv + ถูกเรียก (`@mention` / quote-reply บอท / keyword) | เริ่มบทสนทนา |
| คุยต่อ + เรียกบอทตรงๆ | ตอบปกติ (ตัดคำเรียกออกจากข้อความ) |
| คุยต่อ + `@mention` คนอื่น | **ข้ามทันที ไม่เรียก AI** (`_mentions_others_only`) |
| คุยต่อ + ข้อความเปล่าๆ | ส่งให้ gemma ตัดสิน → ถ้าไม่เกี่ยว = `action="ignore"` |

- `ai_service.intake_turn(..., allow_ignore=True)` → ต่อท้าย prompt ด้วย `IGNORE_BLOCK`
  และอนุญาต `action="ignore"`
- `_run_intake(..., allow_ignore=...)` ประเมิน **ก่อน** commit ข้อความเข้า transcript
  ถ้าได้ `ignore` → ไม่ตอบ ไม่บันทึก ไม่ต่ออายุ conversation (เหมือนบอทไม่ได้ยิน)
- `allow_ignore` เปิดเฉพาะ "คุยต่อในกลุ่มโดยไม่ได้ถูกเรียกซ้ำ" — แชท 1-1 และตอนถูกเรียกตรงๆ
  ไม่เปิด (ชัดเจนว่าพูดกับบอท)

**ข้อแลกเปลี่ยน:** ระหว่าง conv active ในกลุ่ม ข้อความเปล่าๆ แต่ละอันจะเรียก gemma 1 ครั้ง
เพื่อตัดสิน (mention คนอื่นตัดทิ้งก่อนโดยไม่เรียก AI)

---

## 2. แก้: AI บอกจะเปิดเคส แต่ปุ่มยืนยันไม่ขึ้น ต้องทวงก่อน

**อาการเดิม:** gemma สรุปแล้วพูดว่า "จะเปิดเคสให้" แต่ไม่ตั้ง `needs_confirm=true`
ในข้อความเดียวกัน (ปุ่ม `เปิด Ticket ✅ / ยังไม่ต้อง ❌` ผูกกับ `needs_confirm`)
→ ปุ่มไม่โผล่ ต้องพิมพ์ทวงอีกที

**วิธีแก้ (2 ชั้น) ใน `backend/app/services/ai_service.py`:**

1. **เสริม prompt** — ระบุชัดว่าทุกครั้งที่ reply เอ่ยถึงการเปิดเคส/ขอยืนยัน
   ต้องตั้ง `needs_confirm=true` ในข้อความเดียวกัน ห้ามแยกสรุปกับปุ่มเป็นคนละ turn
2. **Safety net (deterministic)** — `_looks_like_confirm_request()` ตรวจ keyword
   (`เปิด ticket`, `เปิดเคส`, `ยืนยัน`, ฯลฯ) ถ้า `action="ask"` แต่โมเดลลืมตั้ง
   `needs_confirm` ขณะที่ reply เข้าข่าย → บังคับ `needs_confirm=true` เอง

> ถ้าเจอเคสที่ข้อความสรุปใช้คำอื่นแล้วปุ่มยังไม่ขึ้น เพิ่มคำใน `_CONFIRM_HINTS`

---

## 3. RAG — ให้ AI ตอบตามนโยบาย/ระบบ IT ของบริษัท

สถาปัตยกรรม: **pgvector** (อยู่บน Postgres เดิม) + embedding ผ่าน **Ollama (bge-m3)**
RAG ช่วยทั้ง "ตอบ" และ "classify" — เช่น รู้ว่า VPN/WiFi ต้องขออนุมัติ → `service_request`,
join domain ด้วย AD ฯลฯ

### องค์ประกอบ

| ส่วน | ไฟล์ |
|---|---|
| Model | `backend/app/models/kb_chunk.py` (`KbChunk` มี `Vector(EMBED_DIM)`) |
| Migration | `backend/alembic/versions/0005_add_kb_chunks.py` (CREATE EXTENSION vector + HNSW index) |
| Service | `backend/app/services/rag_service.py` (`embed`, `retrieve`, `retrieve_context`, `upsert_chunk`) |
| Intake hook | `ai_service.intake_turn(..., kb_context=)` + `_kb_block()` |
| Webhook | `_run_intake` retrieve KB จากข้อความผู้ใช้ก่อนเรียก intake |
| Admin API | `backend/app/api/kb.py` + `backend/app/schemas/kb.py` (`/api/kb` CRUD, admin only) |
| Frontend | `frontend/src/pages/KnowledgeBase.jsx` + route `/kb` ใน `App.jsx` |

### Config ใหม่ (`backend/app/core/config.py` / `.env`)

```env
OLLAMA_EMBED_MODEL=bge-m3      # multilingual รองรับไทย (nomic-embed-text=768 มิติก็ได้)
EMBED_DIM=1024                 # bge-m3 = 1024
RAG_TOP_K=4                    # ดึง chunk ที่ใกล้สุดกี่อัน
RAG_MIN_SIMILARITY=0.4         # cosine similarity ต่ำกว่านี้ตัดทิ้ง (กัน inject ขยะ)
```

### หลักการ

- **1 หัวข้อ / 1 chunk** (เช่น "การขอใช้ VPN") retrieve แม่นกว่าตัดตามตัวอักษร
- เขียน content ให้ชัดว่าเรื่องไหน "ตอบได้เลย" vs "ต้องขออนุมัติ/ให้ IT ดำเนินการ"
- **fail-safe:** embed/retrieve ล่ม → `kb_context=""` intake เดินต่อปกติ ไม่พัง
- `_kb_block` สั่ง AI ให้ยึดตามนโยบาย ห้ามเดาเอง และเปิดเคสตามที่นโยบายกำหนด

### หน้าจัดการ KB (Dashboard)

- เมนู "คลังความรู้" → `/kb` (admin)
- ฟอร์มเพิ่ม/แก้ (หัวข้อ, หมวด, ที่มา, เนื้อหา) + list พร้อมปุ่ม แก้ไข/เปิด-ปิด/ลบ
- บันทึกแล้ว backend ฝัง embedding ให้อัตโนมัติ; ถ้า Ollama embed ไม่พร้อมจะขึ้น error 503
- **หมายเหตุ:** `/api/kb` ใช้ `require_admin` — ต้อง login เป็น admin (NavLink ยังโชว์ให้ทุก role
  เหมือน nav อื่น; ถ้าต้องการซ่อนจาก staff ต้องให้ `useAuth` เก็บ role เพิ่ม)

---

## Deployment / สิ่งที่ต้องทำก่อนใช้งาน RAG

```bash
# 1. ดึง embedding model ที่เครื่อง A5000
ssh a5000 'ollama pull bge-m3'

# 2. ขึ้น postgres image ที่มี pgvector (volume PG15 เดิมใช้ต่อได้)
#    docker-compose*.yml เปลี่ยนเป็น image: pgvector/pgvector:pg15 แล้ว
docker compose -f docker-compose.dev.yml up -d --build postgres backend

# 3. รัน migration (สร้าง extension vector + ตาราง kb_chunks)
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head

# 4. ติดตั้ง dependency ใหม่ (pgvector==0.3.6 อยู่ใน requirements.txt แล้ว — rebuild image จัดการให้)

# 5. ใส่ความรู้ผ่านหน้า /kb หรือ API
curl -X POST http://localhost:8000/api/kb -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"การขอใช้ VPN","category":"service_request","content":"การขอใช้งาน VPN ต้องยื่นขออนุมัติจากหัวหน้าแผนกและ IT ก่อนทุกครั้ง ไม่สามารถใช้ได้ทันที"}'
```

> DB เดิมบน `postgres:15-alpine` ย้ายมาใช้ `pgvector/pgvector:pg15` ได้เลย (PG15 เหมือนกัน
> data compatible) แค่ต้องรัน migration เพื่อ `CREATE EXTENSION vector`
