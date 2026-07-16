from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr
    display_name: str | None = None
    role: str = "staff"
    # LINE userId ของช่าง — ใช้ push การ์ดปิดเคส + ยืนยันตัวตนตอนกดปุ่ม
    line_user_id: str | None = None
    # สิทธิ์ปิดเคสในระบบ itamtv
    itamtv_token: str | None = None
    itamtv_emp_code: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    line_user_id: str | None = None
    itamtv_token: str | None = None
    itamtv_emp_code: str | None = None


class UserSelfUpdate(BaseModel):
    """ผู้ใช้แก้โปรไฟล์ตัวเอง — แก้ role/is_active/username ไม่ได้ (กัน self-escalate)."""
    email: EmailStr | None = None
    display_name: str | None = None
    password: str | None = None
    line_user_id: str | None = None
    itamtv_token: str | None = None
    itamtv_emp_code: str | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
