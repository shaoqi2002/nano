import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api import api_router
from app.core.database import close_database, create_tables
from app.service.document_indexer import indexing_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    stop_event = asyncio.Event()
    worker = asyncio.create_task(indexing_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await close_database()


app = FastAPI(title="Agent API", lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
