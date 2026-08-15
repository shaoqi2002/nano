from fastapi import APIRouter

from app.api.conversation import router as conversation_router
from app.api.document import router as document_router

api_router = APIRouter()

api_router.include_router(conversation_router)
api_router.include_router(document_router)
