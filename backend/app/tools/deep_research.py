import asyncio
import json
import time
from typing import Annotated, Any, Literal

import httpx
from langchain_core.tools import ToolException, tool

from app.core.config import (
    DEEP_RESEARCH_MAX_CONTENT_LENGTH,
    DEEP_RESEARCH_POLL_INTERVAL_SECONDS,
    DEEP_RESEARCH_TIMEOUT_SECONDS,
)


TAVILY_RESEARCH_URL = "https://api.tavily.com/research"
MAX_RESEARCH_INPUT_LENGTH = 2_000


def _validated_input(research_input: str) -> str:
    normalized = research_input.strip()
    if not normalized:
        raise ToolException("研究问题不能为空")
    if len(normalized) > MAX_RESEARCH_INPUT_LENGTH:
        raise ToolException(
            f"研究问题不能超过 {MAX_RESEARCH_INPUT_LENGTH} 个字符"
        )
    return normalized


def _authorization_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    api_key: str,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        response = await client.request(
            method,
            url,
            headers=_authorization_headers(api_key),
            **kwargs,
        )
        response.raise_for_status()
    except httpx.TimeoutException as error:
        raise ToolException("深度研究服务请求超时") from error
    except httpx.HTTPStatusError as error:
        raise ToolException(
            f"深度研究服务返回 HTTP {error.response.status_code}"
        ) from error
    except httpx.RequestError as error:
        raise ToolException("无法连接深度研究服务") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ToolException("深度研究服务返回了无法解析的数据") from error
    if not isinstance(payload, dict):
        raise ToolException("深度研究服务返回了无效的数据格式")
    return payload


def _normalize_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    sources: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        source = {
            "title": str(item.get("title") or ""),
            "url": url,
        }
        sources.append(source)
    return sources


def _completed_result(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content", "")
    if isinstance(content, str):
        content = content[: max(DEEP_RESEARCH_MAX_CONTENT_LENGTH, 1)]
    elif not isinstance(content, (dict, list)):
        content = str(content)

    return {
        "status": "completed",
        "request_id": str(payload.get("request_id") or ""),
        "content": content,
        "sources": _normalize_sources(payload.get("sources")),
    }


async def _research_tavily(
    research_input: str,
    api_key: str,
    client: httpx.AsyncClient,
    model: Literal["auto", "mini", "pro"] = "auto",
) -> dict[str, Any]:
    task = await _request_json(
        client,
        "POST",
        TAVILY_RESEARCH_URL,
        api_key,
        json={
            "input": research_input,
            "model": model,
            "stream": False,
            "citation_format": "numbered",
        },
    )
    request_id = str(task.get("request_id") or "").strip()
    if not request_id:
        raise ToolException("深度研究服务没有返回任务 ID")

    deadline = time.monotonic() + max(DEEP_RESEARCH_TIMEOUT_SECONDS, 1.0)
    payload = task
    while True:
        status = str(payload.get("status") or "").lower()
        if status == "completed":
            return _completed_result(payload)
        if status == "failed":
            detail = str(payload.get("error") or payload.get("message") or "未知原因")
            raise ToolException(f"深度研究任务失败：{detail}")
        if time.monotonic() >= deadline:
            raise ToolException(
                f"深度研究任务在 {DEEP_RESEARCH_TIMEOUT_SECONDS:g} 秒内未完成"
            )

        await asyncio.sleep(max(DEEP_RESEARCH_POLL_INTERVAL_SECONDS, 0.1))
        payload = await _request_json(
            client,
            "GET",
            f"{TAVILY_RESEARCH_URL}/{request_id}",
            api_key,
        )


def create_deep_research_tool(api_key: str):
    request_api_key = api_key.strip()
    if not request_api_key:
        raise ValueError("Tavily API Key 不能为空")

    @tool
    async def deep_research(
        research_input: Annotated[
            str,
            "完整、明确的研究任务，应包含范围、时间、需要比较的维度和期望产出",
        ],
        model: Annotated[
            Literal["auto", "mini", "pro"],
            "auto 自动选择；mini 适合目标明确的研究；pro 适合跨主题、多角度的复杂研究",
        ] = "auto",
    ) -> str:
        """对复杂主题进行多来源深度研究，并返回带引用的综合报告。

        仅在用户要求深入调研、竞品或方案比较、趋势分析、尽调、文献综述，
        或问题需要多轮搜索与交叉验证时使用。简单事实和最新消息应使用 web_search。
        深度研究通常需要几十秒，并比普通搜索消耗更多 Tavily 配额。
        """
        normalized_input = _validated_input(research_input)
        per_request_timeout = httpx.Timeout(
            min(max(DEEP_RESEARCH_TIMEOUT_SECONDS, 10.0), 60.0)
        )
        async with httpx.AsyncClient(
            timeout=per_request_timeout,
            follow_redirects=False,
        ) as client:
            result = await _research_tavily(
                normalized_input,
                request_api_key,
                client,
                model,
            )
        return json.dumps(result, ensure_ascii=False)

    return deep_research

