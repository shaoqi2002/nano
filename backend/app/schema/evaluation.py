from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvalRunRequest(BaseModel):
    case_ids: list[str] | None = Field(default=None, max_length=20)


class EvalCaseResponse(BaseModel):
    id: str
    title: str
    prompt: str
    mode: str
    expected_tools: list[str]
    expected_nodes: list[str]


class EvalDatasetResponse(BaseModel):
    version: str
    description: str
    cases: list[EvalCaseResponse]


class EvalResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eval_run_id: UUID
    case_id: str
    title: str
    passed: bool
    score: float
    output: str
    metrics: dict
    error: str | None
    duration_ms: int
    created_at: datetime


class EvalRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_version: str
    status: str
    case_count: int
    passed_count: int
    score: float | None
    duration_ms: int | None
    config: dict
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class EvalRunDetailResponse(EvalRunResponse):
    results: list[EvalResultResponse]
