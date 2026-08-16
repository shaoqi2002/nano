from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException

from app.schema.account import DeepSeekBalanceResponse, TavilyUsageResponse
from app.service.deepseek_account import DeepSeekBalanceError, fetch_deepseek_balance
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
