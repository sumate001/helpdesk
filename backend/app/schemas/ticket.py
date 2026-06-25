from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LineUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_user_id: str
    display_name: str | None = None
    department: str | None = None
    building: str | None = None
    floor: str | None = None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    created_at: datetime


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    content: str
    is_internal: bool
    created_at: datetime


class CommentCreate(BaseModel):
    content: str
    is_internal: bool = False


class EquipmentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_name: str
    quantity: int
    reason: str | None = None
    status: str
    approved_by: int | None = None
    approved_at: datetime | None = None


class EquipmentRequestUpdate(BaseModel):
    item_name: str | None = None
    quantity: int | None = None
    reason: str | None = None


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    type: str = "L2"
    priority: str = "medium"
    line_user_id: int | None = None


class TicketUpdate(BaseModel):
    status: str | None = None
    assigned_to: int | None = None
    priority: str | None = None
    category: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_no: str
    title: str
    description: str | None = None
    category: str | None = None
    type: str | None = None
    priority: str | None = None
    status: str
    assigned_to: int | None = None
    ai_response: str | None = None
    sla_response_due_at: datetime | None = None
    sla_resolve_due_at: datetime | None = None
    sla_breached: bool
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    line_user: LineUserOut | None = None


class TicketDetail(TicketOut):
    comments: list[CommentOut] = []
    attachments: list[AttachmentOut] = []
    equipment_request: EquipmentRequestOut | None = None
