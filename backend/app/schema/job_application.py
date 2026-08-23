from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


JOB_STATUSES = {
    "preparing",
    "applied",
    "written_test",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
}


class JobApplicationCreate(BaseModel):
    job_url: str = Field(min_length=8, max_length=2000)
    notes: str = Field(default="", max_length=5000)

    @field_validator("job_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("请输入以 http:// 或 https:// 开头的投递链接")
        return value


class JobApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=100)
    channel: str | None = Field(default=None, max_length=80)
    job_url: str | None = Field(default=None, min_length=8, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)
    applied_at: date | None = None

    @field_validator("job_url")
    @classmethod
    def validate_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("请输入以 http:// 或 https:// 开头的投递链接")
        return value


class JobStatusUpdate(BaseModel):
    status: str
    note: str = Field(default="", max_length=1000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in JOB_STATUSES:
            raise ValueError("无效的投递状态")
        return value


class JobApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_status: str | None
    to_status: str
    note: str
    created_at: datetime


class JobApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company: str
    role: str
    location: str
    channel: str
    job_url: str
    notes: str
    status: str
    applied_at: date
    created_at: datetime
    updated_at: datetime
    events: list[JobApplicationEventResponse] = Field(default_factory=list)
