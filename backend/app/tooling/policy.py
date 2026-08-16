from dataclasses import dataclass, field
from typing import Any

from app.tooling.spec import ToolSpec


@dataclass(frozen=True, slots=True)
class ToolContext:
    run_id: str
    conversation_id: str
    agent_role: str = "chat_agent"
    write_allowed: bool = False
    approved_call_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ToolDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str | None = None


class ToolPolicy:
    def decide(
        self,
        spec: ToolSpec,
        context: ToolContext,
        arguments: dict[str, Any],
        *,
        call_id: str = "",
    ) -> ToolDecision:
        del arguments
        if not spec.enabled:
            return ToolDecision(False, reason="工具已停用")
        if context.agent_role not in spec.allowed_agents:
            return ToolDecision(False, reason="当前 Agent 没有该工具权限")
        if spec.side_effect and not context.write_allowed:
            return ToolDecision(False, reason="本次请求未授权写操作")
        if spec.risk_level == "high" and call_id not in context.approved_call_ids:
            return ToolDecision(True, requires_approval=True, reason="高风险操作需要确认")
        return ToolDecision(True)
