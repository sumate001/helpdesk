from pydantic import BaseModel, Field


class FormSubmitIn(BaseModel):
    """ส่งคำตอบฟอร์มจากหน้า LIFF — id_token ไว้ยืนยันตัวตน, values = {field_key: value}."""

    id_token: str = Field(..., description="ID token จาก liff.getIDToken()")
    values: dict[str, str] = Field(default_factory=dict)


class ServiceRequestOut(BaseModel):
    ticket_no: str
    status: str
