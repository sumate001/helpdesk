from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    """ค่า effective ที่ระบบใช้จริง + EMBED_DIM (read-only) + list key ที่ถูก override."""

    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OLLAMA_EMBED_MODEL: str
    RAG_TOP_K: int
    RAG_MIN_SIMILARITY: float
    FOLLOWUP_ENABLED: bool  # สวิตช์ follow-up flow (ถามซ้ำ/เปิด ticket อัตโนมัติเมื่อผู้ใช้เงียบ)
    STAFF_PROGRESS_ENABLED: bool  # สวิตช์ตามถามความคืบหน้าจากช่างที่รับงานทาง LINE
    TICKET_CONFIRM_REQUIRED: bool  # ต้องกดยืนยันก่อนเปิด ticket ไหม (ปิด = เปิดเคสทันทีเมื่อข้อมูลครบ)
    ITAMTV_ENABLED: bool  # เปิดเคสคู่ขนาน + sync สถานะกับ itamtv
    EMPLOYEE_LOOKUP_ENABLED: bool  # ลงทะเบียน/ดึงข้อมูลพนักงานจาก Employee DB
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
    STAFF_PROGRESS_ENABLED: bool | None = None
    TICKET_CONFIRM_REQUIRED: bool | None = None
    ITAMTV_ENABLED: bool | None = None
    EMPLOYEE_LOOKUP_ENABLED: bool | None = None


class IntegrationOut(BaseModel):
    """ระบบภายนอกหนึ่งตัว: สวิตช์เปิด/ปิด + ผลเช็คการเชื่อมต่อสดๆ."""

    key: str  # setting key ของสวิตช์ (ITAMTV_ENABLED / EMPLOYEE_LOOKUP_ENABLED)
    name: str
    description: str
    url: str
    enabled: bool
    reachable: bool | None  # None = ปิดสวิตช์อยู่ เลยไม่ได้เช็ค
    detail: str  # ข้อความผลเช็ค (เวอร์ชัน/error สั้นๆ)


class IntegrationsOut(BaseModel):
    integrations: list[IntegrationOut]


class OllamaModel(BaseModel):
    name: str
    size: int | None = None
    vision: bool = False  # รองรับรูป (multimodal) ไหม — ดูจาก capabilities


class OllamaModelsOut(BaseModel):
    models: list[OllamaModel]
