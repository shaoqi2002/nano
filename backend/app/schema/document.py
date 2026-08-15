from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    content_type: str
    preview_kind: str
    size_bytes: int
    checksum_sha256: str
    index_status: str
    index_error: str | None
    indexed_at: datetime | None
    parser_version: str | None
    embedding_model: str | None
    created_at: datetime
