from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.eval.dataset import EVAL_FORM_OPTIONS


class EvalRunRequest(BaseModel):
    case_ids: list[str] | None = Field(default=None, max_length=20)
    judge_enabled: bool = False
    judge_weight: float = Field(default=0.5, ge=0, le=1)
    baseline_run_id: UUID | None = None


class EvalCaseDefinition(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=10_000)
    mode: Literal["chat", "research"] = "chat"
    required_terms: list[str] = Field(default_factory=list, max_length=20)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=20)
    expected_tools: list[str] = Field(default_factory=list, max_length=10)
    expected_nodes: list[str] = Field(default_factory=list, max_length=20)
    expected_roles: list[str] = Field(default_factory=list, max_length=20)
    expected_events: list[str] = Field(default_factory=list, max_length=20)
    min_citations: int = Field(default=0, ge=0, le=20)
    require_citation_provenance: bool = False
    fault_injection: Literal[
        "none", "researcher_once", "researcher_always"
    ] = "none"
    min_chars: int = Field(default=1, ge=0, le=100_000)
    max_duration_ms: int | None = Field(default=None, ge=1000, le=900_000)
    pass_threshold: float = Field(default=0.8, ge=0, le=1)
    judge_rubric: str = Field(
        default="回答应准确、完整、有依据，并遵循用户的格式和边界要求。",
        min_length=1,
        max_length=3000,
    )

    @model_validator(mode="after")
    def validate_fault_mode(self):
        if self.fault_injection != "none" and self.mode != "research":
            raise ValueError("Fault injection is available only in research mode")
        return self

    @field_validator(
        "required_terms",
        "forbidden_terms",
        "expected_tools",
        "expected_nodes",
        "expected_roles",
        "expected_events",
    )
    @classmethod
    def validate_list_fields(cls, values: list[str], info) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        if any(len(item) > 120 for item in normalized):
            raise ValueError("List values must not exceed 120 characters")
        option_key = {
            "expected_tools": "tools",
            "expected_nodes": "nodes",
            "expected_roles": "roles",
            "expected_events": "events",
        }.get(info.field_name)
        if option_key:
            unknown = set(normalized) - set(EVAL_FORM_OPTIONS[option_key])
            if unknown:
                raise ValueError(f"Unsupported selections: {sorted(unknown)}")
        return normalized


class EvalCaseResponse(EvalCaseDefinition):
    id: str
    source: Literal["builtin", "custom"] = "builtin"
    editable: bool = False
    deletable: bool = True


class EvalDatasetResponse(BaseModel):
    version: str
    description: str
    cases: list[EvalCaseResponse]
    form_options: dict[str, list[str]]
    hidden_builtin_count: int = 0


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
