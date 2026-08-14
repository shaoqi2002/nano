from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
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
