from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.model.agent_run import AgentRun


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

