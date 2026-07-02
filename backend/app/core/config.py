from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://itticket:itticket@postgres:5432/it_ticket_db"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Line
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    LINE_CHANNEL_SECRET: str = ""
    LINE_GROUP_IT_ID: str = ""
    # Channel ID ของ LINE Login channel ที่ผูก LIFF app — ใช้ verify ID token จากฟอร์ม LIFF
    LINE_CHANNEL_ID: str = ""
    # LIFF base URL ของ LIFF app (เช่น https://liff.line.me/<liff id>) — บอทแปะปุ่มฟอร์ม
    # โดยต่อ ?form=<slug> ท้าย URL ให้หน้า LIFF รู้ว่าจะ render ฟอร์มไหน
    LIFF_BASE_URL: str = ""

    # Ollama
    OLLAMA_BASE_URL: str = "http://100.94.37.18:11434"
    OLLAMA_MODEL: str = "gemma4:12b"
    # RAG embedding (multilingual — รองรับไทย) รันที่ Ollama เครื่องเดียวกับ gemma
    OLLAMA_EMBED_MODEL: str = "bge-m3"
    EMBED_DIM: int = 1024            # bge-m3 = 1024, nomic-embed-text = 768
    RAG_TOP_K: int = 4              # ดึง chunk ที่ใกล้สุดกี่อัน
    RAG_MIN_SIMILARITY: float = 0.4  # cosine similarity ต่ำกว่านี้ถือว่าไม่เกี่ยว ตัดทิ้ง
    # threshold สำหรับ "ยื่นฟอร์ม" — เข้มกว่า RAG ทั่วไป กันบอทเด้งฟอร์มผิดเรื่อง
    # (เรื่อง VPN วัดได้ ~0.59-0.73, เรื่อง hardware ~0.39-0.43 → 0.55 อยู่กลางช่องว่าง)
    FORM_MIN_SIMILARITY: float = 0.55

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "it-ticket-attachments"
    MINIO_SECURE: bool = False

    # App
    APP_ENV: str = "production"
    FRONTEND_URL: str = "http://localhost:3000"

    # Follow-up flow (ผู้ใช้เงียบกลางบทสนทนา → ถามซ้ำ → เปิด ticket อัตโนมัติ)
    # เปิด/ปิดสดได้จากหน้า Settings (override ใน DB) — ค่านี้เป็นค่าตั้งต้น
    FOLLOWUP_ENABLED: bool = True
    FOLLOWUP_DELAY_MINUTES: int = 10
    ESCALATE_DELAY_MINUTES: int = 30

    # คำขึ้นต้นที่ใช้เรียกบอทในกลุ่ม (คั่นด้วย comma) — ใช้แทน/ร่วมกับการ @ mention
    GROUP_TRIGGER_KEYWORDS: str = "itadmin,@itadmin,/itadmin"

    # multi-turn intake — หลังเริ่มคุย บอทเก็บข้อมูล/แก้ปัญหาก่อนเปิด ticket
    # conversation จะ active ภายในกี่นาที (ต่ออายุทุกครั้งที่ผู้ใช้ตอบ)
    CONVERSATION_MINUTES: int = 15

    @property
    def group_trigger_list(self) -> list[str]:
        return [k.strip().lower() for k in self.GROUP_TRIGGER_KEYWORDS.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
