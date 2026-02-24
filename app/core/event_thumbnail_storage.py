import uuid
from datetime import timedelta
from urllib.parse import quote

from app.core.minio_client import minio_client  # use your existing client
from app.core.config import settings

EVENT_THUMBNAILS_BUCKET = "vikasana-event-thumbnails"


def build_thumbnail_key(admin_id: int, filename: str) -> str:
    safe_name = filename.replace(" ", "_")
    return f"thumbnails/{admin_id}/{uuid.uuid4().hex}_{safe_name}"


def public_url_for(bucket: str, key: str) -> str:
    # If you already have MINIO_PUBLIC_BASE_URL in settings, use it.
    # Example: http://31.97.230.171:9000
    base = getattr(settings, "MINIO_PUBLIC_BASE_URL", None) or settings.MINIO_ENDPOINT_PUBLIC
    return f"{base}/{bucket}/{quote(key)}"


def presign_put(bucket: str, key: str, content_type: str) -> str:
    # MinIO presigned PUT
    # NOTE: For some MinIO setups, content-type must be provided by client on PUT.
    return minio_client.presigned_put_object(
        bucket,
        key,
        expires=timedelta(minutes=15),
    )