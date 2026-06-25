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

    # แชทกลุ่ม/ห้องหลายคน → ตอบเมื่อถูก @ เรียก, quote-reply ข้อความบอท, หรือขึ้นต้นด้วยคำเรียกบอท
    if source_type in ("group", "room") and mtype == "text":
        text = message.get("text", "")
        if _bot_mentioned(message):
            await _handle_group_query(db, line_user_id, _strip_self_mentions(message), reply_token)
        elif bot_message_service.is_bot_message(db, message.get("quotedMessageId")):
            # user กด reply ข้อความบอทเพื่อคุยต่อ → ถือว่าคุยกับบอท
            await _handle_group_query(db, line_user_id, _strip_self_mentions(message), reply_token)
        else:
            query = _strip_trigger_keyword(text)
            if query is not None:
                await _handle_group_query(db, line_user_id, query, reply_token)


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
) -> None:
    """ตอบคำถามในกลุ่มเมื่อถูก @ เรียก — AI ตอบเลย, ถ้าต้องเปิดงานก็เปิด ticket ให้."""
    if not query:
        await _reply(db, reply_token, "พิมพ์คำถามต่อจาก @ ได้เลยครับ 🙂")
        return

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
    else:
        # ตอบได้ด้วยคำแนะนำ → ตอบเลย ไม่เปิด ticket
        await _reply(db, reply_token, result["reply"])


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


async def _handle_image(db: Session, line_user_id: str, message_id: str) -> None:
    lu = ticket_service.upsert_line_user(db, line_user_id)
    db.commit()
    ticket = await _latest_open_ticket(db, lu.id)
    if ticket is None or message_id is None:
        return
    try:
        content = await line_service.get_message_content(message_id)
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
    except Exception:  # noqa: BLE001
        logger.exception("failed to store image attachment")
