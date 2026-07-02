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


def _text_message(
    text: str, with_quick_reply: bool = False, quick_reply: str | None = None
) -> dict:
    msg = {"type": "text", "text": text}
    if quick_reply and quick_reply in _QUICK_REPLIES:
        msg["quickReply"] = _QUICK_REPLIES[quick_reply]
    elif with_quick_reply:
        msg["quickReply"] = QUICK_REPLY_FOLLOWUP
    return msg


async def reply(
    reply_token: str,
    text: str,
    with_quick_reply: bool = False,
    quick_reply: str | None = None,
) -> list[str]:
    payload = {
        "replyToken": reply_token,
        "messages": [_text_message(text, with_quick_reply, quick_reply)],
    }
    return await _post("/message/reply", payload)


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


async def push(to: str, text: str, with_quick_reply: bool = False) -> list[str]:
    payload = {"to": to, "messages": [_text_message(text, with_quick_reply)]}
    return await _post("/message/push", payload)


async def notify_group(text: str) -> list[str]:
    if not settings.LINE_GROUP_IT_ID:
        logger.info("LINE_GROUP_IT_ID not set, skip group notify")
        return []
    return await push(settings.LINE_GROUP_IT_ID, text)


async def _post(path: str, payload: dict) -> list[str]:
    """ส่งข้อความ แล้วคืน list ของ message id ที่ LINE ตอบกลับใน sentMessages."""
    if not settings.LINE_CHANNEL_ACCESS_TOKEN:
        logger.info("LINE token not set, skip send: %s", payload)
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
        logger.warning("verify id_token failed %s: %s", resp.status_code, resp.text)
        return None
    return resp.json()


async def get_message_content(message_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{LINE_DATA_API}/message/{message_id}/content", headers=_headers()
        )
        resp.raise_for_status()
        return resp.content
