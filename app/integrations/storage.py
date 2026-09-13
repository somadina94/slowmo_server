from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.exceptions import ValidationAppError

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}
MAX_BYTES = 10 * 1024 * 1024
RX_PREFIX = "rx/"


class StorageError(Exception):
    pass


def safe_download_name(filename: str) -> str:
    """ASCII-only name for Content-Disposition (HTTP headers are latin-1)."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 and ch not in {"/", "\\", '"'} else "_" for ch in filename).strip("._ ")
    return cleaned or "prescription"


def content_disposition(filename: str) -> str:
    return f'inline; filename="{safe_download_name(filename)}"'


def normalize_b2_endpoint(endpoint: str) -> str:
    value = (endpoint or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


class FileStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path(settings.storage_dir)
        if settings.storage_backend == "local":
            self.root.mkdir(parents=True, exist_ok=True)
        self._client: BaseClient | None = None

    def validate(self, filename: str, mime: str, size: int) -> tuple[str, str]:
        if size > MAX_BYTES:
            raise ValidationAppError("File exceeds 10 MB")
        ext = ALLOWED_MIME.get(mime)
        if ext is None:
            raise ValidationAppError("Only PDF, JPG or PNG are allowed")
        safe = safe_download_name(filename.replace("/", "_").replace("\\", "_"))
        return f"{uuid4().hex}{ext}", safe

    def object_key(self, stored_name: str) -> str:
        name = stored_name.lstrip("/")
        if name.startswith(RX_PREFIX):
            return name
        return f"{RX_PREFIX}{name}"

    def _b2_client(self) -> BaseClient:
        if self._client is not None:
            return self._client
        if not self.settings.b2_bucket_name:
            raise StorageError("B2 bucket is not configured")
        if not self.settings.b2_application_key_id or not self.settings.b2_application_key:
            raise StorageError("B2 credentials are not configured")
        endpoint = normalize_b2_endpoint(self.settings.b2_endpoint)
        if not endpoint:
            raise StorageError("B2 endpoint is not configured")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self.settings.b2_application_key_id,
            aws_secret_access_key=self.settings.b2_application_key,
            region_name=self.settings.b2_bucket_region or "us-east-005",
        )
        return self._client

    def save_local(self, stored_name: str, data: bytes) -> str:
        path = self.root / stored_name
        path.write_bytes(data)
        return stored_name

    def save_b2(self, stored_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        key = self.object_key(stored_name)
        try:
            self._b2_client().put_object(
                Bucket=self.settings.b2_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("failed to upload file to B2") from exc
        return key

    def save(self, stored_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if self.settings.storage_backend == "b2":
            return self.save_b2(stored_name, data, content_type=content_type)
        return self.save_local(stored_name, data)

    def read_local(self, stored_name: str) -> bytes:
        path = self.root / stored_name
        if not path.exists():
            raise StorageError("file missing")
        return path.read_bytes()

    def read_b2(self, stored_name: str) -> bytes:
        key = self.object_key(stored_name)
        try:
            response = self._b2_client().get_object(Bucket=self.settings.b2_bucket_name, Key=key)
            body = response["Body"].read()
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise StorageError("file missing") from exc
        return body

    def read(self, stored_name: str) -> bytes:
        if self.settings.storage_backend == "b2":
            return self.read_b2(stored_name)
        return self.read_local(stored_name)

    def public_url(self, stored_name: str) -> str:
        key = self.object_key(stored_name)
        base = (self.settings.b2_public_file_base_url or "").rstrip("/")
        if base:
            return f"{base}/{key}"
        endpoint = normalize_b2_endpoint(self.settings.b2_endpoint).rstrip("/")
        bucket = self.settings.b2_bucket_name
        if endpoint and bucket:
            return f"{endpoint}/{bucket}/{key}"
        return key
