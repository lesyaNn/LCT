"""File storage: MinIO/S3 in prod, local ./var/files fallback for demo."""
import logging
import os
import uuid

from app.config import settings

logger = logging.getLogger("rtk")

LOCAL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "var", "files")
os.makedirs(LOCAL_DIR, exist_ok=True)


def save_file(filename: str, content: bytes) -> str:
    """Return storage_key."""
    try:
        from minio import Minio
        from urllib.parse import urlparse

        u = urlparse(settings.s3_endpoint)
        client = Minio(
            u.netloc, access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key, secure=u.scheme == "https",
        )
        if not client.bucket_exists(settings.s3_bucket):
            client.make_bucket(settings.s3_bucket)
        key = f"{uuid.uuid4().hex}/{filename}"
        import io
        client.put_object(settings.s3_bucket, key, io.BytesIO(content), len(content))
        return f"s3://{settings.s3_bucket}/{key}"
    except Exception:
        logger.warning(
            "minio unavailable at %s — storing %s locally (node-local, not shared)",
            settings.s3_endpoint, filename,
        )
        key = f"{uuid.uuid4().hex}_{filename}"
        with open(os.path.join(LOCAL_DIR, key), "wb") as f:
            f.write(content)
        return key


def read_file(storage_key: str) -> bytes | None:
    if storage_key.startswith("s3://"):
        return None  # presigned URL flow in prod; worker resolves via minio
    path = os.path.join(LOCAL_DIR, storage_key)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None
