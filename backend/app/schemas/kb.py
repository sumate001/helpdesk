from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KbChunkCreate(BaseModel):
    content: str
    title: str | None = None
    category: str | None = None
    source: str | None = None
    form_id: int | None = None


class KbChunkUpdate(BaseModel):
    content: str | None = None
    title: str | None = None
    category: str | None = None
    source: str | None = None
    is_active: bool | None = None
    form_id: int | None = None


class KbChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    content: str
    category: str | None
    source: str | None
    is_active: bool
    form_id: int | None
    created_at: datetime
    updated_at: datetime
