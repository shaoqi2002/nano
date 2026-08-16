from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.agent_run import AgentRun, AgentRunEvent


async def create_agent_run(
    session: AsyncSession,
    conversation_id: UUID,
    user_message_id: int,
    query: str,
    mode: str,
) -> AgentRun:
    run = AgentRun(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        query=query,
        mode=mode,
        status="pending",
    )
    session.add(run)
    await session.flush()
    return run


async def get_agent_run(session: AsyncSession, run_id: UUID) -> AgentRun | None:
    return await session.get(AgentRun, run_id)


async def get_agent_run_for_update(
    session: AsyncSession, run_id: UUID
) -> AgentRun | None:
    return await session.get(AgentRun, run_id, with_for_update=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def add_agent_run_event(
    session: AsyncSession,
    run_id: UUID,
    event_type: str,
    *,
    node: str | None = None,
    tool_name: str | None = None,
    duration_ms: int | None = None,
    payload: dict | None = None,
) -> AgentRunEvent:
    event = AgentRunEvent(
        run_id=run_id,
        event_type=event_type,
        node=node,
        tool_name=tool_name,
        duration_ms=duration_ms,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
    return event


async def list_agent_run_events(
    session: AsyncSession, run_id: UUID
) -> list[AgentRunEvent]:
    statement = (
        select(AgentRunEvent)
        .where(AgentRunEvent.run_id == run_id)
        .order_by(AgentRunEvent.id)
    )
    return list(await session.scalars(statement))


async def get_run_ids_by_assistant_message_ids(
    session: AsyncSession, message_ids: list[int]
) -> dict[int, UUID]:
    if not message_ids:
        return {}
    statement = select(AgentRun.assistant_message_id, AgentRun.id).where(
        AgentRun.assistant_message_id.in_(message_ids)
    )
    rows = (await session.execute(statement)).all()
    return {
        int(message_id): run_id
        for message_id, run_id in rows
        if message_id is not None
    }
