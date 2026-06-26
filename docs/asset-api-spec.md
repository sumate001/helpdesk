# Asset/Employee API Spec — สำหรับระบบ 10.7.255.227

เป้าหมาย: เปิด REST API ให้ Line IT Ticket bot ดึงข้อมูล **พนักงาน + อุปกรณ์ IT ที่ถือครอง**
มาใช้ตอน intake (auto-fill ผู้แจ้ง) และให้ staff ดูตอน ticket

Key เชื่อมระหว่างสองระบบ: **`employee_id`** (stable) — ค้นครั้งแรกด้วยชื่อ แล้ว ticket
ฝั่งบอทจะ cache `employee_id` ไว้ใน `line_users` เพื่อครั้งหน้าไม่ต้องค้นชื่อซ้ำ

---

## Auth

ทุก endpoint ต้องมี header:
```
X-API-Key: <STATIC_SECRET>
```
- internal network → static token พอ (ไม่ต้อง OAuth)
- key ผิด/ไม่มี → `401 {"error": "unauthorized"}`

## ข้อกำหนดทั่วไป
- ทุก response เป็น JSON, `Content-Type: application/json; charset=utf-8`
- error คืน JSON เสมอ (อย่าคืน HTML error page)
- field `department` / `building` / `floor` ให้ใช้คำเดียวกับที่ใช้แสดงในระบบ HR
  (ฝั่ง ticket จะเก็บลง `line_users` ตรงๆ)
- timeout เร็ว (< 2-3 วิ) — อยู่ใน webhook flow ที่ผู้ใช้รออยู่

---

## Endpoints

### 1. `GET /api/employees/search?q=<ชื่อ>`  ← สำคัญสุด
ค้นพนักงานด้วยชื่อแบบ **fuzzy / partial** (พิมพ์ไม่ครบ หรือสลับชื่อ-สกุล ก็ต้องเจอ),
คืนได้หลาย candidate เผื่อชื่อซ้ำ

```json
{
  "results": [
    {
      "employee_id": "EMP1234",
      "full_name": "สมชาย ใจดี",
      "department": "บัญชี",
      "position": "เจ้าหน้าที่",
      "building": "อมรินทร์ ทาวเวอร์",
      "floor": "12",
      "email": "somchai@amarin.co.th"
    }
  ]
}
```
ไม่เจอ → `200 {"results": []}`

### 2. `GET /api/employees/{employee_id}`
รายละเอียดพนักงาน + อุปกรณ์ที่ถือครองทั้งหมด
```json
{
  "employee_id": "EMP1234",
  "full_name": "สมชาย ใจดี",
  "department": "บัญชี",
  "position": "เจ้าหน้าที่",
  "building": "อมรินทร์ ทาวเวอร์",
  "floor": "12",
  "email": "somchai@amarin.co.th",
  "assets": [
    {
      "asset_id": "AST-0099",
      "type": "notebook",
      "brand_model": "Dell Latitude 5440",
      "serial_no": "SN12345",
      "status": "in_use",
      "assigned_date": "2024-03-01"
    }
  ]
}
```
ไม่เจอ → `404 {"error": "not_found"}`

### 3. `GET /api/assets/{asset_id}`
รายละเอียดอุปกรณ์ + เจ้าของปัจจุบัน (+ ประวัติถ้ามี)
```json
{
  "asset_id": "AST-0099",
  "type": "notebook",
  "brand_model": "Dell Latitude 5440",
  "serial_no": "SN12345",
  "status": "in_use",
  "current_owner": { "employee_id": "EMP1234", "full_name": "สมชาย ใจดี" }
}
```
ไม่เจอ → `404 {"error": "not_found"}`

### 4. `GET /api/health`
```json
{ "status": "ok" }
```
ไม่ต้องใส่ auth ก็ได้ — ไว้ให้บอทเช็คว่า online ก่อนเรียก

---

## หมายเหตุ enum (ให้ map กับ ticket category ได้)
- `assets[].type`: notebook | desktop | monitor | printer | phone | network | other
- `assets[].status`: in_use | spare | repair | retired
