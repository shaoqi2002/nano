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


class DocumentIndexRequests:
    """Keep per-document browser keys in memory without persisting secrets."""

    def __init__(self) -> None:
        self._keys: dict[UUID, str] = {}

    def submit(self, document_id: UUID, api_key: str | None) -> None:
        if api_key and api_key.strip():
            self._keys[document_id] = api_key.strip()

    def take(self) -> tuple[UUID, str] | None:
        if not self._keys:
            return None
        document_id = next(iter(self._keys))
        return document_id, self._keys.pop(document_id)


async def reset_interrupted_jobs() -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(Document)
            .where(Document.index_status == "processing")
            .values(index_status="pending", index_error=None)
        )


async def _claim_document(document_id: UUID | None = None) -> UUID | None:
    async with SessionLocal() as session, session.begin():
        statement = select(Document).where(Document.index_status == "pending")
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        statement = (
            statement.order_by(Document.created_at)
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


async def _process_document(
    document_id: UUID, api_key: str | None = None
) -> None:
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        path = await run_in_threadpool(cached_document_path, document)
        chunks = await run_in_threadpool(parse_document_chunks, document, path)

    vectors = await embed_texts([chunk.content for chunk in chunks], api_key)
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


async def indexing_worker(
    stop_event: asyncio.Event,
    requests: DocumentIndexRequests | None = None,
) -> None:
    await reset_interrupted_jobs()
    requests = requests or DocumentIndexRequests()
    warned_missing_key = False
    while not stop_event.is_set():
        submitted = requests.take()
        if submitted:
            requested_id, requested_key = submitted
            document_id = await _claim_document(requested_id)
            if document_id:
                try:
                    await _process_document(document_id, requested_key)
                except Exception as error:
                    await _set_failed(document_id, error)
                continue
        elif not embedding_is_configured():
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
