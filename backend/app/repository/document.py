from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.document import Document


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.scalars(
        select(Document).order_by(Document.created_at.desc())
    )
    return list(result)


async def get_document(
    session: AsyncSession,
    document_id: UUID,
) -> Document | None:
    return await session.get(Document, document_id)


async def add_document(session: AsyncSession, document: Document) -> Document:
    session.add(document)
    await session.flush()
    await session.refresh(document)
    return document


async def remove_document(session: AsyncSession, document: Document) -> None:
    await session.delete(document)
