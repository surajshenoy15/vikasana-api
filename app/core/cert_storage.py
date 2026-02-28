# app/core/cert_storage.py

import os
from io import BytesIO
from datetime import timedelta

from minio import Minio
from minio.error import S3Error


def _env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _env_bool(name: str, default: str = "false") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


MINIO_ENDPOINT = _env("MINIO_ENDPOINT")  # example: "minio.yourdomain.com:9000"
MINIO_ACCESS_KEY = _env("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = _env("MINIO_SECRET_KEY")
MINIO_USE_SSL = _env_bool("MINIO_USE_SSL", "false")

MINIO_BUCKET_CERTIFICATES = _env("MINIO_BUCKET_CERTIFICATES")  # example: "certificates"


_minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_USE_SSL,
)


def ensure_certificates_bucket_exists() -> None:
    try:
        found = _minio_client.bucket_exists(MINIO_BUCKET_CERTIFICATES)
        if not found:
            _minio_client.make_bucket(MINIO_BUCKET_CERTIFICATES)
    except S3Error as e:
        raise RuntimeError(f"MinIO bucket check/create failed: {e}") from e


def build_certificate_object_key(cert_id: int) -> str:
    # Keep consistent with your DB storage pattern
    return f"certificates/cert_{cert_id}.pdf"


def upload_certificate_pdf_bytes(object_key: str, pdf_bytes: bytes) -> str:
    """
    Uploads PDF bytes to MinIO and returns the stored object_key.
    object_key example: "certificates/cert_12.pdf"
    """
    ensure_certificates_bucket_exists()

    data = BytesIO(pdf_bytes)
    size = len(pdf_bytes)

    try:
        _minio_client.put_object(
            bucket_name=MINIO_BUCKET_CERTIFICATES,
            object_name=object_key,
            data=data,
            length=size,
            content_type="application/pdf",
        )
    except S3Error as e:
        raise RuntimeError(f"MinIO put_object failed: {e}") from e

    return object_key


def presign_certificate_download_url(object_key: str, expires_in: int = 3600) -> str:
    """
    Returns a presigned URL to download the certificate PDF from MinIO.
    """
    if expires_in < 60:
        expires_in = 60
    if expires_in > 7 * 24 * 3600:
        expires_in = 7 * 24 * 3600  # MinIO/S3 typical max

    try:
        return _minio_client.presigned_get_object(
            bucket_name=MINIO_BUCKET_CERTIFICATES,
            object_name=object_key,
            expires=timedelta(seconds=expires_in),
        )
    except S3Error as e:
        raise RuntimeError(f"MinIO presigned_get_object failed: {e}") from e