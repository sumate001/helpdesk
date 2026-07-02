from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FormField(BaseModel):
    key: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=255)
    type: Literal["text", "textarea", "select", "number"] = "text"
    required: bool = True
    options: list[str] | None = None  # สำหรับ type=select


class ServiceFormCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    category: str | None = None
    priority: str = "low"
    fields: list[FormField] = []
    is_active: bool = True


class ServiceFormUpdate(BaseModel):
    name: str | None = None
    slug: str | None = Field(None, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    category: str | None = None
    priority: str | None = None
    fields: list[FormField] | None = None
    is_active: bool | None = None


class ServiceFormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    category: str | None
    priority: str
    fields: list[FormField]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PublicFormOut(BaseModel):
    """นิยามฟอร์มที่ส่งให้หน้า LIFF render (ไม่มี field ภายใน)."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    description: str | None
    fields: list[FormField]
