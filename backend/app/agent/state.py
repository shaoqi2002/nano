import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


SpecialistRole = Literal["web_researcher", "document_analyst", "general_researcher"]


class ResearchTask(BaseModel):
    id: str
    question: str
    agent: SpecialistRole = "general_researcher"
    preferred_tools: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    objective: str
    tasks: list[ResearchTask] = Field(min_length=1, max_length=5)
    expected_output: str


class ReviewResult(BaseModel):
    passed: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    run_id: str
    conversation_id: str
    query: str
    messages: Annotated[list[BaseMessage], add_messages]
    rag_sources: list[dict[str, Any]]
    tool_rounds: int
    tool_call_count: int
    emitted_content: bool
    final_answer: str
    plan: list[dict[str, Any]]
    task: dict[str, Any]
    research_results: Annotated[list[dict[str, Any]], operator.add]
    draft: str
    review: dict[str, Any]
    revision_count: int
    status: str
    error: str | None
    fault_injection: Literal["none", "researcher_once", "researcher_always"]
