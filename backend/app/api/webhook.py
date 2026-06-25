"""Line Messaging API webhook — รับ event แล้วขับ flow L1/L2."""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ticket import Ticket
from app.services import (
    ai_service,
    bot_message_service,
    followup_service,
    group_session_service,
    line_service,
    storage_service,
    ticket_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

RESOLVED_TEXT = "แก้ได้แล้ว ✅"
NOT_RESOLVED_TEXT = "ยังไม่ได้ ❌"

L1_REPLY_TEMPLATE = "ขอบคุณที่แจ้งมานะครับ 🙏\n\n{reply}\n\nดำเนินการได้แล้วหรือยังครับ?"


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
    db: Session, reply_token: str, text: str, with_quick_reply: bool = False
) -> None:
    """ตอบกลับ + จำ message id ที่ส่ง เพื่อรู้ทีหลังว่า user quote-reply ข้อความบอท."""
    ids = await line_service.reply(reply_token, text, with_quick_reply)
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

    # แชท 1-1 → flow เต็ม (เปิด ticket / AI ตอบ / follow-up)
    if source_type == "user":
        if mtype == "text":
            await _handle_text(db, line_user_id, message.get("text", ""), reply_token)
        elif mtype == "image":
            await _handle_image(db, line_user_id, message.get("id"))
        return

    # แชทกลุ่ม/ห้องหลายคน
    source_id = source.get("groupId") or source.get("roomId")
    if source_type in ("group", "room") and source_id:
        # ข้อความ → ตอบเมื่อถูก @ เรียก, quote-reply ข้อความบอท, หรือขึ้นต้นด้วยคำเรียกบอท
        if mtype == "text":
            text = message.get("text", "")
            triggered = False
            ticket = None
            if _bot_mentioned(message):
                triggered = True
                ticket = await _handle_group_query(
                    db, line_user_id, _strip_self_mentions(message), reply_token
                )
            elif bot_message_service.is_bot_message(db, message.get("quotedMessageId")):
                # user กด reply ข้อความบอทเพื่อคุยต่อ → ถือว่าคุยกับบอท
                triggered = True
                ticket = await _handle_group_query(
                    db, line_user_id, _strip_self_mentions(message), reply_token
                )
            else:
                query = _strip_trigger_keyword(text)
                if query is not None:
                    triggered = True
                    ticket = await _handle_group_query(db, line_user_id, query, reply_token)
            # เปิด session ไว้ → รูปที่ส่งตามมาในกลุ่มถือว่าเป็นของบทสนทนานี้
            if triggered:
                group_session_service.touch(
                    db, source_id, line_user_id, ticket.id if ticket else None
                )
        # รูป → รับเมื่อ quote-reply ข้อความบอท หรืออยู่ใน session ที่เพิ่งเรียกบอท
        elif mtype == "image":
            await _handle_group_image(db, source_id, line_user_id, message, reply_token)


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


async def _handle_group_query(
    db: Session, line_user_id: str, query: str, reply_token: str
) -> Ticket | None:
    """ตอบคำถามในกลุ่มเมื่อถูก @ เรียก — AI ตอบเลย, ถ้าต้องเปิดงานก็เปิด ticket ให้.

    คืน Ticket ที่เปิด (ถ้ามี) เพื่อให้ caller ผูกเข้า session — ไม่เปิดคืน None.
    """
    if not query:
        await _reply(db, reply_token, "พิมพ์คำถามต่อจาก @ ได้เลยครับ 🙂")
        return None

    lu = ticket_service.upsert_line_user(db, line_user_id)
    db.commit()

    result = await ai_service.classify_and_respond(query)

    # ในกลุ่มไม่ทำ quick-reply/follow-up (หลายคน) — ตอบตรงๆ, เปิด ticket เมื่อจำเป็น
    if result["category"] in ("equipment_request", "service_request") or result["needs_ticket"]:
        ticket = ticket_service.create_ticket(
            db,
            title=result["title"],
            description=query,
            category=result["category"],
            ticket_type="L2",
            priority=result["priority"],
            status="pending_approval"
            if result["category"] in ("equipment_request", "service_request")
            else "open",
            line_user_id=lu.id,
            ai_response=result["reply"],
        )
        if result["category"] == "equipment_request":
            from app.models.equipment_request import EquipmentRequest

            db.add(
                EquipmentRequest(
                    ticket_id=ticket.id,
                    item_name=result.get("item_name") or result["title"][:255],
                    quantity=result.get("quantity", 1),
                    reason=query,
                )
            )
            db.commit()
        await _reply(
            db,
            reply_token,
            f"{result['reply']}\n\nเปิด Ticket ให้แล้วครับ: {ticket.ticket_no}",
        )
        return ticket
    # ตอบได้ด้วยคำแนะนำ → ตอบเลย ไม่เปิด ticket
    await _reply(db, reply_token, result["reply"])
    return None


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


async def _handle_text(
    db: Session, line_user_id: str, text: str, reply_token: str
) -> None:
    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()

    # Quick reply responses
    if text.strip() == RESOLVED_TEXT:
        ticket = await _latest_open_ticket(db, lu.id)
        if ticket:
            ticket.status = "resolved"
            from datetime import datetime, timezone

            ticket.resolved_at = datetime.now(timezone.utc)
            followup_service.mark_responded(db, ticket.id)
            db.commit()
        await _reply(db, reply_token, "เยี่ยมเลยครับ 🎉 ขอบคุณที่ใช้บริการนะครับ")
        return

    if text.strip() == NOT_RESOLVED_TEXT:
        ticket = await _latest_open_ticket(db, lu.id)
        if ticket:
            ticket.type = "L2"
            ticket.status = "open"
            followup_service.mark_responded(db, ticket.id)
            db.commit()
            db.refresh(ticket)
            await _notify_group(db, ticket_service.group_notify_text(ticket))
        await _reply(db, reply_token, "ทีม IT จะรีบเข้ามาช่วยดูแลให้นะครับ 🔧")
        return

    # New issue → AI พยายามตอบ/แนะนำก่อน แล้วตัดสินว่าต้องเปิด ticket ไหม
    result = await ai_service.classify_and_respond(text)

    # ขอเบิกอุปกรณ์ / ขอใช้บริการ → เปิด ticket เข้า approval flow เสมอ
    if result["category"] in ("equipment_request", "service_request"):
        ticket = ticket_service.create_ticket(
            db,
            title=result["title"],
            description=text,
            category=result["category"],
            ticket_type="L1",
            priority=result["priority"],
            status="pending_approval",
            line_user_id=lu.id,
            ai_response=result["reply"],
        )
        if result["category"] == "equipment_request":
            from app.models.equipment_request import EquipmentRequest

            db.add(
                EquipmentRequest(
                    ticket_id=ticket.id,
                    item_name=result.get("item_name") or result["title"][:255],
                    quantity=result.get("quantity", 1),
                    reason=text,
                )
            )
            db.commit()
        await _notify_group(db, ticket_service.group_notify_text(ticket))
        await _reply(
            db,
            reply_token,
            f"รับเรื่องแล้วครับ 🙏 ทีม IT กำลังพิจารณาอนุมัติให้นะครับ\n"
            f"หมายเลข Ticket: {ticket.ticket_no}",
        )
        return

    if not result["needs_ticket"]:
        # AI แก้ได้ด้วยคำแนะนำ → ตอบเลย ยังไม่เปิด ticket จริง
        # เก็บเป็น ticket สถานะ ai_answered (ซ่อนจากรายการ open) ไว้ track follow-up + สถิติ
        ticket = ticket_service.create_ticket(
            db,
            title=result["title"],
            description=text,
            category=result["category"],
            ticket_type="L1",
            priority=result["priority"],
            status="ai_answered",
            line_user_id=lu.id,
            ai_response=result["reply"],
        )
        followup_service.schedule_l1_followup(db, ticket)
        reply_text = L1_REPLY_TEMPLATE.format(reply=result["reply"])
        await _reply(db, reply_token, reply_text, with_quick_reply=True)
    else:
        # แก้ด้วยคำแนะนำไม่ได้ → เปิด e-ticket + แจ้งทีม IT ทันที
        ticket = ticket_service.create_ticket(
            db,
            title=result["title"],
            description=text,
            category=result["category"],
            ticket_type="L2",
            priority=result["priority"],
            status="open",
            line_user_id=lu.id,
            ai_response=result["reply"],
        )
        await _notify_group(db, ticket_service.group_notify_text(ticket))
        await _reply(
            db,
            reply_token,
            f"{result['reply']}\n\nรับเรื่องแล้วครับ ทีม IT จะรีบดำเนินการให้นะครับ 🔧\n"
            f"หมายเลข Ticket: {ticket.ticket_no}",
        )


def _store_attachment(
    db: Session, ticket: Ticket, message_id: str, content: bytes
) -> None:
    """อัปโหลดรูปลง MinIO + บันทึก attachment ผูกกับ ticket."""
    object_name = f"{ticket.ticket_no}/{message_id}.jpg"
    path = storage_service.upload_bytes(object_name, content, "image/jpeg")
    from app.models.ticket_attachment import TicketAttachment

    db.add(
        TicketAttachment(
            ticket_id=ticket.id,
            file_name=f"{message_id}.jpg",
            file_path=path,
            mime_type="image/jpeg",
            file_size=len(content),
            line_message_id=message_id,
        )
    )
    db.commit()


async def _handle_image(db: Session, line_user_id: str, message_id: str) -> None:
    lu = ticket_service.upsert_line_user(db, line_user_id)
    db.commit()
    ticket = await _latest_open_ticket(db, lu.id)
    if ticket is None or message_id is None:
        return
    try:
        content = await line_service.get_message_content(message_id)
        _store_attachment(db, ticket, message_id, content)
    except Exception:  # noqa: BLE001
        logger.exception("failed to store image attachment")


async def _handle_group_image(
    db: Session, source_id: str, line_user_id: str, message: dict, reply_token: str
) -> None:
    """รูปในกลุ่ม — รับเมื่อ quote-reply ข้อความบอท หรืออยู่ใน session ที่เพิ่งเรียกบอท.

    gemma อ่านรูป (error screenshot) → เปิด/แนบ ticket แล้วแจ้งทีม IT.
    """
    message_id = message.get("id")
    quoted_is_bot = bot_message_service.is_bot_message(db, message.get("quotedMessageId"))
    session = group_session_service.get_active(db, source_id, line_user_id)
    if not quoted_is_bot and session is None:
        return  # รูปนี้ไม่ได้ตั้งใจคุยกับบอท → ไม่ยุ่ง
    if message_id is None:
        return

    try:
        content = await line_service.get_message_content(message_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to download group image")
        return

    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()

    # ถ้า session มี ticket เปิดอยู่แล้ว → แนบรูปเข้า ticket เดิม (ไม่เปิดใหม่)
    if session and session.ticket_id:
        ticket = db.get(Ticket, session.ticket_id)
        if ticket and ticket.status != "closed":
            _store_attachment(db, ticket, message_id, content)
            await _reply(
                db,
                reply_token,
                f"รับรูปแล้วครับ 📎 แนบเข้า Ticket {ticket.ticket_no} ให้ทีม IT แล้วครับ",
            )
            group_session_service.touch(db, source_id, line_user_id, ticket.id)
            return

    # ยังไม่มี ticket → ให้ gemma อ่านรูปแล้วเปิด ticket ใหม่
    result = await ai_service.classify_and_respond("", images=[content])
    ticket = ticket_service.create_ticket(
        db,
        title=result["title"],
        description=result["reply"],
        category=result["category"],
        ticket_type="L2",
        priority=result["priority"],
        status="open",
        line_user_id=lu.id,
        ai_response=result["reply"],
    )
    _store_attachment(db, ticket, message_id, content)
    await _notify_group(db, ticket_service.group_notify_text(ticket))
    await _reply(
        db,
        reply_token,
        f"{result['reply']}\n\nรับเรื่องแล้วครับ เปิด Ticket {ticket.ticket_no} ส่งทีม IT แล้วครับ 🔧",
    )
    group_session_service.touch(db, source_id, line_user_id, ticket.id)
