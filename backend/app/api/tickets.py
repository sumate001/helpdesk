"""Ticket CRUD + approve/reject สำหรับ IT Staff."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.equipment_request import EquipmentRequest
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.models.ticket_comment import TicketComment
from app.models.user import User
from app.schemas.ticket import (
    CommentCreate,
    CommentOut,
    EquipmentRequestOut,
    EquipmentRequestUpdate,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketUpdate,
)
from app.services import line_service, storage_service, ticket_service

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assigned_to: int | None = None,
    q: str | None = Query(None, description="ค้นหา ticket_no / หัวข้อ / รายละเอียด / ชื่อผู้แจ้ง"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if category:
        query = query.filter(Ticket.category == category)
    if assigned_to:
        query = query.filter(Ticket.assigned_to == assigned_to)
    if q:
        like = f"%{q}%"
        query = query.outerjoin(Ticket.line_user).filter(
            (Ticket.ticket_no.ilike(like))
            | (Ticket.title.ilike(like))
            | (Ticket.description.ilike(like))
            | (LineUser.display_name.ilike(like))
        )
    return query.order_by(Ticket.id.desc()).limit(500).all()


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    return ticket


@router.get("/{ticket_id}/attachments/{attachment_id}/file")
def get_attachment_file(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    attachment = (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.id == attachment_id,
            TicketAttachment.ticket_id == ticket_id,
        )
        .one_or_none()
    )
    if attachment is None or not attachment.file_path:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์แนบ")

    bucket, _, object_name = attachment.file_path.partition("/")
    client = storage_service.get_client()
    try:
        response = client.get_object(bucket, object_name)
    except S3Error as exc:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บน storage") from exc

    return StreamingResponse(
        response.stream(32 * 1024),
        media_type=attachment.mime_type or "application/octet-stream",
    )


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return ticket_service.create_ticket(
        db,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        ticket_type=payload.type,
        priority=payload.priority,
        line_user_id=payload.line_user_id,
    )


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") == "resolved" and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(timezone.utc)
    for key, value in data.items():
        setattr(ticket, key, value)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    ticket_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    comment = TicketComment(
        ticket_id=ticket_id,
        user_id=user.id,
        content=payload.content,
        is_internal=payload.is_internal,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # ส่งกลับหา user ถ้าไม่ใช่ internal
    if not payload.is_internal and ticket.line_user:
        asyncio.run(
            line_service.push(ticket.line_user.line_user_id, payload.content)
        )
    return comment


@router.patch("/{ticket_id}/equipment-request", response_model=EquipmentRequestOut)
def update_equipment_request(
    ticket_id: int,
    payload: EquipmentRequestUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """IT แก้ item_name / quantity ที่ AI สกัดมา ก่อนกดอนุมัติ."""
    ticket, eq = _get_request(db, ticket_id)
    if eq.status != "pending":
        raise HTTPException(status_code=400, detail="คำขอนี้ถูกพิจารณาแล้ว แก้ไขไม่ได้")
    data = payload.model_dump(exclude_unset=True)
    if "quantity" in data and data["quantity"] is not None and data["quantity"] < 1:
        raise HTTPException(status_code=400, detail="quantity ต้องมากกว่า 0")
    for key, value in data.items():
        setattr(eq, key, value)
    db.commit()
    db.refresh(eq)
    return eq


@router.post("/{ticket_id}/approve", response_model=TicketOut)
def approve_request(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket, eq = _get_request(db, ticket_id)
    eq.status = "approved"
    eq.approved_by = user.id
    eq.approved_at = datetime.now(timezone.utc)
    ticket.status = "in_progress"
    db.commit()
    db.refresh(ticket)
    if ticket.line_user:
        msg = (
            f"✅ อนุมัติแล้ว: {eq.item_name} จำนวน {eq.quantity} ชิ้น\n"
            f"ทีม IT จะดำเนินการต่อไปครับ"
        )
        asyncio.run(line_service.push(ticket.line_user.line_user_id, msg))
    return ticket


@router.post("/{ticket_id}/reject", response_model=TicketOut)
def reject_request(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket, eq = _get_request(db, ticket_id)
    eq.status = "rejected"
    eq.approved_by = user.id
    eq.approved_at = datetime.now(timezone.utc)
    ticket.status = "closed"
    db.commit()
    db.refresh(ticket)
    if ticket.line_user:
        msg = f"❌ ขออภัยครับ คำขอ {eq.item_name} ไม่ได้รับการอนุมัติในครั้งนี้"
        asyncio.run(line_service.push(ticket.line_user.line_user_id, msg))
    return ticket


def _get_request(db: Session, ticket_id: int) -> tuple[Ticket, EquipmentRequest]:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    eq = (
        db.query(EquipmentRequest)
        .filter(EquipmentRequest.ticket_id == ticket_id)
        .one_or_none()
    )
    if eq is None:
        raise HTTPException(status_code=400, detail="ticket นี้ไม่มีคำขอเบิกอุปกรณ์")
    return ticket, eq
