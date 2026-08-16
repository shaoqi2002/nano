import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.tooling.policy import ToolContext, ToolPolicy
from app.tooling.spec import ToolSpec


class ToolExecutionError(RuntimeError):
    pass


class ToolApprovalRequired(ToolExecutionError):
    def __init__(self, spec: ToolSpec, reason: str) -> None:
        super().__init__(reason)
        self.spec = spec


@dataclass(frozen=True, slots=True)
class ToolExecution:
    value: Any
    duration_ms: int
    attempts: int
    tool_version: str
    risk_level: str


class ToolExecutor:
    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self.policy = policy or ToolPolicy()

    async def execute(
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
        context: ToolContext,
        *,
        call_id: str = "",
    ) -> ToolExecution:
        decision = self.policy.decide(
            spec, context, arguments, call_id=call_id
        )
        if not decision.allowed:
            raise ToolExecutionError(decision.reason or "工具调用被拒绝")
        if decision.requires_approval:
            raise ToolApprovalRequired(spec, decision.reason or "需要确认")

        started = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            try:
                value = await asyncio.wait_for(
                    spec.tool.ainvoke(arguments), timeout=spec.timeout_seconds
                )
                return ToolExecution(
                    value=value,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    attempts=attempts,
                    tool_version=spec.version,
                    risk_level=spec.risk_level,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if attempts >= spec.max_retries + 1:
                    raise ToolExecutionError(str(error)) from error
