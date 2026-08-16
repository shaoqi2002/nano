from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    use_rag: bool = True
    mode: Literal["auto", "chat", "research"] = "auto"
    allow_write_tools: bool = False


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
    run_id: UUID | None = None


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


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    mode: str
    status: str
    query: str
    current_node: str | None
    plan: list[dict] = Field(default_factory=list)
    progress: list[dict] = Field(default_factory=list)
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    tool_call_count: int
    tool_failure_count: int


class AgentRunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    event_type: str
    node: str | None
    tool_name: str | None
    duration_ms: int | None
    payload: dict = Field(default_factory=dict)
    created_at: datetime
