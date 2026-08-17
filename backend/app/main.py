import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.api import api_router
from app.core.config import LANGGRAPH_DATABASE_URL, LANGGRAPH_POOL_SIZE
from app.core.database import close_database, create_tables
from app.service.document_indexer import DocumentIndexRequests, indexing_worker
from app.tools.local_read import ensure_workspace_directory


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_workspace_directory()
    await create_tables()
    checkpointer_pool = AsyncConnectionPool(
        conninfo=LANGGRAPH_DATABASE_URL,
        min_size=1,
        max_size=max(2, LANGGRAPH_POOL_SIZE),
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await checkpointer_pool.open()
    checkpointer = AsyncPostgresSaver(checkpointer_pool)
    await checkpointer.setup()
    app.state.agent_checkpointer = checkpointer
    document_index_requests = DocumentIndexRequests()
    app.state.document_index_requests = document_index_requests
    stop_event = asyncio.Event()
    worker = asyncio.create_task(
        indexing_worker(stop_event, document_index_requests)
    )
    try:
        yield
    finally:
        stop_event.set()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await checkpointer_pool.close()
        await close_database()


app = FastAPI(title="Agent API", lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
