import os
import uuid
from typing import Optional
from io import BytesIO

from app.core.minio_client import get_minio, ensure_bucket


async def upload_activity_image(
    file_bytes: bytes,
    content_type: str,
    filename: str,
    student_id: int,
    session_id: int,
) -> str:
    """
    Uploads activity image to MinIO under:
    activities/{student_id}/{session_id}/{uuid}.ext
    """

    minio = get_minio()

    bucket = os.getenv("MINIO_BUCKET_ACTIVITIES", "vikasana-activities")
    ensure_bucket(minio, bucket)

    ext = filename.split(".")[-1].lower() if "." in filename else "jpg"

    object_name = (
        f"activities/{student_id}/{session_id}/{uuid.uuid4().hex}.{ext}"
    )

    data = BytesIO(file_bytes)

    minio.put_object(
        bucket,
        object_name,
        data,
        length=len(file_bytes),
        content_type=content_type or "application/octet-stream",
    )

    public_base = os.getenv("MINIO_PUBLIC_BASE", "").rstrip("/")
    if public_base:
        return f"{public_base}/{bucket}/{object_name}"

    # fallback: presigned URL
    return minio.presigned_get_object(bucket, object_name)