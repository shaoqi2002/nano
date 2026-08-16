from collections.abc import Iterable

from langchain_core.tools import BaseTool

from app.tooling.executor import ToolExecutor
from app.tooling.spec import ToolSpec


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self.executor = ToolExecutor()
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具已注册：{spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def select(
        self,
        agent_role: str,
        preferred_tools: Iterable[str] = (),
    ) -> list[ToolSpec]:
        preferred = set(preferred_tools)
        return [
            spec
            for spec in self._specs.values()
            if spec.enabled
            and agent_role in spec.allowed_agents
            and (not preferred or spec.name in preferred)
        ]

    def langchain_tools(
        self,
        agent_role: str = "chat_agent",
        preferred_tools: Iterable[str] = (),
    ) -> list[BaseTool]:
        return [
            spec.tool for spec in self.select(agent_role, preferred_tools)
        ]

    @classmethod
    def from_tools(cls, tools: Iterable[BaseTool]) -> "ToolRegistry":
        return cls(
            ToolSpec(
                name=tool.name,
                version="legacy",
                tool=tool,
                category="legacy",
                allowed_agents=frozenset({
                    "chat_agent",
                    "web_researcher",
                    "general_researcher",
                }),
            )
            for tool in tools
        )
