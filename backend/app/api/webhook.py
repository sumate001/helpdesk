"""Line Messaging API webhook — multi-turn intake: แก้ปัญหาเบื้องต้น/เก็บข้อมูล แล้วยืนยันก่อนเปิด ticket."""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.approval import ApprovalRequest, DepartmentApprover
from app.models.conversation import Conversation
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.models.user import User
from app.services import (
    ai_service,
    approval_service,
    bot_message_service,
    conversation_service,
    followup_service,
    itamtv_service,
    line_service,
    rag_service,
    settings_service,
    staff_agent,
    storage_service,
    ticket_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

RESOLVED_TEXT = "แก้ได้แล้ว ✅"
NOT_RESOLVED_TEXT = "ยังไม่ได้ ❌"
APPROVAL_CATEGORIES = ("equipment_request", "service_request")
IMAGE_PLACEHOLDER = "[ผู้ใช้ส่งรูปภาพ]"

# ลงทะเบียนผูกพนักงาน: ข้อความที่หน้าตาเป็นรหัสพนักงาน/อีเมล → ยิง Employee DB /lookup สด
EMP_CODE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9-]{4,10}$")  # ต้องมีตัวเลข กันชนคำทั่วไป
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
# LINE userId จริง: 'U' + hex 32 ตัว — ใช้แยกจากค่า placeholder ที่ตั้งมือไว้ในตาราง users
_LINE_USER_ID_RE = re.compile(r"^U[0-9a-f]{32}$")
# จำนวนข้อความท้ายสุดของบทสนทนา staff ที่ป้อนโมเดล — จำกัดวงพิษถ้าเผลอมั่ว 1 ครั้ง
_STAFF_HISTORY_LIMIT = 16
REGISTER_PROMPT = (
    "สวัสดีครับ 👋 ผมเป็นผู้ช่วย IT Support ของอมรินทร์\n"
    "ขอรหัสพนักงาน (หรืออีเมลบริษัท) หน่อยครับ\n"
    "จะได้รู้จักกันไว้ คราวหน้าแจ้งปัญหาจะได้ไม่ต้องถามข้อมูลซ้ำครับ 🙏"
)
# ถามก่อนเปิดเคสให้คนที่ยังไม่ได้ลงทะเบียน (ดู _identity_gate) — ถามครั้งเดียวต่อบทสนทนา
IDENTITY_ASK = (
    "ขอรหัสพนักงานหรืออีเมลบริษัทก่อนเปิดเคสหน่อยครับ 🙏\n"
    "จะได้ระบุตัวผู้แจ้งให้ถูกคน (ชื่อใน LINE ส่วนใหญ่เป็นชื่อเล่น ใช้แทนไม่ได้ครับ)\n"
    "ถ้าไม่สะดวก พิมพ์ชื่อ-นามสกุลจริงมาก็ได้ครับ"
)
_IDENTITY_ASK_MARK = "ขอรหัสพนักงานหรืออีเมลบริษัทก่อนเปิดเคส"  # marker ใน transcript


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
    quick_reply: str | dict | None = None,
) -> None:
    """ตอบกลับ + จำ message id ที่ส่ง เพื่อรู้ทีหลังว่า user quote-reply ข้อความบอท."""
    ids = await line_service.reply(reply_token, text, with_quick_reply, quick_reply)
    bot_message_service.record(db, ids)


async def _notify_group(
    db: Session, text: str, mentions: dict[str, str] | None = None
) -> None:
    ids = await line_service.notify_group(text, mentions)
    bot_message_service.record(db, ids)


async def _notify_group_ticket(db: Session, ticket: Ticket) -> None:
    """แจ้งเคสใหม่เข้ากลุ่ม IT พร้อม @mention ผู้รับมอบหมาย (ถ้ามีและผูก LINE ไว้)."""
    text, mentions = ticket_service.group_notify(ticket)
    await _notify_group(db, text, mentions)


async def _maybe_offer_form(db: Session, reply_token: str, text: str) -> bool:
    """ถ้าข้อความเข้าเรื่องที่มีฟอร์มรองรับ (ผ่าน KB) → ยื่นปุ่ม Flex เปิดฟอร์ม คืน True.

    คืน False ถ้าไม่มีฟอร์มเกี่ยวข้อง/ยังไม่ตั้ง LIFF_BASE_URL → ให้ flow intake เดิมเดินต่อ.
    """
    if not text.strip():
        return False
    try:
        form = await rag_service.find_form(db, text)
    except Exception:  # noqa: BLE001
        logger.exception("find_form failed")
        return False
    if form is None:
        return False
    flex = line_service.form_flex(form.name, form.slug, form.description)
    if flex is None:
        return False
    ids = await line_service.reply_flex(reply_token, flex)
    bot_message_service.record(db, ids)
    return True


async def _handle_event(db: Session, event: dict) -> None:
    # LINE ส่ง event ซ้ำเมื่อเราตอบ 200 ไม่ทัน (เช่น Ollama ช้า) — ประมวลผลซ้ำจะทำให้
    # ข้อความเบิ้ลใน transcript และ handler สองตัวเขียนทับกัน (lost update) → ข้ามทิ้ง
    if (event.get("deliveryContext") or {}).get("isRedelivery"):
        logger.info("skip redelivered event %s", event.get("webhookEventId"))
        return

    etype = event.get("type")
    source = event.get("source", {})
    line_user_id = source.get("userId")

    # ช่วยหา groupId ตอน setup — เชิญ bot เข้ากลุ่มแล้วพิมพ์ในกลุ่ม จะเห็นค่านี้ใน log
    if source.get("groupId"):
        logger.info("📌 groupId = %s (เอาไปใส่ LINE_GROUP_IT_ID)", source["groupId"])

    if etype == "follow" and line_user_id:
        profile = await line_service.get_profile(line_user_id)
        lu = ticket_service.upsert_line_user(db, line_user_id, profile)
        db.commit()
        if (
            settings_service.get("EMPLOYEE_LOOKUP_ENABLED")
            and lu.employee_id is None
            and event.get("replyToken")
        ):
            await _reply(db, event["replyToken"], REGISTER_PROMPT)
        return

    if etype == "postback" and line_user_id:
        await _handle_postback(db, line_user_id, event)
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
# Postback (ปุ่มปิดเคสจากช่าง)
# --------------------------------------------------------------------------

def _parse_postback(data: str) -> dict:
    """แปลง 'action=close_case&ticket_id=12' → {'action':..., 'ticket_id':...}."""
    out: dict[str, str] = {}
    for part in (data or "").split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


async def _handle_postback(db: Session, line_user_id: str, event: dict) -> None:
    """ช่างกดปุ่มปิดเคสจาก LINE → ตรวจสิทธิ์ → ปิด ticket + ปิดเคสใน itamtv."""
    data = _parse_postback((event.get("postback") or {}).get("data", ""))
    reply_token = event.get("replyToken")
    action = data.get("action")
    if action in ("approve_req", "reject_req"):
        await _handle_approval_postback(db, line_user_id, reply_token, action, data)
        return
    if action in ("accept_approver", "decline_approver"):
        await _handle_approver_invite(db, line_user_id, reply_token, action, data)
        return
    if action not in ("close_case", "accept_case"):
        return

    # ยืนยันตัวตน: คนกดต้องเป็น IT staff ที่ผูก LINE ไว้ (users.line_user_id)
    staff = _resolve_staff(db, line_user_id)
    if staff is None:
        await _reply(db, reply_token, "ปุ่มนี้ใช้ได้เฉพาะเจ้าหน้าที่ IT ที่ลงทะเบียนไว้ครับ")
        return

    ticket = db.query(Ticket).filter(Ticket.id == int(data.get("ticket_id", 0))).one_or_none()
    if ticket is None:
        await _reply(db, reply_token, "หาเคสนี้ในระบบไม่เจอครับ ลองเช็กเลขที่อีกทีได้ไหมครับ")
        return
    if ticket.status in ("resolved", "closed"):
        await _reply(db, reply_token, f"เคส {ticket.ticket_no} ปิดไปแล้วครับ ✅")
        return

    if action == "accept_case":
        note = await staff_agent.apply_ticket_status(db, ticket, staff, "in_progress")
        await _reply(db, reply_token,
                     f"รับงานเคส {ticket.ticket_no} แล้วครับ 🙋 (กำลังดำเนินการ){note}")
        return

    # close_case → ปิดฝั่ง dashboard + itamtv ด้วยสิทธิ์ช่างคนที่กดปุ่ม
    note = await staff_agent.apply_ticket_status(db, ticket, staff, "resolved")
    await _reply(db, reply_token, f"ปิดเคส {ticket.ticket_no} เรียบร้อยครับ ✅{note}")


async def _handle_approval_postback(db: Session, line_user_id: str, reply_token: str,
                                    action: str, data: dict) -> None:
    """หัวหน้ากดปุ่มอนุมัติ/ไม่อนุมัติจากการ์ดใน LINE.

    ตรวจสิทธิ์จาก userId ของคนกด (LINE เป็นคนบอก ปลอมไม่ได้) เทียบกับผู้อนุมัติที่ระบุไว้ —
    ต่อให้การ์ดถูก forward ไปให้คนอื่น คนอื่นกดก็ไม่ผ่าน
    """
    req = db.get(ApprovalRequest, int(data.get("req_id", 0) or 0))
    if req is None:
        await _reply(db, reply_token, "ไม่พบคำขออนุมัตินี้ในระบบครับ")
        return
    if req.approver_line_user_id and req.approver_line_user_id != line_user_id:
        logger.warning("approval %s pressed by wrong user %s", req.id, line_user_id)
        await _reply(db, reply_token, "ปุ่มนี้ใช้ได้เฉพาะผู้อนุมัติที่ระบุไว้ครับ 🙏")
        return
    if req.status != "pending":
        ticket = db.get(Ticket, req.ticket_id)
        done = {"approved": "อนุมัติ", "rejected": "ไม่อนุมัติ"}.get(req.status, req.status)
        await _reply(db, reply_token,
                     f"คำขอนี้ถูก{done}ไปแล้วครับ ({ticket.ticket_no if ticket else '-'})")
        return

    approve = action == "approve_req"
    ticket = await approval_service.decide(db, req, approve, by_line_user_id=line_user_id)
    if approve:
        await _reply(db, reply_token,
                     f"อนุมัติเรียบร้อยครับ ✅\n{ticket.ticket_no} — {ticket.title}\n"
                     f"ส่งต่อให้ทีม IT ดำเนินการแล้วครับ")
        return
    # ไม่อนุมัติ → เปิดช่องให้พิมพ์เหตุผลตามมาได้ 1 ข้อความ (ผู้ขอควรได้รู้ว่าทำไม)
    req.awaiting_reason = True
    db.commit()
    await _reply(db, reply_token,
                 f"บันทึกว่าไม่อนุมัติแล้วครับ ❌ ({ticket.ticket_no})\n"
                 f"ถ้าจะระบุเหตุผลให้ผู้ขอทราบ พิมพ์มาได้เลยในข้อความถัดไปครับ")


async def _handle_approver_invite(db: Session, line_user_id: str, reply_token: str,
                                  action: str, data: dict) -> None:
    """คนที่ถูกตั้งเป็นผู้อนุมัติกดยอมรับ/ปฏิเสธบทบาทจากการ์ดเชิญ."""
    row = db.get(DepartmentApprover, int(data.get("appr_id", 0) or 0))
    if row is None:
        await _reply(db, reply_token, "ไม่พบข้อมูลผู้อนุมัตินี้ในระบบครับ")
        return
    # ตรวจว่าคนกดคือเจ้าตัวจริง (การ์ดถูก forward ไปให้คนอื่นกดไม่ได้)
    if approval_service.line_id_of(db, row.approver_emp_code) != line_user_id:
        await _reply(db, reply_token, "ปุ่มนี้ใช้ได้เฉพาะผู้ที่ถูกตั้งเป็นผู้อนุมัติครับ 🙏")
        return

    accept = action == "accept_approver"
    await approval_service.accept_approver_role(db, row, accept)
    if accept:
        pending = approval_service.pending_for_approver(db, line_user_id)
        tail = (f"\n\nตอนนี้มีคำขอรอคุณพิจารณาอยู่ {len(pending)} รายการครับ"
                if pending else "")
        await _reply(db, reply_token,
                     f"รับทราบครับ 🙏 คุณเป็นผู้อนุมัติของฝ่าย “{row.department}” แล้ว\n"
                     f"มีคำขอเมื่อไหร่ ผมจะส่งการ์ดมาให้กดที่นี่เลยครับ{tail}")
    else:
        await _reply(db, reply_token,
                     "รับทราบครับ ผมแจ้งทีม IT ให้ตั้งผู้อนุมัติคนใหม่แล้วครับ 🙏")


async def _handle_approver_pick(db: Session, line_user_id: str, reply_token: str,
                                text: str) -> bool:
    """ผู้ขอกำลังถูกถามว่าหัวหน้าคือใคร → ข้อความนี้คือชื่อหัวหน้า. คืน True ถ้าจัดการแล้ว."""
    req = approval_service.awaiting_pick_for(db, line_user_id)
    if req is None:
        return False
    query = text.strip()
    if not query:
        return False
    try:
        found = await itamtv_service.search_employees(query)
    except Exception:  # noqa: BLE001
        logger.exception("search supervisor failed")
        await _reply(db, reply_token, "ตอนนี้ต่อกับระบบพนักงานไม่ติดครับ ลองพิมพ์ชื่ออีกครั้งนะครับ")
        return True

    if not found:
        await _reply(db, reply_token,
                     f"หาพนักงานชื่อ “{query}” ไม่เจอครับ ลองพิมพ์ชื่อจริง-นามสกุลดูได้ไหมครับ")
        return True
    if len(found) > 1:
        names = [e.get("name", "") for e in found][:8]
        listing = "\n".join(
            f"{i}. {e.get('name')} — {e.get('department') or '-'}"
            for i, e in enumerate(found[:8], 1)
        )
        await _reply(db, reply_token,
                     f"เจอหลายคนครับ หัวหน้าของคุณคนไหนครับ?\n{listing}",
                     quick_reply=line_service.choice_quick_reply(names))
        return True

    lu = db.query(LineUser).filter(LineUser.line_user_id == line_user_id).one_or_none()
    ok = await approval_service.attach_picked_approver(
        db, req, found[0], line_user_id,
        lu.known_name if lu else None,
    )
    if not ok:
        await _reply(db, reply_token, "เลือกตัวเองเป็นผู้อนุมัติไม่ได้ครับ 🙏 รบกวนระบุหัวหน้าอีกทีครับ")
        return True
    await _reply(db, reply_token,
                 f"ขอบคุณครับ 🙏 ส่งคำขอไปให้ {found[0].get('name')} พิจารณาแล้ว\n"
                 f"ได้ผลอย่างไรผมจะแจ้งกลับให้ทราบทันทีครับ")
    return True


async def _handle_approval_reason(db: Session, line_user_id: str, reply_token: str,
                                  text: str) -> bool:
    """ข้อความถัดจากการกด 'ไม่อนุมัติ' = เหตุผล → บันทึก + ส่งให้ผู้ขอ. คืน True ถ้าจัดการแล้ว."""
    req = approval_service.awaiting_reason_for(db, line_user_id)
    if req is None:
        return False
    req.awaiting_reason = False
    req.comment = text.strip()[:1000]
    db.commit()
    ticket = db.get(Ticket, req.ticket_id)
    if ticket is not None:
        approval_service._log(db, ticket, f"เหตุผลที่ไม่อนุมัติ: {req.comment}")
        await approval_service.notify_requester(
            db, ticket, False, req.approver_name or "ผู้อนุมัติ", req.comment
        )
    await _reply(db, reply_token, "ส่งเหตุผลให้ผู้ขอแล้วครับ 🙏")
    return True


async def notify_staff_new_ticket(
    db: Session, ticket: Ticket, only_staff: User | None = None
) -> None:
    """มีเคสใหม่เข้ามา → ส่งการ์ดงาน (ปุ่มรับงาน/ปิดเคส) ไปหา staff ทุกคนที่ผูก LINE ไว้.

    ใครก็กด 'รับงาน' ได้ → กลายเป็นผู้รับผิดชอบ (assign) + in_progress. best-effort:
    ส่งไม่ได้ทีละคนก็ข้าม ไม่ให้กระทบการเปิดเคส.

    only_staff = ส่งเฉพาะช่างคนนั้น (ใช้ตอนหัวหน้างานมอบหมายเคสให้คนใดคนหนึ่ง).
    """
    if only_staff is not None:
        staffs = [only_staff] if only_staff.line_user_id else []
    else:
        # ไม่ส่งการ์ด "รับงาน" ให้หัวหน้างาน — เขาไม่ได้ลงมือเอง (เห็นเคสจากกลุ่ม IT/dashboard อยู่แล้ว)
        staffs = (
            db.query(User)
            .filter(
                User.is_active.is_(True),
                User.line_user_id.isnot(None),
                User.role != "supervisor",
            )
            .all()
        )
    if not staffs:
        return
    flex = line_service.work_case_flex(
        ticket.ticket_no, ticket.id,
        ticket.title or ticket.description or "-",
        ticket_service.STATUS_LABELS_TH.get(ticket.status, ticket.status),
        level=ticket.itamtv_level,
    )
    for staff in staffs:
        try:
            await line_service.push_flex(staff.line_user_id, flex)
        except Exception:  # noqa: BLE001
            logger.exception("push งานใหม่ให้ staff %s ไม่สำเร็จ", staff.username)


async def notify_staff_close(db: Session, ticket: Ticket) -> bool:
    """ส่งการ์ดปุ่มปิดเคสไปหาช่างที่รับผิดชอบ ticket นี้ — คืน False ถ้ายังผูก LINE ไม่ได้."""
    if ticket.assigned_to is None:
        return False
    staff = db.query(User).filter(User.id == ticket.assigned_to).one_or_none()
    if staff is None or not staff.line_user_id:
        logger.info("assignee ของ %s ยังไม่ผูก LINE — ข้ามการส่งปุ่มปิดเคส", ticket.ticket_no)
        return False
    flex = line_service.close_case_flex(
        ticket.ticket_no, ticket.id, ticket.title or ticket.description or "-"
    )
    await line_service.push_flex(staff.line_user_id, flex)
    return True


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


def _mentions_others_only(message: dict) -> bool:
    """ข้อความ @ เรียกคนอื่นในกลุ่ม โดยไม่ได้เรียกบอท → ชัดเจนว่าคุยกับคนอื่น."""
    mentionees = (message.get("mention") or {}).get("mentionees") or []
    return bool(mentionees) and not any(m.get("isSelf") for m in mentionees)


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


def _update_user_info(db: Session, lu: LineUser, result: dict) -> None:
    """บันทึกชื่อ/อาคาร/ชั้น ที่เก็บได้ระหว่าง intake ลง line_users."""
    changed = False
    if result.get("full_name"):
        # ลง self_name ไม่ใช่ display_name — display_name โดน LINE profile เขียนทับ
        # ทุกข้อความ (upsert_line_user) ชื่อที่อุตส่าห์ถามมาจึงหายทุกรอบ
        lu.self_name = str(result["full_name"])[:100]
        changed = True
    if result.get("building"):
        lu.building = str(result["building"])[:100]
        changed = True
    if result.get("floor"):
        lu.floor = str(result["floor"])[:20]
    if result.get("phone"):
        lu.phone = str(result["phone"])[:30]
        changed = True
    if changed:
        db.commit()


def _known_info(
    lu: LineUser, conv: Conversation | None = None, db: Session | None = None
) -> dict:
    """ข้อมูลผู้ใช้ที่มีอยู่แล้ว → ส่งให้ AI ไม่ถามซ้ำ.

    ชื่อเอาจาก Employee DB ก่อน (ผูกตอนลงทะเบียน) แล้วค่อยชื่อที่ผู้ใช้บอกบอทเอง —
    ห้าม fallback ไป display_name เด็ดขาด: มันคือชื่อที่ตั้งเองใน LINE (ส่วนใหญ่เป็น
    ชื่อเล่น) ถ้าส่งเข้าไปในบล็อก "ทราบแล้ว" บอทจะนึกว่ารู้ชื่อจริงแล้วเลยไม่ถาม
    แล้วชื่อเล่นจะไหลไปถึง dropdown ผู้แจ้งของ itamtv จนเปิดเคสไม่ผ่าน.

    registered: บอก AI ว่าผู้ใช้ผูกกับฐานข้อมูลพนักงานแล้วหรือยัง — ส่งเฉพาะตอนเปิด
    ระบบทะเบียน (ปิดอยู่ = ไม่มี flow ลงทะเบียน จะพูดถึงก็สับสนเปล่าๆ)."""
    info = {
        "full_name": lu.emp_name or lu.self_name,
        "building": lu.building,
        "floor": lu.floor,
        "phone": lu.phone,
    }
    if settings_service.get("EMPLOYEE_LOOKUP_ENABLED"):
        info["registered"] = lu.employee_id is not None
        info["emp_code"] = lu.emp_code
        info["department"] = lu.department
        # ลงทะเบียนได้เฉพาะแชท 1-1 — ในกลุ่มต้องชวนไปทักบอทส่วนตัวแทน
        info["can_register_here"] = conv is None or conv.channel == "user"
    if db is not None:
        # ticket ล่าสุดของผู้แจ้ง → AI ตอบ "เคสที่แจ้งไปถึงไหนแล้ว" ได้เองโดยไม่ต้องเปิดเคสใหม่
        info["tickets"] = ticket_service.recent_tickets(db, lu.id)
    return info


def _lookup_key(text: str) -> dict | None:
    """ข้อความนี้หน้าตาเป็นรหัสพนักงาน/อีเมลไหม → kwargs สำหรับ lookup_employee_exact."""
    key = text.strip()
    if EMAIL_RE.match(key):
        return {"email": key}
    if EMP_CODE_RE.match(key):
        return {"emp_code": key}
    return None


async def _bind_employee(db: Session, lu: LineUser, key: str) -> tuple[bool, str]:
    """ผูก LINE user เข้ากับ Employee DB ด้วยรหัสพนักงาน/อีเมล (ยิง /lookup สด ไม่ cache).

    คืน (สำเร็จไหม, ข้อความบอกผลไว้ตอบผู้ใช้) — ผู้เรียกเลือกเองว่าจะตอบหรือกลืน.
    """
    kwargs = _lookup_key(key)
    if kwargs is None:
        return False, ""
    try:
        emp = await itamtv_service.lookup_employee_exact(**kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("employee exact lookup failed for %s", key)
        return False, "ตอนนี้ต่อกับระบบทะเบียนพนักงานไม่ติดครับ รบกวนลองใหม่อีกทีนะครับ 🙏"
    if emp is None:
        return False, (
            f"หา \"{key.strip()}\" ในทะเบียนพนักงานไม่เจอครับ\n"
            "ลองเช็กรหัสอีกทีนะครับ หรือจะพิมพ์อีเมลบริษัทมาแทนก็ได้ครับ"
        )

    lu.employee_id = emp["id"]
    lu.emp_code = emp.get("emp_code") or lu.emp_code
    lu.emp_email = emp.get("email") or lu.emp_email
    lu.emp_name = (emp.get("name") or "")[:100] or lu.emp_name
    lu.department = (emp.get("department") or lu.department or "")[:100] or None
    if emp.get("position"):
        lu.position = str(emp["position"])[:100]
    if emp.get("building"):
        lu.building = str(emp["building"])[:100]
    if emp.get("floor"):
        lu.floor = str(emp["floor"])[:20]
    db.commit()
    _maybe_link_staff(db, lu)
    dept = f" ({emp['department']})" if emp.get("department") else ""
    return True, (
        f"เรียบร้อยครับ ✅ สวัสดีคุณ{emp['name']}{dept}\n"
        "ต่อไปมีปัญหา IT ทักมาได้เลย ไม่ต้องแนะนำตัวใหม่แล้วครับ 🙌\n"
        "(ถ้าข้อมูลไม่ตรง พิมพ์รหัสพนักงานหรืออีเมลใหม่มาได้เลยครับ)"
    )


def _identity_asked(conv: Conversation) -> bool:
    """เคยขอรหัสพนักงานก่อนเปิดเคสไปแล้วในบทสนทนานี้ไหม."""
    return any(
        m["role"] == "assistant" and _IDENTITY_ASK_MARK in m.get("content", "")
        for m in conversation_service.get_transcript(conv)
    )


async def _identity_gate(
    db: Session, conv: Conversation, lu: LineUser, result: dict, user_text: str
) -> str | None:
    """ก่อนเปิดเคสจริง ผู้แจ้งต้องระบุตัวได้ — คืนข้อความที่ต้องถามกลับ (None = ผ่าน).

    ชื่อใน LINE เป็นชื่อเล่นที่ตั้งเองได้ ระบุตัวคนไม่ได้ → itamtv รับไม่ได้ (dropdown
    ผู้แจ้งแมตช์ชื่อจริงเท่านั้น) และช่างก็ตามตัวไม่ถูก. ยังไม่ลงทะเบียน = ขอรหัส/อีเมล
    "ครั้งเดียว" ก่อนเปิด — ให้มาก็ผูกให้ทันที, ไม่ให้ก็ยอมเปิดเคสต่อ (ห้ามบล็อกเคสด่วน
    ไว้เพราะข้อมูลทะเบียน) แต่รอบนั้นบอทได้ขอชื่อ-นามสกุลจริงไปแล้วอย่างน้อยหนึ่งครั้ง.
    """
    if not settings_service.get("EMPLOYEE_LOOKUP_ENABLED") or lu.employee_id is not None:
        return None
    # ผู้ใช้เพิ่งพิมพ์รหัส/อีเมลมาเทิร์นนี้ (หรือ AI สกัดมาให้) → ผูกเลย แล้วเปิดเคสต่อได้
    # (ในกลุ่ม _try_register ไม่ทำงาน ทางนี้จึงเป็นทางเดียวที่ผูกให้ได้)
    for key in (user_text, str(result.get("emp_code") or "")):
        if key and _lookup_key(key) and (await _bind_employee(db, lu, key))[0]:
            return None
    return None if _identity_asked(conv) else IDENTITY_ASK


async def _try_register(db: Session, lu: LineUser, text: str, reply_token: str) -> bool:
    """ข้อความหน้าตาเป็นรหัสพนักงาน/อีเมล → ผูกกับ Employee DB แล้วตอบผลให้ผู้ใช้.

    คืน True = จัดการข้อความนี้จบแล้ว (ไม่ต้องเข้า intake), False = ไม่ใช่การลงทะเบียน.
    """
    if not settings_service.get("EMPLOYEE_LOOKUP_ENABLED"):
        return False
    if _lookup_key(text) is None:
        return False
    _ok, msg = await _bind_employee(db, lu, text)
    await _reply(db, reply_token, msg)
    return True


def _resolve_staff(db: Session, line_user_id: str) -> User | None:
    """คน LINE นี้เป็น IT staff ที่ผูกบัญชีไว้ไหม → คืน User (active) หรือ None."""
    return (
        db.query(User)
        .filter(User.line_user_id == line_user_id, User.is_active.is_(True))
        .one_or_none()
    )


def _find_staff_by_name(db: Session, name: str) -> User | None:
    """หา staff จากชื่อที่หัวหน้างานพูดถึง (display_name/username) — คืน None ถ้าไม่ชัด."""
    name = name.strip()
    if not name:
        return None
    rows = (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.role != "supervisor",  # หัวหน้างานไม่ใช่ผู้ปฏิบัติ
            (User.display_name.ilike(f"%{name}%")) | (User.username.ilike(f"%{name}%")),
        )
        .all()
    )
    return rows[0] if len(rows) == 1 else None


def _maybe_link_staff(db: Session, lu: LineUser) -> None:
    """ผูก LINE ↔ staff อัตโนมัติหลังลงทะเบียน: ถ้ามี users ที่ email/emp_code ตรงกับ
    พนักงานคนนี้และยังไม่ผูก LINE → เซ็ต users.line_user_id ให้ (พนักงานที่เป็น staff
    พอลงทะเบียนเสร็จก็เข้าโหมดผู้ช่วย staff ได้ทันที ไม่ต้องตั้งมือในหน้า Users)."""
    conds = []
    if lu.emp_email:
        conds.append(User.email == lu.emp_email)
    if lu.emp_code:
        conds.append(User.itamtv_emp_code == lu.emp_code)
    if not conds:
        return
    from sqlalchemy import or_

    staff = (
        db.query(User)
        .filter(User.is_active.is_(True), or_(*conds))
        .order_by(User.id)
        .first()
    )
    if staff is None:
        return
    current = staff.line_user_id
    # เขียนทับได้เมื่อ: ยังว่าง / เป็น placeholder ที่ไม่ใช่ LINE userId จริง /
    # เป็น LINE userId จริงแต่เป็นคนละตัว = พนักงานคนเดิม rebind จากเครื่องใหม่ (ผ่าน
    # employee lookup แล้ว = พิสูจน์ตัวตนแล้ว จึงย้ายให้). ถ้าตรงอยู่แล้วก็ไม่ต้องทำอะไร
    if current == lu.line_user_id:
        return
    if current and _LINE_USER_ID_RE.match(current):
        logger.info("rebind staff %s: LINE %s → %s", staff.username, current, lu.line_user_id)
    staff.line_user_id = lu.line_user_id
    db.commit()
    logger.info("auto-link staff %s ↔ LINE %s", staff.username, lu.line_user_id)


async def _run_staff_assistant(
    db: Session, staff: User, reply_token: str, text: str
) -> None:
    """โหมดผู้ช่วยสำหรับ IT staff — คุยได้ไม่จำกัด + เรียกเครื่องมือดูข้อมูล/สั่งการเคส.

    วนเรียก ai_service.staff_turn (native tool-calling): ถ้า action=tools → รันทุกเครื่องมือ
    ที่โมเดลขอมาในเทิร์นนั้น (ขอได้หลายตัว) เติมผลลัพธ์เข้า history
    แล้วเรียกซ้ำ (จำกัดรอบกัน loop) จนกว่าจะได้ action=answer → ตอบ staff.

    เก็บ transcript ใน conversations (channel="staff") เพื่อจำบริบทข้ามข้อความ — รวมผล
    เครื่องมือ (role=tool) ด้วย ให้ถามต่อเนื่องได้ (เช่น "ชื่อจริงคนนั้นคืออะไร").
    conversation channel="staff" ถูกกันออกจาก followup/escalation (ไม่เปิด ticket).
    """
    import json

    conv = conversation_service.get_active(db, "staff", None, staff.line_user_id)
    if conv is None:
        conv = conversation_service.start(db, "staff", None, staff.line_user_id)
    conversation_service.append_message(db, conv, "user", text.strip() or "-")

    # จำกัดความยาว history ที่ป้อนโมเดล — กันของมั่ว/บริบทเก่าสะสมจนหลอนรอบถัดๆ
    # (ผล tool ของเทิร์นปัจจุบันอยู่ท้าย transcript จึงไม่โดนตัด)
    ctx = staff_agent.Ctx(db=db, staff=staff)
    performed: set[str] = set()  # เครื่องมือที่ลงมือทำจริงไปแล้วในเทิร์นนี้
    history = conversation_service.get_transcript(conv)[-_STAFF_HISTORY_LIMIT:]
    for _ in range(5):
        result = await ai_service.staff_turn(history, role=staff.role)
        if result["action"] == "answer":
            reply = (staff_agent.guard_unbacked_claim(result["reply"], performed)
                     or staff_agent.guard_fake_ticket_no(result["reply"], history))
            conversation_service.append_message(db, conv, "assistant", reply)
            await _reply(db, reply_token, reply)
            return
        # action == "tools" → โมเดลขอเรียกเครื่องมือ (ได้หลายตัวในเทิร์นเดียว)
        # บันทึกคำสั่ง + ผลลัพธ์ลง transcript ให้จำข้ามข้อความได้
        blocks: list[str] = []
        quick: dict | None = None
        for c in result["calls"]:
            call = json.dumps({"tool": c["tool"], "args": c["args"]}, ensure_ascii=False)
            conversation_service.append_message(db, conv, "assistant", call)
            tool_data = await staff_agent.run(ctx, c["tool"], c["args"])
            if tool_data.get("ok"):
                performed.add(c["tool"])
            conversation_service.append_message(
                db, conv, "tool", json.dumps(tool_data, ensure_ascii=False))

            # กันมั่วขั้นสรุป: โมเดลเชื่อไม่ได้เวลาต้องอ่านผล tool มาเรียบเรียง (เคยได้ 5 คน
            # แต่ตอบ "ไม่พบ"). สำหรับ tool ที่ "แสดงข้อมูล/ยืนยันผล" ให้ "โค้ด" จัดรูปคำตอบเอง
            # จากผลจริง แล้วตอบ staff เลย — โมเดลมีหน้าที่แค่เลือก tool+args เท่านั้น
            rendered = staff_agent.render(c["tool"], tool_data, c["args"])
            if rendered is not None:
                blocks.append(rendered)
                quick = staff_agent.choices(c["tool"], tool_data) or quick
        if blocks:
            out = "\n\n".join(blocks)
            conversation_service.append_message(db, conv, "assistant", out)
            await _reply(db, reply_token, out, quick_reply=quick)
            return
        # tool ที่ยัง error/ต้องให้โมเดลถามต่อ (เช่น create_ticket เจอผู้แจ้งหลายคน) → วนต่อ
        history = conversation_service.get_transcript(conv)[-_STAFF_HISTORY_LIMIT:]
    # เรียกเครื่องมือวนเกินลิมิต → บอกให้ลองใหม่ (กันค้าง)
    await _reply(db, reply_token,
                 "ขอโทษครับ ผมประมวลผลคำขอนี้ไม่จบ ลองถามใหม่แบบเจาะจงขึ้นได้ไหมครับ 🙏")


async def _conversation_had_issue(db: Session, conv: Conversation) -> bool:
    """บทสนทนานี้เคยมีปัญหา IT จริงไหม — ใช้กันเคสผีตอน action=resolved."""
    return await ai_service.conversation_had_issue(
        conversation_service.get_transcript(conv)
    )


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


def _rag_query(candidate_history: list[dict]) -> str:
    """รวมข้อความผู้ใช้ 3 turn ล่าสุดเป็น query ค้น KB — turn สั้นๆ ("ชั้น 5 ครับ")
    ลำพังจะค้นไม่เจอ/เจอผิดเรื่อง ต้องมีบริบทของปัญหาจาก turn ก่อนๆ ประกอบ."""
    msgs = [
        m["content"]
        for m in candidate_history
        if m["role"] == "user" and m["content"].strip() and m["content"] != IMAGE_PLACEHOLDER
    ]
    return "\n".join(msgs[-3:])


async def _run_intake(
    db: Session,
    conv: Conversation,
    lu: LineUser,
    reply_token: str,
    user_text: str,
    images: list[bytes] | None,
    allow_ignore: bool = False,
) -> None:
    """เดินบทสนทนา intake หนึ่ง turn แล้วทำตาม action (ask/resolved/open/ignore)."""
    msg = user_text.strip() or IMAGE_PLACEHOLDER
    # ประเมินก่อน "ยังไม่" commit ข้อความเข้า transcript — เผื่อ AI ตัดสินว่า ignore
    candidate_history = conversation_service.get_transcript(conv) + [
        {"role": "user", "content": msg}
    ]
    # RAG: ดึงความรู้ระบบ/นโยบาย IT ที่เกี่ยวกับบทสนทนา (ล่มก็ปล่อยว่าง ไม่พัง intake)
    kb_context = ""
    query = _rag_query(candidate_history)
    if query:
        try:
            kb_context = await rag_service.retrieve_context(db, query)
        except Exception:  # noqa: BLE001
            logger.exception("RAG retrieve failed")
    result = await ai_service.intake_turn(
        candidate_history, images=images, known_info=_known_info(lu, conv, db),
        allow_ignore=allow_ignore, kb_context=kb_context,
    )

    if result["action"] == "ignore":
        # ข้อความนี้คุยกับคนอื่นในกลุ่ม ไม่ใช่กับบอท → ไม่ตอบ ไม่บันทึก ไม่ต่ออายุ conversation
        return

    conversation_service.append_message(db, conv, "user", msg)
    action = result["action"]

    # จะเปิดเคสแล้วแต่ยังไม่รู้ว่าผู้แจ้งเป็นใคร → ขอรหัสพนักงานก่อน (ครั้งเดียว)
    if action == "open":
        ask = await _identity_gate(db, conv, lu, result, msg)
        if ask:
            _update_user_info(db, lu, result)  # ข้อมูลที่เก็บได้เทิร์นนี้อย่าให้หล่นหาย
            # needs_confirm=True: ผู้ใช้ยืนยันเปิดเคสมาแล้ว เก็บสถานะนั้นไว้ให้เทิร์นหน้า
            # เปิดต่อได้เลยหลังได้รหัส ไม่ต้องให้ยืนยันซ้ำ
            conversation_service.append_message(db, conv, "assistant", ask, needs_confirm=True)
            await _reply(db, reply_token, ask)
            return

    conversation_service.append_message(
        db, conv, "assistant", result["reply"],
        needs_confirm=result["action"] == "ask" and bool(result.get("needs_confirm")),
    )

    if action == "ask":
        qr = "confirm" if result.get("needs_confirm") else None
        await _reply(db, reply_token, result["reply"], quick_reply=qr)
        return

    if action == "resolved":
        # แก้ได้จากคำแนะนำ → เก็บเป็น ticket สถานะ ai_answered ไว้ทำสถิติ ไม่แจ้ง IT
        # แต่เฉพาะเมื่อบทสนทนานี้ "เคยมีปัญหา IT จริง" — กันเคสผีจากการกด "แก้ได้แล้ว"
        # ในบทสนทนาที่ไม่เคยมีปัญหา (เช่น ทักทาย/ขอให้ตามคน แล้ว followup เด้งถาม)
        if _conversation_had_issue(db, conv):
            ticket = _create_ticket_from_intake(db, lu, result, "ai_answered", "L1")
            _attach_pending_images(db, conv, ticket)
            _update_user_info(db, lu, result)
            conversation_service.close(db, conv, ticket.id)
        else:
            logger.info("resolved แต่ไม่เคยมีปัญหาจริงในบทสนทนา — ไม่เปิดเคสสถิติ")
            conversation_service.close(db, conv, None)
        await _reply(db, reply_token, result["reply"])
        return

    # action == "open" → เปิด ticket จริง
    is_approval = result["category"] in APPROVAL_CATEGORIES
    status = "pending_approval" if is_approval else "open"
    ticket_type = result.get("type") or ("L1" if is_approval else "L2")
    ticket = _create_ticket_from_intake(db, lu, result, status, ticket_type)
    _attach_pending_images(db, conv, ticket)
    _update_user_info(db, lu, result)
    conversation_service.close(db, conv, ticket.id)

    # ประเมิน Level SLA ตั้งแต่เปิด (การ์ดช่าง/dashboard จะได้แสดงทันที ไม่ต้องรอตอน mirror)
    level = await ai_service.estimate_level(
        ticket.title, ticket.description or "", ticket.priority
    )
    if level:
        ticket.itamtv_level = level
        db.commit()

    db.refresh(ticket)
    await _notify_group_ticket(db, ticket)
    if not is_approval:
        # เคสจากผู้ใช้: เก็บไว้ในระบบเราก่อน — ไป itamtv ตอนช่างกดรับงาน (ensure_mirrored)
        # เพื่อให้เคสขึ้นชื่อช่างคนที่รับจริง ไม่ใช่ token กลาง
        # แจ้ง staff ที่ผูก LINE ให้รู้ว่ามีงานเข้า + กดรับงาน/ปิดเคสได้จาก LINE
        await notify_staff_new_ticket(db, ticket)
    if is_approval:
        tail = "ส่งให้ทีม IT พิจารณาอนุมัติแล้วนะครับ มีความคืบหน้าจะรีบแจ้งครับ 🙏"
    else:
        tail = "ส่งเรื่องให้ทีม IT แล้วนะครับ เดี๋ยวมีคนมาดูให้ 🔧"
    await _reply(
        db,
        reply_token,
        f"{result['reply']}\n\n{tail}\nหมายเลข Ticket: {ticket.ticket_no}",
    )


# --------------------------------------------------------------------------
# 1-1 chat
# --------------------------------------------------------------------------

async def _latest_ticket(
    db: Session, line_user_db_id: int, statuses: tuple[str, ...]
) -> Ticket | None:
    return (
        db.query(Ticket)
        .filter(
            Ticket.line_user_id == line_user_db_id,
            Ticket.status.in_(statuses),
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

    # เพิ่งกด "ไม่อนุมัติ" ไป → ข้อความนี้คือเหตุผล (ต้องดักก่อน flow อื่นทั้งหมด)
    if await _handle_approval_reason(db, line_user_id, reply_token, text):
        return

    # ถูกถามว่าหัวหน้าคือใคร → ข้อความนี้คือชื่อหัวหน้า (ดักก่อน intake ไม่งั้นจะกลายเป็นเคสใหม่)
    if await _handle_approver_pick(db, line_user_id, reply_token, text):
        return

    # ข้อความหน้าตาเป็นรหัสพนักงาน/อีเมล → ลงทะเบียน/แก้การผูกพนักงาน
    # (ทำก่อนเช็ก staff เพราะเป็นทางที่ auto-link บัญชี staff เข้ากับ LINE)
    # ปกติทำเฉพาะนอกบทสนทนา แต่ถ้ายังไม่เคยลงทะเบียน (employee_id ว่าง) ให้จับรหัส/อีเมล
    # ได้แม้มีบทสนทนาค้าง — กันเคสผู้ใช้พิมพ์ "ลงทะเบียน" (เปิด conv) แล้วค่อยส่งรหัสตามมา
    # (โค้ด 90004 จะถูกกลืนเข้า intake ไม่งั้น). จำกัดไว้ที่ยังไม่ลงทะเบียนเพื่อกัน false
    # positive ตอนผู้ใช้ที่ลงทะเบียนแล้วพิมพ์ตัวเลข (เช่น Asset Tag) ระหว่าง troubleshoot
    if (conv is None or lu.employee_id is None) and await _try_register(
        db, lu, text, reply_token
    ):
        return

    # IT staff ที่ผูกบัญชีไว้ → โหมดผู้ช่วยไม่จำกัด (ไม่เข้า flow แจ้งปัญหาของ user ทั่วไป)
    staff = _resolve_staff(db, line_user_id)
    if staff is not None:
        await _run_staff_assistant(db, staff, reply_token, text)
        return

    # ไม่มีบทสนทนา + เป็นปุ่ม follow-up เดิม → จัดการแบบเดิม (ticket ที่เปิดค้างไว้)
    if conv is None and text.strip() in (RESOLVED_TEXT, NOT_RESOLVED_TEXT):
        await _handle_followup_quickreply(db, lu, text, reply_token)
        return

    # เรื่องที่มีฟอร์มรองรับ (ผ่าน KB) → ยื่นปุ่มฟอร์ม LIFF แทน (เฉพาะตอนยังไม่อยู่ในบทสนทนา)
    if conv is None and await _maybe_offer_form(db, reply_token, text):
        return

    if conv is None:
        conv = conversation_service.start(db, "user", None, line_user_id)
    await _run_intake(db, conv, lu, reply_token, text, None)


async def _handle_followup_quickreply(
    db: Session, lu: LineUser, text: str, reply_token: str
) -> None:
    """ปุ่ม 'แก้ได้แล้ว/ยังไม่ได้' ที่กดหลังบทสนทนาปิดไปแล้ว (เช่นจาก follow-up push).

    จำกัดเฉพาะ ticket ที่ยังรอคำตอบผู้ใช้ได้จริง (ai_answered/open/in_progress) —
    ไม่หยิบ ticket ที่ resolved/pending_approval มา escalate มั่ว.
    """
    ticket = await _latest_ticket(db, lu.id, ("ai_answered", "open", "in_progress"))
    if text.strip() == RESOLVED_TEXT:
        if ticket:
            ticket.status = "resolved"
            ticket.resolved_at = datetime.now(timezone.utc)
            followup_service.mark_responded(db, ticket.id)
            db.commit()
        await _reply(db, reply_token, "เยี่ยมเลยครับ 🎉 มีอะไรอีกทักมาได้ตลอดนะครับ")
        return
    # NOT_RESOLVED → escalate เฉพาะ ticket ที่ยังไม่ได้เป็น L2 open อยู่แล้ว (กันแจ้งกลุ่มซ้ำ)
    if ticket and not (ticket.type == "L2" and ticket.status == "open"):
        ticket.type = "L2"
        ticket.status = "open"
        followup_service.mark_responded(db, ticket.id)
        db.commit()
        db.refresh(ticket)
        await _notify_group_ticket(db, ticket)
    elif ticket:
        followup_service.mark_responded(db, ticket.id)
        db.commit()
    await _reply(db, reply_token, "โอเคครับ เดี๋ยวผมส่งให้ทีม IT เข้ามาดูให้นะครับ 🔧")


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
        # ไม่มีบทสนทนา แต่มี ticket ที่ยังทำงานอยู่ → แนบรูปเข้า ticket เดิม
        # (ไม่แนบเข้า ticket ที่จบแล้ว — รูปใหม่อาจเป็นปัญหาใหม่ ให้เข้า intake แทน)
        ticket = await _latest_ticket(db, lu.id, ("open", "in_progress", "pending_approval"))
        if ticket is not None:
            try:
                content = await line_service.get_message_content(message_id)
                _store_attachment(db, ticket, message_id, content)
                await _reply(
                    db, reply_token, f"แนบรูปเข้าเคส {ticket.ticket_no} ให้แล้วครับ 📎"
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

    # บอทถูกเรียกตรงๆ ไหม (@mention / quote-reply บอท / keyword) → addressed ไม่ใช่ None
    addressed = _group_trigger_query(db, message)

    if conv is None:
        # ยังไม่มีบทสนทนา → ต้องถูกเรียกก่อนถึงเริ่ม
        if addressed is None:
            return
        text = addressed
    elif addressed is not None:
        # คุยต่อ + เรียกบอทตรงๆ → ตัดคำเรียกออก เหลือคำถามจริง
        text = addressed or text
    elif _mentions_others_only(message):
        # คุยต่อ แต่ @ เรียกคนอื่นในกลุ่ม → ชัดเจนว่าไม่ได้คุยกับบอท ข้ามเลย ไม่ต้องเรียก AI
        return

    # คุยต่อโดยไม่ได้เรียกบอทตรงๆ → ให้ AI ตัดสินว่าข้อความนี้คุยกับบอทหรือกับคนอื่นในกลุ่ม
    allow_ignore = conv is not None and addressed is None

    # เรื่องที่มีฟอร์มรองรับ (ผ่าน KB) → ยื่นปุ่มฟอร์ม LIFF แทน (เฉพาะตอนเพิ่งถูกเรียก)
    if conv is None and await _maybe_offer_form(db, reply_token, text):
        return

    profile = await line_service.get_profile(line_user_id)
    lu = ticket_service.upsert_line_user(db, line_user_id, profile)
    db.commit()
    if conv is None:
        conv = conversation_service.start(db, "group", source_id, line_user_id)
    await _run_intake(db, conv, lu, reply_token, text, None, allow_ignore=allow_ignore)


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
