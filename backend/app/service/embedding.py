from typing import Sequence
from urllib.parse import urlsplit

import httpx

from app.core.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SECONDS,
)


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingServiceError(RuntimeError):
    pass


def resolve_embedding_base_url(base_url: str | None = None) -> str:
    resolved = (base_url or EMBEDDING_BASE_URL).strip().rstrip("/")
    parsed = urlsplit(resolved)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not (hostname == "aliyuncs.com" or hostname.endswith(".aliyuncs.com"))
    ):
        raise EmbeddingConfigurationError(
            "Embedding Base URL 必须是 aliyuncs.com 域名下的 HTTPS 地址"
        )
    return resolved


def embedding_is_configured(
    api_key: str | None = None, base_url: str | None = None
) -> bool:
    if not (api_key or EMBEDDING_API_KEY).strip():
        return False
    try:
        resolve_embedding_base_url(base_url)
    except EmbeddingConfigurationError:
        return False
    return True


async def embed_texts(
    texts: Sequence[str],
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    resolved_api_key = (api_key or EMBEDDING_API_KEY).strip()
    if not resolved_api_key:
        raise EmbeddingConfigurationError("尚未配置 EMBEDDING_API_KEY")

    resolved_base_url = resolve_embedding_base_url(base_url)
    vectors: list[list[float]] = []
    batch_size = max(1, EMBEDDING_BATCH_SIZE)
    url = f"{resolved_base_url}/embeddings"
    headers = {"Authorization": f"Bearer {resolved_api_key}"}

    async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT_SECONDS) as client:
        for offset in range(0, len(texts), batch_size):
            batch = list(texts[offset : offset + batch_size])
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": EMBEDDING_MODEL,
                        "input": batch,
                        "dimensions": EMBEDDING_DIMENSIONS,
                        "encoding_format": "float",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                rows = sorted(payload["data"], key=lambda item: item["index"])
                batch_vectors = [row["embedding"] for row in rows]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                detail = ""
                if isinstance(error, httpx.HTTPStatusError):
                    detail = f": {error.response.text[:500]}"
                raise EmbeddingServiceError(f"Embedding 请求失败{detail}") from error

            if len(batch_vectors) != len(batch):
                raise EmbeddingServiceError("Embedding 返回数量与输入不一致")
            if any(len(vector) != EMBEDDING_DIMENSIONS for vector in batch_vectors):
                raise EmbeddingServiceError(
                    f"Embedding 维度不是配置的 {EMBEDDING_DIMENSIONS}"
                )
            vectors.extend(batch_vectors)
    return vectors
