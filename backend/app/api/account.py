from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException

from app.core.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from app.schema.account import (
    DeepSeekBalanceResponse,
    EmbeddingStatusResponse,
    TavilyUsageResponse,
)
from app.service.deepseek_account import DeepSeekBalanceError, fetch_deepseek_balance
from app.service.embedding import (
    EmbeddingConfigurationError,
    EmbeddingServiceError,
    embed_texts,
)
from app.service.tavily_account import TavilyUsageError, fetch_tavily_usage


router = APIRouter(prefix="/account", tags=["account"])


@router.get("/deepseek/balance", response_model=DeepSeekBalanceResponse)
async def read_deepseek_balance(
    api_key: Annotated[
        str, Header(alias="X-DeepSeek-API-Key", min_length=1)
    ],
) -> DeepSeekBalanceResponse:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            return await fetch_deepseek_balance(client, api_key)
    except DeepSeekBalanceError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.message
        ) from error


@router.get("/tavily/usage", response_model=TavilyUsageResponse)
async def read_tavily_usage(
    api_key: Annotated[str, Header(alias="X-Tavily-API-Key", min_length=1)],
) -> TavilyUsageResponse:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            return await fetch_tavily_usage(client, api_key)
    except TavilyUsageError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.message
        ) from error


@router.get("/embedding/status", response_model=EmbeddingStatusResponse)
async def read_embedding_status(
    api_key: Annotated[
        str, Header(alias="X-Embedding-API-Key", min_length=1)
    ],
) -> EmbeddingStatusResponse:
    try:
        await embed_texts(["Nano embedding configuration check"], api_key)
    except (EmbeddingConfigurationError, EmbeddingServiceError) as error:
        raise HTTPException(
            status_code=502, detail="百炼 Embedding Key 验证失败"
        ) from error
    return EmbeddingStatusResponse(
        configured=True,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )
