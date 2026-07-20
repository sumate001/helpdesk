"""Runtime settings — override ค่าใน .env ได้จาก UI โดยไม่ต้อง restart.

ค่าใน DB (ตาราง app_settings) ทับค่า default จาก settings (.env). โหลดเข้า in-memory
cache ตอน start + อัปเดต cache ทุกครั้งที่ PATCH → ai_service/rag_service อ่านค่าผ่าน
get() เพื่อให้เปลี่ยน model/RAG params ได้สดๆ.

EMBED_DIM ไม่อยู่ในรายการที่แก้ได้ — มันผูกกับ dimension ของ vector column ใน DB
การเปลี่ยนต้องทำ migration + re-embed ใหม่ทั้งหมด จึงปล่อยให้คุมผ่าน .env เท่านั้น.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in {"true", "1", "yes", "on"}:
        return True
    if s in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"ค่า boolean ไม่ถูกต้อง: {raw!r}")


# key -> ฟังก์ชัน coerce จาก string เป็น type จริง (ใช้ validate ตอน save ด้วย)
EDITABLE_KEYS: dict[str, Callable[[Any], Any]] = {
    "OLLAMA_BASE_URL": str,
    "OLLAMA_MODEL": str,
    "OLLAMA_EMBED_MODEL": str,
    "RAG_TOP_K": int,
    "RAG_MIN_SIMILARITY": float,
    "FOLLOWUP_ENABLED": _to_bool,
    "TICKET_CONFIRM_REQUIRED": _to_bool,
}

_cache: dict[str, Any] = {}


def _coerce(key: str, raw: Any) -> Any:
    return EDITABLE_KEYS[key](raw)


def load(db: Session) -> None:
    """โหลดค่าจาก DB เข้า cache (เรียกตอน start แอป)."""
    _cache.clear()
    for row in db.query(AppSetting).all():
        if row.key not in EDITABLE_KEYS:
            continue
        try:
            _cache[row.key] = _coerce(row.key, row.value)
        except (ValueError, TypeError):
            logger.warning("ค่า setting '%s'=%r ใน DB ไม่ถูก type — ใช้ค่า .env แทน", row.key, row.value)


def get(key: str) -> Any:
    """คืนค่า effective: ใช้ค่าจาก DB ถ้ามี ไม่งั้น fallback ค่า .env."""
    if key in _cache:
        return _cache[key]
    return getattr(settings, key)


def all_effective() -> dict[str, Any]:
    return {key: get(key) for key in EDITABLE_KEYS}


def overridden_keys() -> set[str]:
    """key ที่ถูก override จาก DB (ต่างจากค่า .env)."""
    return set(_cache.keys())


def update(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    """validate + บันทึกลง DB + อัปเดต cache. คืนค่า effective ทั้งหมด.

    ค่าไหนส่งมาเป็น None/ค่าว่าง → ลบ override (กลับไปใช้ค่า .env).
    """
    now = datetime.now(timezone.utc)
    for key, raw in values.items():
        if key not in EDITABLE_KEYS:
            raise ValueError(f"แก้ setting '{key}' ไม่ได้")

        row = db.query(AppSetting).filter(AppSetting.key == key).one_or_none()

        # ค่าว่าง = ล้าง override กลับไปใช้ default
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if row is not None:
                db.delete(row)
            _cache.pop(key, None)
            continue

        coerced = _coerce(key, raw)  # validate type — ValueError ถ้าผิด
        if row is None:
            row = AppSetting(key=key, created_at=now)
            db.add(row)
        row.value = str(raw)
        row.updated_at = now
        _cache[key] = coerced

    db.commit()
    return all_effective()
