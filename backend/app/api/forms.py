"""Service forms management (Admin only) — แบบฟอร์มขอใช้บริการแบบ dynamic.

นิยาม field เองได้ (text/textarea/select/number) แล้วผูกกับ KB chunk เพื่อให้บอท
ยื่นปุ่มเปิดฟอร์มอัตโนมัติเมื่อ RAG เจอความรู้ที่เกี่ยวข้อง.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.service_form import ServiceForm
from app.models.user import User
from app.schemas.form import ServiceFormCreate, ServiceFormOut, ServiceFormUpdate

router = APIRouter(prefix="/api/forms", tags=["forms"])


def _dump_fields(payload) -> list:
    return [f.model_dump() for f in payload]


@router.get("", response_model=list[ServiceFormOut])
def list_forms(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(ServiceForm).order_by(ServiceForm.id).all()


@router.post("", response_model=ServiceFormOut, status_code=201)
def create_form(
    payload: ServiceFormCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(ServiceForm).filter(ServiceForm.slug == payload.slug).first():
        raise HTTPException(status_code=409, detail=f"slug '{payload.slug}' ถูกใช้แล้ว")
    now = datetime.now(timezone.utc)
    form = ServiceForm(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        fields=_dump_fields(payload.fields),
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


@router.patch("/{form_id}", response_model=ServiceFormOut)
def update_form(
    form_id: int,
    payload: ServiceFormUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    form = db.get(ServiceForm, form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="ไม่พบฟอร์ม")
    data = payload.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"] != form.slug:
        if db.query(ServiceForm).filter(ServiceForm.slug == data["slug"]).first():
            raise HTTPException(status_code=409, detail=f"slug '{data['slug']}' ถูกใช้แล้ว")
    if "fields" in data:
        data["fields"] = _dump_fields(payload.fields)
    for key, value in data.items():
        setattr(form, key, value)
    form.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(form)
    return form


@router.delete("/{form_id}", status_code=204)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    form = db.get(ServiceForm, form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="ไม่พบฟอร์ม")
    db.delete(form)
    db.commit()
