"""Line Messaging API webhook — multi-turn intake: แก้ปัญหาเบื้องต้น/เก็บข้อมูล แล้วยืนยันก่อนเปิด ticket."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.services import (
    ai_service,
    bot_message_service,
    conversation_service,
    followup_service,
    line_service,
    storage_service,
    ticket_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

RESOLVED_TEXT = "แก้ได้แล้ว ✅"
NOT_RESOLVED_TEXT = "ยังไม่ได้ ❌"
APPROVAL_CATEGORIES = ("equipment_request", "service_request")


@router.post("/line")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not line_service.verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="invalid signature")

    payload = await request.json()
    for event in payload.get("events", []):
        try:
            await _handle_event(db, event)
        except Exception:  # noqa: BLE001
            logger.exception("error handling event")
    return {"status": "ok"}


async def _reply(
    db: Session,
    reply_token: str,
    text: str,
    with_quick_reply: bool = False,
    quick_reply: str | None = None,
) -> None:
    """ตอบกลับ + จำ message id ที่ส่ง เพื่อรู้ทีหลังว่า user quote-reply ข้อความบอท."""
    ids = await line_service.reply(reply_token, text, with_quick_reply, quick_reply)
    bot_message_service.record(db, ids)


async def _notify_group(db: Session, text: str) -> None:
    ids = await line_service.notify_group(text)
    bot_message_service.record(db, ids)


async def _handle_event(db: Session, event: dict) -> None:
    etype = event.get("type")
    source = event.get("source", {})
    line_user_id = source.get("userId")

    # ช่วยหา groupId ตอน setup — เชิญ bot เข้ากลุ่มแล้วพิมพ์ในกลุ่ม จะเห็นค่านี้ใน log
    if source.get("groupId"):
        logger.info("📌 groupId = %s (เอาไปใส่ LINE_GROUP_IT_ID)", source["groupId"])

    if etype == "follow" and line_user_id:
        profile = await line_service.get_profile(line_user_id)
        ticket_service.upsert_line_user(db, line_user_id, profile)
        db.commit()
        return

    if etype != "message" or not line_user_id:
        return

    message = event.get("message", {})
    mtype = message.get("type")
    reply_token = event.get("replyToken")
    source_type = source.get("type")

    # แชท 1-1 → ทุกข้อความเข้า intake
    if source_type == "user":
        if mtype == "text":
            await _handle_user_text(db, line_user_id, message.get("text", ""), reply_token)
        elif mtype == "image":
            await _handle_user_image(db, line_user_id, message.get("id"), reply_token)
        return

    # แชทกลุ่ม/ห้อง → intake เฉพาะเมื่อถูกเรียก หรืออยู่ในบทสนทนาที่ยัง active
    source_id = source.get("groupId") or source.get("roomId")
    if source_type in ("group", "room") and source_id:
        if mtype == "text":
            await _handle_group_text(db, source_id, line_user_id, message, reply_token)
        elif mtype == "image":
            await _handle_group_image(db, source_id, line_user_id, message, reply_token)


# --------------------------------------------------------------------------
# Group trigger helpers
# --------------------------------------------------------------------------

def _strip_trigger_keyword(text: str) -> str | None:
    """ถ้าข้อความขึ้นต้นด้วยคำเรียกบอท → คืนคำถามที่ตัดคำเรียกออก, ไม่ใช่ → None."""
    from app.core.config import settings

    stripped = text.lstrip()
    low = stripped.lower()
    for kw in settings.group_trigger_list:
        if low.startswith(kw):
            return stripped[len(kw):].lstrip(" :,-") or ""
    return None


def _bot_mentioned(message: dict) -> bool:
    """bot ถูก @ เรียกในข้อความกลุ่มหรือไม่ (Line แนบ mention.mentionees[].isSelf)."""
    mentionees = (message.get("mention") or {}).get("mentionees") or []
    return any(m.get("isSelf") for m in mentionees)


def _strip_self_mentions(message: dict) -> str:
    """ตัดข้อความส่วนที่เป็น @ชื่อบอท ออก เหลือเฉพาะคำถามจริง."""
    text = message.get("text", "")
    mentionees = (message.get("mention") or {}).get("mentionees") or []
    spans = sorted(
        (m["index"], m["index"] + m["length"])
        for m in mentionees
        if m.get("isSelf") and "index" in m and "length" in m
    )
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text.strip()


def _group_trigger_query(db: Session, message: dict) -> str | None:
    """ในกลุ่ม: บอทถูกเรียกไหม → คืนข้อความคำถาม (อาจ ""), ไม่ถูกเรียก → None."""
    if _bot_mentioned(message):
        return _strip_self_mentions(message)
    if bot_message_service.is_bot_message(db, message.get("quotedMessageId")):
        return _strip_self_mentions(message)
    return _strip_trigger_keyword(message.get("text", ""))


# --------------------------------------------------------------------------
# Intake core
# --------------------------------------------------------------------------

def _store_attachment(
    db: Session, ticket: Ticket, message_id: str, content: bytes
) -> None:
    """อัปโหลดรูปลง MinIO + บันทึก attachment ผูกกับ ticket."""
    object_name = f"{ticket.ticket_no}/{message_id}.jpg"
    path = storage_service.upload_bytes(object_name, content, "image/jpeg")
    _add_attachment_row(db, ticket.id, message_id, path, len(content))


def _add_attachment_row(
    db: Session, ticket_id: int, message_id: str, path: str, size: int
) -> None:
    from app.models.ticket_attachment import TicketAttachment

    db.add(
        TicketAttachment(
            ticket_id=ticket_id,
            file_name=f"{message_id}.jpg",
            file_path=path,
            mime_type="image/jpeg",
            file_size=size,
            line_message_id=message_id,
        )
    )
    db.commit()


def _store_pending_image(
    db: Session, conv: Conversation, message_id: str, content: bytes
) -> None:
    """ระหว่าง intake ยังไม่มี ticket → เก็บรูปลง MinIO ชั่วคราว รอผูกตอนเปิด ticket."""
    object_name = f"conv-{conv.id}/{message_id}.jpg"
    path = storage_service.upload_bytes(object_name, content, "image/jpeg")
    conversation_service.add_pending_image(db, conv, message_id, path, len(content))


def _attach_pending_images(db: Session, conv: Conversation, ticket: Ticket) -> None:
    for img in conversation_service.get_pending_images(conv):
        _add_attachment_row(
            db, ticket.id, img["message_id"], img["object_path"], img["size"]
        )


def _update_location(db: Session, lu: LineUser, result: dict) -> None:
    changed = False
    if result.get("building"):
        lu.building = str(result["building"])[:100]
        changed = True
    if result.get("floor"):
        lu.floor = str(result["floor"])[:20]
        changed = True
    if changed:
        db.commit()


def _create_ticket_from_intake(
    db: Session, lu: LineUser, result: dict, status: str, ticket_type: str
) -> Ticket:
    ticket = ticket_service.create_ticket(
        db,
        title=result["title"],
        description=result.get("description") or result.get("reply"),
        category=result["category"],
        ticket_type=ticket_type,
        priority=result["priority"],
        status=status,
        line_user_id=lu.id,
        ai_response=result.get("reply"),
    )
    if result["category"] == "equipment_request":
        from app.models.equipment_request import EquipmentRequest

        db.add(
            EquipmentRequest(
                ticket_id=ticket.id,
                item_name=(result.get("item_name") or result["title"])[:255],
                quantity=result.get("quantity", 1),
                reason=result.get("description") or result["title"],
            )
        )
        db.commit()
    return ticket


async def _run_intake(
    db: Session,
    conv: Conversation,
    lu: LineUser,
    reply_token: str,
    user_text: str,
    images: list[bytes] | None,
) -> None:
    """เดินบทสนทนา intake หนึ่ง turn แล้วทำตาม action (ask/resolved/open)."""
    conversation_service.append_message(
        db, conv, "user", user_text.strip() or "[ผู้ใช้ส่งรูปภาพ]"
    )
    history = conversation_service.get_transcript(conv)
    result = await ai_service.intake_turn(history, images=images)
    conversation_service.append_message(db, conv, "assistant", result["reply"])

    action = result["action"]

    if action == "ask":
        qr = "confirm" if result.get("needs_confirm") else None
        await _reply(db, reply_token, result["reply"], quick_reply=qr)
        return

    if action == "resolved":
        # แก้ได้จากคำแนะนำ → เก็บเป็น ticket สถานะ ai_answered ไว้ทำสถิติ ไม่แจ้ง IT
        ticket = _create_ticket_from_intake(db, lu, result, "ai_answered", "L1")
        _attach_pending_images(db, conv, ticket)
        _update_location(db, lu, result)
        conversation_service.close(db, conv, ticket.id)
        await _reply(db, reply_token, result["reply"])
        return

    # action == "open" → เปิด ticket จริง
    is_approval = result["category"] in APPROVAL_CATEGORIES
    status = "pending_approval" if is_approval else "open"
    ticket_type = result.get("type") or ("L1" if is_approval else "L2")
    ticket = _create_ticket_from_intake(db, lu, result, status, ticket_type)
    _attach_pending_images(db, conv, ticket)
    _update_location(db, lu, result)
    conversation_service.close(db, conv, ticket.id)

    db.refresh(ticket)
    await _notify_group(db, ticket_service.group_notify_text(ticket))
    if is_approval:
        tail = "ทีม IT กำลังพิจารณาอนุมัติให้นะครับ 🙏"
    else:
        tail = "ทีม IT จะรีบดำเนินการให้นะครับ 🔧"
    await _reply(
        db,
        reply_token,
        f"{result['reply']}\n\n{tail}\nหมายเลข Ticket: {ticket.ticket_no}",
    )


# --------------------------------------------------------------------------
# 1-1 chat
# --------------------------------------------------------------------------

async def _latest_open_ticket(db: Session, line_user_db_id: int) -> Ticket | None:
    return (
        db.query(Ticket)
        .filter(
            Ticket.line_user_id == line_user_db_id,
            Ticket.status.notin_(["closed"]),
        )
        .order_by(Ticket.id.desc())
        .first()
    )


async def _handle_user_text(
    db: Session, line_user_id: str, text: str, reply_token: str
) -> None:
    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()

    conv = conversation_service.get_active(db, "user", None, line_user_id)

    # ไม่มีบทสนทนา + เป็นปุ่ม follow-up เดิม → จัดการแบบเดิม (ticket ที่เปิดค้างไว้)
    if conv is None and text.strip() in (RESOLVED_TEXT, NOT_RESOLVED_TEXT):
        await _handle_followup_quickreply(db, lu, text, reply_token)
        return

    if conv is None:
        conv = conversation_service.start(db, "user", None, line_user_id)
    await _run_intake(db, conv, lu, reply_token, text, None)


async def _handle_followup_quickreply(
    db: Session, lu: LineUser, text: str, reply_token: str
) -> None:
    """ปุ่ม 'แก้ได้แล้ว/ยังไม่ได้' จาก follow-up ของ ai_answered ticket เดิม."""
    ticket = await _latest_open_ticket(db, lu.id)
    if text.strip() == RESOLVED_TEXT:
        if ticket:
            ticket.status = "resolved"
            ticket.resolved_at = datetime.now(timezone.utc)
            followup_service.mark_responded(db, ticket.id)
            db.commit()
        await _reply(db, reply_token, "เยี่ยมเลยครับ 🎉 ขอบคุณที่ใช้บริการนะครับ")
        return
    # NOT_RESOLVED → escalate
    if ticket:
        ticket.type = "L2"
        ticket.status = "open"
        followup_service.mark_responded(db, ticket.id)
        db.commit()
        db.refresh(ticket)
        await _notify_group(db, ticket_service.group_notify_text(ticket))
    await _reply(db, reply_token, "ทีม IT จะรีบเข้ามาช่วยดูแลให้นะครับ 🔧")


async def _handle_user_image(
    db: Session, line_user_id: str, message_id: str, reply_token: str
) -> None:
    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()
    if message_id is None:
        return

    conv = conversation_service.get_active(db, "user", None, line_user_id)
    if conv is None:
        # ไม่มีบทสนทนา แต่มี ticket เปิดค้าง → แนบรูปเข้า ticket เดิม
        ticket = await _latest_open_ticket(db, lu.id)
        if ticket is not None:
            try:
                content = await line_service.get_message_content(message_id)
                _store_attachment(db, ticket, message_id, content)
                await _reply(
                    db, reply_token, f"แนบรูปเข้า Ticket {ticket.ticket_no} ให้แล้วครับ 📎"
                )
            except Exception:  # noqa: BLE001
                logger.exception("failed to attach 1-1 image")
            return
        conv = conversation_service.start(db, "user", None, line_user_id)

    try:
        content = await line_service.get_message_content(message_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to download 1-1 image")
        return
    _store_pending_image(db, conv, message_id, content)
    await _run_intake(db, conv, lu, reply_token, "", [content])


# --------------------------------------------------------------------------
# Group chat
# --------------------------------------------------------------------------

async def _handle_group_text(
    db: Session, source_id: str, line_user_id: str, message: dict, reply_token: str
) -> None:
    conv = conversation_service.get_active(db, "group", source_id, line_user_id)
    text = message.get("text", "")

    if conv is None:
        # ยังไม่มีบทสนทนา → ต้องถูกเรียกก่อนถึงเริ่ม
        query = _group_trigger_query(db, message)
        if query is None:
            return
        text = query

    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()
    if conv is None:
        conv = conversation_service.start(db, "group", source_id, line_user_id)
    await _run_intake(db, conv, lu, reply_token, text, None)


async def _handle_group_image(
    db: Session, source_id: str, line_user_id: str, message: dict, reply_token: str
) -> None:
    message_id = message.get("id")
    conv = conversation_service.get_active(db, "group", source_id, line_user_id)
    quoted_is_bot = bot_message_service.is_bot_message(db, message.get("quotedMessageId"))

    # รูปในกลุ่มจะรับเมื่ออยู่ในบทสนทนา หรือ quote-reply ข้อความบอท เท่านั้น
    if conv is None and not quoted_is_bot:
        return
    if message_id is None:
        return

    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()
    if conv is None:
        conv = conversation_service.start(db, "group", source_id, line_user_id)

    try:
        content = await line_service.get_message_content(message_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to download group image")
        return
    _store_pending_image(db, conv, message_id, content)
    await _run_intake(db, conv, lu, reply_token, "", [content])
