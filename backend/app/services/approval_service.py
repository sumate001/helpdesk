"""ระบบขออนุมัติคำขอใช้ทรัพยากร — หาผู้อนุมัติ ส่งให้กด แล้วเดินสถานะ ticket ต่อ.

หลักคิด: "ต้องอนุมัติไหม / ใครอนุมัติ" เป็นโครงสร้างบน service_forms + department_approvers
ที่โค้ดบังคับได้ 100% ไม่ใช่ข้อความใน KB ที่โมเดลต้องตีความ (KB มีไว้อธิบายให้คนอ่าน)

เส้นทาง:
    ผู้ใช้ส่งฟอร์ม → ticket=pending_approval + approval_requests(pending)
    → ส่ง Flex ให้หัวหน้ากดใน LINE (postback = รู้ userId ผู้กด ปลอมไม่ได้)
    → อนุมัติ: ticket→open + แจ้งทีม IT / ไม่อนุมัติ: ticket→closed + แจ้งผู้ขอพร้อมเหตุผล
    → หาหัวหน้าไม่ได้/หัวหน้าไม่ได้ผูก LINE: ไม่เงียบหาย — แจ้งกลุ่ม IT ให้ตามเอง
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, DepartmentApprover
from app.models.line_user import LineUser
from app.models.service_form import ServiceForm
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.services import itamtv_service, line_service

logger = logging.getLogger(__name__)

# ไม่ตอบภายในกี่ชั่วโมง → เตือนซ้ำ / หมดอายุ
REMIND_AFTER_HOURS = 4
EXPIRE_AFTER_HOURS = 48


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# หาผู้อนุมัติ
# ---------------------------------------------------------------------------

def find_department_approver(db: Session, department: str | None) -> DepartmentApprover | None:
    if not department:
        return None
    return (
        db.query(DepartmentApprover)
        .filter(DepartmentApprover.department == department.strip())
        .one_or_none()
    )


def can_self_approve(form: ServiceForm, position: str | None) -> bool:
    """ผู้ขอเป็นระดับที่อนุมัติตัวเองได้ไหม — เทียบแบบ 'มีคำนี้อยู่ในตำแหน่ง'."""
    positions = form.self_approve_positions or []
    if not position or not positions:
        return False
    pos = position.strip().lower()
    return any(str(p).strip().lower() in pos for p in positions if str(p).strip())


def line_id_of(db: Session, emp_code: str | None) -> str | None:
    """หา LINE userId ของพนักงานจาก emp_code (ต้องเคยผูก LINE กับระบบไว้)."""
    if not emp_code:
        return None
    row = (
        db.query(LineUser)
        .filter(LineUser.emp_code == emp_code)
        .order_by(LineUser.updated_at.desc())
        .first()
    )
    return row.line_user_id if row else None


async def resolve_approver(db: Session, form: ServiceForm, requester: dict) -> dict | None:
    """ตัดสินว่าใครต้องอนุมัติคำขอนี้ — คืน dict ผู้อนุมัติ หรือ None ถ้าหาไม่ได้.

    requester: {emp_code, department, position, name} ของผู้ขอ (จาก Employee DB สด)
    """
    if form.approver_rule == "fixed" and form.fixed_approver_emp_code:
        emp = None
        try:
            emp = await itamtv_service.lookup_employee_exact(
                emp_code=form.fixed_approver_emp_code
            )
        except Exception:  # noqa: BLE001
            logger.exception("lookup fixed approver failed")
        return {
            "emp_code": form.fixed_approver_emp_code,
            "name": (emp or {}).get("name"),
            "email": (emp or {}).get("email"),
            "from_requester": False,
        }

    row = find_department_approver(db, requester.get("department"))
    if row is None:
        return None
    # ห้ามอนุมัติให้ตัวเอง → ถ้าผู้ขอคือผู้อนุมัติของแผนก ให้ตกไปที่คนสำรอง
    if row.approver_emp_code and row.approver_emp_code == requester.get("emp_code"):
        if not row.backup_emp_code:
            return None
        return {"emp_code": row.backup_emp_code, "name": row.backup_name,
                "email": None, "from_requester": False}
    return {"emp_code": row.approver_emp_code, "name": row.approver_name,
            "email": row.approver_email, "from_requester": not row.is_confirmed}


# ---------------------------------------------------------------------------
# ตั้ง/แจ้งผู้อนุมัติ — ทางเดินเดียวกันทั้งที่ IT เพิ่มเองและที่ผู้ขอแจ้งชื่อหัวหน้ามา
# ---------------------------------------------------------------------------

def approval_scope(db: Session) -> list[str]:
    """รายชื่อเรื่องที่ต้องผ่านผู้อนุมัติ — เอาไปบอกเจ้าตัวว่าจะได้พิจารณาอะไรบ้าง."""
    rows = (
        db.query(ServiceForm)
        .filter(ServiceForm.is_active.is_(True), ServiceForm.requires_approval.is_(True))
        .order_by(ServiceForm.name)
        .all()
    )
    return [f.name for f in rows]


async def set_department_approver(
    db: Session, department: str, emp: dict, *,
    from_requester: bool = False, proposed_by_line_user_id: str | None = None,
    proposed_by_name: str | None = None,
) -> DepartmentApprover:
    """เพิ่ม/แก้ผู้อนุมัติของแผนก แล้วแจ้งเจ้าตัวทาง LINE ให้กดยอมรับ.

    ใช้ร่วมกัน 2 ทาง: IT เพิ่มจากหน้า dashboard / ผู้ขอแจ้งชื่อหัวหน้าเองตอนยื่นคำขอ
    (from_requester=True → is_confirmed=False รอ IT ตรวจ แต่ใช้งานได้ทันที)
    """
    dept = (department or "").strip()
    now = _now()
    row = find_department_approver(db, dept)
    if row is None:
        row = DepartmentApprover(department=dept, created_at=now, updated_at=now)
        db.add(row)
    changed = row.approver_emp_code != emp.get("emp_code")
    row.approver_emp_code = emp.get("emp_code")
    row.approver_name = emp.get("name") or row.approver_name
    row.approver_email = emp.get("email") or row.approver_email
    row.updated_at = now
    if from_requester:
        row.is_confirmed = False
        row.proposed_by_line_user_id = proposed_by_line_user_id
    if changed:
        # เปลี่ยนตัวผู้อนุมัติ = คนใหม่ยังไม่เคยรับทราบ ต้องแจ้งใหม่
        row.accepted = False
        row.accepted_at = None
    db.commit()
    db.refresh(row)

    await notify_new_approver(db, row, proposed_by_name)
    return row


async def notify_new_approver(db: Session, row: DepartmentApprover,
                              proposed_by_name: str | None = None) -> bool:
    """ส่งการ์ด "คุณถูกตั้งเป็นผู้อนุมัติ" — คืน False ถ้าเจ้าตัวยังไม่ผูก LINE."""
    line_user_id = line_id_of(db, row.approver_emp_code)
    if not line_user_id:
        logger.info("approver %s ยังไม่ผูก LINE — ยังแจ้งไม่ได้", row.approver_emp_code)
        return False
    flex = line_service.approver_invite_flex(
        approver_id=row.id, department=row.department,
        scope=approval_scope(db), proposed_by=proposed_by_name,
    )
    try:
        await line_service.push_flex(line_user_id, flex)
    except Exception:  # noqa: BLE001
        logger.exception("push approver invite failed for %s", row.approver_emp_code)
        return False
    row.notified_at = _now()
    db.commit()
    return True


async def accept_approver_role(db: Session, row: DepartmentApprover, accept: bool) -> None:
    """ผู้อนุมัติกดยอมรับ/ปฏิเสธบทบาท."""
    row.accepted = accept
    row.accepted_at = _now() if accept else None
    if not accept:
        # ปฏิเสธ = ผังนี้ใช้ไม่ได้ ต้องให้ IT หาคนใหม่ ไม่ปล่อยให้คำขอไปจ่อผิดคน
        row.is_confirmed = False
        row.note = ((row.note or "") + " | ผู้ถูกตั้งปฏิเสธบทบาท").strip(" |")
    db.commit()
    if not accept:
        try:
            await line_service.notify_group(
                f"⚠️ {row.approver_name or row.approver_emp_code} ปฏิเสธการเป็นผู้อนุมัติ"
                f"ของฝ่าย “{row.department}” — รบกวนตั้งคนใหม่ในหน้าการอนุมัติครับ"
            )
        except Exception:  # noqa: BLE001
            logger.exception("notify group about declined approver failed")


# ---------------------------------------------------------------------------
# สร้างคำขออนุมัติ + ส่งให้กด
# ---------------------------------------------------------------------------

async def start_approval(db: Session, ticket: Ticket, form: ServiceForm,
                         requester: dict, summary: str) -> ApprovalRequest:
    """สร้าง approval_request ของ ticket แล้วส่ง Flex ให้ผู้อนุมัติกดใน LINE."""
    approver = await resolve_approver(db, form, requester)
    req = ApprovalRequest(
        ticket_id=ticket.id, step=1, created_at=_now(),
        approver_emp_code=(approver or {}).get("emp_code"),
        approver_name=(approver or {}).get("name"),
        approver_email=(approver or {}).get("email"),
        approver_from_requester=bool((approver or {}).get("from_requester")),
        status="pending" if approver else "no_approver",
    )
    if approver:
        req.approver_line_user_id = line_id_of(db, approver.get("emp_code"))
    db.add(req)
    db.commit()
    db.refresh(req)

    if not approver:
        # ไม่มีในผัง → ถามผู้ขอเองว่าหัวหน้าคือใคร (ตอบแล้วระบบจะเพิ่มเข้าผังให้เลย)
        if await ask_requester_for_approver(db, ticket, requester):
            req.status = "awaiting_pick"
            db.commit()
            return req
        await _escalate_to_it(
            db, ticket,
            f"หาผู้อนุมัติของแผนก “{requester.get('department') or '-'}” ไม่ได้ "
            f"(ยังไม่ได้ตั้งผังผู้อนุมัติ) — รบกวนทีม IT ตามอนุมัติเองครับ",
        )
        return req

    if not req.approver_line_user_id:
        await _escalate_to_it(
            db, ticket,
            f"ผู้อนุมัติ {req.approver_name or req.approver_emp_code} "
            f"ยังไม่ได้ผูก LINE กับระบบ — ส่งปุ่มอนุมัติให้อัตโนมัติไม่ได้ครับ",
        )
        return req

    flex = line_service.approval_flex(
        request_id=req.id, ticket_no=ticket.ticket_no,
        title=ticket.title, summary=summary,
        requester=requester.get("name") or "-",
        department=requester.get("department") or "-",
    )
    try:
        await line_service.push_flex(req.approver_line_user_id, flex)
    except Exception:  # noqa: BLE001
        logger.exception("push approval flex failed for %s", ticket.ticket_no)
        await _escalate_to_it(db, ticket, "ส่งปุ่มอนุมัติทาง LINE ไม่สำเร็จ รบกวนตามเองครับ")
    _log(db, ticket, f"ส่งคำขออนุมัติไปที่ {req.approver_name or req.approver_emp_code} แล้ว")
    return req


async def ask_requester_for_approver(db: Session, ticket: Ticket, requester: dict) -> bool:
    """ยังไม่มีผู้อนุมัติของแผนกนี้ → ถามผู้ขอว่าหัวหน้าคือใคร. คืน False ถ้าถามไม่ได้."""
    lu = db.get(LineUser, ticket.line_user_id) if ticket.line_user_id else None
    if lu is None or not lu.line_user_id:
        return False
    try:
        await line_service.push(
            lu.line_user_id,
            f"คำขอ “{ticket.title}” ต้องผ่านการอนุมัติจากหัวหน้าก่อนครับ 🙏\n"
            f"ยังไม่มีข้อมูลผู้อนุมัติของฝ่าย “{requester.get('department') or '-'}” ในระบบ\n"
            f"รบกวนพิมพ์ชื่อหัวหน้าของคุณมาได้เลยครับ (ชื่อจริงหรือชื่อเล่นก็ได้)",
        )
    except Exception:  # noqa: BLE001
        logger.exception("ask requester for approver failed")
        return False
    _log(db, ticket, "ถามผู้ขอว่าใครเป็นผู้อนุมัติ (ยังไม่มีในผัง)")
    return True


def awaiting_pick_for(db: Session, line_user_id: str) -> ApprovalRequest | None:
    """คำขอของผู้ใช้คนนี้ที่กำลังรอให้เขาบอกชื่อหัวหน้า."""
    return (
        db.query(ApprovalRequest)
        .join(Ticket, ApprovalRequest.ticket_id == Ticket.id)
        .join(LineUser, Ticket.line_user_id == LineUser.id)
        .filter(LineUser.line_user_id == line_user_id,
                ApprovalRequest.status == "awaiting_pick")
        .order_by(ApprovalRequest.created_at.desc())
        .first()
    )


async def attach_picked_approver(db: Session, req: ApprovalRequest, emp: dict,
                                 requester_line_user_id: str,
                                 requester_name: str | None) -> bool:
    """ผู้ขอเลือกหัวหน้าแล้ว → เพิ่มเข้าผัง + แจ้งหัวหน้า + ส่งคำขออนุมัติให้เลย."""
    ticket = db.get(Ticket, req.ticket_id)
    lu = db.get(LineUser, ticket.line_user_id) if ticket and ticket.line_user_id else None
    department = (lu.department if lu else None) or "-"
    if emp.get("emp_code") and lu and emp["emp_code"] == lu.emp_code:
        return False  # เลือกตัวเองไม่ได้

    row = await set_department_approver(
        db, department, emp, from_requester=True,
        proposed_by_line_user_id=requester_line_user_id, proposed_by_name=requester_name,
    )
    req.approver_emp_code = row.approver_emp_code
    req.approver_name = row.approver_name
    req.approver_email = row.approver_email
    req.approver_line_user_id = line_id_of(db, row.approver_emp_code)
    req.approver_from_requester = True
    req.status = "pending"
    db.commit()

    _log(db, ticket, f"ผู้ขอระบุผู้อนุมัติเอง: {row.approver_name or row.approver_emp_code}")
    if not req.approver_line_user_id:
        await _escalate_to_it(
            db, ticket,
            f"ผู้ขอระบุผู้อนุมัติเป็น {row.approver_name or row.approver_emp_code} "
            f"แต่ท่านยังไม่ได้ผูก LINE — ส่งปุ่มอนุมัติอัตโนมัติไม่ได้ครับ",
        )
        return True
    flex = line_service.approval_flex(
        request_id=req.id, ticket_no=ticket.ticket_no, title=ticket.title,
        summary=(ticket.description or "")[:300],
        requester=requester_name or "-", department=department,
    )
    try:
        await line_service.push_flex(req.approver_line_user_id, flex)
    except Exception:  # noqa: BLE001
        logger.exception("push approval flex after pick failed")
    return True


async def _escalate_to_it(db: Session, ticket: Ticket, reason: str) -> None:
    _log(db, ticket, f"⚠️ {reason}")
    try:
        await line_service.notify_group(
            f"⚠️ เคส {ticket.ticket_no} รออนุมัติแต่ส่งให้ผู้อนุมัติไม่ได้\n{reason}"
        )
    except Exception:  # noqa: BLE001
        logger.exception("notify group about stuck approval failed")


def _log(db: Session, ticket: Ticket, content: str) -> None:
    db.add(TicketComment(ticket_id=ticket.id, user_id=None,
                         is_internal=True, content=content))
    db.commit()


# ---------------------------------------------------------------------------
# ตัดสินใจ (อนุมัติ / ไม่อนุมัติ)
# ---------------------------------------------------------------------------

async def decide(db: Session, req: ApprovalRequest, approve: bool, *,
                 by_line_user_id: str | None = None, by_user_id: int | None = None,
                 comment: str | None = None) -> Ticket:
    """บันทึกผลอนุมัติ → เดินสถานะ ticket + แจ้งผู้ขอ. คืน ticket ที่อัปเดตแล้ว."""
    ticket = db.get(Ticket, req.ticket_id)
    req.status = "approved" if approve else "rejected"
    req.decided_at = _now()
    req.decided_by_line_user_id = by_line_user_id
    req.decided_by_user_id = by_user_id
    if comment:
        req.comment = comment
    who = req.approver_name or req.approver_emp_code or "ผู้อนุมัติ"

    if approve:
        ticket.status = "open"
        _log(db, ticket, f"✅ อนุมัติโดย {who}" + (f" — {comment}" if comment else ""))
        try:
            from app.api.webhook import notify_staff_new_ticket
            await notify_staff_new_ticket(db, ticket)
            await line_service.notify_group(
                f"✅ เคส {ticket.ticket_no} ได้รับอนุมัติแล้ว ({who})\n{ticket.title}"
            )
        except Exception:  # noqa: BLE001
            logger.exception("notify staff after approval failed")
    else:
        ticket.status = "closed"
        ticket.resolved_at = _now()
        _log(db, ticket, f"❌ ไม่อนุมัติโดย {who}" + (f" — {comment}" if comment else ""))
    db.commit()

    await notify_requester(db, ticket, approve, who, comment)
    return ticket


async def notify_requester(db: Session, ticket: Ticket, approve: bool,
                           who: str, comment: str | None) -> None:
    """แจ้งผลกลับผู้ขอทาง LINE — คนแจ้งกลัวที่สุดคือ 'ส่งไปแล้วเงียบ ไม่รู้ค้างที่ใคร'."""
    lu = db.get(LineUser, ticket.line_user_id) if ticket.line_user_id else None
    if lu is None or not lu.line_user_id:
        return
    if approve:
        text = (f"คำขอ “{ticket.title}” ได้รับอนุมัติแล้วครับ ✅\n"
                f"ผู้อนุมัติ: {who}\nเลขที่เคส: {ticket.ticket_no}\n"
                f"ทีม IT จะดำเนินการต่อให้ครับ")
    else:
        text = (f"คำขอ “{ticket.title}” ไม่ได้รับอนุมัติครับ ❌\n"
                f"ผู้อนุมัติ: {who}\nเลขที่เคส: {ticket.ticket_no}")
        if comment:
            text += f"\nเหตุผล: {comment}"
    try:
        await line_service.push(lu.line_user_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("notify requester about approval failed")


async def resend(db: Session, req: ApprovalRequest) -> bool:
    """ส่งการ์ดอนุมัติซ้ำ — คืน False ถ้าผู้อนุมัติยังไม่ได้ผูก LINE."""
    ticket = db.get(Ticket, req.ticket_id)
    if ticket is None:
        return False
    if not req.approver_line_user_id:
        req.approver_line_user_id = line_id_of(db, req.approver_emp_code)
    if not req.approver_line_user_id:
        return False
    if req.status == "no_approver":
        req.status = "pending"
    lu = db.get(LineUser, ticket.line_user_id) if ticket.line_user_id else None
    flex = line_service.approval_flex(
        request_id=req.id, ticket_no=ticket.ticket_no, title=ticket.title,
        summary=(ticket.description or "")[:300],
        requester=lu.known_name if lu else (ticket.reporter_name or "-"),
        department=(lu.department if lu else None) or "-",
    )
    await line_service.push_flex(req.approver_line_user_id, flex)
    req.reminded_at = _now()
    db.commit()
    return True


def pending_for_approver(db: Session, line_user_id: str) -> list[ApprovalRequest]:
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.approver_line_user_id == line_user_id,
                ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at)
        .all()
    )


def awaiting_reason_for(db: Session, line_user_id: str) -> ApprovalRequest | None:
    """คำขอที่เพิ่งถูกปฏิเสธและกำลังรอให้ผู้อนุมัติพิมพ์เหตุผลตามมา."""
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.decided_by_line_user_id == line_user_id,
                ApprovalRequest.awaiting_reason.is_(True))
        .order_by(ApprovalRequest.decided_at.desc())
        .first()
    )
