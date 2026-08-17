"""Approval workflow API (Admin/IT) — ผังผู้อนุมัติ + คำขอที่รออนุมัติ.

ผังผู้อนุมัติ (department_approvers) เติมได้ 2 ทาง: IT กรอกเอง หรือระบบเสนอให้อัตโนมัติ
จากที่ผู้ขอเลือกหัวหน้าเอง (is_confirmed=False) แล้ว IT มากดยืนยันทีหลัง
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.approval import ApprovalRequest, DepartmentApprover
from app.models.ticket import Ticket
from app.models.user import User
from app.services import approval_service, itamtv_service


async def _verify_emp(emp_code: str | None, label: str) -> dict | None:
    """ตรวจรหัสพนักงานกับ Employee DB ก่อนบันทึก — พิมพ์ผิดตัวเดียว (9004 vs 90004)
    ทำให้ระบบหา LINE ไม่เจอแล้วคำขอไปค้างเงียบๆ จึงต้องกันตั้งแต่ตอนกรอก
    """
    code = (emp_code or "").strip()
    if not code:
        return None
    try:
        emp = await itamtv_service.lookup_employee_exact(emp_code=code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503,
                            detail=f"ต่อกับระบบพนักงานไม่ติด ({exc})") from exc
    if emp is None:
        raise HTTPException(status_code=422,
                            detail=f"ไม่พบรหัสพนักงาน '{code}' ({label}) ในระบบพนักงาน")
    return emp

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# --------------------------------------------------------------------------
# schemas
# --------------------------------------------------------------------------

class ApproverIn(BaseModel):
    department: str = Field(..., min_length=1, max_length=100)
    approver_emp_code: str = Field(..., min_length=1, max_length=20)
    approver_name: str | None = None
    approver_email: str | None = None
    backup_emp_code: str | None = None
    backup_name: str | None = None
    is_confirmed: bool = True
    note: str | None = None


class ApproverUpdate(BaseModel):
    approver_emp_code: str | None = None
    approver_name: str | None = None
    approver_email: str | None = None
    backup_emp_code: str | None = None
    backup_name: str | None = None
    is_confirmed: bool | None = None
    note: str | None = None


class ApproverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department: str
    approver_emp_code: str
    approver_name: str | None
    approver_email: str | None
    backup_emp_code: str | None
    backup_name: str | None
    is_confirmed: bool
    accepted: bool | None = False
    note: str | None
    # เติมจากฝั่ง service: ผู้อนุมัติคนนี้ผูก LINE ไว้หรือยัง (ถ้ายัง ส่งปุ่มให้ไม่ได้)
    line_linked: bool = False


class ApprovalOut(BaseModel):
    id: int
    ticket_id: int
    ticket_no: str
    title: str
    requester: str | None
    step: int
    status: str
    channel: str
    approver_name: str | None
    approver_emp_code: str | None
    approver_from_requester: bool
    line_linked: bool
    comment: str | None
    created_at: datetime
    decided_at: datetime | None


class DecideIn(BaseModel):
    approve: bool
    comment: str | None = None


# --------------------------------------------------------------------------
# ผังผู้อนุมัติ
# --------------------------------------------------------------------------

@router.get("/approvers", response_model=list[ApproverOut])
def list_approvers(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(DepartmentApprover).order_by(DepartmentApprover.department).all()
    out = []
    for r in rows:
        item = ApproverOut.model_validate(r)
        item.line_linked = bool(approval_service.line_id_of(db, r.approver_emp_code))
        out.append(item)
    return out


@router.post("/approvers", response_model=ApproverOut, status_code=201)
async def create_approver(payload: ApproverIn, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    dept = payload.department.strip()
    if db.query(DepartmentApprover).filter(DepartmentApprover.department == dept).first():
        raise HTTPException(status_code=409, detail=f"แผนก '{dept}' มีผู้อนุมัติแล้ว")
    # ตรวจรหัสจริงก่อน แล้วเติมชื่อ/อีเมลจาก Employee DB (ที่กรอกมาเป็นแค่ตัวช่วยจำ)
    emp = await _verify_emp(payload.approver_emp_code, "ผู้อนุมัติ")
    backup = await _verify_emp(payload.backup_emp_code, "ผู้อนุมัติสำรอง")
    data = payload.model_dump()
    data["approver_name"] = (emp or {}).get("name") or data.get("approver_name")
    data["approver_email"] = (emp or {}).get("email") or data.get("approver_email")
    if backup:
        data["backup_name"] = backup.get("name") or data.get("backup_name")
    now = datetime.now(timezone.utc)
    row = DepartmentApprover(**{**data, "department": dept},
                             accepted=False, created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    # แจ้งเจ้าตัวทาง LINE ให้กดยอมรับ — ถูกตั้งแล้วไม่รู้ตัว = คำขอไปจ่ออยู่เงียบๆ
    notified = await approval_service.notify_new_approver(
        db, row, proposed_by_name=user.display_name or user.username
    )
    out = ApproverOut.model_validate(row)
    out.line_linked = notified or bool(approval_service.line_id_of(db, row.approver_emp_code))
    return out


@router.patch("/approvers/{approver_id}", response_model=ApproverOut)
async def update_approver(approver_id: int, payload: ApproverUpdate,
                          db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    row = db.get(DepartmentApprover, approver_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ไม่พบผังผู้อนุมัตินี้")
    before = row.approver_emp_code
    data = payload.model_dump(exclude_unset=True)
    if "approver_emp_code" in data:
        emp = await _verify_emp(data["approver_emp_code"], "ผู้อนุมัติ")
        if emp:
            data["approver_name"] = emp.get("name") or data.get("approver_name")
            data["approver_email"] = emp.get("email") or data.get("approver_email")
    if data.get("backup_emp_code"):
        backup = await _verify_emp(data["backup_emp_code"], "ผู้อนุมัติสำรอง")
        if backup:
            data["backup_name"] = backup.get("name") or data.get("backup_name")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    if row.approver_emp_code != before:
        # เปลี่ยนตัวผู้อนุมัติ = คนใหม่ยังไม่รับทราบ ต้องแจ้ง+ให้กดยอมรับใหม่
        row.accepted = False
        row.accepted_at = None
    db.commit()
    db.refresh(row)
    # ยังไม่ได้กดยอมรับ → บันทึกทีไรก็ส่งการ์ดให้ใหม่ (ไม่ใช่เฉพาะตอนเปลี่ยนรหัส —
    # กรณีที่เจอจริง: แก้รหัสให้ถูกแล้วบันทึก แต่ค่าบังเอิญเท่าเดิม เลยไม่มีอะไรเด้ง)
    if not row.accepted:
        await approval_service.notify_new_approver(
            db, row, proposed_by_name=user.display_name or user.username
        )
    out = ApproverOut.model_validate(row)
    out.line_linked = bool(approval_service.line_id_of(db, row.approver_emp_code))
    return out


@router.delete("/approvers/{approver_id}", status_code=204)
def delete_approver(approver_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    row = db.get(DepartmentApprover, approver_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ไม่พบผังผู้อนุมัตินี้")
    db.delete(row)
    db.commit()


# --------------------------------------------------------------------------
# คำขออนุมัติ
# --------------------------------------------------------------------------

@router.get("", response_model=list[ApprovalOut])
def list_approvals(status: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    q = db.query(ApprovalRequest, Ticket).join(Ticket, ApprovalRequest.ticket_id == Ticket.id)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    rows = q.order_by(ApprovalRequest.created_at.desc()).limit(200).all()
    return [
        ApprovalOut(
            id=r.id, ticket_id=t.id, ticket_no=t.ticket_no, title=t.title,
            requester=t.reporter_name or (t.line_user.emp_name if t.line_user else None),
            step=r.step, status=r.status, channel=r.channel,
            approver_name=r.approver_name, approver_emp_code=r.approver_emp_code,
            approver_from_requester=r.approver_from_requester,
            line_linked=bool(r.approver_line_user_id),
            comment=r.comment, created_at=r.created_at, decided_at=r.decided_at,
        )
        for r, t in rows
    ]


@router.post("/{request_id}/decide")
async def decide_approval(request_id: int, payload: DecideIn,
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """IT ตัดสินแทนผู้อนุมัติ (เช่น หัวหน้าแจ้งทางโทรศัพท์) — บันทึกว่าใครเป็นคนกดไว้เสมอ."""
    req = db.get(ApprovalRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="ไม่พบคำขออนุมัตินี้")
    if req.status != "pending" and req.status != "no_approver":
        raise HTTPException(status_code=409, detail=f"คำขอนี้ถูกตัดสินไปแล้ว ({req.status})")
    comment = payload.comment
    note = f"(ทีม IT บันทึกแทนโดย {user.display_name or user.username})"
    comment = f"{comment} {note}" if comment else note
    ticket = await approval_service.decide(db, req, payload.approve,
                                           by_user_id=user.id, comment=comment)
    return {"ok": True, "ticket_no": ticket.ticket_no, "status": ticket.status}


@router.post("/{request_id}/resend")
async def resend_approval(request_id: int, db: Session = Depends(get_db),
                          _: User = Depends(get_current_user)):
    """ส่งการ์ดอนุมัติซ้ำ (เช่น หัวหน้าเพิ่งมาผูก LINE หลังคำขอถูกสร้าง)."""
    req = db.get(ApprovalRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="ไม่พบคำขออนุมัตินี้")
    ok = await approval_service.resend(db, req)
    if not ok:
        raise HTTPException(status_code=409,
                            detail="ส่งไม่ได้ — ผู้อนุมัติยังไม่ได้ผูก LINE กับระบบ")
    return {"ok": True}


@router.post("/approvers/{approver_id}/invite")
async def invite_approver(approver_id: int, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    """ส่งการ์ด "คุณถูกตั้งเป็นผู้อนุมัติ" ซ้ำ (เช่น เพิ่งมาผูก LINE ทีหลัง)."""
    row = db.get(DepartmentApprover, approver_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ไม่พบผังผู้อนุมัตินี้")
    ok = await approval_service.notify_new_approver(
        db, row, proposed_by_name=user.display_name or user.username
    )
    if not ok:
        raise HTTPException(status_code=409,
                            detail="ส่งไม่ได้ — ผู้อนุมัติยังไม่ได้ผูก LINE กับระบบ")
    return {"ok": True}
