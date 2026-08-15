from collections.abc import Iterator
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from boto3.s3.transfer import TransferConfig

from app.core.config import (
    OBJECT_STORAGE_ACCESS_KEY_ID,
    OBJECT_STORAGE_BUCKET,
    OBJECT_STORAGE_ENDPOINT_URL,
    OBJECT_STORAGE_REGION,
    OBJECT_STORAGE_SECRET_ACCESS_KEY,
)


class ObjectStorageConfigurationError(RuntimeError):
    pass


class ObjectStorageError(RuntimeError):
    pass


UPLOAD_CONFIG = TransferConfig(max_concurrency=2, use_threads=True)


def _require_storage_config() -> None:
    values = {
        "OBJECT_STORAGE_ENDPOINT_URL": OBJECT_STORAGE_ENDPOINT_URL,
        "OBJECT_STORAGE_REGION": OBJECT_STORAGE_REGION,
        "OBJECT_STORAGE_ACCESS_KEY_ID": OBJECT_STORAGE_ACCESS_KEY_ID,
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": OBJECT_STORAGE_SECRET_ACCESS_KEY,
        "OBJECT_STORAGE_BUCKET": OBJECT_STORAGE_BUCKET,
    }
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise ObjectStorageConfigurationError(
            "对象存储尚未配置：" + ", ".join(missing)
        )


@lru_cache(maxsize=1)
def _client():
    _require_storage_config()
    return boto3.client(
        "s3",
        endpoint_url=OBJECT_STORAGE_ENDPOINT_URL,
        region_name=OBJECT_STORAGE_REGION,
        aws_access_key_id=OBJECT_STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=OBJECT_STORAGE_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )


def upload_object(
    object_key: str,
    stream: BinaryIO,
    content_type: str,
) -> None:
    try:
        _client().upload_fileobj(
            stream,
            OBJECT_STORAGE_BUCKET,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
            },
            Config=UPLOAD_CONFIG,
        )
    except (BotoCoreError, ClientError, OSError) as error:
        raise ObjectStorageError("上传到对象存储失败") from error


def delete_object(object_key: str) -> None:
    try:
        _client().delete_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError("从对象存储删除文件失败") from error


def object_stream(
    object_key: str,
    byte_range: str | None = None,
) -> tuple[Iterator[bytes], int | None, str | None]:
    try:
        arguments = {"Bucket": OBJECT_STORAGE_BUCKET, "Key": object_key}
        if byte_range:
            arguments["Range"] = byte_range
        response = _client().get_object(**arguments)
        body = response["Body"]
        content_length = response.get("ContentLength")
        content_range = response.get("ContentRange")
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError("读取对象失败") from error

    def iterator() -> Iterator[bytes]:
        try:
            for chunk in body.iter_chunks(chunk_size=256 * 1024):
                if chunk:
                    yield chunk
        finally:
            body.close()

    return iterator(), content_length, content_range


def read_object(object_key: str, maximum_bytes: int) -> bytes:
    chunks, _, _ = object_stream(object_key)
    content = bytearray()
    for chunk in chunks:
        content.extend(chunk)
        if len(content) > maximum_bytes:
            raise ObjectStorageError("文档内容超过预览大小限制")
    return bytes(content)
