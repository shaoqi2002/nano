from dataclasses import dataclass, field
from typing import Literal

from langchain_core.tools import BaseTool


RiskLevel = Literal["read", "write", "high"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Server-owned metadata for one callable Agent capability."""

    name: str
    version: str
    tool: BaseTool
    category: str
    risk_level: RiskLevel = "read"
    side_effect: bool = False
    safe_artifact_write: bool = False
    idempotent: bool = True
    timeout_seconds: float = 30.0
    max_retries: int = 0
    allowed_agents: frozenset[str] = field(
        default_factory=lambda: frozenset({"chat_agent", "general_researcher"})
    )
    tags: frozenset[str] = field(default_factory=frozenset)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name or self.name != self.tool.name:
            raise ValueError("ToolSpec name must match the LangChain tool name")
        if not self.version:
            raise ValueError("ToolSpec version is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("Tool retries cannot be negative")
        if self.safe_artifact_write and not self.side_effect:
            raise ValueError("Safe artifact writes must be side-effecting tools")
