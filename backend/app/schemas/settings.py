from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    """ค่า effective ที่ระบบใช้จริง + EMBED_DIM (read-only) + list key ที่ถูก override."""

    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OLLAMA_EMBED_MODEL: str
    RAG_TOP_K: int
    RAG_MIN_SIMILARITY: float
    FOLLOWUP_ENABLED: bool  # สวิตช์ follow-up flow (ถามซ้ำ/เปิด ticket อัตโนมัติเมื่อผู้ใช้เงียบ)
    TICKET_CONFIRM_REQUIRED: bool  # ต้องกดยืนยันก่อนเปิด ticket ไหม (ปิด = เปิดเคสทันทีเมื่อข้อมูลครบ)
    EMBED_DIM: int  # read-only — ผูกกับ vector column ใน DB
    overridden: list[str]  # key ที่มาจาก DB (ต่างจาก .env)


class SettingsUpdate(BaseModel):
    """ส่งเฉพาะ field ที่อยากแก้. ค่าว่าง/None = ล้าง override กลับไปใช้ค่า .env."""

    OLLAMA_BASE_URL: str | None = None
    OLLAMA_MODEL: str | None = None
    OLLAMA_EMBED_MODEL: str | None = None
    RAG_TOP_K: int | None = Field(default=None, ge=1, le=20)
    RAG_MIN_SIMILARITY: float | None = Field(default=None, ge=0.0, le=1.0)
    FOLLOWUP_ENABLED: bool | None = None
    TICKET_CONFIRM_REQUIRED: bool | None = None


class OllamaModel(BaseModel):
    name: str
    size: int | None = None
    vision: bool = False  # รองรับรูป (multimodal) ไหม — ดูจาก capabilities


class OllamaModelsOut(BaseModel):
    models: list[OllamaModel]
