from fastapi import APIRouter

from app.api.conversation import router as conversation_router

api_router = APIRouter()

api_router.include_router(conversation_router)
