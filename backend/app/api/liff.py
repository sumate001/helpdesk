"""LIFF endpoints — ฟอร์มขอใช้บริการแบบ dynamic ที่ user กรอกผ่าน LINE (ไม่ผ่าน JWT).

- GET  /api/liff/forms/{slug}         → นิยามฟอร์มไว้ render หน้า LIFF
- POST /api/liff/forms/{slug}/submit  → verify ID token + เปิด ticket จากคำตอบ

ยืนยันตัวตนด้วย ID token จาก LIFF (LINE เซ็นมา ปลอมไม่ได้) → ได้ userId ที่เชื่อถือได้.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.service_form import ServiceForm
from app.schemas.form import PublicFormOut
from app.schemas.liff import FormSubmitIn, ServiceRequestOut
from app.services import line_service, ticket_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/liff", tags=["liff"])

APPROVAL_CATEGORIES = ("equipment_request", "service_request")


def _get_active_form(db: Session, slug: str) -> ServiceForm:
    form = db.query(ServiceForm).filter(ServiceForm.slug == slug).first()
    if form is None or not form.is_active:
        raise HTTPException(status_code=404, detail="ไม่พบฟอร์ม หรือฟอร์มถูกปิดใช้งาน")
    return form


@router.get("/forms/{slug}", response_model=PublicFormOut)
def get_form(slug: str, db: Session = Depends(get_db)):
    return _get_active_form(db, slug)


@router.post("/forms/{slug}/submit", response_model=ServiceRequestOut)
async def submit_form(slug: str, payload: FormSubmitIn, db: Session = Depends(get_db)):
    form = _get_active_form(db, slug)

    verified = await line_service.verify_id_token(payload.id_token)
    if not verified or not verified.get("sub"):
        raise HTTPException(status_code=401, detail="ยืนยันตัวตนไม่สำเร็จ (id_token ไม่ถูกต้อง)")
    line_user_id = verified["sub"]

    values = payload.values or {}
    # ตรวจ field ที่ required ตามนิยามฟอร์ม
    for f in form.fields:
        if f.get("required") and not str(values.get(f["key"], "")).strip():
            raise HTTPException(status_code=422, detail=f"กรุณากรอก: {f.get('label', f['key'])}")

    lu = ticket_service.upsert_line_user(
        db, line_user_id, {"displayName": verified.get("name"), "pictureUrl": verified.get("picture")}
    )
    # field มาตรฐานที่ map เข้าโปรไฟล์ผู้แจ้งได้ → อัปเดต line_users
    if values.get("full_name"):
        lu.display_name = values["full_name"][:100]
    if values.get("building"):
        lu.building = values["building"][:100]
    if values.get("floor"):
        lu.floor = values["floor"][:20]

    # ประกอบ description จาก label+value ตามลำดับ field
    lines = [f"{f['label']}: {values.get(f['key'], '-')}" for f in form.fields]
    description = f"{form.name}\n" + "\n".join(lines)
    requester = values.get("full_name") or lu.display_name or "-"

    is_approval = form.category in APPROVAL_CATEGORIES
    ticket = ticket_service.create_ticket(
        db,
        title=f"{form.name} — {requester}",
        description=description,
        category=form.category,
        ticket_type="L1" if is_approval else "L2",
        priority=form.priority or "low",
        status="pending_approval" if is_approval else "open",
        line_user_id=lu.id,
    )
    db.commit()

    await line_service.notify_group(ticket_service.group_notify_text(ticket))
    tail = (
        "ทีม IT จะตรวจสอบและอนุมัติ แล้วแจ้งกลับให้ทราบครับ"
        if is_approval
        else "ทีม IT จะรีบดำเนินการให้ครับ"
    )
    await line_service.push(
        line_user_id,
        f"รับคำขอ “{form.name}” ของคุณแล้วครับ 🙏\nหมายเลข Ticket: {ticket.ticket_no}\n{tail}",
    )
    return ServiceRequestOut(ticket_no=ticket.ticket_no, status=ticket.status)
