"""RAG — ฝัง embedding ด้วย Ollama (bge-m3) + ค้น knowledge base ด้วย pgvector.

ใช้ป้อนความรู้ระบบ/นโยบาย IT ภายในบริษัทให้ gemma ตอนทำ intake — ทั้งช่วย "ตอบ"
และช่วย "classify" (เช่น รู้ว่า VPN/WiFi ต้องขออนุมัติ → service_request).
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.kb_chunk import KbChunk
from app.services import settings_service

logger = logging.getLogger(__name__)


async def embed(text: str) -> list[float] | None:
    """ฝัง embedding หนึ่งข้อความ — คืน None ถ้า Ollama ล่ม (ตัวเรียกต้องเผื่อ)."""
    url = f"{settings_service.get('OLLAMA_BASE_URL')}/api/embeddings"
    payload = {"model": settings_service.get("OLLAMA_EMBED_MODEL"), "prompt": text}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            vec = resp.json().get("embedding")
        if not vec or len(vec) != settings.EMBED_DIM:
            logger.warning("embedding มิติไม่ตรง: ได้ %s คาด %s", len(vec or []), settings.EMBED_DIM)
            return None
        return vec
    except httpx.HTTPError as exc:
        logger.warning("embed failed: %s", exc)
        return None


def retrieve(db: Session, query_embedding: list[float], k: int | None = None) -> list[KbChunk]:
    """คืน chunk ที่ใกล้ที่สุด (cosine) ที่ผ่าน threshold — เรียงจากใกล้สุด."""
    k = k or settings_service.get("RAG_TOP_K")
    distance = KbChunk.embedding.cosine_distance(query_embedding).label("distance")
    rows = (
        db.query(KbChunk, distance)
        .filter(KbChunk.is_active.is_(True))
        .order_by(distance)
        .limit(k)
        .all()
    )
    # cosine similarity = 1 - distance → ตัดที่ต่ำกว่า threshold
    return [
        chunk
        for chunk, dist in rows
        if (1 - dist) >= settings_service.get("RAG_MIN_SIMILARITY")
    ]


async def retrieve_context(db: Session, query: str) -> str:
    """ค้น KB จากข้อความผู้ใช้ → คืนข้อความ context พร้อมแปะ prompt (ว่างถ้าไม่เจอ/ล่ม)."""
    if not query or not query.strip():
        return ""
    emb = await embed(query)
    if emb is None:
        return ""
    chunks = retrieve(db, emb)
    if not chunks:
        return ""
    return "\n---\n".join(
        f"[{c.title or c.category or 'นโยบาย'}] {c.content}" for c in chunks
    )


async def find_form(db: Session, query: str):
    """ค้น KB จากข้อความผู้ใช้ → คืน ServiceForm ที่ผูกกับ chunk ที่ "ใกล้สุดจริงๆ" ถ้ามี.

    เกณฑ์ 2 ชั้น กันเด้งฟอร์มผิดเรื่อง (เช่น "ขอย้ายเครื่อง" ไปโดนฟอร์มเบิกอุปกรณ์):
    1. top-1 ต้องใกล้จริง (FORM_MIN_SIMILARITY — เข้มกว่าการดึง context ทั่วไปมาก)
    2. ต้องชนะฟอร์มอื่นที่ใกล้รองลงมา "ขาด" (FORM_MATCH_MARGIN) — แมตช์ผิดมัก
       ก้ำกึ่งกันทั้งกระดาน แมตช์ถูกจะทิ้งห่างชัด
    คืน None ถ้าไม่ผ่านเกณฑ์/embed ล่ม/ไม่ได้ผูกฟอร์ม.
    """
    from app.models.service_form import ServiceForm

    if not query or not query.strip():
        return None
    emb = await embed(query)
    if emb is None:
        return None

    distance = KbChunk.embedding.cosine_distance(emb).label("distance")
    rows = (
        db.query(KbChunk, distance)
        .filter(KbChunk.is_active.is_(True), KbChunk.form_id.isnot(None))
        .order_by(distance)
        .limit(5)
        .all()
    )
    if not rows:
        return None
    chunk, dist = rows[0]
    top_sim = 1 - dist
    if top_sim < settings.FORM_MIN_SIMILARITY:
        return None
    # margin เทียบกับ chunk ที่ใกล้รองลงมาซึ่งผูก "ฟอร์มคนละตัว" (ฟอร์มเดียวกันหลาย chunk ไม่นับ)
    runner_up = next((1 - d for c, d in rows[1:] if c.form_id != chunk.form_id), None)
    if runner_up is not None and (top_sim - runner_up) < settings.FORM_MATCH_MARGIN:
        return None
    form = db.get(ServiceForm, chunk.form_id)
    return form if form and form.is_active else None


async def upsert_chunk(
    db: Session,
    content: str,
    title: str | None = None,
    category: str | None = None,
    source: str | None = None,
    chunk_id: int | None = None,
) -> KbChunk:
    """สร้าง/แก้ chunk แล้วฝัง embedding ใหม่จาก title+content."""
    emb = await embed(f"{title or ''}\n{content}".strip())
    if emb is None:
        raise RuntimeError("ฝัง embedding ไม่สำเร็จ (Ollama embed model ไม่พร้อม)")
    now = datetime.now(timezone.utc)
    chunk = db.get(KbChunk, chunk_id) if chunk_id else None
    if chunk is None:
        chunk = KbChunk(created_at=now)
        db.add(chunk)
    chunk.title = title
    chunk.content = content
    chunk.category = category
    chunk.source = source
    chunk.embedding = emb
    chunk.updated_at = now
    db.commit()
    db.refresh(chunk)
    return chunk
