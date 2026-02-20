import os
from minio import Minio
from minio.error import S3Error


def get_minio() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "")
    secret_key = os.getenv("MINIO_SECRET_KEY", "")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def ensure_bucket(minio: Minio, bucket: str) -> None:
    found = minio.bucket_exists(bucket)
    if not found:
        minio.make_bucket(bucket)