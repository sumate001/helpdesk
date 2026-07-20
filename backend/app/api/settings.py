"""Runtime AI settings (Admin only) — ปรับ model/RAG params สดๆ ไม่ต้อง restart.

ค่าเก็บใน DB (override .env) แล้วอัปเดต in-memory cache ที่ ai_service/rag_service อ่าน.
"""
import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings as env_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.settings import (
    IntegrationOut,
    IntegrationsOut,
    OllamaModelsOut,
    SettingsOut,
    SettingsUpdate,
)
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current() -> SettingsOut:
    eff = settings_service.all_effective()
    return SettingsOut(
        **eff,
        EMBED_DIM=env_settings.EMBED_DIM,
        overridden=sorted(settings_service.overridden_keys()),
    )


@router.get("", response_model=SettingsOut)
def get_settings(_: User = Depends(require_admin)):
    return _current()


@router.patch("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return _current()
    try:
        settings_service.update(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _current()


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[bool, str]:
    """GET หนึ่งครั้งดูว่าปลายทางตอบไหม — (reachable, ข้อความสั้นๆ)."""
    try:
        resp = await client.get(url)
        if resp.status_code < 500:
            return True, f"ตอบ HTTP {resp.status_code}"
        return False, f"ปลายทาง error (HTTP {resp.status_code})"
    except httpx.HTTPError as exc:
        return False, f"เชื่อมต่อไม่ได้: {type(exc).__name__}"


@router.get("/integrations", response_model=IntegrationsOut)
async def list_integrations(_: User = Depends(require_admin)):
    """ระบบภายนอกที่เชื่อมต่อ + สถานะสดๆ — สวิตช์เปิด/ปิดแก้ผ่าน PATCH /api/settings."""
    specs = [
        {
            "key": "ITAMTV_ENABLED",
            "name": "itamtv (ระบบแจ้งซ่อมกลาง)",
            "description": "เปิดเคสคู่ขนาน + sync สถานะเคสสองทาง",
            "url": env_settings.ITAMTV_ADDJOB_URL,
        },
        {
            "key": "EMPLOYEE_LOOKUP_ENABLED",
            "name": "Amarin Employee Database",
            "description": "ลงทะเบียนผูกผู้ใช้ LINE + ดึงข้อมูลพนักงาน/เครื่องที่ถือครอง",
            "url": env_settings.EMPLOYEE_DB_URL,
        },
    ]
    out: list[IntegrationOut] = []
    async with httpx.AsyncClient(timeout=5) as client:
        results = await asyncio.gather(*(_probe(client, s["url"]) for s in specs))
    for spec, (reachable, detail) in zip(specs, results):
        enabled = bool(settings_service.get(spec["key"]))
        spec["url"] = spec["url"].split("?")[0]  # ไม่โชว์ token ใน query ให้หน้า UI
        out.append(IntegrationOut(**spec, enabled=enabled, reachable=reachable, detail=detail))
    return IntegrationsOut(integrations=out)


@router.get("/ollama-models", response_model=OllamaModelsOut)
async def list_ollama_models(
    base_url: str | None = None,
    _: User = Depends(require_admin),
):
    """ทดสอบเชื่อมต่อ Ollama + ดึงรายชื่อ model ที่ pull ไว้แล้ว.

    base_url: ถ้าส่งมา → ทดสอบ URL ที่ผู้ใช้พิมพ์ (ยังไม่ save) ไม่งั้นใช้ค่าปัจจุบัน.
    """
    base = (base_url or settings_service.get("OLLAMA_BASE_URL")).strip().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            tags = resp.json().get("models", [])

            async def _vision(name: str) -> bool:
                # /api/show บอก capabilities ของโมเดล — มี "vision" = รับรูปได้
                try:
                    r = await client.post(f"{base}/api/show", json={"model": name})
                    r.raise_for_status()
                    return "vision" in (r.json().get("capabilities") or [])
                except httpx.HTTPError:
                    return False

            names = [m.get("name", "") for m in tags]
            visions = await asyncio.gather(*(_vision(n) for n in names))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"เชื่อมต่อ Ollama ไม่ได้: {exc}")
    return OllamaModelsOut(
        models=[
            {"name": m.get("name", ""), "size": m.get("size"), "vision": v}
            for m, v in zip(tags, visions)
        ]
    )
