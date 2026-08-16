import httpx
from pydantic import ValidationError

from app.schema.account import DeepSeekBalanceResponse


DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"


class DeepSeekBalanceError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def fetch_deepseek_balance(
    client: httpx.AsyncClient, api_key: str
) -> DeepSeekBalanceResponse:
    try:
        response = await client.get(
            DEEPSEEK_BALANCE_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
    except httpx.RequestError as error:
        raise DeepSeekBalanceError(502, "无法连接 DeepSeek 余额服务") from error

    if response.status_code == 401:
        raise DeepSeekBalanceError(401, "DeepSeek API Key 无效")
    if response.status_code == 429:
        raise DeepSeekBalanceError(429, "DeepSeek 请求过于频繁，请稍后重试")
    if response.status_code != 200:
        raise DeepSeekBalanceError(502, "DeepSeek 余额查询失败")
    try:
        return DeepSeekBalanceResponse.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise DeepSeekBalanceError(502, "DeepSeek 返回了无效的余额数据") from error
