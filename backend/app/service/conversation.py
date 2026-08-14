from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
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


class ConversationNotFoundError(Exception):
    pass


def create_model(api_key: str) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=SecretStr(api_key),
        temperature=0.7,
        max_retries=2,
    )


def convert_messages(messages: list[Message]) -> list[BaseMessage]:
    converted: list[BaseMessage] = [
        SystemMessage(content="You are a friendly and accurate Chinese AI assistant.")
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
    model_response = await create_model(api_key).ainvoke(model_messages)

    if isinstance(model_response.content, str):
        response_text = model_response.content
    else:
        response_text = str(model_response.content)

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
