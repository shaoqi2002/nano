import asyncio
import unittest

from langchain_core.tools import tool

from app.tooling import ToolContext, ToolRegistry, ToolSpec
from app.tooling.executor import ToolExecutionError


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_selects_by_server_owned_agent_permissions(self) -> None:
        @tool
        async def visible(query: str) -> str:
            """Return a visible result."""
            return query

        registry = ToolRegistry([ToolSpec(
            name="visible",
            version="1.2.0",
            tool=visible,
            category="test",
            allowed_agents=frozenset({"chat_agent"}),
        )])

        self.assertEqual(
            [item.name for item in registry.langchain_tools("chat_agent")],
            ["visible"],
        )
        self.assertEqual(registry.langchain_tools("document_analyst"), [])

    async def test_executor_retries_and_reports_metadata(self) -> None:
        attempts = 0

        @tool
        async def flaky(query: str) -> str:
            """Fail once, then return a result."""
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary")
            return query

        spec = ToolSpec(
            name="flaky",
            version="2.0.0",
            tool=flaky,
            category="test",
            max_retries=1,
        )
        registry = ToolRegistry([spec])
        result = await registry.executor.execute(
            spec,
            {"query": "ok"},
            ToolContext(run_id="run", conversation_id="conversation"),
        )

        self.assertEqual(result.value, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.tool_version, "2.0.0")

    async def test_executor_enforces_timeout(self) -> None:
        @tool
        async def slow() -> str:
            """Wait too long."""
            await asyncio.sleep(0.05)
            return "late"

        spec = ToolSpec(
            name="slow",
            version="1.0.0",
            tool=slow,
            category="test",
            timeout_seconds=0.001,
        )
        registry = ToolRegistry([spec])
        with self.assertRaises(ToolExecutionError):
            await registry.executor.execute(
                spec,
                {},
                ToolContext(run_id="run", conversation_id="conversation"),
            )

    async def test_write_tool_requires_explicit_request_authorization(self) -> None:
        @tool
        async def write_note(content: str) -> str:
            """Write a note."""
            return content

        spec = ToolSpec(
            name="write_note",
            version="1.0.0",
            tool=write_note,
            category="test",
            risk_level="write",
            side_effect=True,
        )
        registry = ToolRegistry([spec])
        with self.assertRaises(ToolExecutionError):
            await registry.executor.execute(
                spec,
                {"content": "blocked"},
                ToolContext(run_id="run", conversation_id="conversation"),
            )
        result = await registry.executor.execute(
            spec,
            {"content": "allowed"},
            ToolContext(
                run_id="run", conversation_id="conversation", write_allowed=True
            ),
        )
        self.assertEqual(result.value, "allowed")


if __name__ == "__main__":
    unittest.main()
