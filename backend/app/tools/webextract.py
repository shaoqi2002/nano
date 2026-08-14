import ipaddress
import json
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from langchain_core.tools import ToolException, tool

from app.core.config import (
    WEB_EXTRACT_MAX_CONTENT_LENGTH,
    WEB_EXTRACT_MAX_URLS,
    WEB_EXTRACT_TIMEOUT_SECONDS,
)


TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
MAX_URL_LENGTH = 2_048
MAX_EXTRACT_QUERY_LENGTH = 500


def _validated_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ToolException("提取目标不能为空")
    if len(normalized) > MAX_EXTRACT_QUERY_LENGTH:
        raise ToolException(
            f"提取目标不能超过 {MAX_EXTRACT_QUERY_LENGTH} 个字符"
        )
    return normalized


def _validated_urls(urls: list[str]) -> list[str]:
    if not urls:
        raise ToolException("至少需要提供一个 URL")

    max_urls = min(max(WEB_EXTRACT_MAX_URLS, 1), 20)
    if len(urls) > max_urls:
        raise ToolException(f"一次最多提取 {max_urls} 个 URL")

    normalized_urls: list[str] = []
    seen: set[str] = set()
    for value in urls:
        normalized = value.strip()
        if not normalized or len(normalized) > MAX_URL_LENGTH:
            raise ToolException("URL 为空或长度超出限制")

        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ToolException(f"只支持公开的 HTTP(S) URL：{normalized}")
        if parsed.username or parsed.password:
            raise ToolException(f"URL 不能包含登录凭据：{normalized}")

        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ToolException(f"不支持本地或私有地址：{normalized}")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ToolException(f"不支持本地或私有地址：{normalized}")

        if normalized not in seen:
            normalized_urls.append(normalized)
            seen.add(normalized)

    return normalized_urls


def _normalize_failed_results(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    failures: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        failures.append(
            {
                "url": url,
                "error": str(item.get("error") or item.get("message") or "提取失败"),
            }
        )
    return failures


def _normalize_results(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ToolException("网页提取服务返回了无效的结果列表")

    candidates = [item for item in value if isinstance(item, dict)]
    remaining = max(WEB_EXTRACT_MAX_CONTENT_LENGTH, 1)
    results: list[dict[str, str]] = []
    for index, item in enumerate(candidates):
        url = str(item.get("url") or "").strip()
        if not url:
            continue

        remaining_sources = max(len(candidates) - index, 1)
        allowance = max(remaining // remaining_sources, 1) if remaining else 0
        content = str(item.get("raw_content") or "")[:allowance]
        remaining = max(remaining - len(content), 0)
        results.append({"url": url, "content": content})

    return results


async def _extract_tavily(
    urls: list[str],
    query: str,
    api_key: str,
    client: httpx.AsyncClient,
    depth: Literal["basic", "advanced"] = "advanced",
) -> dict[str, Any]:
    request_body = {
        "urls": urls,
        "query": query,
        "chunks_per_source": 5 if depth == "advanced" else 3,
        "extract_depth": depth,
        "include_images": False,
        "format": "markdown",
        "timeout": min(max(WEB_EXTRACT_TIMEOUT_SECONDS, 1.0), 60.0),
    }
    try:
        response = await client.post(
            TAVILY_EXTRACT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
    except httpx.TimeoutException as error:
        raise ToolException("网页原文提取超时") from error
    except httpx.HTTPStatusError as error:
        raise ToolException(
            f"网页提取服务返回 HTTP {error.response.status_code}"
        ) from error
    except httpx.RequestError as error:
        raise ToolException("无法连接网页提取服务") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ToolException("网页提取服务返回了无法解析的数据") from error
    if not isinstance(payload, dict):
        raise ToolException("网页提取服务返回了无效的数据格式")

    return {
        "query": query,
        "extract_depth": depth,
        "results": _normalize_results(payload.get("results", [])),
        "failed_results": _normalize_failed_results(payload.get("failed_results")),
    }


def create_web_extract_tool(api_key: str):
    request_api_key = api_key.strip()
    if not request_api_key:
        raise ValueError("Tavily API Key 不能为空")

    @tool
    async def web_extract(
        urls: Annotated[
            list[str],
            "需要读取原文的 1 至 5 个公开网页 URL，优先选择权威且相互独立的来源",
        ],
        query: Annotated[
            str,
            "希望从这些网页核实或提取的具体信息，用于筛选最相关的原文片段",
        ],
        depth: Annotated[
            Literal["basic", "advanced"],
            "basic 适合普通文章；advanced 适合表格、复杂页面或需要更高提取成功率的来源",
        ] = "advanced",
    ) -> str:
        """读取指定网页的相关原文片段，用于核实搜索摘要和支撑引用。

        通常先用 web_search 发现来源，再选择 2 至 5 个可靠 URL 调用本工具。
        如果用户已经提供 URL，可以直接使用。返回内容不足时应补充搜索或更换来源，
        最终回答必须引用实际使用的 URL。不要用本工具代替广泛的网页搜索。
        """
        normalized_urls = _validated_urls(urls)
        normalized_query = _validated_query(query)
        timeout = httpx.Timeout(max(WEB_EXTRACT_TIMEOUT_SECONDS, 1.0))
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            result = await _extract_tavily(
                normalized_urls,
                normalized_query,
                request_api_key,
                client,
                depth,
            )

        if not result["results"]:
            result["message"] = "没有提取到可用的网页内容"
        return json.dumps(result, ensure_ascii=False)

    return web_extract
