# Employee Database API — สเปคที่ระบบ Helpdesk (LINE) ต้องการ

> เอกสารนี้สำหรับทีม/Claude ที่ดูแล **Amarin Employee Database** (`http://10.7.255.227:5100`)
> เป้าหมาย: เพิ่ม/ปรับ API ให้ระบบ LINE Helpdesk ผูก LINE user เข้ากับพนักงานได้แม่นและเบา
> โดยไม่ต้องดึงข้อมูลพนักงานทั้งหมดมา match ฝั่ง client

---

## บริบท — ทำไมต้องปรับ

ระบบ LINE Helpdesk มี flow "ลงทะเบียนครั้งแรก": ผู้ใช้พิมพ์ **รหัสพนักงาน** (fallback เป็น
**อีเมล**) → บอทยืนยันชื่อ → ผูก LINE user id เข้ากับพนักงานคนนั้น

ปัญหาของ API ปัจจุบัน (ยืนยันด้วยการยิงจริง 2026-07-20):

| อาการที่เจอ | ผลกระทบ |
|---|---|
| `?q=` ค้นได้แค่ **ชื่อ** — `?q=60045` และ `?q=<email>` คืน 0 | หา emp_code / email ตรงๆ ไม่ได้ |
| `?emp_code=60045` ถูก **ignore** — คืน total 2016 ทั้งหมด | ต้องดึงทั้ง list มา match ฝั่ง client |
| ไม่มี exact lookup ราย emp_code / email | client ต้อง cache 2,016 แถว + TTL + refresh |

ถ้ามี exact lookup 2 ตัวด้านล่าง → ฝั่ง Helpdesk ลบ cache layer ทั้งก้อนทิ้งได้ เหลือยิงตรง 1 request

---

## Endpoint ที่ขอให้เพิ่ม/แก้

### 1. `GET /api/employees/lookup` — **(สำคัญสุด)** exact lookup ราย key

ค้นแบบตรงตัว (exact, ไม่ fuzzy) ด้วย key ใดkey หนึ่ง เลือกได้ทีละตัว:

```
GET /api/employees/lookup?emp_code=90004
GET /api/employees/lookup?email=sumet_ro@amarin.co.th
```

**Query params** (ต้องส่งมาอย่างใดอย่างหนึ่ง):
| param | ชนิด | หมายเหตุ |
|---|---|---|
| `emp_code` | string | เทียบตรงตัว (trim ช่องว่าง; ควร case-insensitive) |
| `email` | string | เทียบตรงตัว, case-insensitive, trim |

**Response 200 — เจอ (ตรง 1 คน):**
```json
{
  "found": true,
  "employee": {
    "id": 1619,
    "emp_code": "90004",
    "name": "สุเมธ รอดขาว",
    "nickname": "เมธ",
    "email": "sumet_ro@amarin.co.th",
    "phone": "-",
    "position": "Project Manager",
    "department": "IT Governance & IT Service",
    "bu": "Amarin Omniverse",
    "bu_code": "AOMNI",
    "status": "active",
    "building": null,
    "floor": null
  }
}
```

**Response 200 — ไม่เจอ:**
```json
{ "found": false, "employee": null }
```

**Response 400 — ไม่ได้ส่ง key หรือส่งหลาย key:**
```json
{ "found": false, "error": "provide exactly one of: emp_code, email" }
```

**เงื่อนไขสำคัญ:**
- คืน **อย่างมาก 1 record** — ถ้า match ได้หลายคน (ไม่ควรเกิดกับ emp_code/email เพราะ unique)
  ให้ถือว่า ambiguous → `{"found": false, "error": "ambiguous"}` (ฝั่ง LINE จะได้ไม่ผูกมั่ว)
- ต้องทำงานกับ **inactive** ด้วย (ส่ง `status` กลับมา ให้ฝั่ง LINE ตัดสินเอง) — อย่า filter ทิ้งเงียบๆ

---

### 2. `GET /api/employees` — เพิ่ม exact filter (ทางเลือกแทนข้อ 1 ถ้าไม่อยากเพิ่ม route)

ทำให้ query param เหล่านี้ **filter จริง** (ปัจจุบันถูก ignore):

```
GET /api/employees?emp_code=90004      → คืนเฉพาะคนที่ emp_code ตรง
GET /api/employees?email=...@amarin... → คืนเฉพาะคนที่ email ตรง
```

Response shape เดิม (`{ "employees": [...], "total": N, "page": ... }`) โดย `total` สะท้อนผล filter จริง
(ถ้าเลือกทำข้อนี้ ก็ไม่ต้องทำข้อ 1 — แต่ข้อ 1 อ่านง่ายและ intent ชัดกว่า **แนะนำข้อ 1**)

---

## เรื่อง data quality (ไม่ใช่โค้ด แต่กระทบ flow มาก)

### emp_code ครบแค่ 22%
จาก 2,016 คน มี `emp_code` แค่ **462 คน (22%)** ที่เหลือ 1,554 คนเป็น `null`

- **ถ้าเติม emp_code ให้ครบได้** → flow ลงทะเบียนใช้รหัสอย่างเดียวจบ ตัด fallback email ทิ้งได้
- **ถ้ายังเติมไม่ได้** → ฝั่ง LINE จะคง fallback email ไว้ (email ครบ 74%, unique)

ความครบของแต่ละ field (อ้างอิงจากข้อมูลจริงวันสำรวจ):

| field | ความครบ | unique |
|---|---|---|
| name | 100% | ชื่อซ้ำได้ |
| phone (เบอร์ภายใน) | 99% | ❌ 139 เบอร์ใช้ร่วมกัน — **ห้ามใช้เป็น key** |
| nickname | 97% | ซ้ำได้ |
| email | 74% | unique (ซ้ำ 1 คู่) |
| emp_code | **22%** | unique |

### (ทางเลือก) เพิ่ม field `building` / `floor`
ตอนนี้ปลายทางไม่มี ทำให้บอท LINE ต้องถาม "อาคาร/ชั้น" ทุกครั้งตอนเปิดตั๋ว
ถ้า HR เก็บ 2 field นี้และส่งกลับใน response → intake ไม่ต้องถามเลย (ดูใน response ข้อ 1 มี key ไว้ให้แล้ว, ค่า null ได้)

---

## สิ่งที่ **ไม่ต้อง** ทำที่ปลายทาง
- ไม่ต้องเก็บ `line_user_id` — ฝั่ง Helpdesk เก็บ binding เองใน `line_users`
- ไม่ต้องมี auth เพิ่ม (เรียกภายใน LAN) — แต่ถ้าจะใส่ API key header ก็รับได้ แจ้งมาด้วย
- ไม่ต้องแตะ endpoint `/api/assets`, `/api/stats`, `/api/employees/{id}/assets` (ใช้ได้ดีอยู่แล้ว)

---

## เกณฑ์ตรวจรับ (acceptance)
1. `GET /api/employees/lookup?emp_code=90004` → `found:true` + record ของ "สุเมธ รอดขาว"
2. `GET /api/employees/lookup?emp_code=ไม่มีจริง` → `found:false`
3. `GET /api/employees/lookup?email=sumet_ro@amarin.co.th` → `found:true` ตรงคนเดียวกัน
4. ส่งทั้ง emp_code และ email พร้อมกัน หรือไม่ส่งเลย → `400` + error
5. response มี field ครบตามตัวอย่าง (รวม `id`, `department`, `bu`, `status`)
