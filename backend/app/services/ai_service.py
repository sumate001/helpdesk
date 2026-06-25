"""Ollama qwen3:8b integration — classify L1/L2 และสร้าง first response ภาษาไทย."""
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "hardware",
    "software",
    "network",
    "account",
    "service_request",
    "equipment_request",
    "other",
}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}

CLASSIFY_SYSTEM_PROMPT = """คุณเป็นผู้ช่วย IT Support สำหรับองค์กร หน้าที่ของคุณคือ "พยายามช่วยแก้ปัญหาให้ผู้ใช้ก่อน" ด้วยการให้คำแนะนำ/วิธีทำที่ชัดเจน แล้วค่อยตัดสินว่าต้องเปิด e-ticket ส่งทีม IT หรือไม่

หลักการตัดสิน needs_ticket:
- needs_ticket = false → ปัญหานี้ "แก้ได้ด้วยคำแนะนำ" ตอบจบในข้อความได้ เช่น สอบถามวิธีใช้งาน/ขั้นตอน, IT policy, ปัญหาเล็กที่ผู้ใช้ทำเองได้ (restart, เคลียร์ cache, ตั้งค่าเบื้องต้น) → ใส่วิธีแก้จริงๆ ลงใน reply
- needs_ticket = true → "แก้ด้วยคำแนะนำไม่ได้" ต้องมีคน IT ลงมือทำ เช่น อุปกรณ์เสีย/ต้องซ่อม, network/ระบบล่ม, ขอเปิด/รีเซ็ต account หรือสิทธิ์ที่ IT ต้องทำให้, ขอเบิกอุปกรณ์, ปัญหาซับซ้อนกระทบหลายคน → reply ให้ตอบรับว่ารับเรื่องและจะส่งทีม IT

category ต้องเป็นหนึ่งใน: hardware, software, network, account, service_request, equipment_request, other
priority ต้องเป็นหนึ่งใน: low, medium, high, critical
equipment_request และ service_request ให้ถือว่า needs_ticket = true เสมอ (ต้องอนุมัติ)

ถ้า category เป็น equipment_request ให้สกัดชื่ออุปกรณ์หลักที่ขอลง item_name (สั้นๆ เช่น "เมาส์") และจำนวนลง quantity (จำนวนเต็ม ถ้าไม่ระบุให้ใช้ 1) หากขอหลายชนิดให้เลือกชนิดหลักชนิดเดียว

ตอบกลับเป็น JSON เท่านั้น รูปแบบ:
{"needs_ticket":true,"category":"...","priority":"...","title":"หัวข้อสั้นๆ","reply":"ข้อความตอบผู้ใช้ภาษาไทย กระชับ สุภาพ — ถ้า needs_ticket=false ให้ใส่วิธีแก้จริง","item_name":"ชื่ออุปกรณ์ (เฉพาะ equipment_request)","quantity":1}"""


async def _ollama_chat(system: str, user: str) -> str:
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "think": False,  # gemma4 เป็น thinking model — ปิด think งานเรา (classify+ตอบสั้น) ไม่ต้อง reason เร็วขึ้นมาก
        "keep_alive": "30m",  # คาโมเดลไว้ใน VRAM กัน cold-load ตอน user ทักจริง
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


def _fallback() -> dict:
    # ถ้า AI ใช้ไม่ได้ → เปิด ticket ไว้ก่อนเพื่อไม่ให้เรื่องตกหล่น (ปลอดภัยกว่า)
    return {
        "needs_ticket": True,
        "category": "other",
        "priority": "medium",
        "title": "ปัญหาที่แจ้งผ่าน Line",
        "reply": "ขอบคุณที่แจ้งมานะครับ ทีม IT จะรีบดำเนินการให้ครับ 🔧",
    }


# category ที่ต้องเปิด ticket เสมอ (ต้องมีคน IT ดำเนินการ/อนุมัติ)
ALWAYS_TICKET_CATEGORIES = {"equipment_request", "service_request"}


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


async def classify_and_respond(message: str) -> dict:
    """คืน dict: needs_ticket, category, priority, title, reply (+ item_name/quantity)."""
    try:
        raw = await _ollama_chat(CLASSIFY_SYSTEM_PROMPT, message)
        result = json.loads(raw)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("AI classify failed, fallback to ticket: %s", exc)
        return _fallback()

    # sanitize
    if result.get("category") not in VALID_CATEGORIES:
        result["category"] = "other"
    if result.get("priority") not in VALID_PRIORITIES:
        result["priority"] = "medium"
    result.setdefault("reply", "ขอบคุณที่แจ้งมานะครับ ทีม IT จะดำเนินการให้ครับ")
    result["title"] = (result.get("title") or message[:80])[:255]

    result["needs_ticket"] = _as_bool(result.get("needs_ticket"))
    # บาง category ต้องเปิด ticket เสมอ ไม่ว่า AI จะตอบยังไง
    if result["category"] in ALWAYS_TICKET_CATEGORIES:
        result["needs_ticket"] = True

    if result["category"] == "equipment_request":
        result["item_name"] = (result.get("item_name") or result["title"])[:255]
        result["quantity"] = _parse_quantity(result.get("quantity"))

    return result


def _parse_quantity(value) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError):
        return 1
    return qty if qty >= 1 else 1
