from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    use_rag: bool = True


class RagSourceResponse(BaseModel):
    document_id: UUID
    document_name: str
    chunk_id: int
    page_number: int | None = None
    section_title: str | None = None
    excerpt: str
    similarity: float


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[RagSourceResponse] = Field(default_factory=list)
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class ConversationSummaryResponse(ConversationResponse):
    title: str


class SendMessageResponse(BaseModel):
    conversation_id: UUID
    assistant_message: MessageResponse


class ConversationMessagesResponse(BaseModel):
    conversation_id: UUID
    messages: list[MessageResponse]
