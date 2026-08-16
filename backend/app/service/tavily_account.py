import httpx
from pydantic import ValidationError

from app.schema.account import TavilyUsageResponse


TAVILY_USAGE_URL = "https://api.tavily.com/usage"


class TavilyUsageError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def fetch_tavily_usage(
    client: httpx.AsyncClient, api_key: str
) -> TavilyUsageResponse:
    try:
        response = await client.get(
            TAVILY_USAGE_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
    except httpx.RequestError as error:
        raise TavilyUsageError(502, "无法连接 Tavily 用量服务") from error
    if response.status_code == 401:
        raise TavilyUsageError(401, "Tavily API Key 无效")
    if response.status_code == 429:
        raise TavilyUsageError(429, "Tavily 请求过于频繁，请稍后重试")
    if response.status_code != 200:
        raise TavilyUsageError(502, "Tavily 用量查询失败")
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("key"), dict):
            raise ValueError("Tavily usage response is missing key usage")
        if not isinstance(payload.get("account"), dict):
            payload["account"] = {}
        return TavilyUsageResponse.model_validate(payload)
    except (ValueError, ValidationError) as error:
        raise TavilyUsageError(502, "Tavily 返回了无效的用量数据") from error
