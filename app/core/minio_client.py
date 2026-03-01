import os
from datetime import timedelta
from minio import Minio


def _env_bool(name: str, default: bool = False) -> bool:
    v = str(os.getenv(name, "")).strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def get_minio() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000").strip()
    access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
    secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
    secure = _env_bool("MINIO_SECURE", default=False)  # keep false for http

    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def get_presigned_url_internal(bucket: str, object_name: str, expiry_seconds: int = 900) -> str:
    """
    Internal presigned URL (HTTP). DO NOT use directly in HTTPS browser pages.
    Use the proxy route below instead.
    """
    minio = get_minio()
    return minio.presigned_get_object(
        bucket_name=bucket,
        object_name=object_name,
        expires=timedelta(seconds=int(expiry_seconds or 900)),
    )