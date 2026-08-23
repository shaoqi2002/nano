from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.job_application import JobApplication


async def list_job_applications(session: AsyncSession) -> list[JobApplication]:
    statement = (
        select(JobApplication)
        .options(selectinload(JobApplication.events))
        .order_by(JobApplication.updated_at.desc())
    )
    return list(await session.scalars(statement))


async def get_job_application(
    session: AsyncSession, application_id: UUID
) -> JobApplication | None:
    statement = (
        select(JobApplication)
        .options(selectinload(JobApplication.events))
        .where(JobApplication.id == application_id)
    )
    return await session.scalar(statement)
