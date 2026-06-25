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

    # Ollama
    OLLAMA_BASE_URL: str = "http://100.94.37.18:11434"
    OLLAMA_MODEL: str = "gemma4:12b"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "it-ticket-attachments"
    MINIO_SECURE: bool = False

    # App
    APP_ENV: str = "production"
    FRONTEND_URL: str = "http://localhost:3000"

    # Follow-up timings (minutes)
    FOLLOWUP_DELAY_MINUTES: int = 10
    ESCALATE_DELAY_MINUTES: int = 30

    # คำขึ้นต้นที่ใช้เรียกบอทในกลุ่ม (คั่นด้วย comma) — ใช้แทน/ร่วมกับการ @ mention
    GROUP_TRIGGER_KEYWORDS: str = "itadmin,@itadmin,/itadmin"

    # หลังเรียกบอทในกลุ่ม → เปิด session ชั่วคราว รูปที่ส่งตามมาในช่วงนี้ถือว่าคุยกับบอท
    GROUP_SESSION_MINUTES: int = 10

    @property
    def group_trigger_list(self) -> list[str]:
        return [k.strip().lower() for k in self.GROUP_TRIGGER_KEYWORDS.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
