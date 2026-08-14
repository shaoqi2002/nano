import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, ToolException
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    AGENT_MAX_TOOL_CALLS,
    AGENT_MAX_TOOL_ROUNDS,
    CHAT_CONTEXT_MESSAGE_LIMIT,
    DEEPSEEK_MODEL,
)
from app.model.conversation import Conversation, Message
from app.repository.conversation import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_for_update,
    list_conversations,
    list_messages,
    list_recent_messages,
)
from app.tools import create_tools


logger = logging.getLogger(__name__)


class ConversationNotFoundError(Exception):
    pass


def create_model(api_key: str) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=SecretStr(api_key),
        temperature=0.7,
        max_retries=2,
    )


def _tool_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


async def _execute_tool_call(
    tool_call: dict[str, Any],
    tools_by_name: dict[str, BaseTool],
    allowed: bool,
) -> ToolMessage:
    tool_call_id = str(tool_call.get("id") or "unknown-tool-call")
    tool_name = str(tool_call.get("name") or "")

    if not allowed:
        content = "工具调用次数已达到上限，请基于已有信息回答。"
    elif tool_name not in tools_by_name:
        content = f"未知工具：{tool_name}"
    else:
        try:
            result = await tools_by_name[tool_name].ainvoke(
                tool_call.get("args") or {}
            )
            content = _tool_result_text(result)
        except ToolException as error:
            content = f"工具执行失败：{error}"
        except Exception:
            logger.exception("Unexpected failure while executing tool %s", tool_name)
            content = "工具执行时发生内部错误。"

    return ToolMessage(
        content=content,
        tool_call_id=tool_call_id,
        name=tool_name or None,
    )


async def invoke_model_with_tools(
    model: Any,
    request_tools: list[BaseTool],
    messages: list[BaseMessage],
) -> AIMessage:
    if not request_tools:
        response = await model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("模型返回了无效的消息类型")
        return response

    tool_model = model.bind_tools(request_tools)
    tools_by_name = {registered.name: registered for registered in request_tools}
    working_messages = list(messages)
    total_tool_calls = 0

    for _ in range(max(AGENT_MAX_TOOL_ROUNDS, 1)):
        response = await tool_model.ainvoke(working_messages)
        if not isinstance(response, AIMessage):
            raise TypeError("模型返回了无效的消息类型")
        if not response.tool_calls:
            return response

        working_messages.append(response)
        executions = []
        for tool_call in response.tool_calls:
            allowed = total_tool_calls < max(AGENT_MAX_TOOL_CALLS, 1)
            if allowed:
                total_tool_calls += 1
            executions.append(
                _execute_tool_call(tool_call, tools_by_name, allowed)
            )
        working_messages.extend(await asyncio.gather(*executions))

    final_response = await model.ainvoke(working_messages)
    if not isinstance(final_response, AIMessage):
        raise TypeError("模型返回了无效的消息类型")
    return final_response


def _response_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content

    text_parts: list[str] = []
    for block in message.content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
    return "\n".join(text_parts).strip()


def convert_messages(messages: list[Message]) -> list[BaseMessage]:
    converted: list[BaseMessage] = [
        SystemMessage(
            content=(
                "You are a friendly and accurate Chinese AI assistant named Nano. "
                "Use web_search for current facts, quick lookups, and targeted source discovery. "
                "After web_search, use web_extract on 2 to 5 promising, independent URLs when "
                "the answer needs source details or verification beyond search snippets. If the "
                "user already provides URLs, web_extract may be used directly. If extraction is "
                "insufficient, refine web_search and extract better sources. "
                "Use deep_research for explicit in-depth research, multi-angle comparisons, "
                "due diligence, literature reviews, or questions requiring multiple searches "
                "and cross-checking. Do not use deep_research for a simple factual lookup. "
                "If deep_research fails, fall back to focused web_search and web_extract calls. "
                "Base claims on returned sources and preserve their URLs in the answer."
            )
        )
    ]

    for message in messages:
        if message.role == "user":
            converted.append(HumanMessage(content=message.content))
        else:
            converted.append(AIMessage(content=message.content))

    return converted


async def create_new_conversation(session: AsyncSession) -> Conversation:
    async with session.begin():
        return await create_conversation(session)


async def get_conversations(
    session: AsyncSession,
) -> list[tuple[Conversation, str]]:
    rows = await list_conversations(session)
    return [
        (conversation, title or "New conversation")
        for conversation, title in rows
    ]


async def get_conversation_messages(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    conversation = await get_conversation(session, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError

    return await list_messages(session, conversation_id)


async def delete_existing_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> None:
    async with session.begin():
        conversation = await get_conversation_for_update(session, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError

        await delete_conversation(session, conversation)


async def send_message(
    session: AsyncSession,
    conversation_id: UUID,
    content: str,
    api_key: str,
    tavily_api_key: str | None = None,
) -> Message:
    async with session.begin():
        conversation = await get_conversation_for_update(session, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError

        history = await list_recent_messages(
            session,
            conversation_id,
            CHAT_CONTEXT_MESSAGE_LIMIT,
        )
        await add_message(session, conversation_id, "user", content)

    model_messages = convert_messages(history)
    model_messages.append(HumanMessage(content=content))
    request_tools = create_tools(tavily_api_key)
    model_response = await invoke_model_with_tools(
        create_model(api_key),
        request_tools,
        model_messages,
    )
    response_text = _response_text(model_response)
    if not response_text:
        response_text = "模型未生成可显示的回答，请重试。"

    async with session.begin():
        conversation = await get_conversation_for_update(session, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError

        return await add_message(
            session,
            conversation_id,
            "assistant",
            response_text,
        )
