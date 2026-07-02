"""Ollama gemma4:12b integration — multi-turn intake: ช่วยแก้/เก็บข้อมูล/ตัดสินเปิด ticket.

gemma4:12b เป็น multimodal — รับรูปได้ ใช้ดู error screenshot ที่ผู้ใช้ส่งมาในกลุ่ม.
"""
import base64
import json
import logging
import re

import httpx

from app.services import settings_service

logger = logging.getLogger(__name__)


def _parse_json(raw: str) -> dict:
    """parse JSON จาก content ของ Ollama แบบทนทาน.

    บางโมเดล (เช่น ornith) ห่อ JSON ด้วย markdown fence ```json ... ``` หรือมีข้อความ
    นำ/ตาม แม้สั่ง format=json — json.loads ตรงๆ จะพัง ("char 0") ทำให้ตกไป fallback
    (= เปิดเคสเสมอ). ฟังก์ชันนี้ลอก fence + ดึงบล็อก {...} ออกมาก่อน parse.
    """
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            return json.loads(s[start : end + 1])  # อาจ raise ต่อ → ตัวเรียกจับเอง
        raise

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

def _strip_images(messages: list[dict]) -> bool:
    """ลบ field images ออกจากทุก message — คืน True ถ้ามีรูปให้ลบจริง."""
    had = False
    for m in messages:
        if m.pop("images", None) is not None:
            had = True
    return had


async def _post_chat(messages: list[dict]) -> str:
    """ยิง /api/chat. ถ้าโมเดลไม่รองรับรูป (multimodal) → ลบรูปแล้วลองใหม่ด้วย text
    ล้วน แทนที่จะ error (ไม่งั้น intake จะตกไป fallback = เปิดเคสทุกครั้ง).
    """
    url = f"{settings_service.get('OLLAMA_BASE_URL')}/api/chat"
    payload = {
        "model": settings_service.get("OLLAMA_MODEL"),
        "messages": messages,
        "stream": False,
        "format": "json",
        "think": False,  # บางโมเดลเป็น thinking model — ปิด think งานเรา (classify+ตอบสั้น) เร็วขึ้นมาก
        "keep_alive": "30m",  # คาโมเดลไว้ใน VRAM กัน cold-load ตอน user ทักจริง
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        # โมเดลที่ไม่ multimodal จะตอบ 400 ว่า "does not support multimodal" → ลองใหม่ไม่มีรูป
        if resp.status_code == 400 and "multimodal" in resp.text.lower():
            if _strip_images(messages):
                logger.warning(
                    "model '%s' ไม่รองรับรูป — ลองใหม่แบบ text ล้วน",
                    payload["model"],
                )
                resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _ollama_chat_messages(
    system: str, history: list[dict], images: list[bytes] | None = None
) -> str:
    """chat แบบ multi-turn — history = [{role, content}, ...]; images แนบที่ turn ล่าสุด."""
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    if images and messages[-1]["role"] == "user":
        messages[-1]["images"] = [base64.b64encode(b).decode() for b in images]
    return await _post_chat(messages)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


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

เมื่อจะเปิดเคส ให้ขอข้อมูลที่จำเป็น "รวมในข้อความเดียว" เฉพาะที่ยัง "ไม่ทราบ" — ทั้งข้อมูลผู้แจ้ง และข้อมูลที่ช่าง IT ต้องใช้ทำงานต่อ:

[ข้อมูลผู้แจ้ง — ทุกเคส]
  - ชื่อ-นามสกุล (full_name), อาคาร (building), ชั้น (floor)

[ข้อมูลที่ช่างต้องใช้ — เลือกถามเฉพาะที่ "เกี่ยวกับปัญหานี้" และ "ยังไม่รู้จากที่ผู้ใช้เล่ามา" อย่าถามครบทุกข้อพร่ำเพรื่อ]
ปัญหาฮาร์ดแวร์/อุปกรณ์/เน็ตเวิร์ก/ซอฟต์แวร์ (กลุ่ม B ที่ต้องซ่อม/แก้):
  - อุปกรณ์/ระบบที่มีปัญหาคืออะไร + รุ่น/หมายเลขเครื่อง/asset tag ถ้าผู้ใช้พอบอกได้
  - อาการที่เกิดจริงเป็นยังไง + มีข้อความ error อะไรขึ้นไหม (ให้พิมพ์มาตามที่เห็น)
  - เริ่มมีปัญหาตั้งแต่เมื่อไหร่ / เป็นตลอดหรือเป็นๆหายๆ
  - กระทบเฉพาะคุณ หรือคนอื่นด้วย (ทั้งแผนก/ทั้งตึก) — ใช้ประเมินความเร่งด่วน
  - เคยลองแก้อะไรไปแล้วบ้าง (ถ้ามี)
ขอเบิกอุปกรณ์/ขอใช้บริการ/ขอสิทธิ์ (equipment_request/service_request):
  - ต้องการอะไร / จำนวน / เหตุผล-ความจำเป็น (ไม่ต้องถามอาการหรือ troubleshoot)

ห้ามถามทีละข้อหลายรอบ — เลือกเฉพาะที่ขาดและเกี่ยวข้อง รวมถามครั้งเดียวให้ครบในข้อความเดียว กระชับ เป็นข้อๆ ได้

*** ลำดับสำคัญ: เทิร์นที่คุณ "ขอข้อมูลใดๆ ก็ตาม" (ชื่อ/อาคาร/ชั้น/อาการ/รุ่นเครื่อง/asset tag/จำนวน/เหตุผล ฯลฯ) ต้องตั้ง needs_confirm=false เสมอ — ห้ามขอข้อมูลแล้วขึ้นปุ่มยืนยันในเทิร์นเดียวกัน ต้องรอผู้ใช้ตอบข้อมูลก่อน เทิร์นถัดไปที่ข้อมูลครบแล้วค่อยสรุป+ยืนยัน ***

เมื่อได้ข้อมูลครบ → สรุปสั้นๆ แล้วถามยืนยันเปิด Ticket (action="ask", needs_confirm=true)
*** กฎสำคัญ: ทุกครั้งที่ reply ของคุณ "เอ่ยถึงการเปิดเคส/ถามว่าจะเปิด Ticket ให้ไหม/สรุปเรื่องเพื่อเตรียมเปิด" ต้องตั้ง needs_confirm=true ในข้อความเดียวกันนั้นเสมอ — ห้ามสรุปแล้วถามยืนยันโดยปล่อย needs_confirm=false (ปุ่มยืนยันจะไม่ขึ้น ผู้ใช้ต้องทวงซ้ำ ซึ่งผิด) ***
ห้ามแยก "สรุป" กับ "ปุ่มยืนยัน" เป็นคนละ turn — ต้องอยู่ใน turn เดียวกัน
*** ห้ามถามคำถามอื่นปนอยู่ในเทิร์นเดียวกับที่สรุป+ขอยืนยันเปิด Ticket (needs_confirm=true) — เทิร์นนั้นต้องมีคำถามเดียวคือ "ยืนยันเปิด Ticket ไหม" เท่านั้น ถ้ายังมีอะไรต้องถามเพิ่ม (อาการ/ข้อมูล/วินิจฉัย) ให้ถามให้จบก่อน แล้วค่อยสรุป+ยืนยันในเทิร์นถัดไป ***
ผู้ใช้ยืนยัน (เช่น "เปิดเลย","ใช่",กดปุ่ม) → action="open"
ผู้ใช้บอกว่าหายเองแล้ว → action="resolved"

ถ้าส่วน "ข้อมูลผู้ใช้ที่ทราบแล้ว" ด้านล่างมีครบ (ชื่อ+อาคาร+ชั้น) และรายละเอียดปัญหาพอแล้ว → ข้ามไปขั้นยืนยันได้เลย ห้ามถามข้อมูลซ้ำ

equipment_request/service_request: ไม่ต้อง troubleshoot — ถาม (อะไร/จำนวน/เหตุผล) + ชื่อ/อาคาร/ชั้น ที่ยังไม่ทราบ รวมข้อความเดียว แล้วยืนยัน → open

ภาษาไทย กระชับ สุภาพ. ถ้ามีรูปแนบให้ดูรูปประกอบการวิเคราะห์.

category: hardware, software, network, account, service_request, equipment_request, other
priority: low, medium, high, critical | type: L1 หรือ L2

ตอบกลับเป็น JSON เท่านั้น:
{"reply":"ข้อความถึงผู้ใช้ (ภาษาไทย กระชับ)","action":"ask|resolved|open","needs_confirm":false,"category":"...","priority":"...","type":"L2","title":"หัวข้อสั้นๆ","description":"สรุปให้ช่างทำงานต่อได้ทันที","full_name":null,"building":null,"floor":null,"item_name":null,"quantity":1}
- ใส่ category/priority/type/title/description ให้ครบเมื่อ action=open หรือ resolved
- description ต้องเขียนให้ช่าง IT หยิบไปทำต่อได้เลย รวบรวมจากบทสนทนาทั้งหมด: อาการ/ปัญหา, อุปกรณ์-รุ่น-asset tag, ข้อความ error, เวลาที่เริ่ม, ขอบเขตผลกระทบ, สิ่งที่ลองแก้แล้ว + ชื่อผู้แจ้ง/อาคาร/ชั้น (อย่าใส่แค่ประโยคเดียวลอยๆ)
- full_name/building/floor ใส่เมื่อทราบ (จากผู้ใช้หรือจากข้อมูลที่ทราบแล้ว) ไม่งั้น null"""

VALID_ACTIONS = {"ask", "resolved", "open"}

CONFIRM_OPEN_TEXT = "เปิด Ticket ✅"  # ข้อความจากปุ่ม quick reply "confirm"


def _confirm_was_requested(history: list[dict]) -> bool:
    """เทิร์น assistant ล่าสุดใน history ขึ้นปุ่มยืนยันเปิด ticket ไปหรือยัง
    (webhook เก็บ marker needs_confirm ไว้ใน transcript)."""
    for m in reversed(history):
        if m["role"] == "assistant":
            return bool(m.get("needs_confirm"))
    return False

# วลีที่บ่งว่า reply กำลัง "สรุป + ขอยืนยันเปิดเคส" → ควรขึ้นปุ่มยืนยันเสมอ
_CONFIRM_HINTS = (
    "เปิด ticket",
    "เปิดเคส",
    "เปิดเรื่อง",
    "เปิด ticket ให้",
    "ยืนยัน",
    "เปิดให้ไหม",
    "เปิดเลยไหม",
    "ดำเนินการเปิด",
    "open ticket",
)


def _looks_like_confirm_request(reply: str) -> bool:
    low = (reply or "").lower()
    return any(hint in low for hint in _CONFIRM_HINTS)


# คำบ่งคำถาม (ใช้ตอนไม่มี "?" เลย) — นับได้สูงสุด 1 คำถามต่อบรรทัด กันนับซ้ำ
# เพราะประโยคเดียวมักมีหลาย marker ปนกัน (เช่น "...ไหมครับ?" มีทั้ง "ไหม" และ "?")
_QUESTION_WORD_MARKERS = ("ไหม", "มั้ย", "รึยัง", "หรือยัง", "หรือไม่", "รึเปล่า", "หรือเปล่า")


def _count_questions(reply: str) -> int:
    """นับจำนวนประโยคคำถามแบบหยาบๆ — ใช้ "?" เป็นหลักเพราะแม่นสุด (นับตามจำนวนจริง ไม่ซ้ำ
    ต่อให้ประโยคนั้นมีทั้ง "ไหม" และ "?" ก็นับเป็น 1 คำถาม). ถ้าไม่มี "?" เลยค่อย fallback ไป
    นับ marker คำถามแยกตามบรรทัด (อย่างมาก 1 คำถามต่อบรรทัด)."""
    text = reply or ""
    if "?" in text:
        return text.count("?")
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) <= 1:
        return 1 if any(m in text for m in _QUESTION_WORD_MARKERS) else 0
    return sum(1 for l in lines if any(m in l for m in _QUESTION_WORD_MARKERS))


def _reply_has_extra_question(reply: str) -> bool:
    """True ถ้า reply มีคำถามมากกว่า 1 ประโยค — เช่นถามข้อมูล/วินิจฉัยต่อ พร้อมกับสรุปขอยืนยัน
    ในเทิร์นเดียวกัน. กรณีนี้ต้องรอผู้ใช้ตอบคำถามที่ค้างอยู่ก่อน ยังไม่ควรขึ้นปุ่มยืนยัน."""
    return _count_questions(reply) > 1


def _question_sentences(reply: str) -> list[str]:
    """แยกประโยคคำถามใน reply ออกมาเป็น list — ใช้ "?" เป็นหลัก (เอาท่อนข้อความ
    ก่อน "?" ในบรรทัดเดียวกันเป็นตัวคำถาม), ไม่มี "?" เลยค่อย fallback หา marker รายบรรทัด."""
    text = reply or ""
    if "?" in text:
        questions = []
        for seg in text.split("?")[:-1]:
            q = seg.split("\n")[-1].strip()
            if q:
                questions.append(q)
        return questions
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return [l for l in lines if any(m in l for m in _QUESTION_WORD_MARKERS)]


# คำที่บ่งว่าประโยคคำถามนั้นคือ "คำถามยืนยันเปิดเคส" — คำถามที่ไม่มีคำพวกนี้ถือว่าเป็น
# คำถามขอข้อมูล/วินิจฉัย (เช่น "อาการเป็นยังไง", "รุ่นอะไร") ซึ่งต้องรอคำตอบก่อน
_CONFIRM_QUESTION_HINTS = ("เปิด", "ยืนยัน", "ดำเนินการ", "ถูกต้อง", "ticket", "เคส")

# วลีคำสั่ง "ขอข้อมูล" — เจอที่ไหนใน reply ก็ถือว่าเทิร์นนี้กำลังรอคำตอบจากผู้ใช้
# (ครอบคลุมทั้งประโยคคำถามผสม "ขอทราบรุ่น...แล้วจะเปิดเคสให้" และประโยคบอกเล่า
# "รบกวนแจ้งชื่อ...ด้วยครับ" ที่ไม่มี "?"/marker คำถามเลย)
_INFO_REQUEST_HINTS = (
    "ขอทราบ",
    "รบกวนแจ้ง",
    "รบกวนบอก",
    "รบกวนขอ",
    "รบกวนระบุ",
    "ช่วยแจ้ง",
    "ช่วยบอก",
    "ช่วยระบุ",
    "ขอข้อมูล",
    "ขอรายละเอียด",
    "ขอชื่อ",
    "พิมพ์มาตามที่เห็น",
)


def _has_info_question(reply: str) -> bool:
    """True ถ้าเทิร์นนี้ยังขอข้อมูลจากผู้ใช้อยู่ (ไม่ใช่แค่ถามยืนยันเปิดเคส) —
    ห้ามขึ้นปุ่มยืนยัน ต้องรอผู้ใช้ตอบข้อมูลก่อน."""
    text = (reply or "").lower()
    if any(h in text for h in _INFO_REQUEST_HINTS):
        return True
    return any(
        not any(h in q.lower() for h in _CONFIRM_QUESTION_HINTS)
        for q in _question_sentences(reply)
    )


def _has_required_identity(result: dict, known_info: dict | None) -> bool:
    """ข้อมูลผู้แจ้งครบหรือยัง (ชื่อ + อาคาร + ชั้น) — รวมจาก known_info (DB) กับที่ AI
    สกัดได้ในเทิร์นนี้. ใช้กันไม่ให้ขึ้นปุ่มยืนยันทั้งที่ยังถามข้อมูลผู้แจ้งไม่ครบ.
    """
    known = known_info or {}
    return all(
        bool(result.get(key) or known.get(key))
        for key in ("full_name", "building", "floor")
    )

# ต่อท้าย system prompt เฉพาะแชทกลุ่ม — ให้บอทประเมินว่าข้อความล่าสุด "คุยกับบอท" จริงไหม
IGNORE_BLOCK = """

[บริบทแชทกลุ่ม] ข้อความนี้มาจากห้องแชทกลุ่มที่มีหลายคนคุยกัน ก่อนตอบให้ประเมินก่อนว่า "ข้อความล่าสุดของผู้ใช้ กำลังคุยกับคุณ (บอท IT) เรื่องปัญหาที่กำลังช่วยอยู่หรือไม่":
- ถ้าข้อความล่าสุดดูเหมือนคุยกับคนอื่นในกลุ่ม คุยเล่น ทักทาย หรือเปลี่ยนเรื่องไปเรื่องที่ไม่เกี่ยวกับปัญหา IT ที่กำลังช่วย → action="ignore" (ปล่อยผ่าน ไม่ต้องตอบ ไม่ต้องสนใจ)
- ถ้ายังเป็นการคุยกับคุณเรื่องที่กำลังช่วยอยู่ (ตอบคำถามคุณ ให้ข้อมูลเพิ่ม ยืนยัน ฯลฯ) → ตอบตามปกติ"""


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


def _kb_block(kb_context: str | None) -> str:
    """ต่อท้าย system prompt ด้วยความรู้ระบบ/นโยบายจาก RAG."""
    if not kb_context:
        return ""
    return (
        "\n\nข้อมูลระบบ/นโยบาย IT ภายในบริษัท (ใช้อ้างอิงเมื่อเกี่ยวข้อง ยึดตามนี้ ห้ามเดาเอง — "
        "ถ้านโยบายระบุว่าเรื่องใดต้องขออนุมัติ/ต้องให้ IT ดำเนินการ ให้เปิดเคสตามนั้น):\n"
        + kb_context
    )


async def intake_turn(
    history: list[dict],
    images: list[bytes] | None = None,
    known_info: dict | None = None,
    allow_ignore: bool = False,
    kb_context: str | None = None,
) -> dict:
    """เดินบทสนทนา intake หนึ่ง turn — history = [{role, content}, ...] (รวมข้อความล่าสุดของผู้ใช้).

    known_info: ข้อมูลผู้ใช้ที่มีใน DB (full_name/building/floor) → ป้อนให้ AI ไม่ถามซ้ำ.
    allow_ignore: เปิดในแชทกลุ่ม → ให้ AI คืน action="ignore" ถ้าข้อความไม่ได้คุยกับบอท.
    kb_context: ความรู้ระบบ/นโยบาย IT ที่ retrieve มาจาก RAG → ใช้ตอบ/classify ให้ตรงบริษัท.
    คืน dict: reply, action(ask|resolved|open|ignore), needs_confirm, และ field สำหรับเปิด ticket.
    """
    system = INTAKE_SYSTEM_PROMPT + _known_info_block(known_info) + _kb_block(kb_context)
    if allow_ignore:
        system += IGNORE_BLOCK
    try:
        raw = await _ollama_chat_messages(system, history, images)
        result = _parse_json(raw)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        if allow_ignore:
            # ข้อความในกลุ่มที่ไม่ได้เรียกบอทตรงๆ — AI ล่มก็เงียบไว้ ดีกว่าเปิด ticket
            # จากข้อความที่อาจไม่ได้คุยกับบอทเลย (กัน ticket spam ตอน Ollama ล่ม)
            logger.warning("AI intake failed on unaddressed group message, ignoring: %s", exc)
            return {"action": "ignore", "reply": ""}
        logger.warning("AI intake failed, fallback to open ticket: %s", exc)
        return _intake_fallback()

    valid_actions = VALID_ACTIONS | {"ignore"} if allow_ignore else VALID_ACTIONS
    if result.get("action") not in valid_actions:
        result["action"] = "ask"
    if result["action"] == "ignore":
        return {"action": "ignore", "reply": ""}
    result["needs_confirm"] = _as_bool(result.get("needs_confirm"))
    result.setdefault("reply", "รบกวนเล่ารายละเอียดเพิ่มอีกนิดได้ไหมครับ")

    # เปิด ticket ได้เฉพาะเมื่อ "ผ่านการยืนยัน" แล้ว: เทิร์นก่อนขึ้นปุ่มยืนยันไว้ หรือ
    # ผู้ใช้กดปุ่มยืนยันตรงๆ — โมเดลข้ามขั้น (open ทันที) → ปรับเป็น ask แล้วปล่อยให้
    # กฎด้านล่างตัดสินว่าเทิร์นนี้ควรขึ้นปุ่มหรือยัง (ถ้า reply ยังขอข้อมูลอยู่ ปุ่มจะไม่ขึ้น)
    if result["action"] == "open":
        last_user = next(
            (m["content"] for m in reversed(history) if m["role"] == "user"), ""
        )
        confirmed = (
            _confirm_was_requested(history[:-1])
            or last_user.strip() == CONFIRM_OPEN_TEXT
        )
        if not confirmed:
            result["action"] = "ask"
            result["needs_confirm"] = True

    if result["action"] == "ask":
        if not _has_required_identity(result, known_info):
            # ยังเก็บข้อมูลผู้แจ้งไม่ครบ (ชื่อ/อาคาร/ชั้น) → ยังไม่ถึงขั้นยืนยัน
            # ห้ามขึ้นปุ่ม แม้โมเดลจะตั้ง needs_confirm มา (กันบอทถามแล้วเด้งปุ่มเลย)
            result["needs_confirm"] = False
        else:
            if not result["needs_confirm"] and _looks_like_confirm_request(result["reply"]):
                # ข้อมูลครบแล้ว + reply เป็นการสรุป/ขอยืนยัน แต่โมเดลลืมตั้ง → บังคับขึ้นปุ่ม
                result["needs_confirm"] = True
            if result["needs_confirm"] and (
                _reply_has_extra_question(result["reply"])
                or _has_info_question(result["reply"])
            ):
                # reply ยังมีคำถามค้างที่ต้องรอคำตอบ: มีหลายคำถามปนกัน หรือมีคำถาม "ขอข้อมูล/
                # วินิจฉัย" อยู่ (แม้จะคำถามเดียว เช่น "ขอทราบรุ่นเครื่อง...แล้วจะเปิดเคสให้") —
                # ต้องรอผู้ใช้ตอบข้อมูลก่อน ยังไม่ขึ้นปุ่มยืนยันในเทิร์นนี้ ไม่ว่า needs_confirm
                # จะมาจากโมเดลหรือถูกบังคับตั้งจากด้านบนก็ตาม
                result["needs_confirm"] = False

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
