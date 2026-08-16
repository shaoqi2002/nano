import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


EVAL_FORM_OPTIONS = {
    "modes": ["chat", "research"],
    "tools": ["document_search", "web_search", "web_extract", "deep_research"],
    "nodes": [
        "agent", "tools", "finalize", "planner", "writer", "reviewer", "revise",
    ],
    "roles": [
        "supervisor", "web_researcher", "document_analyst",
        "general_researcher", "writer", "reviewer",
    ],
    "events": [
        "plan.ready", "agent.delegated", "agent.retrying", "agent.completed",
        "agent.failed", "review.completed", "tool.started", "tool.completed",
    ],
}


class EvalCase(BaseModel):
    id: str
    title: str
    prompt: str
    mode: Literal["chat", "research"] = "chat"
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    expected_nodes: list[str] = Field(default_factory=list)
    expected_roles: list[str] = Field(default_factory=list)
    expected_events: list[str] = Field(default_factory=list)
    min_chars: int = 1
    max_duration_ms: int | None = None
    pass_threshold: float = Field(default=0.8, ge=0, le=1)
    judge_rubric: str = "回答应准确、完整、有依据，并遵循用户的格式和边界要求。"


class EvalDataset(BaseModel):
    version: str
    description: str
    cases: list[EvalCase]


@lru_cache(maxsize=1)
def load_golden_dataset() -> EvalDataset:
    path = Path(__file__).parent / "datasets" / "golden_v2.json"
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def public_dataset(dataset: EvalDataset) -> dict:
    return json.loads(dataset.model_dump_json())
