import json
from typing import Annotated, Any, Literal

import httpx
from langchain_core.tools import ToolException, tool

from app.core.config import WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_TIMEOUT_SECONDS


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
MAX_QUERY_LENGTH = 500
BASIC_MAX_SNIPPET_LENGTH = 1_000
ADVANCED_MAX_SNIPPET_LENGTH = 1_800


def _validated_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ToolException("搜索关键词不能为空")
    if len(normalized) > MAX_QUERY_LENGTH:
        raise ToolException(
            f"搜索关键词不能超过 {MAX_QUERY_LENGTH} 个字符"
        )
    return normalized


def _normalize_result(
    item: Any,
    max_snippet_length: int,
) -> dict[str, str | float]:
    if not isinstance(item, dict):
        return {}

    normalized: dict[str, str | float] = {
        "title": str(item.get("title") or ""),
        "url": str(item.get("url") or ""),
        "snippet": str(item.get("content") or "")[:max_snippet_length],
    }

    score = item.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        normalized["score"] = float(score)

    published_date = item.get("published_date")
    if isinstance(published_date, str) and published_date:
        normalized["published_date"] = published_date

    return normalized


async def _search_tavily(
    query: str,
    api_key: str,
    client: httpx.AsyncClient,
    depth: Literal["basic", "advanced"] = "basic",
    topic: Literal["general", "news", "finance"] = "general",
    time_range: Literal["day", "week", "month", "year"] | None = None,
) -> dict[str, Any]:
    max_results = min(max(WEB_SEARCH_MAX_RESULTS, 1), 10)
    max_snippet_length = (
        ADVANCED_MAX_SNIPPET_LENGTH
        if depth == "advanced"
        else BASIC_MAX_SNIPPET_LENGTH
    )
    request_body: dict[str, Any] = {
        "query": query,
        "search_depth": depth,
        "chunks_per_source": 3 if depth == "advanced" else 2,
        "max_results": max_results,
        "topic": topic,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    if time_range is not None:
        request_body["time_range"] = time_range

    try:
        response = await client.post(
            TAVILY_SEARCH_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
    except httpx.TimeoutException as error:
        raise ToolException("网页搜索超时") from error
    except httpx.HTTPStatusError as error:
        raise ToolException(
            f"搜索服务返回 HTTP {error.response.status_code}"
        ) from error
    except httpx.RequestError as error:
        raise ToolException("无法连接网页搜索服务") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ToolException("搜索服务返回了无法解析的数据") from error

    if not isinstance(payload, dict):
        raise ToolException("搜索服务返回了无效的数据格式")

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raise ToolException("搜索服务返回了无效的结果列表")

    results = [
        normalized
        for item in raw_results[:max_results]
        if (normalized := _normalize_result(item, max_snippet_length))
    ]
    return {
        "query": query,
        "search_depth": depth,
        "topic": topic,
        "time_range": time_range,
        "results": results,
    }


def create_web_search_tool(api_key: str):
    request_api_key = api_key.strip()
    if not request_api_key:
        raise ValueError("Tavily API Key 不能为空")

    @tool
    async def web_search(
        query: Annotated[
            str,
            "具体的搜索关键词，应包含要查询的主体、主题和必要的时间信息",
        ],
        depth: Annotated[
            Literal["basic", "advanced"],
            "basic 用于普通查询；advanced 用于复杂、精确或多来源查询",
        ] = "basic",
        topic: Annotated[
            Literal["general", "news", "finance"],
            "搜索类别：普通信息、新闻或金融信息",
        ] = "general",
        time_range: Annotated[
            Literal["day", "week", "month", "year"] | None,
            "可选的发布时间范围过滤",
        ] = None,
    ) -> str:
        """搜索互联网中的最新公开信息。

        当问题涉及近期事件、新闻、价格、版本变化，或者现有知识不足时使用。
        query 应当包含主体和需要查询的具体信息；必要时使用中英文关键词。
        返回搜索结果的标题、URL、摘要、相关性分数和可用的发布日期。
        """
        normalized_query = _validated_query(query)
        timeout = httpx.Timeout(max(WEB_SEARCH_TIMEOUT_SECONDS, 1.0))
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            result = await _search_tavily(
                normalized_query,
                request_api_key,
                client,
                depth,
                topic,
                time_range,
            )

        if not result["results"]:
            result["message"] = "没有找到相关结果"
        return json.dumps(result, ensure_ascii=False)

    return web_search
