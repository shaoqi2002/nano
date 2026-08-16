from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException

from app.schema.account import DeepSeekBalanceResponse
from app.service.deepseek_account import DeepSeekBalanceError, fetch_deepseek_balance


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
