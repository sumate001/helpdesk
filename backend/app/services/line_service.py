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


def _text_message(text: str, with_quick_reply: bool = False) -> dict:
    msg = {"type": "text", "text": text}
    if with_quick_reply:
        msg["quickReply"] = QUICK_REPLY_FOLLOWUP
    return msg


async def reply(
    reply_token: str, text: str, with_quick_reply: bool = False
) -> list[str]:
    payload = {
        "replyToken": reply_token,
        "messages": [_text_message(text, with_quick_reply)],
    }
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


async def get_message_content(message_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{LINE_DATA_API}/message/{message_id}/content", headers=_headers()
        )
        resp.raise_for_status()
        return resp.content
