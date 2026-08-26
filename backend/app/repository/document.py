from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.document import Document
from app.service.workspace import current_workspace_id


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.scalars(
        select(Document)
        .where(Document.workspace_id == current_workspace_id(session))
        .order_by(Document.created_at.desc())
    )
    return list(result)


async def get_document(
    session: AsyncSession,
    document_id: UUID,
) -> Document | None:
    return await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == current_workspace_id(session),
        )
    )


async def add_document(session: AsyncSession, document: Document) -> Document:
    document.workspace_id = current_workspace_id(session)
    session.add(document)
    await session.flush()
    await session.refresh(document)
    return document


async def remove_document(session: AsyncSession, document: Document) -> None:
    await session.delete(document)
