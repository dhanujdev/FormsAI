"""Object storage abstraction for housing grant documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


@dataclass
class PresignedUpload:
    object_key: str
    upload_url: str
    required_headers: dict[str, str]
    expires_at: datetime


class S3StorageClient:
    def __init__(self) -> None:
        cfg = Config(s3={"addressing_style": "path" if settings.HOUSING_S3_FORCE_PATH_STYLE else "virtual"})
        self._client = boto3.client(
            "s3",
            region_name=settings.HOUSING_S3_REGION,
            endpoint_url=settings.HOUSING_S3_ENDPOINT_URL,
            config=cfg,
        )
        self._bucket = settings.HOUSING_S3_BUCKET

    @property
    def bucket(self) -> str:
        return self._bucket

    def create_presigned_upload(self, *, object_key: str, content_type: str) -> PresignedUpload:
        expires = settings.HOUSING_S3_UPLOAD_EXPIRES_SECONDS
        try:
            upload_url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires,
                HttpMethod="PUT",
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed generating upload URL: {exc}") from exc

        return PresignedUpload(
            object_key=object_key,
            upload_url=upload_url,
            required_headers={"Content-Type": content_type},
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )

    def head_object(self, *, object_key: str) -> dict[str, object]:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed reading uploaded object metadata: {exc}") from exc
        return cast(dict[str, object], response)

    def get_object_bytes(self, *, object_key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
            body_obj = cast(Any, response["Body"])
            body = cast(bytes, body_obj.read())
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"failed downloading object: {exc}") from exc
        return body

    def delete_object(self, *, object_key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Object deletion failed for %s: %s", object_key, exc)


def get_storage_client() -> S3StorageClient:
    if settings.HOUSING_STORAGE_PROVIDER != "s3":
        raise StorageError(f"unsupported storage provider: {settings.HOUSING_STORAGE_PROVIDER}")
    return S3StorageClient()
