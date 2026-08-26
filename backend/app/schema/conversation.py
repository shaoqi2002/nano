import base64
import binascii
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatAttachment(BaseModel):
    kind: Literal["text", "image", "document"]
    name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    content: str | None = Field(default=None, max_length=500_000)
    data: str | None = Field(default=None, max_length=14_000_000)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.kind == "text" and self.content is None:
            raise ValueError("Text attachments require content")
        if self.kind == "image" and self.data is None:
            raise ValueError("Image attachments require base64 data")
        if self.kind == "document" and self.data is None:
            raise ValueError("Document attachments require base64 data")
        if self.kind == "image":
            if self.media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                raise ValueError("Unsupported image type")
            try:
                decoded = base64.b64decode(self.data or "", validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("Invalid image data") from error
            signatures = {
                "image/png": decoded.startswith(b"\x89PNG\r\n\x1a\n"),
                "image/jpeg": decoded.startswith(b"\xff\xd8\xff"),
                "image/gif": decoded.startswith((b"GIF87a", b"GIF89a")),
                "image/webp": (
                    len(decoded) >= 12
                    and decoded.startswith(b"RIFF")
                    and decoded[8:12] == b"WEBP"
                ),
            }
            if not signatures[self.media_type]:
                raise ValueError("Image content does not match its media type")
            if len(decoded) > 5 * 1024 * 1024:
                raise ValueError("Images must not exceed 5 MB")
        if self.kind == "document":
            allowed = {
                "application/pdf": ".pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            }
            if self.media_type not in allowed:
                raise ValueError("Unsupported document type")
            try:
                decoded = base64.b64decode(self.data or "", validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("Invalid document data") from error
            if not decoded:
                raise ValueError("Documents must not be empty")
            if self.media_type == "application/pdf" and not decoded.startswith(b"%PDF-"):
                raise ValueError("Document content does not match PDF")
            if self.media_type.endswith("document") and not decoded.startswith(b"PK"):
                raise ValueError("Document content does not match DOCX")
            if not self.name.lower().endswith(allowed[self.media_type]):
                raise ValueError("Document filename extension does not match its type")
            if len(decoded) > 10 * 1024 * 1024:
                raise ValueError("Documents must not exceed 10 MB")
        return self


class SendMessageRequest(BaseModel):
    message: str = Field(default="", max_length=10_000)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=8)
    use_rag: bool = True
    mode: Literal["auto", "chat", "research"] = "auto"
    allow_write_tools: bool = False

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.attachments:
            raise ValueError("A message or attachment is required")
        encoded_image_bytes = sum(
            len(item.data or "") * 3 // 4
            for item in self.attachments
            if item.kind in {"image", "document"}
        )
        text_bytes = sum(
            len((item.content or "").encode("utf-8"))
            for item in self.attachments
            if item.kind == "text"
        )
        if encoded_image_bytes + text_bytes > 15 * 1024 * 1024:
            raise ValueError("Attachments must not exceed 15 MB in total")
        return self


class RagSourceResponse(BaseModel):
    document_id: UUID
    document_name: str
    chunk_id: int
    page_number: int | None = None
    section_title: str | None = None
    excerpt: str
    similarity: float


class ChatArtifactResponse(BaseModel):
    artifact_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    download_url: str
    expires_in_seconds: int
    kind: Literal["word", "pdf"]
    page_count: int | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    attachments: list[ChatAttachment] = Field(default_factory=list)
    artifacts: list[ChatArtifactResponse] = Field(default_factory=list)
    sources: list[RagSourceResponse] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
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
