import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from starlette.concurrency import run_in_threadpool

from app.core.config import DOCUMENT_INDEX_POLL_SECONDS, EMBEDDING_MODEL
from app.core.database import SessionLocal
from app.model.document import Document, DocumentChunk
from app.service.document import cached_document_path
from app.service.embedding import embed_texts, embedding_is_configured
from app.service.rag import PARSER_VERSION, parse_document_chunks


logger = logging.getLogger(__name__)


async def reset_interrupted_jobs() -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(Document)
            .where(Document.index_status == "processing")
            .values(index_status="pending", index_error=None)
        )


async def _claim_document() -> UUID | None:
    async with SessionLocal() as session, session.begin():
        statement = (
            select(Document)
            .where(Document.index_status == "pending")
            .order_by(Document.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        document = await session.scalar(statement)
        if document is None:
            return None
        if document.preview_kind == "image":
            document.index_status = "unsupported"
            document.index_error = "图片需要 OCR，当前版本暂未启用"
            return None
        document.index_status = "processing"
        document.index_error = None
        return document.id


async def _set_failed(document_id: UUID, error: Exception) -> None:
    logger.exception("Failed to index document %s", document_id)
    async with SessionLocal() as session, session.begin():
        document = await session.get(Document, document_id, with_for_update=True)
        if document:
            document.index_status = "failed"
            document.index_error = str(error)[:2000]


async def _process_document(document_id: UUID) -> None:
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        path = await run_in_threadpool(cached_document_path, document)
        chunks = await run_in_threadpool(parse_document_chunks, document, path)

    vectors = await embed_texts([chunk.content for chunk in chunks])
    async with SessionLocal() as session, session.begin():
        document = await session.get(Document, document_id, with_for_update=True)
        if document is None:
            return
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        session.add_all(
            [
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=index,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    character_count=len(chunk.content),
                    embedding=vector,
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors))
            ]
        )
        document.index_status = "ready"
        document.index_error = None
        document.indexed_at = datetime.now(timezone.utc)
        document.parser_version = PARSER_VERSION
        document.embedding_model = EMBEDDING_MODEL


async def indexing_worker(stop_event: asyncio.Event) -> None:
    await reset_interrupted_jobs()
    warned_missing_key = False
    while not stop_event.is_set():
        if not embedding_is_configured():
            if not warned_missing_key:
                logger.warning("Document indexing is waiting for EMBEDDING_API_KEY")
                warned_missing_key = True
        else:
            warned_missing_key = False
            document_id = await _claim_document()
            if document_id:
                try:
                    await _process_document(document_id)
                except Exception as error:
                    await _set_failed(document_id, error)
                continue
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=max(1.0, DOCUMENT_INDEX_POLL_SECONDS)
            )
        except TimeoutError:
            pass

