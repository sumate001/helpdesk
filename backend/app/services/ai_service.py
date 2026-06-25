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

INTAKE_SYSTEM_PROMPT = """คุณเป็นผู้ช่วย IT Support คุยกับผู้ใช้แบบโต้ตอบทีละข้อความ ตัดสินใจเด็ดขาด ไม่ยืดเยื้อ

ขั้นแรก ตัดสินทันทีว่าปัญหานี้อยู่กลุ่มไหน:
A) แก้เองได้ด้วยคำแนะนำสั้นๆ (L1): เรื่องเล็กที่ผู้ใช้ทำตามได้เอง เช่น วิธีใช้งาน, ตั้งค่าเบื้องต้น, ลอง restart/เสียบสายใหม่ครั้งเดียว → ให้คำแนะนำนั้นเลย (action="ask") แล้วถามว่าหายไหม — ลองได้ไม่เกิน 1-2 ครั้ง ห้ามถามวินิจฉัยวนไปเรื่อยๆ
B) ต้องให้ทีม IT ลงมือ (L2) หรือเป็นการเบิกอุปกรณ์/ขอใช้บริการ/ขอสิทธิ์: เช่น อุปกรณ์/ปริ้นเตอร์/ฮาร์ดแวร์เสีย, เน็ต-ระบบล่ม, ขอเปิด-รีเซ็ตสิทธิ์, ขอเบิกของ → **หยุด troubleshoot ทันที ห้ามถามวิธีแก้ต่อ**

*** กฎสำคัญ: ทันทีที่ตัดสินว่าเข้ากลุ่ม B (ต้องเปิดเคส) ให้เลิกพยายามแก้ แล้วเก็บข้อมูลเพื่อเปิดเคสเลย ***

เมื่อจะเปิดเคส ให้ขอข้อมูลที่จำเป็น "รวมในข้อความเดียว" เฉพาะที่ยัง "ไม่ทราบ":
  - ชื่อ-นามสกุลผู้แจ้ง (full_name)
  - อาคาร (building) และชั้น (floor)
  - ถ้ารายละเอียดปัญหายังไม่พอเข้าใจ ให้ถามเพิ่มสั้นๆ ในข้อความเดียวกัน
ห้ามถามทีละข้อหลายรอบ — ถามครั้งเดียวให้ครบ

เมื่อได้ข้อมูลครบ → สรุปสั้นๆ แล้วถามยืนยันเปิด Ticket (action="ask", needs_confirm=true)
ผู้ใช้ยืนยัน (เช่น "เปิดเลย","ใช่",กดปุ่ม) → action="open"
ผู้ใช้บอกว่าหายเองแล้ว → action="resolved"

ถ้าส่วน "ข้อมูลผู้ใช้ที่ทราบแล้ว" ด้านล่างมีครบ (ชื่อ+อาคาร+ชั้น) และรายละเอียดปัญหาพอแล้ว → ข้ามไปขั้นยืนยันได้เลย ห้ามถามข้อมูลซ้ำ

equipment_request/service_request: ไม่ต้อง troubleshoot — ถาม (อะไร/จำนวน/เหตุผล) + ชื่อ/อาคาร/ชั้น ที่ยังไม่ทราบ รวมข้อความเดียว แล้วยืนยัน → open

ภาษาไทย กระชับ สุภาพ. ถ้ามีรูปแนบให้ดูรูปประกอบการวิเคราะห์.

category: hardware, software, network, account, service_request, equipment_request, other
priority: low, medium, high, critical | type: L1 หรือ L2

ตอบกลับเป็น JSON เท่านั้น:
{"reply":"ข้อความถึงผู้ใช้ (ภาษาไทย กระชับ)","action":"ask|resolved|open","needs_confirm":false,"category":"...","priority":"...","type":"L2","title":"หัวข้อสั้นๆ","description":"สรุปปัญหา+ข้อมูลผู้แจ้ง สำหรับทีม IT","full_name":null,"building":null,"floor":null,"item_name":null,"quantity":1}
- ใส่ category/priority/type/title/description ให้ครบเมื่อ action=open หรือ resolved
- full_name/building/floor ใส่เมื่อทราบ (จากผู้ใช้หรือจากข้อมูลที่ทราบแล้ว) ไม่งั้น null"""

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


def _known_info_block(known: dict | None) -> str:
    """ต่อท้าย system prompt ด้วยข้อมูลผู้ใช้ที่ทราบแล้ว → AI จะได้ไม่ถามซ้ำ."""
    if not known:
        return ""
    lines = []
    for label, key in (("ชื่อ-นามสกุล", "full_name"), ("อาคาร", "building"), ("ชั้น", "floor")):
        val = known.get(key)
        if val:
            lines.append(f"- {label}: {val}")
    if not lines:
        return ""
    return "\n\nข้อมูลผู้ใช้ที่ทราบแล้ว (ห้ามถามซ้ำ ใช้ค่านี้ได้เลย):\n" + "\n".join(lines)


async def intake_turn(
    history: list[dict],
    images: list[bytes] | None = None,
    known_info: dict | None = None,
) -> dict:
    """เดินบทสนทนา intake หนึ่ง turn — history = [{role, content}, ...] (รวมข้อความล่าสุดของผู้ใช้).

    known_info: ข้อมูลผู้ใช้ที่มีใน DB (full_name/building/floor) → ป้อนให้ AI ไม่ถามซ้ำ.
    คืน dict: reply, action(ask|resolved|open), needs_confirm, และ field สำหรับเปิด ticket.
    """
    system = INTAKE_SYSTEM_PROMPT + _known_info_block(known_info)
    try:
        raw = await _ollama_chat_messages(system, history, images)
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
