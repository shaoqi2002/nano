from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.core.database import close_database, create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    await close_database()


app = FastAPI(title="Agent API", lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
