"""Ollama gemma4:12b integration — classify L1/L2 และสร้าง first response ภาษาไทย.

gemma4:12b เป็น multimodal — รับรูปได้ ใช้ดู error screenshot ที่ผู้ใช้ส่งมาในกลุ่ม.
"""
import base64
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


async def _ollama_chat(
    system: str, user: str, images: list[bytes] | None = None
) -> str:
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    user_msg: dict = {"role": "user", "content": user}
    if images:
        # Ollama รับรูปเป็น base64 ใน field images ของ message
        user_msg["images"] = [base64.b64encode(b).decode() for b in images]
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            user_msg,
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


async def _ollama_chat_messages(
    system: str, history: list[dict], images: list[bytes] | None = None
) -> str:
    """chat แบบ multi-turn — history = [{role, content}, ...]; images แนบที่ turn ล่าสุด."""
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    if images and messages[-1]["role"] == "user":
        messages[-1]["images"] = [base64.b64encode(b).decode() for b in images]
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


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


IMAGE_ONLY_PROMPT = (
    "ผู้ใช้ส่งรูปภาพปัญหา IT มาให้ (มักเป็น error screenshot หรือรูปอุปกรณ์เสีย) "
    "โดยไม่มีข้อความประกอบ กรุณาดูรูปแล้ววิเคราะห์ว่าเป็นปัญหาอะไร "
    "ใน reply ให้สรุปสิ่งที่เห็นในรูปและปัญหาที่น่าจะเป็น"
)


async def classify_and_respond(
    message: str, images: list[bytes] | None = None
) -> dict:
    """คืน dict: needs_ticket, category, priority, title, reply (+ item_name/quantity).

    images: ถ้ามี → ส่งให้ gemma อ่านรูป (เช่น error screenshot จากกลุ่ม).
    """
    user_text = message.strip() if message and message.strip() else IMAGE_ONLY_PROMPT
    try:
        raw = await _ollama_chat(CLASSIFY_SYSTEM_PROMPT, user_text, images)
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
    result["title"] = (result.get("title") or message[:80] or "ปัญหาจากรูปภาพที่แจ้ง")[:255]

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


# ---------------------------------------------------------------------------
# Multi-turn intake — แก้ปัญหาเบื้องต้นก่อน แล้วเก็บข้อมูล + ยืนยันก่อนเปิด ticket
# ---------------------------------------------------------------------------

INTAKE_SYSTEM_PROMPT = """คุณเป็นผู้ช่วย IT Support ที่คุยกับผู้ใช้แบบโต้ตอบทีละข้อความ เป้าหมายเรียงตามลำดับ:

1) แก้ปัญหาเบื้องต้น (L1) ก่อน: ถามคำถามวินิจฉัยทีละข้อ และแนะนำให้ผู้ใช้ "ลองทำ" บางอย่าง (เช่น restart, เสียบสายใหม่, เช็ค WiFi, ล้าง cache, ลองอุปกรณ์อื่น) เพื่อพยายามแก้ให้จบโดยไม่ต้องเปิดงาน
2) ถ้าผู้ใช้บอกว่าหายแล้ว/แก้ได้ → action = "resolved"
3) ถ้าแก้เบื้องต้นไม่ได้ หรือเป็นงานที่ต้องให้ IT ลงมือ (อุปกรณ์เสีย, ระบบล่ม, ขอเปิด/รีเซ็ตสิทธิ์, เบิกอุปกรณ์) → เก็บข้อมูลที่ "ยังขาด" ให้ครบก่อน ถามทีละข้อ:
   - อาการ/รายละเอียดปัญหา
   - สถานที่: ตึก (building) และชั้น (floor)
   - เริ่มเป็นตั้งแต่เมื่อไหร่ / กระทบคนอื่นไหม
   - ถ้ายังไม่มีรูป ให้ขอรูปประกอบ (เช่น error screenshot) ถ้าช่วยได้
   ระหว่างนี้ action = "ask"
4) เมื่อข้อมูลครบพอเปิดงาน → สรุปสั้นๆ ให้ผู้ใช้ฟังแล้วถามยืนยันว่าจะเปิด Ticket ส่งทีม IT ไหม → action = "ask" และ needs_confirm = true
5) เมื่อผู้ใช้ยืนยัน (เช่นตอบ "เปิดเลย", "ใช่", กดปุ่มยืนยัน) → action = "open"

กรณีเบิกอุปกรณ์ (equipment_request) หรือขอใช้บริการ (service_request): ไม่ต้อง troubleshoot มาก ให้ถามรายละเอียด (อะไร/จำนวน/เหตุผล) ให้ครบแล้วขอยืนยัน → open (จะเข้าขั้นตอนอนุมัติ)

หลักการ:
- ถามทีละข้อ สั้น สุภาพ ภาษาไทย อย่ายิงคำถามรัวหลายข้อพร้อมกัน
- อย่าเปิด ticket เองโดยไม่ขอยืนยันก่อน (ยกเว้นผู้ใช้สั่งเปิดชัดเจน)
- ถ้ามีรูปแนบมา ให้ดูรูปประกอบการวิเคราะห์

category ต้องเป็นหนึ่งใน: hardware, software, network, account, service_request, equipment_request, other
priority: low, medium, high, critical | type: L1 หรือ L2

ตอบกลับเป็น JSON เท่านั้น:
{"reply":"ข้อความถึงผู้ใช้ (ภาษาไทย กระชับ)","action":"ask|resolved|open","needs_confirm":false,"category":"...","priority":"...","type":"L2","title":"หัวข้อสั้นๆ","description":"สรุปปัญหา+ข้อมูลที่เก็บได้ สำหรับทีม IT","building":null,"floor":null,"item_name":null,"quantity":1}
- ใส่ category/priority/type/title/description ให้ครบเมื่อ action=open หรือ resolved
- building/floor ใส่เมื่อผู้ใช้บอก ไม่งั้น null"""

VALID_ACTIONS = {"ask", "resolved", "open"}


def _intake_fallback() -> dict:
    return {
        "reply": "ขอโทษครับ ระบบขัดข้องชั่วคราว ผมเปิดเรื่องส่งทีม IT ให้เลยนะครับ 🔧",
        "action": "open",
        "needs_confirm": False,
        "category": "other",
        "priority": "medium",
        "type": "L2",
        "title": "ปัญหาที่แจ้งผ่าน Line",
        "description": "เปิดอัตโนมัติเพราะ AI ขัดข้อง",
        "building": None,
        "floor": None,
    }


async def intake_turn(history: list[dict], images: list[bytes] | None = None) -> dict:
    """เดินบทสนทนา intake หนึ่ง turn — history = [{role, content}, ...] (รวมข้อความล่าสุดของผู้ใช้).

    คืน dict: reply, action(ask|resolved|open), needs_confirm, และ field สำหรับเปิด ticket.
    """
    try:
        raw = await _ollama_chat_messages(INTAKE_SYSTEM_PROMPT, history, images)
        result = json.loads(raw)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("AI intake failed, fallback to open ticket: %s", exc)
        return _intake_fallback()

    if result.get("action") not in VALID_ACTIONS:
        result["action"] = "ask"
    result["needs_confirm"] = _as_bool(result.get("needs_confirm"))
    result.setdefault("reply", "รบกวนเล่ารายละเอียดเพิ่มอีกนิดได้ไหมครับ")

    if result["action"] in ("open", "resolved"):
        if result.get("category") not in VALID_CATEGORIES:
            result["category"] = "other"
        if result.get("priority") not in VALID_PRIORITIES:
            result["priority"] = "medium"
        if result.get("type") not in {"L1", "L2"}:
            result["type"] = "L1" if result["action"] == "resolved" else "L2"
        result["title"] = (result.get("title") or "ปัญหาที่แจ้งผ่าน Line")[:255]
        result.setdefault("description", result["reply"])
        if result["category"] == "equipment_request":
            result["item_name"] = (result.get("item_name") or result["title"])[:255]
            result["quantity"] = _parse_quantity(result.get("quantity"))

    return result
