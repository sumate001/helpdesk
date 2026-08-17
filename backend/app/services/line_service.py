"""Line Messaging API — reply, push, group notify, profile, content download."""
import hashlib
import hmac
import base64
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot"
LINE_DATA_API = "https://api-data.line.me/v2/bot"

QUICK_REPLY_FOLLOWUP = {
    "items": [
        {
            "type": "action",
            "action": {"type": "message", "label": "แก้ได้แล้ว ✅", "text": "แก้ได้แล้ว ✅"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "ยังไม่ได้ ❌", "text": "ยังไม่ได้ ❌"},
        },
    ]
}

# ปุ่มยืนยันตอน intake สรุปเสร็จ ก่อนเปิด ticket
QUICK_REPLY_CONFIRM = {
    "items": [
        {
            "type": "action",
            "action": {"type": "message", "label": "เปิด Ticket ✅", "text": "เปิด Ticket ✅"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "ยังไม่ต้อง ❌", "text": "ยังไม่ต้อง ❌"},
        },
    ]
}

_QUICK_REPLIES = {"followup": QUICK_REPLY_FOLLOWUP, "confirm": QUICK_REPLY_CONFIRM}


def choice_quick_reply(labels: list[str]) -> dict | None:
    """ปุ่มตัวเลือกแบบสร้างสด (เช่น รายชื่อช่างให้หัวหน้างานกดมอบหมาย).

    LINE จำกัด 13 ปุ่ม/ข้อความ และ label ยาวได้ 20 ตัวอักษร — ตัดให้อัตโนมัติ.
    """
    items = [
        {
            "type": "action",
            "action": {"type": "message", "label": lb[:20], "text": lb},
        }
        for lb in labels[:13] if lb
    ]
    return {"items": items} if items else None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.LINE_CHANNEL_SECRET:
        return True  # dev mode
    mac = hmac.new(
        settings.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature or "")


def _utf16_len(s: str) -> int:
    """ความยาวแบบ UTF-16 code unit — LINE นับ index/length ของ mention แบบนี้
    (อีโมจิ 1 ตัว = 2 หน่วย) ใช้ len() ตรงๆ ตำแหน่ง mention จะเพี้ยนเพราะข้อความมีอีโมจิ."""
    return len(s.encode("utf-16-le")) // 2


def _mentionees(text: str, mentions: dict[str, str] | None) -> list[dict]:
    """แปลง {"@ชื่อ": lineUserId} เป็น mentionees ตามตำแหน่งที่ label โผล่ในข้อความ."""
    out = []
    for label, user_id in (mentions or {}).items():
        pos = text.find(label)
        if pos < 0 or not user_id:
            continue
        out.append({
            "index": _utf16_len(text[:pos]),
            "length": _utf16_len(label),
            "userId": user_id,
        })
    return out


def _text_message(
    text: str,
    with_quick_reply: bool = False,
    quick_reply: str | dict | None = None,
    mentions: dict[str, str] | None = None,
) -> dict:
    msg = {"type": "text", "text": text}
    mentionees = _mentionees(text, mentions)
    if mentionees:
        msg["mention"] = {"mentionees": mentionees}
    if isinstance(quick_reply, dict):  # ปุ่มที่สร้างสด (choice_quick_reply)
        msg["quickReply"] = quick_reply
    elif quick_reply and quick_reply in _QUICK_REPLIES:
        msg["quickReply"] = _QUICK_REPLIES[quick_reply]
    elif with_quick_reply:
        msg["quickReply"] = QUICK_REPLY_FOLLOWUP
    return msg


async def reply(
    reply_token: str,
    text: str,
    with_quick_reply: bool = False,
    quick_reply: str | dict | None = None,
) -> list[str]:
    payload = {
        "replyToken": reply_token,
        "messages": [_text_message(text, with_quick_reply, quick_reply)],
    }
    return await _post("/message/reply", payload)


def form_link(slug: str) -> str | None:
    """ลิงก์เปิดฟอร์ม LIFF แบบข้อความล้วน — None ถ้ายังไม่ตั้ง LIFF_BASE_URL."""
    if not settings.LIFF_BASE_URL:
        return None
    return f"{settings.LIFF_BASE_URL}?form={slug}"


def form_flex(name: str, slug: str, description: str | None = None) -> dict | None:
    """Flex bubble ปุ่มเปิดฟอร์ม LIFF — None ถ้ายังไม่ตั้ง LIFF_BASE_URL."""
    if not settings.LIFF_BASE_URL:
        return None
    uri = f"{settings.LIFF_BASE_URL}?form={slug}"
    body = [{"type": "text", "text": name, "weight": "bold", "size": "lg", "wrap": True}]
    if description:
        body.append(
            {"type": "text", "text": description, "wrap": True, "size": "sm", "color": "#666666"}
        )
    body.append(
        {"type": "text", "text": "กดปุ่มด้านล่างเพื่อกรอกแบบฟอร์ม", "wrap": True, "size": "sm", "color": "#666666"}
    )
    return {
        "type": "flex",
        "altText": f"แบบฟอร์ม: {name}",
        "contents": {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": body},
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#4F46E5",
                        "action": {"type": "uri", "label": "กรอกฟอร์ม", "uri": uri},
                    }
                ],
            },
        },
    }


async def reply_flex(reply_token: str, flex: dict) -> list[str]:
    payload = {"replyToken": reply_token, "messages": [flex]}
    return await _post("/message/reply", payload)


async def push(
    to: str,
    text: str,
    with_quick_reply: bool = False,
    mentions: dict[str, str] | None = None,
) -> list[str]:
    payload = {
        "to": to,
        "messages": [_text_message(text, with_quick_reply, mentions=mentions)],
    }
    return await _post("/message/push", payload)


def close_case_flex(ticket_no: str, ticket_id: int, summary: str) -> dict:
    """Flex bubble แจ้งช่างพร้อมปุ่ม 'ปิดเคส ✅' (postback) — กดแล้วบอทไปปิดเคสให้.

    postback.data พก action+ticket_id เพื่อให้ webhook รู้ว่าจะปิด ticket ไหน.
    """
    return {
        "type": "flex",
        "altText": f"เคส {ticket_no} รอปิดงาน",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"🎫 {ticket_no}", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": summary, "size": "sm", "wrap": True, "color": "#555555"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#22c55e",
                        "action": {
                            "type": "postback",
                            "label": "ปิดเคส ✅",
                            "data": f"action=close_case&ticket_id={ticket_id}",
                            "displayText": f"ปิดเคส {ticket_no}",
                        },
                    }
                ],
            },
        },
    }


# itamtv Level (SLA) → ป้ายอ่านง่ายบนการ์ดช่าง
ITAMTV_LEVEL_LABELS = {
    "1": "Level 1 · ควรเสร็จใน 30 นาที",
    "2": "Level 2 · ควรเสร็จใน 2 ชั่วโมง",
    "3": "Level 3 · ควรเสร็จใน 1 วันทำการ",
    "4": "Level 4 · Open (งานยาว)",
}


def work_case_flex(ticket_no: str, ticket_id: int, summary: str, status_th: str,
                   level: str | None = None) -> dict:
    """Flex bubble แจ้ง staff ว่ามีงานเข้า พร้อมปุ่มปรับสถานะครบ workflow.

    ปุ่มพก action ต่างกันใน postback.data → webhook `_handle_postback` แยกจัดการ:
    รับงาน (accept → in_progress + assign) / ปิดเคส (close_case → resolved).
    level = itamtv Level ที่ AI ประเมิน — แสดงให้ช่างเห็นพร้อมกำกับว่าเป็นการประเมินของระบบ
    """
    def _btn(label: str, action: str, color: str) -> dict:
        return {
            "type": "button",
            "style": "primary",
            "color": color,
            "height": "sm",
            "action": {
                "type": "postback",
                "label": label,
                "data": f"action={action}&ticket_id={ticket_id}",
                "displayText": f"{label} {ticket_no}",
            },
        }

    return {
        "type": "flex",
        "altText": f"งานใหม่ {ticket_no}",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"🎫 {ticket_no}", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": summary, "size": "sm", "wrap": True, "color": "#555555"},
                    {"type": "text", "text": f"สถานะ: {status_th}", "size": "xs", "color": "#888888"},
                    *([{
                        "type": "text",
                        "text": f"⏱️ {ITAMTV_LEVEL_LABELS[level]} (ระบบประเมิน)",
                        "size": "xs", "color": "#d97706", "wrap": True,
                    }] if level in ITAMTV_LEVEL_LABELS else []),
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _btn("รับงาน 🙋", "accept_case", "#3b82f6"),
                    _btn("ปิดเคส ✅", "close_case", "#22c55e"),
                ],
            },
        },
    }


def approver_invite_flex(approver_id: int, department: str, scope: list[str],
                         proposed_by: str | None = None) -> dict:
    """การ์ดแจ้งคนที่ถูกตั้งเป็นผู้อนุมัติ — บอกว่าอนุมัติอะไรได้บ้าง + ปุ่มยอมรับ/ปฏิเสธ.

    ถูกตั้งแล้วไม่รู้ตัว = คำขอไปจ่ออยู่เงียบๆ ที่คนที่ไม่รู้ว่าต้องกด จึงต้องแจ้งตั้งแต่ต้น
    """
    def _btn(label: str, action: str, color: str) -> dict:
        return {
            "type": "button", "style": "primary", "color": color, "height": "sm",
            "action": {
                "type": "postback", "label": label,
                "data": f"action={action}&appr_id={approver_id}",
                "displayText": label,
            },
        }

    body = [
        {"type": "text", "text": "คุณถูกตั้งเป็นผู้อนุมัติ", "weight": "bold",
         "size": "lg", "wrap": True},
        {"type": "text", "text": f"ของฝ่าย: {department}", "size": "sm",
         "color": "#555555", "wrap": True},
    ]
    if proposed_by:
        body.append({"type": "text", "text": f"แจ้งโดย: {proposed_by}", "size": "xs",
                     "color": "#888888", "wrap": True})
    body.append({"type": "separator", "margin": "md"})
    body.append({"type": "text", "text": "เรื่องที่คุณจะได้รับให้พิจารณา:", "size": "sm",
                 "color": "#333333", "margin": "md"})
    if scope:
        body += [{"type": "text", "text": f"• {s}", "size": "sm", "color": "#555555",
                  "wrap": True} for s in scope[:8]]
    else:
        body.append({"type": "text", "text": "• (ยังไม่มีเรื่องที่ต้องอนุมัติในระบบ)",
                     "size": "sm", "color": "#999999", "wrap": True})
    body.append({
        "type": "text", "margin": "md", "size": "xs", "color": "#888888", "wrap": True,
        "text": "เมื่อมีพนักงานในฝ่ายยื่นคำขอ ระบบจะส่งการ์ดให้คุณกดอนุมัติ/ไม่อนุมัติที่นี่",
    })

    return {
        "type": "flex",
        "altText": f"คุณถูกตั้งเป็นผู้อนุมัติของฝ่าย {department}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "🔐 สิทธิ์ผู้อนุมัติ", "weight": "bold",
                              "color": "#ffffff", "size": "md"}],
                "backgroundColor": "#0ea5e9", "paddingAll": "12px",
            },
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body},
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    _btn("ยอมรับ ✅", "accept_approver", "#22c55e"),
                    _btn("ไม่ใช่ผมนะ ❌", "decline_approver", "#ef4444"),
                ],
            },
        },
    }


def approval_flex(request_id: int, ticket_no: str, title: str, summary: str,
                  requester: str, department: str) -> dict:
    """การ์ดขออนุมัติสำหรับหัวหน้า — ปุ่มเป็น postback จึงรู้ userId คนกดแน่นอน
    (ต่อให้ forward การ์ดให้คนอื่น คนอื่นกดก็ไม่ผ่านการตรวจสิทธิ์)."""
    def _btn(label: str, action: str, color: str) -> dict:
        return {
            "type": "button", "style": "primary", "color": color, "height": "sm",
            "action": {
                "type": "postback", "label": label,
                "data": f"action={action}&req_id={request_id}",
                "displayText": f"{label} — {ticket_no}",
            },
        }

    def _row(label: str, value: str) -> dict:
        return {
            "type": "box", "layout": "baseline", "spacing": "sm",
            "contents": [
                {"type": "text", "text": label, "size": "sm", "color": "#888888", "flex": 2},
                {"type": "text", "text": value or "-", "size": "sm", "color": "#333333",
                 "flex": 5, "wrap": True},
            ],
        }

    return {
        "type": "flex",
        "altText": f"ขออนุมัติ: {title} ({ticket_no})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🔐 คำขออนุมัติ", "weight": "bold",
                     "color": "#ffffff", "size": "md"},
                ],
                "backgroundColor": "#4f46e5", "paddingAll": "12px",
            },
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True},
                    _row("ผู้ขอ", requester),
                    _row("แผนก", department),
                    _row("เลขที่", ticket_no),
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": summary, "size": "sm", "wrap": True,
                     "color": "#555555", "margin": "md"},
                ],
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    _btn("อนุมัติ ✅", "approve_req", "#22c55e"),
                    _btn("ไม่อนุมัติ ❌", "reject_req", "#ef4444"),
                    {"type": "text", "text": "กดได้เฉพาะผู้อนุมัติที่ระบุไว้เท่านั้น",
                     "size": "xxs", "color": "#aaaaaa", "align": "center"},
                ],
            },
        },
    }


def progress_case_flex(ticket_no: str, ticket_id: int, summary: str) -> dict:
    """Flex ตามถามความคืบหน้าจากช่างที่รับงาน + ปุ่มปิดเคสในตัว (เสร็จแล้วกดปิดได้เลย)."""
    return {
        "type": "flex",
        "altText": f"คืบหน้าถึงไหนแล้ว {ticket_no}",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"🎫 {ticket_no}", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": summary, "size": "sm", "wrap": True, "color": "#555555"},
                    {"type": "text", "text": "งานคืบหน้าถึงไหนแล้วครับ? เสร็จแล้วกดปิดได้เลย 👇",
                     "size": "sm", "wrap": True, "color": "#888888"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#22c55e",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "ปิดเคส ✅",
                            "data": f"action=close_case&ticket_id={ticket_id}",
                            "displayText": f"ปิดเคส {ticket_no}",
                        },
                    }
                ],
            },
        },
    }


async def push_flex(to: str, flex: dict) -> list[str]:
    return await _post("/message/push", {"to": to, "messages": [flex]})


async def notify_group(text: str, mentions: dict[str, str] | None = None) -> list[str]:
    if not settings.LINE_GROUP_IT_ID:
        logger.info("LINE_GROUP_IT_ID not set, skip group notify")
        return []
    ids = await push(settings.LINE_GROUP_IT_ID, text, mentions=mentions)
    if not ids and mentions:
        # mention คนที่ไม่ได้อยู่ในกลุ่มนี้ LINE จะตีกลับทั้งข้อความ → ส่งซ้ำแบบไม่ mention
        logger.warning("group notify with mention failed, retry without mention")
        ids = await push(settings.LINE_GROUP_IT_ID, text)
    return ids


async def _post(path: str, payload: dict) -> list[str]:
    """ส่งข้อความ แล้วคืน list ของ message id ที่ LINE ตอบกลับใน sentMessages."""
    if not settings.LINE_CHANNEL_ACCESS_TOKEN:
        logger.info("LINE token not set, skip send to path %s", path)
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(LINE_API + path, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error("Line API error %s: %s", resp.status_code, resp.text)
            return []
        sent = resp.json().get("sentMessages", [])
        return [m["id"] for m in sent if m.get("id")]


async def get_profile(line_user_id: str) -> dict:
    if not settings.LINE_CHANNEL_ACCESS_TOKEN:
        return {}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{LINE_API}/profile/{line_user_id}", headers=_headers()
        )
        if resp.status_code >= 400:
            return {}
        return resp.json()


async def verify_id_token(id_token: str) -> dict | None:
    """ตรวจ ID token จาก LIFF กับ LINE — คืน payload ({sub, name, picture}) ถ้าจริง.

    sub = LINE userId ที่เชื่อถือได้ (LINE เซ็นมา ปลอมไม่ได้). คืน None ถ้า token ไม่ผ่าน.
    """
    if not settings.LINE_CHANNEL_ID:
        logger.error("LINE_CHANNEL_ID ไม่ได้ตั้ง — verify ID token ไม่ได้")
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.line.me/oauth2/v2.1/verify",
            data={"id_token": id_token, "client_id": settings.LINE_CHANNEL_ID},
        )
    if resp.status_code >= 400:
        logger.warning("verify id_token failed with status %s", resp.status_code)
        return None
    return resp.json()


async def get_message_content(message_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{LINE_DATA_API}/message/{message_id}/content", headers=_headers()
        )
        resp.raise_for_status()
        return resp.content
