"""Knowledge base management (Admin only) — ความรู้ระบบ/นโยบาย IT สำหรับ RAG.

สร้าง/แก้ chunk แล้วระบบจะฝัง embedding ให้อัตโนมัติ. แนะนำ 1 หัวข้อ/1 chunk.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.kb_chunk import KbChunk
from app.models.user import User
from app.schemas.kb import KbChunkCreate, KbChunkOut, KbChunkUpdate
from app.services import rag_service

router = APIRouter(prefix="/api/kb", tags=["kb"])


@router.get("", response_model=list[KbChunkOut])
def list_chunks(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(KbChunk).order_by(KbChunk.id).all()


@router.post("", response_model=KbChunkOut, status_code=201)
async def create_chunk(
    payload: KbChunkCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        return await rag_service.upsert_chunk(
            db,
            content=payload.content,
            title=payload.title,
            category=payload.category,
            source=payload.source,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.patch("/{chunk_id}", response_model=KbChunkOut)
async def update_chunk(
    chunk_id: int,
    payload: KbChunkUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    chunk = db.get(KbChunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="ไม่พบ KB chunk")

    data = payload.model_dump(exclude_unset=True)
    # ถ้าแก้เนื้อหา/หัวข้อ → ต้องฝัง embedding ใหม่
    if "content" in data or "title" in data:
        try:
            chunk = await rag_service.upsert_chunk(
                db,
                content=data.get("content", chunk.content),
                title=data.get("title", chunk.title),
                category=data.get("category", chunk.category),
                source=data.get("source", chunk.source),
                chunk_id=chunk.id,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        data.pop("content", None)
        data.pop("title", None)
        data.pop("category", None)
        data.pop("source", None)

    # field ที่เหลือ (เช่น is_active, category/source เดี่ยวๆ) ไม่ต้อง re-embed
    for key, value in data.items():
        setattr(chunk, key, value)
    db.commit()
    db.refresh(chunk)
    return chunk


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(
    chunk_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    chunk = db.get(KbChunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="ไม่พบ KB chunk")
    db.delete(chunk)
    db.commit()
