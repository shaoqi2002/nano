import unittest
from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.service.conversation import (
    invoke_model_with_tools,
    invoke_model_with_tools_stream,
)


class FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)
        self.invocations: list[list[Any]] = []
        self.bound_tools = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.invocations.append(list(messages))
        return self.responses.pop(0)


class FakeStreamingModel(FakeModel):
    async def astream(self, messages):
        self.invocations.append(list(messages))
        response = self.responses.pop(0)
        yield response


class ToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_answer_deltas(self) -> None:
        model = FakeStreamingModel([AIMessage(content="streamed answer")])

        events = [
            event
            async for event in invoke_model_with_tools_stream(
                model, [], [HumanMessage(content="hello")]
            )
        ]

        self.assertEqual(events[0], {"type": "message.delta", "delta": "streamed answer"})
        self.assertEqual(events[-1]["type"], "_model.response")

    async def test_streams_tool_progress_and_resets_preamble(self) -> None:
        @tool
        async def echo(query: str) -> str:
            """Return the query for testing."""
            return query

        model = FakeStreamingModel(
            [
                AIMessage(
                    content="I will look that up.",
                    tool_calls=[{
                        "name": "echo",
                        "args": {"query": "nano"},
                        "id": "stream-call-1",
                        "type": "tool_call",
                    }],
                ),
                AIMessage(content="final streamed answer"),
            ]
        )

        events = [
            event
            async for event in invoke_model_with_tools_stream(
                model, [echo], [HumanMessage(content="search")]
            )
        ]
        event_types = [event["type"] for event in events]

        self.assertIn("message.reset", event_types)
        self.assertIn("tool.started", event_types)
        self.assertIn("tool.completed", event_types)
        self.assertEqual(
            [event["delta"] for event in events if event["type"] == "message.delta"][-1],
            "final streamed answer",
        )

    async def test_executes_tool_and_returns_final_answer(self) -> None:
        @tool
        async def echo(query: str) -> str:
            """Return the query for testing."""
            return f"result:{query}"

        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo",
                            "args": {"query": "nano"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="final answer"),
            ]
        )

        response = await invoke_model_with_tools(
            model,
            [echo],
            [HumanMessage(content="search")],
        )

        self.assertEqual(response.content, "final answer")
        self.assertEqual(len(model.invocations), 2)
        tool_message = model.invocations[1][-1]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertEqual(tool_message.tool_call_id, "call-1")
        self.assertEqual(tool_message.content, "result:nano")

    async def test_unknown_tool_is_reported_back_to_model(self) -> None:
        @tool
        async def echo(query: str) -> str:
            """Return the query for testing."""
            return query

        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "missing_tool",
                            "args": {},
                            "id": "call-2",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="fallback answer"),
            ]
        )

        response = await invoke_model_with_tools(
            model,
            [echo],
            [HumanMessage(content="search")],
        )

        self.assertEqual(response.content, "fallback answer")
        tool_message = model.invocations[1][-1]
        self.assertIn("未知工具", tool_message.content)

    async def test_without_tools_invokes_model_once(self) -> None:
        model = FakeModel([AIMessage(content="plain answer")])

        response = await invoke_model_with_tools(
            model,
            [],
            [HumanMessage(content="hello")],
        )

        self.assertEqual(response.content, "plain answer")
        self.assertEqual(len(model.invocations), 1)
        self.assertEqual(model.bound_tools, [])

    async def test_limits_tool_calls_and_forces_final_answer(self) -> None:
        calls = 0

        @tool
        async def echo(query: str) -> str:
            """Return the query for testing."""
            nonlocal calls
            calls += 1
            return query

        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo",
                            "args": {"query": "first"},
                            "id": "call-3",
                            "type": "tool_call",
                        },
                        {
                            "name": "echo",
                            "args": {"query": "second"},
                            "id": "call-4",
                            "type": "tool_call",
                        },
                    ],
                ),
                AIMessage(content="limited final answer"),
            ]
        )

        with (
            patch("app.service.conversation.AGENT_MAX_TOOL_ROUNDS", 1),
            patch("app.service.conversation.AGENT_MAX_TOOL_CALLS", 1),
        ):
            response = await invoke_model_with_tools(
                model,
                [echo],
                [HumanMessage(content="search")],
            )

        self.assertEqual(response.content, "limited final answer")
        self.assertEqual(calls, 1)
        tool_messages = [
            message
            for message in model.invocations[1]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 2)
        self.assertIn("达到上限", tool_messages[1].content)


if __name__ == "__main__":
    unittest.main()
