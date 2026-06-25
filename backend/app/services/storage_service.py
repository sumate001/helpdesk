"""MinIO file upload — เก็บรูปภาพจาก Line."""
import io
import logging

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


def ensure_bucket() -> None:
    client = get_client()
    try:
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
    except S3Error as exc:
        logger.error("MinIO ensure_bucket failed: %s", exc)


def upload_bytes(
    object_name: str, data: bytes, content_type: str = "application/octet-stream"
) -> str:
    """อัปโหลด bytes คืน object path (bucket/object_name)."""
    client = get_client()
    ensure_bucket()
    client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.MINIO_BUCKET}/{object_name}"
