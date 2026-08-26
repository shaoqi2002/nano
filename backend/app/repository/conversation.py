from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.conversation import Conversation, Message


async def create_conversation(session: AsyncSession) -> Conversation:
    conversation = Conversation()
    session.add(conversation)
    await session.flush()
    return conversation


async def get_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def list_conversations(
    session: AsyncSession,
) -> list[tuple[Conversation, str | None]]:
    first_user_message = (
        select(Message.content)
        .where(
            Message.conversation_id == Conversation.id,
            Message.role == "user",
        )
        .order_by(Message.id)
        .limit(1)
        .scalar_subquery()
    )
    statement = (
        select(Conversation, first_user_message.label("title"))
        .order_by(Conversation.created_at.desc())
    )
    result = await session.execute(statement)
    return [(row.Conversation, row.title) for row in result]


async def get_conversation_for_update(
    session: AsyncSession,
    conversation_id: UUID,
) -> Conversation | None:
    statement = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .with_for_update()
    )
    return await session.scalar(statement)


async def delete_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> None:
    await session.delete(conversation)


async def list_messages(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id)
    )
    result = await session.scalars(statement)
    return list(result)


async def list_recent_messages(
    session: AsyncSession,
    conversation_id: UUID,
    limit: int,
) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    result = list(await session.scalars(statement))
    result.reverse()
    return result


async def add_message(
    session: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    sources: list[dict] | None = None,
    options: dict | None = None,
    attachments: list[dict] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources or [],
        options=options or {},
        attachments=attachments or [],
    )
    session.add(message)
    await session.flush()
    return message
